# Transcriber & CV Creator

This repository provides tools for transcribing audio and generating tailored CVs based on job descriptions and detailed transcripts. It includes scripts for transcription and CV creation, with flexible configuration options.

## Prerequisites

- Python 3.7+
- pip (Python package manager)

## Getting Started

### 1. Clone the Repository

```
git clone https://github.com/bdevay/transcriber
cd transcriber
```

### 2. Create a Virtual Environment

It is recommended to use a Python virtual environment to manage dependencies:

```
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

Install all required Python packages using `requirements.txt`:

```
pip install -r requirements.txt
```

### 4. Set your Gemini API key in `.env`:
   ```
   GEMINI_API_KEY=your_api_key_here
   ```

### 5. Edit `config_cv_creator.yml` as needed.

## Usage

- **Transcription**: Use `transcribe.py` to transcribe audio files.

Example command:

```
python3 ./transcribe.py --audio <audio_file_path> --output <transcript_output_file>
```

- **CV Creation**: Use `cv_creator.py` to generate a CV from a job description and transcript.

Example command:

```
python3 ./cv_creator.py --jd <job_description_url> --details <transcript_file> --config config_cv_creator.yml --output <output_file>
```

## Configuration: `config_cv_creator.yml`

The `config_cv_creator.yml` file defines a step-by-step workflow for generating a tailored CV using LLMs and advanced prompt engineering. Each step in the workflow is configurable and can be extended or modified to fit your needs.

### Example Structure

```yaml
workflow:
  - step: start_and_gather_inputs
    description: "Start the CV creation process and gather necessary inputs."
    type: gather_inputs
    cv_structure: |
      # Your Name
      Location ◆ email@example.com ◆ +31234567890 ◆ in/mylinkedinprofile
      ## INTRODUCTION
      ## KEY STRENGTHS
      ## PROFESSIONAL EXPERIENCE
      ## FURTHER ROLES
      ## EDUCATION
      ## PATENTS & INNOVATION
      ## LANGUAGE SKILLS
  - step: download_job_description
    description: "Download the job description from the provided link."
    type: download_document
    dependencies: [start_and_gather_inputs]
  # ... more steps ...
```

### Workflow Steps

Each item in the `workflow` list represents a step in the CV creation pipeline. Common fields include:

- **step**: (string) Unique identifier for the step.
- **description**: (string) Human-readable explanation of the step's purpose.
- **type**: (string) The type of operation (e.g., `gather_inputs`, `download_document`, `llm_task`, `json_iterator`, `write_file`).
- **dependencies**: (list, optional) Steps that must be completed before this one runs.
- **cv_structure**: (string, optional) Template for the CV structure (used only in the start_and_gather_inputs step).
- **prompt_variables**: (list, optional) Variables to be injected into prompts for LLM tasks.
- **output_variable**: (string, optional) Name of the variable to store the output of this step.
- **llm**: (object, optional) LLM configuration for steps that require language model calls. Includes:
  - `endpoint`: (string) API endpoint for the LLM.
  - `model`: (string) Model name (e.g., `gemini-flash-latest`).
  - `prompt`: (string) The prompt template to use.

### Example: LLM Task Step

```yaml
- step: extract_job_description
  description: "Extract plain text from the downloaded job description HTML."
  type: llm_task
  dependencies: [download_job_description]
  prompt_variables: [jd_html]
  output_variable: jd_text
  llm:
    endpoint: "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent"
    model: "gemini-flash-latest"
    prompt: |
      Extract and return the plain text content from the following HTML document that are related to the job description and remove unrelated contents:
      {{jd_html}}
```

### Key Concepts

- **Modular Workflow**: The process is broken into discrete, configurable steps. You can add, remove, or modify steps to customize the pipeline.
- **Prompt Engineering**: Prompts for LLMs are defined in the config, allowing improvements.
- **Data Flow**: Steps can depend on outputs from previous steps using the `dependencies` and variable passing.
- **Output File**: The final step typically writes the generated CV to a file (e.g., `data/cv_result.md`).

### Customization Tips
- Review and adjust the `cv_structure` to match your preferred CV layout.
- Edit LLM prompts as you think the pipeline produces better output.
- Add or remove workflow steps to include additional research or formatting as needed.
- Play with more advanced Gemini models–I can guarantee the surprise ;)

For a full example and advanced usage, see the provided `config_cv_creator.yml` file in the repository.

## Support

For questions or issues, please refer to the documentation or open an issue in the repository.

## License

This project is licensed under the terms described in [LICENSE](LICENSE).