#!/usr/bin/env python3
# Markdown Translation Script with Gemini API
# Usage: python translate_md.py --input input.md --output output.md

import os
import sys
import argparse
import yaml
import re
import time
from dotenv import load_dotenv
from google import genai
from google.genai import errors
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

class TranslationError(Exception):
    pass

class APIKeyError(TranslationError):
    pass

def load_config(config_path="config_translator.yml"):
    """Load configuration from YAML file."""
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    return config

def parse_markdown(text):
    """
    Parse markdown text into blocks for translation.
    Returns a list of dicts with keys: type, text, original
    """
    blocks = []

    # Split by double newlines to get blocks
    parts = text.split('\n\n')

    for part in parts:
        part = part.strip()
        if not part:
            # Preserve empty blocks to maintain spacing
            blocks.append({
                'type': 'empty',
                'text': '',
                'original': ''
            })
            continue

        # Classify block type
        block_type = 'paragraph'

        # Check if heading
        if part.startswith('#'):
            block_type = 'heading'
        # Check if list item
        elif re.match(r'^[\-\*\•\d]+[\.\)]\s', part) or part.startswith('- ') or part.startswith('* '):
            block_type = 'list'
        # Check if table
        elif '|' in part and part.count('|') >= 2:
            block_type = 'table'
        # Check if code block
        elif '```' in part:
            block_type = 'code'

        blocks.append({
            'type': block_type,
            'text': part,
            'original': part
        })

    return blocks

def translate_block(block, client, config, retry_count=0):
    """
    Translate a single block using Gemini API.
    Returns translated text.
    """
    # Skip empty blocks and code blocks
    if block['type'] in ['empty', 'code']:
        return block['text']

    # For very short blocks (< 3 chars), skip translation
    if len(block['text'].strip()) < 3:
        return block['text']

    source_lang = config['translation']['source_lang']
    target_lang = config['translation']['target_lang']
    model = config['gemini']['model']

    # Create translation prompt
    prompt = f"""You are a professional technical translator specializing in OECD policy documents.
Translate the following text from {source_lang} to {target_lang}.

Requirements:
- Maintain technical accuracy and formal tone
- Preserve markdown formatting exactly (headings, bullets, numbering)
- Keep technical abbreviations unchanged (R&D, OECD, UNESCO, GDP, etc.)
- Output ONLY the translated text without explanations

Text to translate:
{block['text']}"""

    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config={
                'temperature': config['gemini'].get('temperature', 0.3)
            }
        )

        translated = response.text.strip()

        # Validate translation is not empty
        if not translated:
            print(f"[WARNING] Empty translation for block: {block['text'][:50]}...")
            return block['text']

        return translated

    except errors.APIError as e:
        max_retries = config['processing']['retry_attempts']
        if retry_count < max_retries:
            wait_time = 2 ** retry_count  # Exponential backoff
            print(f"[WARNING] API error ({e.code}): {e.message}. Retrying in {wait_time}s... (attempt {retry_count + 1}/{max_retries})")
            time.sleep(wait_time)
            return translate_block(block, client, config, retry_count + 1)
        else:
            print(f"[ERROR] Failed to translate block after {max_retries} attempts: {block['text'][:50]}...")
            return block['text']  # Return original on failure
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
        return block['text']

def translate_worker(block_data, client, config, rate_limit_delay):
    """Worker function for parallel translation."""
    idx, block = block_data

    # Rate limiting
    if rate_limit_delay > 0:
        time.sleep(rate_limit_delay)

    translated = translate_block(block, client, config)

    return idx, translated

