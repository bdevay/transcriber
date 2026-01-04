# Audio Transcription Script with Gemini API
# Usage: python transcribe.py <input_m4a_path> <output_txt_path>

import os
import sys
import argparse
import subprocess
import tempfile
import shutil
import yaml
from dotenv import load_dotenv
from google import genai
from google.genai import errors, types
from tqdm import tqdm

class TranscriptionError(Exception):
    pass
class FFmpegError(TranscriptionError):
    pass
class APIKeyError(TranscriptionError):
    pass

def check_ffmpeg_installed(ffmpeg_path):
    if shutil.which(ffmpeg_path) is not None:
        return True
    try:
        subprocess.run([ffmpeg_path, '-version'], capture_output=True, text=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def validate_input_file(file_path, allowed_extensions, max_size_mb):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Audio file not found: {file_path}")
    if not os.path.isfile(file_path):
        raise ValueError(f"Path is not a file: {file_path}")
    if not any(file_path.lower().endswith(ext) for ext in allowed_extensions):
        raise ValueError(f"Expected file with extension {allowed_extensions}, got: {file_path}")
    size_mb = os.path.getsize(file_path) / (1024 * 1024)
    if size_mb == 0:
        raise ValueError(f"File is empty: {file_path}")
    if size_mb > max_size_mb:
        raise ValueError(f"File size {size_mb:.2f} MB exceeds max allowed {max_size_mb} MB")

def convert_m4a_to_flac(input_path, ffmpeg_path, temp_dir):
    print(f"[INFO] Converting '{input_path}' to FLAC format...")
    if temp_dir and os.path.isdir(temp_dir):
        temp_flac = tempfile.mktemp(suffix=".flac", dir=temp_dir)
    else:
        temp_flac = tempfile.mktemp(suffix=".flac")
    try:
        result = subprocess.run([
            ffmpeg_path, '-i', input_path, '-y', temp_flac
        ], capture_output=True, text=True, check=True)
        print(f"[INFO] Conversion complete. FLAC file: {temp_flac}")
    except FileNotFoundError:
        print("[ERROR] ffmpeg not found.")
        raise FFmpegError("ffmpeg not found. Please install ffmpeg.")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] ffmpeg conversion failed: {e.stderr}")
        raise FFmpegError(f"ffmpeg conversion failed: {e.stderr}")
    return temp_flac

def transcribe_with_gemini(flac_path, api_key, model, prompt):
    print(f"[INFO] Starting transcription with Gemini API...")
    client = genai.Client(api_key=api_key)
    file_size = os.path.getsize(flac_path)
    try:
        if file_size <= 20 * 1024 * 1024:  # <= 20MB
            print(f"[INFO] Reading FLAC file into memory ({file_size/1024/1024:.2f} MB)...")
            audio_bytes = b''
            with open(flac_path, 'rb') as f:
                for chunk in tqdm(iter(lambda: f.read(1024 * 1024), b''), desc="Reading FLAC", unit="MB"):
                    audio_bytes += chunk
            print("[INFO] Sending audio to Gemini API (inline)...")
            response = client.models.generate_content(
                model=model,
                contents=[
                    prompt,
                    types.Part.from_bytes(data=audio_bytes, mime_type='audio/flac')
                ]
            )
        else:
            print(f"[INFO] Large file detected ({file_size/1024/1024:.2f} MB). Uploading to Gemini API...")
            uploaded = client.files.upload(file=flac_path)
            print("[INFO] File upload complete. Requesting transcription...")
            response = client.models.generate_content(
                model=model,
                contents=[
                    prompt,
                    uploaded
                ]
            )
        print("[INFO] Transcription received from Gemini API.")
        return response.text
    except errors.APIError as e:
        print(f"[ERROR] Gemini API error ({e.code}): {e.message}")
        raise TranscriptionError(f"Gemini API error ({e.code}): {e.message}")

def load_config(config_path="config.yml"):
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    return config

def main():
    parser = argparse.ArgumentParser(description="Transcribe M4A audio to text using Gemini API.")
    parser.add_argument('input_m4a', help="Path to input .m4a file")
    parser.add_argument('output_txt', help="Path to output .txt file")
    args = parser.parse_args()

    print("[INFO] Loading configuration from config.yml...")
    config = load_config()

    print("[INFO] Loading environment variables from .env file...")
    load_dotenv()
    api_key_env = config['gemini'].get('api_key_env', 'GOOGLE_API_KEY')
    api_key = os.getenv(api_key_env)
    if not api_key:
        print(f"[ERROR] {api_key_env} not found in environment or .env file.")
        raise APIKeyError(f"{api_key_env} not found in environment or .env file.")

    allowed_extensions = config['input'].get('allowed_extensions', ['.m4a'])
    max_size_mb = config['input'].get('max_size_mb', 100)
    print(f"[INFO] Validating input file: {args.input_m4a}")
    validate_input_file(args.input_m4a, allowed_extensions, max_size_mb)

    ffmpeg_path = config['conversion'].get('ffmpeg_path', 'ffmpeg')
    temp_dir = config['conversion'].get('temp_dir', None)
    print(f"[INFO] Checking ffmpeg installation...")
    if not check_ffmpeg_installed(ffmpeg_path):
        print("[ERROR] ffmpeg is not installed.")
        raise FFmpegError("ffmpeg is not installed. Please install ffmpeg.")

    flac_path = None
    try:
        flac_path = convert_m4a_to_flac(args.input_m4a, ffmpeg_path, temp_dir)
        print("[INFO] Beginning transcription...")
        model = config['gemini'].get('model', 'gemini-2.5-flash')
        prompt = config['gemini'].get('prompt', 'Generate a transcript of the speech.')
        transcript = transcribe_with_gemini(flac_path, api_key, model, prompt)
        encoding = config['output'].get('encoding', 'utf-8')
        overwrite = config['output'].get('overwrite', True)
        if not overwrite and os.path.exists(args.output_txt):
            print(f"[ERROR] Output file {args.output_txt} exists and overwrite is disabled.")
            raise ValueError(f"Output file {args.output_txt} exists and overwrite is disabled.")
        print(f"[INFO] Writing transcript to {args.output_txt}")
        with open(args.output_txt, 'w', encoding=encoding) as out:
            out.write(transcript)
        print(f"[SUCCESS] Transcription complete. Output written to {args.output_txt}")
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        delete_temp = config['conversion'].get('delete_temp', True)
        if flac_path and os.path.exists(flac_path) and delete_temp:
            try:
                os.remove(flac_path)
                print(f"[INFO] Temporary FLAC file deleted: {flac_path}")
            except Exception:
                print(f"[WARNING] Could not delete temporary FLAC file: {flac_path}")

if __name__ == "__main__":
    main()
