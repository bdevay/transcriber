def list_gemini_models(api_key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    try:
        response = requests.get(url)
        print("\n--- Gemini API Models ---")
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"Error listing models: {e}")

# Gemini API CLI Script
# Usage: python gemini_cli.py --prompt "Your prompt" --files file1.txt file2.pdf


import argparse
import os
import sys
import yaml
import requests
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed

def load_config(config_path):
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def load_input(input_path):
    with open(input_path, 'r') as f:
        return yaml.safe_load(f)

def send_gemini_request(prompt, file_paths, endpoint, model, options, api_key):
    files = []
    file_handles = []
    errors = []
    for file_path in file_paths:
        if not os.path.isfile(file_path):
            errors.append(f"File not found: {file_path}")
            continue
        try:
            fh = open(file_path, 'rb')
            file_handles.append(fh)
            files.append(('files', (os.path.basename(file_path), fh)))
        except Exception as e:
            errors.append(f"Error opening {file_path}: {e}")

    # Gemini API expects a JSON payload with 'contents' field
    payload = {
        "contents": [
            {"parts": [{"text": prompt}]}
        ]
    }
    # Add any additional options to payload if needed
    if options:
        payload.update(options)
    # Add API key as query parameter to endpoint
    if '?key=' not in endpoint:
        endpoint = endpoint.rstrip('?')
        endpoint = f"{endpoint}?key={api_key}"
    try:
        # If files are needed, Gemini API may require multipart upload or binary data handling (not covered here)
        response = requests.post(endpoint, json=payload)
        result = {
            'prompt': prompt,
            'files': file_paths,
            'status_code': response.status_code,
            'response': response.text,
            'errors': errors
        }
    except Exception as e:
        result = {
            'prompt': prompt,
            'files': file_paths,
            'status_code': None,
            'response': None,
            'errors': errors + [str(e)]
        }
    for fh in file_handles:
        fh.close()
    return result

def main():
    if '-h' in sys.argv or '--help' in sys.argv:
        print("""
Gemini API CLI client: Send prompts and attach files to Gemini API.

USAGE EXAMPLES:
  Single prompt and files:
    python gemini_cli.py --prompt 'Your prompt' --files file1.txt file2.pdf

  Multiple prompts and files from YAML:
    python gemini_cli.py --input input.yml

YAML input format (input.yml):
- prompt: 'First prompt'
  files:
    - file1.txt
    - file2.pdf
- prompt: 'Second prompt'
  files:
    - file3.txt

Arguments:
  --prompt PROMPT       Prompt to send to Gemini API (use with --files)
  --input INPUT         YAML file with prompts and files (see README for format)
  --files [FILES ...]   Paths to files to attach (use with --prompt)
  --config CONFIG       Path to config YAML file (default: config_gemini_cli.yml)
  --max-workers N       Max parallel requests (default: 4)
  -h, --help            Show this help message and exit
""")
        sys.exit(0)
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--prompt', help='Prompt to send to Gemini API (use with --files)')
    parser.add_argument('--input', help='YAML file with prompts and files (see README for format)')
    parser.add_argument('--files', nargs='*', help='Paths to files to attach (use with --prompt)', default=[])
    parser.add_argument('--config', default='config_gemini_cli.yml', help='Path to config YAML file (default: config_gemini_cli.yml or config_cv_creator.yml)')
    parser.add_argument('--max-workers', type=int, default=4, help='Max parallel requests (default: 4)')
    parser.add_argument('--list-models', action='store_true', help='List available Gemini models and exit')
    args = parser.parse_args()

    load_dotenv()
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("Error: GEMINI_API_KEY not found in .env")
        sys.exit(1)
    if args.list_models:
        list_gemini_models(api_key)
        sys.exit(0)
    # Require either --prompt or --input if not listing models
    if not args.prompt and not args.input:
        print("Error: one of the arguments --prompt or --input is required unless --list-models is used.")
        sys.exit(2)

    config = load_config(args.config)
    # Try to get model/endpoint/options from config, fallback to config_gemini_cli.yml if missing
    model = config.get('model', None)
    endpoint = config.get('endpoint', None)
    options = config.get('options', {})
    if not model or not endpoint:
        fallback_config = load_config('config_gemini_cli.yml')
        if not model:
            model = fallback_config.get('model')
        if not endpoint:
            endpoint = fallback_config.get('endpoint')
        if not options:
            options = fallback_config.get('options', {})

    jobs = []
    if args.input:
        input_data = load_input(args.input)
        # Expecting YAML structure: list of {prompt: ..., files: [...]}
        if not isinstance(input_data, list):
            print("Error: Input YAML must be a list of objects with 'prompt' and 'files'.")
            sys.exit(1)
        for entry in input_data:
            prompt = entry.get('prompt')
            file_paths = entry.get('files', [])
            if not prompt:
                print("Error: Each entry must have a 'prompt'.")
                continue
            jobs.append((prompt, file_paths))
    else:
        if not args.prompt:
            print("Error: --prompt required if --input not provided.")
            sys.exit(1)
        jobs.append((args.prompt, args.files))

    results = []
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        future_to_job = {
            executor.submit(send_gemini_request, prompt, file_paths, endpoint, model, options, api_key): (prompt, file_paths)
            for prompt, file_paths in jobs
        }
        for future in as_completed(future_to_job):
            result = future.result()
            results.append(result)

    for result in results:
        print("\n--- Gemini API Call ---")
        print(f"Prompt: {result['prompt']}")
        print(f"Files: {result['files']}")
        if result['errors']:
            print(f"Errors: {result['errors']}")
        print(f"Status Code: {result['status_code']}")
        print(f"Response: {result['response']}")

if __name__ == "__main__":
    main()
