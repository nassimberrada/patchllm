import textwrap
import argparse
import litellm
import pprint
import os
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

from .context import build_context
from .parser import paste_response
from .utils import load_from_py_file

console = Console()

# --- Core Functions ---

def collect_context(config_name, configs):
    """Builds the code context from a provided configuration dictionary."""
    console.print("\n--- Building Code Context... ---", style="bold")
    if not configs:
        raise FileNotFoundError("Could not find a 'configs.py' file.")
    selected_config = configs.get(config_name)
    if selected_config is None:
        raise KeyError(f"Context config '{config_name}' not found in provided configs file.")
    
    context_object = build_context(selected_config)
    if context_object:
        tree, context = context_object.values()
        console.print("--- Context Building Finished. The following files were extracted ---", style="bold")
        console.print(tree)
        return context
    else:
        console.print("--- Context Building Failed (No files found) ---", style="yellow")
        return None

def run_update(task_instructions, model_name, history, context=None):
    """
    Assembles the final prompt, sends it to the LLM, and applies file updates.
    """
    console.print("\n--- Sending Prompt to LLM... ---", style="bold")
    final_prompt = task_instructions
    if context:
        final_prompt = f"{context}\n\n{task_instructions}"
    
    history.append({"role": "user", "content": final_prompt})
    
    try:
        with console.status("[bold cyan]Waiting for LLM response...", spinner="dots"):
            response = litellm.completion(model=model_name, messages=history)
        
        assistant_response_content = response.choices[0].message.content
        history.append({"role": "assistant", "content": assistant_response_content})

        if not assistant_response_content or not assistant_response_content.strip():
            console.print("⚠️  Response is empty. Nothing to paste.", style="yellow")
            return
        
        console.print("\n--- Updating files ---", style="bold")
        paste_response(assistant_response_content)
        console.print("--- File Update Process Finished ---", style="bold")

    except Exception as e:
        history.pop() # Keep history clean on error
        raise RuntimeError(f"An error occurred while communicating with the LLM via litellm: {e}") from e

def write_context_to_file(file_path, context):
    """Utility function to write the context to a file."""
    console.print("Exporting context..", style="cyan")
    with open(file_path, "w", encoding="utf-8") as file:
        file.write(context)
    console.print(f'✅ Context exported to {file_path.split("/")[-1]}', style="green")

def read_from_file(file_path):
    """Utility function to read and return the content of a file."""
    console.print(f"Importing from {file_path}..", style="cyan")
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            content = file.read()
            console.print("✅ Finished reading file.", style="green")
            return content
    except Exception as e:
        raise RuntimeError(f"Failed to read from file {file_path}: {e}") from e

def create_new_config(configs, configs_file_str):
    """Interactively creates a new configuration and saves it to the specified configs file."""
    console.print(f"\n--- Creating a new configuration in '{configs_file_str}' ---", style="bold")
    
    try:
        name = console.input("[bold]Enter a name for the new configuration: [/]").strip()
        if not name:
            console.print("❌ Configuration name cannot be empty.", style="red")
            return

        if name in configs:
            overwrite = console.input(f"Configuration '[bold]{name}[/]' already exists. Overwrite? (y/n): ").lower()
            if overwrite not in ['y', 'yes']:
                console.print("Operation cancelled.", style="yellow")
                return

        path = console.input("[bold]Enter the base path[/] (e.g., '.' for current directory): ").strip() or "."
        
        console.print("\nEnter comma-separated glob patterns for files to include.")
        include_raw = console.input('[cyan]> (e.g., "[bold]**/*.py, src/**/*.js[/]"): [/]').strip()
        include_patterns = [p.strip() for p in include_raw.split(',') if p.strip()]

        console.print("\nEnter comma-separated glob patterns for files to exclude (optional).")
        exclude_raw = console.input('[cyan]> (e.g., "[bold]**/tests/*, venv/*[/]"): [/]').strip()
        exclude_patterns = [p.strip() for p in exclude_raw.split(',') if p.strip()]
        
        console.print("\nEnter comma-separated URLs to include as context (optional).")
        urls_raw = console.input('[cyan]> (e.g., "[bold]https://docs.example.com, ...[/]"): [/]').strip()
        urls = [u.strip() for u in urls_raw.split(',') if u.strip()]

        new_config_data = {
            "path": path,
            "include_patterns": include_patterns,
            "exclude_patterns": exclude_patterns,
            "urls": urls,
        }

        configs[name] = new_config_data

        with open(configs_file_str, "w", encoding="utf-8") as f:
            f.write("# configs.py\n")
            f.write("configs = ")
            f.write(pprint.pformat(configs, indent=4))
            f.write("\n")
        
        console.print(f"\n✅ Successfully created and saved configuration '[bold]{name}[/]' in '[bold]{configs_file_str}[/]'.", style="green")

    except KeyboardInterrupt:
        console.print("\n\n⚠️ Configuration creation cancelled by user.", style="yellow")
        return

