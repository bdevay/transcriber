# Gemini API CLI Client

A Python CLI tool to interact with the Gemini API, supporting multiple file attachments and prompt customization.

## Features
- Send prompts to Gemini API
- Attach multiple files (multipart/form-data)
- Configurable via YAML and .env

## Prerequisites

- Python 3.7+
- pip (Python package manager)

## Setup
1. Clone repo and install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Set your Gemini API key in `.env`:
   ```
   GEMINI_API_KEY=your_api_key_here
   ```
3. Edit `config_gemini_cli.yml` for endpoint/model/options as needed.


## Usage

### Single Prompt & Files
```bash
python gemini_cli.py --prompt "Your prompt here" --files file1.txt file2.pdf
```

### Multiple Prompts & Files (YAML Input)
Create an input YAML file (e.g., `input.yml`) with:
```yaml
- prompt: "First prompt"
   files:
      - file1.txt
      - file2.pdf
- prompt: "Second prompt"
   files:
      - file3.txt
```
Run:
```bash
python gemini_cli.py --input input.yml
```

### Parallel Execution
Use `--max-workers` to control parallel requests (default: 4):
```bash
python gemini_cli.py --input input.yml --max-workers 8
```

## Config
- `config_gemini_cli.yml`: endpoint, model, options
- `.env`: GEMINI_API_KEY

## Error Handling
- Missing files and API errors are reported per request.


## License
This project is licensed under the terms described in [LICENSE](LICENSE).
