import textwrap
import argparse
import litellm
import pprint
import os
import ast
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from pathlib import Path

from .context import build_context
from .parser import paste_response
from .utils import load_from_py_file

console = Console()

# --- Core Functions ---

def collect_context(scope_name, scopes):
    """Builds the code context from a provided scope name."""
    console.print("\n--- Building Code Context... ---", style="bold")
    base_path = Path(".").resolve()

    # build_context now handles all logic (dynamic vs static)
    context_object = build_context(scope_name, scopes, base_path)
    
    if context_object:
        tree, context = context_object.values()
        console.print("--- Context Building Finished. The following files were extracted ---", style="bold")
        console.print(tree)
        return context
    else:
        console.print("--- Context Building Failed ---", style="yellow")
        return None

def run_llm_query(task_instructions, model_name, history, context=None):
    """
    Assembles the final prompt, sends it to the LLM, and returns the response.
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
            console.print("⚠️  Response is empty. Nothing to process.", style="yellow")
            return None
        
        return assistant_response_content

    except Exception as e:
        history.pop() # Keep history clean on error
        raise RuntimeError(f"An error occurred while communicating with the LLM via litellm: {e}") from e

def write_to_file(file_path, content):
    """Utility function to write content to a file."""
    console.print(f"Writing to {file_path}..", style="cyan")
    try:
        with open(file_path, "w", encoding="utf-8") as file:
            file.write(content)
        console.print(f'✅ Content saved to {file_path}', style="green")
    except Exception as e:
        raise RuntimeError(f"Failed to write to file {file_path}: {e}") from e

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

def write_scopes_to_file(file_path, scopes_dict):
    """Writes the scopes dictionary back to a Python file."""
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("scopes = ")
            f.write(pprint.pformat(scopes_dict, indent=4))
            f.write("\n")
        console.print(f"✅ Successfully updated '{file_path}'.", style="green")
    except Exception as e:
        console.print(f"❌ Failed to write to '{file_path}': {e}", style="red")

def main():
    """
    Main entry point for the patchllm command-line tool.
    """
    load_dotenv()
    
    scopes_file_path = os.getenv("PATCHLLM_SCOPES_FILE", "./scopes.py")

    parser = argparse.ArgumentParser(
        description="A CLI tool to apply code changes using an LLM.",
        formatter_class=argparse.RawTextHelpFormatter
    )

    # --- Group: Core Patching Flow ---
    patch_group = parser.add_argument_group('Core Patching Flow')
    patch_group.add_argument(
        "-s", "--scope", type=str, default=None,
        help=textwrap.dedent("""\
        Name of the scope to use. Can be a static scope from your scopes file
        or a dynamic scope. Available dynamic scopes:
        - @git or @git:staged: Files staged for commit.
        - @git:unstaged: Files modified but not staged.
        - @git:branch[:base]: Files changed on current branch vs. 'main' or :base.
        - @git:lastcommit: Files from the last commit.
        - @git:conflicts: Files with merge conflicts.
        - @recent: 5 most recently modified files.
        - @dir:<path>: All files in a directory.
        - @related:<file>: A file and its likely related files (e.g., tests).
        - @search:"<term>": All files containing a search term.
        - @error:"<traceback>": Parses file paths from a traceback.
        """))
    patch_group.add_argument("-t", "--task", type=str, default=None, help="The task instructions to guide the assistant.")
    patch_group.add_argument("-p", "--patch", action="store_true", help="Query the LLM and directly apply the file updates from the response. Requires --task.")

    # --- Group: Scope Management ---
    scope_group = parser.add_argument_group('Scope Management')
    scope_group.add_argument("-i", "--init", action="store_true", help="Create a default 'scopes.py' file with a 'base' scope.")
    scope_group.add_argument("-sl", "--list-scopes", action="store_true", help="List all available scopes from the scopes file and exit.")
    scope_group.add_argument("-ss", "--show-scope", type=str, help="Display the settings for a specific scope and exit.")
    scope_group.add_argument("-sa", "--add-scope", type=str, help="Add a new scope with default settings.")
    scope_group.add_argument("-sr", "--remove-scope", type=str, help="Remove a scope from the scopes file.")
    scope_group.add_argument("-su", "--update-scope", nargs='+', help="Update a scope. Usage: -su <scope_name> key=\"['value']\" key2=value2")


    # --- Group: I/O Utils---
    code_io = parser.add_argument_group('Code I/O')
    code_io.add_argument("-co", "--context-out", nargs='?', const="context.md", default=None, help="Export the generated context to a file. Defaults to 'context.md'.")
    code_io.add_argument("-ci", "--context-in", type=str, default=None, help="Import a previously saved context from a file.")
    code_io.add_argument("-tf", "--to-file", nargs='?', const="response.md", default=None, help="Query the LLM and save the response to a file. Requires --task. Defaults to 'response.md'.")
    code_io.add_argument("-tc", "--to-clipboard", action="store_true", help="Query the LLM and save the response to the clipboard. Requires --task.")
    code_io.add_argument("-ff", "--from-file", type=str, default=None, help="Apply code updates directly from a file.")
    code_io.add_argument("-fc", "--from-clipboard", action="store_true", help="Apply code updates directly from the clipboard.")
    
    # --- Group: General Options ---
    options_group = parser.add_argument_group('General Options')
    options_group.add_argument("-m", "--model", type=str, default="gemini/gemini-1.5-flash", help="Model name to use (e.g., 'gpt-4o', 'claude-3-sonnet').")
    options_group.add_argument("-v", "--voice", type=str, default="False", help="Enable voice interaction for providing task instructions. (True/False)")
    options_group.add_argument("-g", "--guidelines", nargs='?', const=True, default=None, help="Prepend guidelines to the context. If no value, uses the default system prompt.")

    args = parser.parse_args()

    if args.init:
        if Path(scopes_file_path).exists():
            console.print(f"⚠️  '{scopes_file_path}' already exists. Aborting.", style="yellow")
            return

        default_scopes = {
            "base": {
                "path": ".",
                "include_patterns": ["**/*"],
                "exclude_patterns": [],
            }
        }
        write_scopes_to_file(scopes_file_path, default_scopes)
        console.print(f"✅ Successfully created a default '{scopes_file_path}' with a 'base' scope.", style="green")
        return

    try:
        scopes = load_from_py_file(scopes_file_path, "scopes")
    except FileNotFoundError:
        scopes = {}
        if not any([args.list_scopes, args.show_scope, args.add_scope]):
             console.print(f"⚠️  Scope file '{scopes_file_path}' not found. You can create one with the --init flag.", style="yellow")
    except Exception as e:
        console.print(f"❌ Error loading scopes file: {e}", style="red")
        return


    if args.add_scope:
        scope_name = args.add_scope
        if scope_name in scopes:
            console.print(f"❌ Scope '[bold]{scope_name}[/]' already exists.", style="red")
            return
        
        scopes[scope_name] = {
            "path": ".",
            "include_patterns": ["**/*"],
            "exclude_patterns": [],
        }
        write_scopes_to_file(scopes_file_path, scopes)
        console.print(f"✅ Added new scope '[bold]{scope_name}[/]' with default settings.")
        return

    if args.remove_scope:
        scope_name = args.remove_scope
        if scope_name not in scopes:
            console.print(f"❌ Scope '[bold]{scope_name}[/]' not found.", style="red")
            return
        
        del scopes[scope_name]
        write_scopes_to_file(scopes_file_path, scopes)
        console.print(f"✅ Removed scope '[bold]{scope_name}[/]'.")
        return

    if args.update_scope:
        if len(args.update_scope) < 2:
            parser.error("--update-scope requires a scope name and at least one 'key=value' pair.")
        
        scope_name = args.update_scope[0]
        updates = args.update_scope[1:]

        if scope_name not in scopes:
            console.print(f"❌ Scope '[bold]{scope_name}[/]' not found.", style="red")
            return

        try:
            for update in updates:
                if '=' not in update:
                    raise ValueError(f"Invalid update format. Expected 'key=value', but got '{update}'")
                key, value_str = update.split('=', 1)
                key = key.strip()
                
                if key not in scopes[scope_name]:
                     console.print(f"⚠️  Key '[bold]{key}[/]' not found in scope. It will be added.", style="yellow")

                value = ast.literal_eval(value_str) # Safely evaluate string to Python literal.
                scopes[scope_name][key] = value
                console.print(f"  -> Updated '{key}' in scope '[bold]{scope_name}[/]'.")

            write_scopes_to_file(scopes_file_path, scopes)
        except (ValueError, SyntaxError) as e:
            console.print(f"❌ Error parsing update values: {e}", style="red")
            console.print("  -> Make sure values are valid Python literals (e.g., strings in quotes, lists in brackets).", style="yellow")
        except Exception as e:
            console.print(f"❌ An unexpected error occurred during scope update: {e}", style="red")
        return


    if args.list_scopes:
        console.print(f"Available scopes in '[bold]{scopes_file_path}[/]':", style="bold")
        if not scopes:
            console.print(f"  -> No scopes found or '{scopes_file_path}' is missing.")
        else:
            for scope_name in scopes:
                console.print(f"  - {scope_name}")
        return

    if args.show_scope:
        scope_name = args.show_scope
        if not scopes:
            console.print(f"⚠️  Scope file '{scopes_file_path}' not found or is empty.", style="yellow")
            return
        
        scope_data = scopes.get(scope_name)
        if scope_data:
            pretty_scope = pprint.pformat(scope_data, indent=2)
            console.print(
                Panel(
                    pretty_scope,
                    title=f"[bold cyan]Scope: '{scope_name}'[/]",
                    subtitle=f"[dim]from {scopes_file_path}[/dim]",
                    border_style="blue"
                )
            )
        else:
            console.print(f"❌ Scope '[bold]{scope_name}[/]' not found in '{scopes_file_path}'.", style="red")
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
            if not args.scope:
                parser.error("A --scope name is required when using --voice.")
            context = collect_context(args.scope, scopes)
            llm_response = run_llm_query(task, args.model, history, context)
            if ll_response:
                paste_response(llm_response)
                speak("Changes applied.")
        else:
            speak("Cancelled.")
        return

    # --- Main LLM Task Logic ---
    context = None

    if args.context_in:
        context = read_from_file(args.context_in)
    elif args.scope:
        context = collect_context(args.scope, scopes)

    if args.guidelines is not None:
        guidelines_content = system_prompt if args.guidelines is True else args.guidelines
        if context:
            context = f"{guidelines_content}\n\n{context}"
        else:
            context = guidelines_content

    if args.task:
        action_flags = [args.patch, args.to_file is not None, args.to_clipboard]
        if sum(action_flags) == 0:
            parser.error("A task was provided, but no action was specified. Use --patch, --to-file, or --to-clipboard.")
        if sum(action_flags) > 1:
            parser.error("Please specify only one action: --patch, --to-file, or --to-clipboard.")

        if not args.scope and not args.context_in:
            parser.error("A --scope or --context-in is required to build context for a task.")

        if context and args.context_out:
            write_to_file(args.context_out, context)

        if not context:
            console.print("Proceeding with task but without any file context.", style="yellow")

        llm_response = run_llm_query(args.task, args.model, history, context)

        if llm_response:
            if args.patch:
                console.print("\n--- Updating files ---", style="bold")
                paste_response(llm_response)
                console.print("--- File Update Process Finished ---", style="bold")

            elif args.to_file is not None:
                write_to_file(args.to_file, llm_response)

            elif args.to_clipboard:
                try:
                    import pyperclip
                    pyperclip.copy(llm_response)
                    console.print("✅ Copied LLM response to clipboard.", style="green")
                except ImportError:
                    console.print("❌ The 'pyperclip' library is required for clipboard functionality.", style="red")
                    console.print("Please install it using: pip install pyperclip", style="cyan")
                except Exception as e:
                    console.print(f"❌ An error occurred while copying to the clipboard: {e}", style="red")

    elif args.context_out:
        if context:
            write_to_file(args.context_out, context)
        else:
            console.print("No context to export. A scope (-s), context-in (-ci), or guidelines (-g) must be provided.", style="yellow")

if __name__ == "__main__":
    main()