def main():
    """
    Main entry point for the patchllm command-line tool.
    """
    load_dotenv()
    
    configs_file_path = os.getenv("PATCHLLM_CONFIGS_FILE", "./configs.py")

    parser = argparse.ArgumentParser(
        description="A CLI tool to apply code changes using an LLM.",
        formatter_class=argparse.RawTextHelpFormatter
    )

    parser.add_argument("-i", "--init", action="store_true", help="Create a new configuration interactively.")
    
    parser.add_argument("-c", "--config", type=str, default=None, help="Name of the config key to use from the configs file.")
    parser.add_argument("-t", "--task", type=str, default=None, help="The task instructions to guide the assistant.")
    
    parser.add_argument("-co", "--context-out", nargs='?', const="context.md", default=None, help="Export the generated context to a file. Defaults to 'context.md'.")
    parser.add_argument("-ci", "--context-in", type=str, default=None, help="Import a previously saved context from a file.")
    
    parser.add_argument("-u", "--update", type=str, default="True", help="Control whether to send the context to the LLM for updates. (True/False)")
    parser.add_argument("-ff", "--from-file", type=str, default=None, help="Apply updates directly from a file instead of the LLM.")
    parser.add_argument("-fc", "--from-clipboard", action="store_true", help="Apply updates directly from the clipboard.")
    
    parser.add_argument("--model", type=str, default="gemini/gemini-1.5-flash", help="Model name to use (e.g., 'gpt-4o', 'claude-3-sonnet').")
    parser.add_argument("--voice", type=str, default="False", help="Enable voice interaction for providing task instructions. (True/False)")
    
    parser.add_argument("--list-configs", action="store_true", help="List all available configurations from the configs file and exit.")
    parser.add_argument("--show-config", type=str, help="Display the settings for a specific configuration and exit.")
    
    args = parser.parse_args()

    try:
        configs = load_from_py_file(configs_file_path, "configs")
    except FileNotFoundError:
        configs = {}
        if not any([args.init, args.list_configs, args.show_config]):
             console.print(f"⚠️  Config file '{configs_file_path}' not found. You can create one with the --init flag.", style="yellow")


    if args.list_configs:
        console.print(f"Available configurations in '[bold]{configs_file_path}[/]':", style="bold")
        if not configs:
            console.print(f"  -> No configurations found or '{configs_file_path}' is missing.")
        else:
            for config_name in configs:
                console.print(f"  - {config_name}")
        return

    if args.show_config:
        config_name = args.show_config
        if not configs:
            console.print(f"⚠️  Config file '{configs_file_path}' not found or is empty.", style="yellow")
            return
        
        config_data = configs.get(config_name)
        if config_data:
            pretty_config = pprint.pformat(config_data, indent=2)
            console.print(
                Panel(
                    pretty_config,
                    title=f"[bold cyan]Configuration: '{config_name}'[/]",
                    subtitle=f"[dim]from {configs_file_path}[/dim]",
                    border_style="blue"
                )
            )
        else:
            console.print(f"❌ Configuration '[bold]{config_name}[/]' not found in '{configs_file_path}'.", style="red")
        return

    if args.init:
        create_new_config(configs, configs_file_path)
        return

    if args.from_clipboard:
        try:
            import pyperclip
            updates = pyperclip.paste()
            if updates:
                console.print("--- Parsing updates from clipboard ---", style="bold")
                paste_response(updates)
            else:
                console.print("⚠️ Clipboard is empty. Nothing to parse.", style="yellow")
        except ImportError:
            console.print("❌ The 'pyperclip' library is required for clipboard functionality.", style="red")
            console.print("Please install it using: pip install pyperclip", style="cyan")
        except Exception as e:
            console.print(f"❌ An error occurred while reading from the clipboard: {e}", style="red")
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
            parser.error("A --config name is required unless using other flags like --context-in or other utility flags.")
        context = collect_context(args.config, configs)
        if context and args.context_out:
            write_context_to_file(args.context_out, context)

    if args.update not in ["False", "false"]:
        if not args.task:
            parser.error("The --task argument is required to generate updates.")
        if context:
            run_update(args.task, args.model, history, context)

if __name__ == "__main__":
    main()