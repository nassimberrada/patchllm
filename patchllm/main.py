import sys
import textwrap
import argparse
import litellm
import pprint
from pathlib import Path
from dotenv import load_dotenv

from .context import build_context
from .parser import paste_response
from .utils import load_from_py_file

# --- Core Functions ---

def collect_context(config_name, configs):
    """Builds the code context from a provided configuration dictionary."""
    print("\n--- Building Code Context... ---")
    if not configs:
        raise FileNotFoundError("Could not find a 'configs.py' file.")
    selected_config = configs.get(config_name)
    if selected_config is None:
        raise KeyError(f"Context config '{config_name}' not found in provided configs file.")
    
    context_object = build_context(selected_config)
    if context_object:
        tree, context = context_object.values()
        print("--- Context Building Finished. The following files were extracted ---", file=sys.stderr)
        print(tree)
        return context
    else:
        print("--- Context Building Failed (No files found) ---", file=sys.stderr)
        return None

def run_update(task_instructions, model_name, history, context=None):
    """
    Assembles the final prompt, sends it to the LLM, and applies file updates.
    """
    print("\n--- Sending Prompt to LLM... ---")
    final_prompt = task_instructions
    if context:
        final_prompt = f"{context}\n\n{task_instructions}"
    
    history.append({"role": "user", "content": final_prompt})
    
    try:
        response = litellm.completion(model=model_name, messages=history)
        assistant_response_content = response.choices[0].message.content
        history.append({"role": "assistant", "content": assistant_response_content})

        if not assistant_response_content or not assistant_response_content.strip():
            print("Response is empty. Nothing to paste.")
            return
        
        print("\n--- Updating files ---")
        paste_response(assistant_response_content)
        print("--- File Update Process Finished ---")

    except Exception as e:
        history.pop() # Keep history clean on error
        raise RuntimeError(f"An error occurred while communicating with the LLM via litellm: {e}") from e

def write_context_to_file(file_path, context):
    """Utility function to write the context to a file."""
    print("Exporting context..")
    with open(file_path, "w") as file:
        file.write(context)
    print(f'Context exported to {file_path.split("/")[-1]}')

def read_from_file(file_path):
    """Utility function to read and return the content of a file."""
    print("Importing from file..")
    try:
        with open(file_path, "r") as file:
            print("Finished reading")
            return file.read()
    except Exception as e:
        raise RuntimeError(f"Failed to read from file {file_path}: {e}") from e

def create_new_config(configs, configs_file_str):
    """Interactively creates a new configuration and saves it to the specified configs file."""
    print(f"\n--- Creating a new configuration in '{configs_file_str}' ---")
    
    try:
        name = input("Enter a name for the new configuration: ").strip()
        if not name:
            print("Configuration name cannot be empty.")
            return

        if name in configs:
            overwrite = input(f"Configuration '{name}' already exists. Overwrite? (y/n): ").lower()
            if overwrite not in ['y', 'yes']:
                print("Operation cancelled.")
                return

        path = input("Enter the base path (e.g., '.' for current directory): ").strip() or "."
        
        print("Enter comma-separated glob patterns for files to include (e.g., **/*.py, src/**/*.js):")
        include_raw = input("> ").strip()
        include_patterns = [p.strip() for p in include_raw.split(',') if p.strip()]

        print("Enter comma-separated glob patterns for files to exclude (e.g., **/tests/*, venv/*):")
        exclude_raw = input("> ").strip()
        exclude_patterns = [p.strip() for p in exclude_raw.split(',') if p.strip()]

        new_config_data = {
            "path": path,
            "include_patterns": include_patterns,
            "exclude_patterns": exclude_patterns,
        }

        configs[name] = new_config_data

        # Write the updated configs back to the file
        with open(configs_file_str, "w", encoding="utf-8") as f:
            f.write("# configs.py\n")
            f.write("configs = ")
            # Use pprint for a nicely formatted dictionary string
            f.write(pprint.pformat(configs, indent=4))
            f.write("\n")
        
        print(f"\nSuccessfully created and saved configuration '{name}' in '{configs_file_str}'.")

    except KeyboardInterrupt:
        print("\n\nConfiguration creation cancelled by user.")
        return

