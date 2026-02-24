import argparse
import os
import yaml
import requests
import json
import json
from dotenv import load_dotenv
from gemini_cli import send_gemini_request
from docx import Document
import PyPDF2

# Global variables to store step outputs
variables = {}

# Helper to render prompt templates
def render_prompt(prompt, context):
    # Replace {{var}} with context[var]
    for k, v in context.items():
        prompt = prompt.replace(f'{{{{{k}}}}}', str(v))
    return prompt

def validate_config(config) -> bool:
    """
    Validate the workflow configuration.
    Valid if:
    - Each step has a unique name.
    - Each step's dependencies refer to previous steps.
    - Each step's variables are unique.
    - The step types are recognized.
    - The config has a 'workflow' key with a list of steps.
    
    Returns True if valid, False otherwise.
    """
    recognized_types = {
        'llm_task', 
        'download_document',
        'gather_inputs',
        'json_iterator',
        'write_file'}
    
    if not isinstance(config, dict):
        print("Config is not a dictionary.")
        return False
    
    steps = config.get('workflow')
    if not isinstance(steps, list) or not steps:
        print("Config 'workflow' key is missing or not a non-empty list.")
        return False
    
    step_names = set()
    variables = set()
    prev_steps = set()

    for idx, step in enumerate(steps):
        # Step name uniqueness
        step_name = step.get('step')
        if not step_name or step_name in step_names:
            print(f"Step name missing or not unique at index {idx}: '{step_name}'")
            return False
        step_names.add(step_name)

        # Step type recognition
        step_type = step.get('type')
        if step_type not in recognized_types:
            print(f"Unrecognized step type '{step_type}' in step '{step_name}'")
            return False
        
        # Dependencies refer to previous steps
        dependencies = step.get('dependencies', [])
        if not isinstance(dependencies, list):
            print(f"Dependencies for step '{step_name}' are not a list.")
            return False
        
        for dep in dependencies:
            if dep not in prev_steps:
                print(f"Dependency '{dep}' for step '{step_name}' not found among previous steps.")
                return False

        # variables uniqueness
        variables = step.get('variables', [])
        if not isinstance(variables, list):
            print(f"variables for step '{step_name}' are not a list.")
            return False
        
        for out_var in variables:
            if out_var in variables:
                print(f"Output variable '{out_var}' in step '{step_name}' is not unique.")
                return False
            variables.add(out_var)
        prev_steps.add(step_name)

    return True

