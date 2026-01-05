# Audio Transcription Script with Gemini API
# Usage: python transcribe.py <input_m4a_path> <output_txt_path>

import os
import sys
import argparse
import subprocess
import tempfile
import shutil
import yaml
import threading
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

def parse_input_files(input_args, input_list_file):
    files = set()
    if input_args:
        files.update(input_args)
    if input_list_file:
        try:
            with open(input_list_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        files.add(line)
        except Exception as e:
            print(f"[ERROR] Could not read input list file: {e}")
            sys.exit(1)
    return list(files)

def prompt_overwrite_action(output_path):
    while True:
        resp = input(f"[PROMPT] Output file '{output_path}' exists. [a]ppend, [o]verride, [s]kip? (a/o/s): ").strip().lower()
        if resp in ('a', 'o', 's'):
            return resp

def transcribe_worker(input_file, output_path, config, api_key, model, prompt, encoding, ffmpeg_path, temp_dir, delete_temp, allowed_extensions, max_size_mb):
    try:
        validate_input_file(input_file, allowed_extensions, max_size_mb)
        if not check_ffmpeg_installed(ffmpeg_path):
            print(f"[ERROR] ffmpeg is not installed for file {input_file}.")
            return
        flac_path = convert_m4a_to_flac(input_file, ffmpeg_path, temp_dir)
        transcript = transcribe_with_gemini(flac_path, api_key, model, prompt)
        write_mode = 'w'
        if os.path.exists(output_path):
            action = prompt_overwrite_action(output_path)
            if action == 's':
                print(f"[INFO] Skipping {output_path}")
                return
            elif action == 'a':
                write_mode = 'a'
            elif action == 'o':
                write_mode = 'w'
        with open(output_path, write_mode, encoding=encoding) as out:
            if write_mode == 'a':
                out.write("\n\n---\n\n")
            out.write(transcript)
        print(f"[SUCCESS] Transcription complete. Output written to {output_path}")
    except Exception as e:
        print(f"[ERROR] [{input_file}] {e}", file=sys.stderr)
    finally:
        try:
            if 'flac_path' in locals() and flac_path and os.path.exists(flac_path) and delete_temp:
                os.remove(flac_path)
                print(f"[INFO] Temporary FLAC file deleted: {flac_path}")
        except Exception:
            print(f"[WARNING] Could not delete temporary FLAC file: {flac_path}")


class CustomArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        sys.stderr.write(f"error: {message}\n\n")
        self.print_help()
        sys.exit(2)

def main():
    parser = CustomArgumentParser(
        description="Transcribe M4A audio to text using Gemini API.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    class NoDefaultHelpFormatter(argparse.ArgumentDefaultsHelpFormatter):
        def _get_help_string(self, action):
            help_str = action.help
            if action.default is not argparse.SUPPRESS and action.default is not None and action.nargs != '*':
                help_str += f' (default: {action.default})'
            return help_str


    parser = CustomArgumentParser(
        description="Transcribe M4A audio to text using Gemini API.",
        formatter_class=NoDefaultHelpFormatter
    )
    parser.add_argument(
        'input_files', nargs='*',
        help="Input .m4a files (can specify one or more, e.g. 'python transcribe.py file1.m4a file2.m4a')"
    )
    parser.add_argument('--input-list', help="Text file with list of input files (one per line)")
    parser.add_argument('--output-dir', help="Directory to write output files")
    parser.add_argument('--prefix', help="Prefix for output files if not specified")
    parser.add_argument('--config', default="config.yml", help="Path to config file")
    # argparse adds -h/--help by default, so do not add it explicitly

    # First parse only --config to get config path
    config_args, remaining_argv = parser.parse_known_args()
    try:
        config = load_config(config_args.config)
    except Exception as e:
        print(f"[ERROR] Could not load config: {e}")
        sys.exit(1)

    # Set defaults from config if available
    output_dir_default = None
    prefix_default = None
    if config.get('output', {}):
        output_dir_default = config['output'].get('output_dir')
        prefix_default = config['output'].get('prefix')
    if output_dir_default:
        parser.set_defaults(output_dir=output_dir_default)
    else:
        parser.set_defaults(output_dir=os.getcwd())
    if prefix_default:
        parser.set_defaults(prefix=prefix_default)
    else:
        parser.set_defaults(prefix="transcript")

    # Now parse all args with updated defaults
    args = parser.parse_args()

    # Gather input files
    input_files = parse_input_files(args.input_files, args.input_list)
    if not input_files:
        print("[ERROR] No input files specified.\n")
        parser.print_help()
        sys.exit(2)

    # Load env
    load_dotenv()
    api_key_env = args.__dict__.get('api_key_env') or config.get('gemini', {}).get('api_key_env', 'GOOGLE_API_KEY')
    api_key = os.getenv(api_key_env)
    if not api_key:
        print(f"[ERROR] {api_key_env} not found in environment or .env file.")
        raise APIKeyError(f"{api_key_env} not found in environment or .env file.")

    allowed_extensions = config.get('input', {}).get('allowed_extensions', ['.m4a'])
    max_size_mb = config.get('input', {}).get('max_size_mb', 100)
    ffmpeg_path = config.get('conversion', {}).get('ffmpeg_path', 'ffmpeg')
    temp_dir = config.get('conversion', {}).get('temp_dir', None)
    delete_temp = config.get('conversion', {}).get('delete_temp', True)
    model = config.get('gemini', {}).get('model', 'gemini-2.5-flash')
    prompt = config.get('gemini', {}).get('prompt', 'Generate a transcript of the speech.')
    encoding = config.get('output', {}).get('encoding', 'utf-8')

    # Precedence: CLI > config > default
    output_dir = args.output_dir or os.getcwd()
    prefix = args.prefix or "transcript"


    transcript_files = []
    threads = []
    for input_file in input_files:
        if not os.path.exists(input_file):
            print(f"[ERROR] Input file does not exist: {input_file}")
            continue
        input_basename = os.path.basename(input_file)
        input_name, _ = os.path.splitext(input_basename)
        out_dir = output_dir
        os.makedirs(out_dir, exist_ok=True)
        output_path = os.path.join(out_dir, f"{prefix}-{input_name}.txt")
        transcript_files.append(output_path)
        t = threading.Thread(target=transcribe_worker, args=(
            input_file, output_path, config, api_key, model, prompt, encoding, ffmpeg_path, temp_dir, delete_temp, allowed_extensions, max_size_mb
        ))
        t.start()
        threads.append(t)
    for t in threads:
        t.join()

    # Concatenate all transcript files if enabled in config and more than one file
    concat_cfg = config.get('concat', {})
    if concat_cfg.get('enabled', False) and len(transcript_files) > 1:
        concat_filename = concat_cfg.get('output_filename', 'all_transcripts.txt')
        concat_path = os.path.join(output_dir, concat_filename)
        print(f"[INFO] Concatenating all transcripts into {concat_path}")
        try:
            with open(concat_path, 'w', encoding=encoding) as outfile:
                for idx, tf in enumerate(transcript_files):
                    if not os.path.exists(tf):
                        print(f"[WARNING] Transcript file missing: {tf}")
                        continue
                    with open(tf, 'r', encoding=encoding) as infile:
                        if idx > 0:
                            outfile.write("\n\n---\n\n")
                        outfile.write(infile.read())
            print(f"[SUCCESS] All transcripts concatenated into {concat_path}")
            if concat_cfg.get('delete_individual', False):
                for tf in transcript_files:
                    try:
                        os.remove(tf)
                        print(f"[INFO] Deleted individual transcript: {tf}")
                    except Exception as e:
                        print(f"[WARNING] Could not delete {tf}: {e}")
        except Exception as e:
            print(f"[ERROR] Failed to concatenate transcripts: {e}")

if __name__ == "__main__":
    main()