def main():
    """
    Main entry point for the patchllm command-line tool.
    """
    load_dotenv()
    
    parser = argparse.ArgumentParser(
        description="A CLI tool to apply code changes using an LLM."
    )

    parser.add_argument("-c", "--config", type=str, default=None, help="Name of the config key to use from the configs.py file.")
    parser.add_argument("-f", "--configs-file", type=str, default="./configs.py", help="Path to the configuration file. Defaults to './configs.py'.")
    parser.add_argument("-t", "--task", type=str, default=None, help="The task instructions to guide the assistant.")
    parser.add_argument("-o", "--context-out", nargs='?', const="context.md", default=None, help="Optional path to export the generated context. Defaults to 'context.md' if no path is given.")
    parser.add_argument("-i", "--context-in", type=str, default=None, help="Optional path to import a previously saved context from a file.")
    parser.add_argument("--model", type=str, default="gemini/gemini-1.5-flash", help="Optional model name to override the default model.")
    parser.add_argument("--from-file", type=str, default=None, help="File path for a file with pre-formatted updates.")
    parser.add_argument("--from-clipboard", action="store_true", help="Parse updates directly from the clipboard.")
    parser.add_argument("--update", type=str, default="True", help="Whether to pass the input context to the llm to update the files.")
    parser.add_argument("--voice", type=str, default="False", help="Whether to interact with the script using voice commands.")
    parser.add_argument("--list-configs", action="store_true", help="List all available configuration keys from the configs file and exit.")
    parser.add_argument("--init", action="store_true", help="Create a new configuration interactively.")


    args = parser.parse_args()

    try:
        configs = load_from_py_file(args.configs_file, "configs")
    except FileNotFoundError:
        configs = {}

    if args.list_configs:
        print(f"Available configurations in '{args.configs_file}':")
        if not configs:
            print(f"  -> No configurations found or '{args.configs_file}' is missing.")
        else:
            for config_name in configs:
                print(f"  - {config_name}")
        return

    if args.init:
        create_new_config(configs, args.configs_file)
        return

    if args.from_clipboard:
        try:
            import pyperclip
            updates = pyperclip.paste()
            if updates:
                print("--- Parsing updates from clipboard ---")
                paste_response(updates)
            else:
                print("Clipboard is empty. Nothing to parse.")
        except ImportError:
            print("Error: The 'pyperclip' library is required for clipboard functionality.", file=sys.stderr)
            print("Please install it using: pip install pyperclip", file=sys.stderr)
        except Exception as e:
            print(f"An error occurred while reading from the clipboard: {e}", file=sys.stderr)
        return

    if args.from_file:
        updates = read_from_file(args.from_file)
        paste_response(updates)
        return
        
    system_prompt = textwrap.dedent("""
        You are an expert pair programmer. Your purpose is to help users by modifying files based on their instructions.
        Follow these rules strictly:
        Your output should be a single file including all the updated files. For each file-block:
        1. Only include code for files that need to be updated / edited.
        2. For updated files, do not exclude any code even if it is unchanged code; assume the file code will be copy-pasted full in the file.
        3. Do not include verbose inline comments explaining what every small change does. Try to keep comments concise but informative, if any.
        4. Only update the relevant parts of each file relative to the provided task; do not make irrelevant edits even if you notice areas of improvements elsewhere.
        5. Do not use diffs.
        6. Make sure each file-block is returned in the following exact format. No additional text, comments, or explanations should be outside these blocks.
        Expected format for a modified or new file:
        <file_path:/absolute/path/to/your/file.py>
        ```python
        # The full, complete content of /absolute/path/to/your/file.py goes here.
        def example_function():
            return "Hello, World!"
        ```
    """)
    history = [{"role": "system", "content": system_prompt}]
    
    context = None
    if args.voice not in ["False", "false"]:
        from .listener import listen, speak
        speak("Say your task instruction.")
        task = listen()
        if not task:
            speak("No instruction heard. Exiting.")
            return
        speak(f"You said: {task}. Should I proceed?")
        confirm = listen()
        if confirm and "yes" in confirm.lower():
            context = collect_context(args.config, configs)
            run_update(task, args.model, history, context)
            speak("Changes applied.")
        else:
            speak("Cancelled.")
        return

    if args.context_in:
        context = read_from_file(args.context_in)
    else:
        if not args.config:
            parser.error("A --config name is required unless using other flags like --context-in or --list-configs.")
        context = collect_context(args.config, configs)
        if args.context_out:
            write_context_to_file(args.context_out, context)

    if args.update not in ["False", "false"]:
        if not args.task:
            parser.error("The --task argument is required to generate updates.")
        run_update(args.task, args.model, history, context)

if __name__ == "__main__":
    main()