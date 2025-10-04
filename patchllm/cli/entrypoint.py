import argparse
import textwrap
import os
from pathlib import Path
from rich.console import Console

from .handlers import (
    handle_init, handle_scope_management, handle_file_io, 
    handle_main_task_flow, handle_voice_flow, handle_chat_flow
)
from ..utils import load_from_py_file

console = Console()

def main():
    """Main entry point for the patchllm command-line tool."""
    from dotenv import load_dotenv
    load_dotenv()
    
    scopes_file_path = os.getenv("PATCHLLM_SCOPES_FILE", "./scopes.py")
    recipes_file_path = os.getenv("PATCHLLM_RECIPES_FILE", "./recipes.py")

    parser = argparse.ArgumentParser(
        description="A CLI tool to apply code changes using an LLM.",
        formatter_class=argparse.RawTextHelpFormatter
    )

    patch_group = parser.add_argument_group('Core Patching Flow')
    scope_group = parser.add_argument_group('Scope Management')
    code_io = parser.add_argument_group('Code I/O')
    options_group = parser.add_argument_group('General Options')

    patch_group.add_argument(
        "-c", "--chat", action="store_true",
        help="Start an interactive chat session to guide the patching process."
    )
    patch_group.add_argument(
        "-in", "--interactive", action="store_true",
        help="Interactively build the context by selecting files and folders."
    )
    patch_group.add_argument(
        "-s", "--scope", type=str, default=None,
        help=textwrap.dedent("""\
        Name of the scope to use (static or dynamic).
        Dynamic: @structure, @git, @git:staged, @git:unstaged, @git:branch[:base], 
                 @git:lastcommit, @git:conflicts, @recent, @dir:<path>, 
                 @related:<file>, @search:"<term>", @error:"<traceback>"
        """))
    patch_group.add_argument(
        "-r", "--recipe", type=str, default=None,
        help="Name of the recipe to use from your 'recipes.py' file."
    )
    patch_group.add_argument("-t", "--task", type=str, help="The task instructions for the assistant.")
    patch_group.add_argument("-p", "--patch", action="store_true", help="Query the LLM and apply file updates.")

    scope_group.add_argument("-i", "--init", action="store_true", help="Create a default 'scopes.py' file.")
    scope_group.add_argument("-sl", "--list-scopes", action="store_true", help="List all available scopes.")
    scope_group.add_argument("-ss", "--show-scope", type=str, help="Display the settings for a specific scope.")
    scope_group.add_argument("-sa", "--add-scope", type=str, help="Add a new scope with default settings.")
    scope_group.add_argument("-sr", "--remove-scope", type=str, help="Remove a scope.")
    scope_group.add_argument("-su", "--update-scope", nargs='+', help="Update a scope. Usage: -su <scope> key=\"['val']\"")

    code_io.add_argument("-co", "--context-out", nargs='?', const="context.md", default=None, help="Export context to a file.")
    code_io.add_argument("-ci", "--context-in", type=str, default=None, help="Import context from a file.")
    code_io.add_argument("-tf", "--to-file", nargs='?', const="response.md", default=None, help="Save LLM response to a file.")
    code_io.add_argument("-tc", "--to-clipboard", action="store_true", help="Copy LLM response to clipboard.")
    code_io.add_argument("-ff", "--from-file", type=str, default=None, help="Apply updates from a file.")
    code_io.add_argument("-fc", "--from-clipboard", action="store_true", help="Apply updates from the clipboard.")
    
    options_group.add_argument("-m", "--model", type=str, default="gemini/gemini-1.5-flash", help="Model name to use.")
    options_group.add_argument("-v", "--voice", type=str, default="False", help="Enable voice interaction (True/False).")
    options_group.add_argument("-g", "--guidelines", nargs='?', const=True, default=None, help="Prepend guidelines to the context.")

    args = parser.parse_args()

    if args.init:
        handle_init(scopes_file_path)
        return

    try:
        scopes = load_from_py_file(scopes_file_path, "scopes")
    except FileNotFoundError:
        scopes = {}
        if not any([args.list_scopes, args.show_scope, args.add_scope, args.init, args.chat]):
             console.print(f"⚠️  Scope file '{scopes_file_path}' not found. You can create one with --init.", style="yellow")
    except Exception as e:
        console.print(f"❌ Error loading scopes file: {e}", style="red")
        return

    try:
        recipes = load_from_py_file(recipes_file_path, "recipes")
    except FileNotFoundError:
        recipes = {}
        if args.recipe:
            console.print(f"⚠️  Recipes file '{recipes_file_path}' not found, but a recipe was requested.", style="yellow")
    except Exception as e:
        console.print(f"❌ Error loading recipes file: {e}", style="red")
        return

    if args.chat:
        handle_chat_flow(args, scopes, recipes)
        return

    if any([args.list_scopes, args.show_scope, args.add_scope, args.remove_scope, args.update_scope]):
        handle_scope_management(args, scopes, scopes_file_path, parser)
        return
        
    if any([args.from_file, args.from_clipboard]):
        handle_file_io(args)
        return

    if args.voice.lower() == 'true':
        handle_voice_flow(args, scopes, parser)
        return

    handle_main_task_flow(args, scopes, recipes, parser)