def load_details_file(details_path):
    """
    Load the background story file (pdf, docx, txt, md) and return its text content in a dict with the given output_var as key.
    """
    if not os.path.isfile(details_path):
        raise FileNotFoundError(f"Details file not found: {details_path}")

    ext = os.path.splitext(details_path)[1].lower()
    if ext == '.pdf':
        with open(details_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            text = ''
            for page in reader.pages:
                text += page.extract_text() + '\n'
        return text
    elif ext == '.docx':
        doc = Document(details_path)
        text = '\n'.join([para.text for para in doc.paragraphs])
        return text
    elif ext in ['.txt', '.md']:
        with open(details_path, 'r') as f:
            text = f.read()
        return text
    else:
        raise ValueError(f"Unsupported details file format: {ext}")

def gather_inputs(step, args):
    """
    Gather inputs as specified in the 'gather_inputs' step.
    Currently supports loading background story from file.
    """
    global variables

    # Store job description link
    variables['jd_link'] = args.jd

    # Load user-specific details config
    with open(args.details_config, 'r') as f:
        user_details_config = yaml.safe_load(f)
    cv_structure = user_details_config.get('cv_structure', [])

    # For each section, load input files and store in variables by section name
    for section in cv_structure:
        section_name = section.get('section_name')
        fixed = section.get('fixed', None)
        description = section.get('description', '')
        input_files = section.get('input_files', [])
        step_name = section.get('step', None)

        section_texts = []
        for file_path in input_files:
            if not os.path.isfile(file_path):
                raise FileNotFoundError(f"Section '{section_name}' input file not found: {file_path}")
            with open(file_path, 'r') as f:
                section_texts.append(f.read())

        # Store all user setting from the config_cv_creator.yml in the step's variable 
        variables[step_name]['input_files'] = section_texts
        variables[step_name]['description'] = description
        variables[step_name]['fixed'] = fixed

def download_document():
    """
    Download document from URL specified in variables and store its text in variables.
    """
    global variables

    link = variables.get('jd_link', '')
    if not link.startswith('http'):
        raise ValueError(f"Invalid URL for download_document: '{link}'")
    response = requests.get(link)
    if response.status_code != 200:
        raise ValueError(f"Failed to download document from '{link}': Status {response.status_code}")
    variables['jd_html'] = response.text

def llm_task(step):
    """
    Calls send_gemini_request from gemini_cli.py with the given prompt and files.
    Returns the parsed response.
    """
    global variables
    api_key = os.getenv('GEMINI_API_KEY')

    required_variables = step.get('prompt_variables', [])
    if not all(var in variables.keys() for var in required_variables):
        raise ValueError(f"LLM task requires variables: {required_variables}")
    context = {var: variables.get(var, '') for var in required_variables}
    rendered = render_prompt(step.get('llm', {}).get('prompt', ''), context)

    output_var = step.get('output_variable', 'llm_response')

    endpoint = step.get('llm', {}).get('endpoint', '')
    if not endpoint:
        raise ValueError("LLM task must specify an endpoint in llm.endpoint")
    
    model = step.get('llm', {}).get('model', '')
    if not model:
        raise ValueError("LLM task must specify the model in llm.model")

    options = step.get('llm', {}).get('options', {})

    api_result = send_gemini_request(rendered, [], endpoint, model, options, api_key)

    response = api_result.get('response', {})
    # Try to parse as JSON if it's a string
    if isinstance(response, str):
        try:
            response_json = json.loads(response)
        except Exception:
            response_json = None
    else:
        response_json = response

    # If response_json matches the new structure
    text_value = None
    if isinstance(response_json, dict):
        candidates = response_json.get('candidates')
        if candidates and isinstance(candidates, list):
            content = candidates[0].get('content') if candidates else None
            if content and isinstance(content, dict):
                parts = content.get('parts')
                if parts and isinstance(parts, list) and 'text' in parts[0]:
                    text_value = parts[0]['text']
    # Fallback to previous logic if not found
    if text_value is None:
        if isinstance(response, dict) and 'parts' in response and isinstance(response['parts'], list):
            text_value = response['parts'][0].get('text', '') if response['parts'] else ''
        elif isinstance(response, dict) and 'text' in response:
            text_value = response.get('text', '')
        else:
            text_value = str(response)
    variables[output_var] = text_value

def json_iterator(step):
    """
    Iterate over a JSON array variable, calling a specified llm_task step for each item.
    Accumulate results into a single output variable.
    """
    global variables

    input_var = step.get('list_variable', [])
    if input_var not in variables.keys():
        raise ValueError(f"Input variable '{input_var}' for json_iterator not found in variables")
    
    json_array_str = variables[input_var]
    try:
        json_array = json.loads(json_array_str)
        if not isinstance(json_array, list):
            raise ValueError(f"Input variable '{input_var}' is not a JSON array")
    except Exception as e:
        raise ValueError(f"Failed to parse JSON array from variable '{input_var}': {e}")
    
    results = []
    output_var = step.get('output_variable', 'iterator_output')
    for action in step.get('actions', {}):
        if action.get('type') == 'llm_task':
            item_output_var = action.get('output_variable', 'item_output')
            for item in json_array:
                action_description = action.get('description', [])
                print(f"[ITERATOR] Processing item: {item}")
                print(f"  [ACTION] {action_description}")
                variables['current_item'] = item
                llm_task(action)
                results.append(variables.get(item_output_var, ''))
        else:
            raise ValueError(f"Unsupported action type '{action.get('type')}' in json_iterator")
        
    variables[output_var] = '\n\n'.join(results)

def write_file(step, args):
    """
    Write the specified output variable to a file.
    """
    global variables

    required_variables = step.get('to_write_variables', [])
    for var in required_variables:
        if var not in variables or variables[var] is None:
            raise ValueError(f"Required variable '{var}' for write_file step is not set in variables")
    
    # Use variables config if present, else input_var name
    out_path = step.get('output_file', args.output)
    if not out_path:
        raise ValueError("Output file path not specified in write_file step or args")

    with open(out_path, 'w') as out:
        for var in required_variables:
            #out.write(f'# OUTPUT {var}\n\n')
            out.write(variables[var] + '\n\n')

def main():
    parser = argparse.ArgumentParser(description="CV Creator - Advanced Workflow")
    parser.add_argument('--jd', required=True, help='URL or path to job description')
    parser.add_argument('--details-config', required=True, help='Path to user-specific details config YAML (sections, files, etc.)')
    parser.add_argument('--config', default='config_cv_creator.yml', help='Path to workflow config YAML')
    parser.add_argument('--output', default='results/cv_result.md', help='Output markdown file')
    args = parser.parse_args()

    load_dotenv()

    # Load workflow config
    with open(args.config, 'r') as f:
        config = yaml.safe_load(f)

    # Execute workflow steps in order
    steps = config.get('workflow', [])
    if not validate_config(config):
        print("Invalid workflow configuration.")
        raise SystemExit(1)

    global variables
    variables = {}

    executed_steps = {}
    last_executed_steps_count = -1
    while len(executed_steps) < len(steps):
        if len(executed_steps) == last_executed_steps_count:
            pending_steps = [step.get('step') for step in steps if step.get('step') not in executed_steps]
            raise ValueError(f"Circular dependency detected or missing dependencies for step: {pending_steps}")
        last_executed_steps_count = len(executed_steps)

        for step in steps:
            step_name = step.get('step')
            if step_name in executed_steps:
                continue
            step_description = step.get('description', '')
            step_type = step.get('type')
            step_dependencies = step.get('dependencies', [])
            step_input_vars = step.get('input_vars', [])
            dependency_not_yet_executed = False
            for dependency in step_dependencies:
                if dependency not in executed_steps:
                    dependency_not_yet_executed = True
                    break
            if dependency_not_yet_executed:
                continue
            # Log input variables for this step
            print(f"\n[STEP] {step_name} ({step_type})\n Description: {step_description}")
            for var in step_input_vars:
                print(f"  [INPUT] {var}: {repr(variables.get(var, None))}")
            if step_type == 'gather_inputs':
                gather_inputs(step, args)
            elif step_type == 'download_document':
                download_document()
            elif step_type == 'llm_task':
                llm_task(step)
            elif step_type == 'write_file':
                write_file(step, args)
            elif step_type == 'json_iterator':
                json_iterator(step)
            else:
                raise ValueError(f"Unknown step type: {step_type}")
            executed_steps[step_name] = step

    print(f"[SUCCESS] CV document written to {args.output}")

if __name__ == "__main__":
    main()
