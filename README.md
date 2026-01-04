# Transcriber

A simple Python script for transcribing and managing text transcriptions. This repository provides tools to process, split, and manage large transcription files, making it easier to handle and review lengthy audio or video transcriptions.

## Features

- **Transcription Processing**: Handles large transcription files and splits them into manageable parts.
- **Configurable**: Uses a YAML configuration file for easy customization.
- **Easy to Use**: Simple command-line interface for running transcription tasks.

## Repository Structure

```
config.yml                  # Configuration file for the transcription process
requirements.txt            # Python dependencies
transcribe.py               # Main script for processing transcriptions
transcription_orig.txt      # Original transcription file
transcription_orig_part1.txt
transcription_orig_part2.txt
transcription_orig_part3.txt
```

## Getting Started

### Prerequisites

- Python 3.7+
- pip (Python package manager)

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/transcriber.git
   cd transcriber
   ```
2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

### Configuration

Edit the `config.yml` file to adjust settings for your transcription process. Example configuration options may include input/output file paths, splitting parameters, etc.

### Usage

Run the main script to process your transcription:

```bash
python transcribe.py
```

Depending on your configuration, the script will read the original transcription file and output split files (e.g., `transcription_orig_part1.txt`, `transcription_orig_part2.txt`, etc.).

## Example

Suppose you have a large transcription in `transcription_orig.txt`. After running the script, you will get several smaller files:

- `transcription_orig_part1.txt`
- `transcription_orig_part2.txt`
- `transcription_orig_part3.txt`

These files are easier to review and manage.

## Customization

- Adjust the splitting logic or output format by modifying `transcribe.py`.
- Update `config.yml` to change input/output file names or other parameters.

## Contributing

Contributions are welcome! Please open issues or submit pull requests for improvements or bug fixes.

## License

This project is licensed under the MIT License.

## Contact

For questions or suggestions, please open an issue in this repository.