def process_file(input_path, output_path, config):
    """
    Main processing function.
    Reads input file, translates blocks, writes output file.
    """
    # Load API key
    load_dotenv()
    api_key_env = config['gemini']['api_key_env']
    api_key = os.getenv(api_key_env)

    if not api_key:
        raise APIKeyError(f"API key not found in environment variable: {api_key_env}")

    # Initialize Gemini client
    print(f"[INFO] Initializing Gemini API client...")
    client = genai.Client(api_key=api_key)

    # Read input file
    print(f"[INFO] Reading input file: {input_path}")
    encoding = config['output']['encoding']
    with open(input_path, 'r', encoding=encoding) as f:
        input_text = f.read()

    # Parse markdown
    print(f"[INFO] Parsing markdown structure...")
    blocks = parse_markdown(input_text)
    print(f"[INFO] Found {len(blocks)} blocks to process")

    # Prepare for parallel processing
    max_workers = config['processing']['max_workers']
    rate_limit_delay = config['processing']['rate_limit_delay']

    print(f"[INFO] Starting translation with {max_workers} workers...")

    # Create list to store results in order
    results = [None] * len(blocks)

    # Process blocks in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all jobs
        future_to_idx = {
            executor.submit(translate_worker, (i, block), client, config, rate_limit_delay): i
            for i, block in enumerate(blocks)
        }

        # Collect results with progress bar
        for future in tqdm(as_completed(future_to_idx), total=len(blocks), desc="Translating", unit="block"):
            idx = future_to_idx[future]
            try:
                result_idx, translated_text = future.result()
                results[result_idx] = translated_text
            except Exception as e:
                print(f"[ERROR] Error processing block {idx}: {e}")
                results[idx] = blocks[idx]['text']  # Use original on error

    # Reassemble document
    print(f"[INFO] Reassembling translated document...")
    translated_doc = '\n\n'.join(results)

    # Write output file
    print(f"[INFO] Writing output file: {output_path}")
    with open(output_path, 'w', encoding=encoding) as f:
        f.write(translated_doc)

    print(f"[SUCCESS] Translation complete! Output written to: {output_path}")

    # Print statistics
    total_blocks = len(blocks)
    non_empty_blocks = sum(1 for b in blocks if b['type'] not in ['empty', 'code'])
    print(f"\n[STATS] Total blocks: {total_blocks}")
    print(f"[STATS] Translated blocks: {non_empty_blocks}")
    print(f"[STATS] Skipped blocks: {total_blocks - non_empty_blocks}")

def main():
    parser = argparse.ArgumentParser(
        description='Translate markdown files using Gemini API',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Translate with explicit output path
  python translate_md.py --input document.md --output document_hu.md

  # Translate with auto-generated output filename
  python translate_md.py --input document.md

  # Use custom config file
  python translate_md.py --input document.md --config my_config.yml

  # Override number of workers
  python translate_md.py --input document.md --workers 8
"""
    )

    parser.add_argument('--input', required=True, help='Path to input markdown file')
    parser.add_argument('--output', help='Path to output file (default: input with _hu suffix)')
    parser.add_argument('--config', default='config_translator.yml', help='Path to config file (default: config_translator.yml)')
    parser.add_argument('--workers', type=int, help='Number of concurrent workers (overrides config)')
    parser.add_argument('--source-lang', help='Source language code (overrides config)')
    parser.add_argument('--target-lang', help='Target language code (overrides config)')

    args = parser.parse_args()

    # Validate input file exists
    if not os.path.isfile(args.input):
        print(f"[ERROR] Input file not found: {args.input}")
        sys.exit(1)

    # Load config
    try:
        config = load_config(args.config)
    except FileNotFoundError:
        print(f"[ERROR] Config file not found: {args.config}")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Failed to load config: {e}")
        sys.exit(1)

    # Override config with CLI arguments
    if args.workers:
        config['processing']['max_workers'] = args.workers
    if args.source_lang:
        config['translation']['source_lang'] = args.source_lang
    if args.target_lang:
        config['translation']['target_lang'] = args.target_lang

    # Determine output path
    if args.output:
        output_path = args.output
    else:
        # Auto-generate output filename with _hu suffix
        input_dir = os.path.dirname(args.input)
        input_filename = os.path.basename(args.input)
        name, ext = os.path.splitext(input_filename)
        suffix = config['output']['suffix']
        output_filename = f"{name}{suffix}{ext}"
        output_path = os.path.join(input_dir, output_filename)

    print(f"[INFO] Input: {args.input}")
    print(f"[INFO] Output: {output_path}")
    print(f"[INFO] Source language: {config['translation']['source_lang']}")
    print(f"[INFO] Target language: {config['translation']['target_lang']}")
    print(f"[INFO] Model: {config['gemini']['model']}")

    # Process file
    try:
        process_file(args.input, output_path, config)
    except APIKeyError as e:
        print(f"[ERROR] {e}")
        print(f"[ERROR] Please set {config['gemini']['api_key_env']} in your .env file")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Translation failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
