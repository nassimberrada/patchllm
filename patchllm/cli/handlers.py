import pprint
import ast
import textwrap
import re
import argparse
from pathlib import Path
from rich.console import Console
from rich.panel import Panel

from ..utils import write_scopes_to_file
from ..parser import paste_response
from ..patcher import apply_external_patch
from ..scopes.builder import build_context_from_files, helpers
from ..llm import run_llm_query
from .helpers import get_system_prompt, _collect_context

from InquirerPy import prompt
from InquirerPy.exceptions import InvalidArgument
from InquirerPy.validator import EmptyInputValidator

console = Console()

def handle_init(scopes_file_path):
    if Path(scopes_file_path).exists():
        console.print(f"⚠️  '{scopes_file_path}' already exists. Aborting.", style="yellow")
        return
    default_scopes = {"base": {"path": ".", "include_patterns": ["**/*"], "exclude_patterns": []}}
    write_scopes_to_file(scopes_file_path, default_scopes)
    console.print(f"✅ Successfully created '{scopes_file_path}'.", style="green")

def handle_scope_management(args, scopes, scopes_file_path, parser):
    """Handles all commands related to managing scopes."""
    if args.list_scopes:
        console.print(f"Available scopes in '[bold]{scopes_file_path}[/]':", style="bold")
        if not scopes:
            console.print(f"  -> No scopes found.")
        else:
            for scope_name in sorted(scopes.keys()):
                console.print(f"  - {scope_name}")

    elif args.show_scope:
        scope_data = scopes.get(args.show_scope)
        if scope_data:
            console.print(Panel(pprint.pformat(scope_data, indent=2), title=f"[bold cyan]Scope: '{args.show_scope}'[/]"))
        else:
            console.print(f"❌ Scope '[bold]{args.show_scope}[/]' not found.", style="red")

    elif args.add_scope:
        if args.add_scope in scopes:
            console.print(f"❌ Scope '[bold]{args.add_scope}[/]' already exists.", style="red")
            return
        scopes[args.add_scope] = {"path": ".", "include_patterns": ["**/*"], "exclude_patterns": []}
        write_scopes_to_file(scopes_file_path, scopes)
        console.print(f"✅ Scope '[bold]{args.add_scope}[/]' added.", style="green")


    elif args.remove_scope:
        if args.remove_scope not in scopes:
            console.print(f"❌ Scope '[bold]{args.remove_scope}[/]' not found.", style="red")
            return
        del scopes[args.remove_scope]
        write_scopes_to_file(scopes_file_path, scopes)
        console.print(f"✅ Scope '[bold]{args.remove_scope}[/]' removed.", style="green")

    elif args.update_scope:
        if len(args.update_scope) < 2:
            parser.error("--update-scope requires a scope name and at least one 'key=value' pair.")
        scope_name = args.update_scope[0]
        updates = args.update_scope[1:]
        if scope_name not in scopes:
            console.print(f"❌ Scope '[bold]{scope_name}[/]' not found.", style="red")
            return
        try:
            for update in updates:
                key, value_str = update.split('=', 1)
                value = ast.literal_eval(value_str)
                scopes[scope_name][key.strip()] = value
            write_scopes_to_file(scopes_file_path, scopes)
        except (ValueError, SyntaxError) as e:
            console.print(f"❌ Error parsing update values: {e}", style="red")

def handle_file_io(args):
    """Handles commands that read from files or clipboard to apply patches."""
    content_to_patch = None
    if args.from_clipboard:
        try:
            import pyperclip
            content_to_patch = pyperclip.paste()
            if not content_to_patch:
                console.print("⚠️ Clipboard is empty.", style="yellow")
                return
        except ImportError:
            console.print("❌ 'pyperclip' is required. `pip install pyperclip`", style="red")
            return
    elif args.from_file:
        try:
            content_to_patch = Path(args.from_file).read_text(encoding="utf-8")
        except Exception as e:
            console.print(f"❌ Failed to read from file {args.from_file}: {e}", style="red")
            return

    if content_to_patch:
        base_path = Path(".").resolve()
        apply_external_patch(content_to_patch, base_path)

def handle_main_task_flow(args, scopes, recipes, parser):
    """Handles the primary workflow of building context and querying the LLM."""
    system_prompt = get_system_prompt()
    history = [{"role": "system", "content": system_prompt}]
    
    task = args.task
    if args.recipe:
        if args.task:
            console.print(f"⚠️ Both --task and --recipe provided. Using explicit --task.", style="yellow")
        else:
            task = recipes.get(args.recipe)
            if not task:
                parser.error(f"Recipe '{args.recipe}' not found in recipes file.")

    context = None
    if args.context_in:
        context = Path(args.context_in).read_text()
    else:
        context_object = _collect_context(args, scopes)
        context = context_object.get("context") if context_object else None
        if context is None and not args.guidelines:
             if any([args.scope, args.interactive]):
                 return
             if task:
                 parser.error("A scope (-s), interactive (-in), or context-in (-ci) is required for a task or recipe.")

    if args.guidelines:
        guidelines_content = system_prompt if args.guidelines is True else args.guidelines
        context = f"{guidelines_content}\n\n{context}" if context else guidelines_content

    if args.context_out and context:
        Path(args.context_out).write_text(context)

    if task:
        action_flags = [args.patch, args.to_file is not None, args.to_clipboard]
        if sum(action_flags) > 1:
            parser.error("Please specify only one action: --patch, --to-file, or --to-clipboard.")
        if sum(action_flags) == 0:
            parser.error("A task or recipe was provided, but no action was specified (e.g., --patch).")

        if not context:
            console.print("Proceeding with task but without any file context.", style="yellow")

        llm_response = run_llm_query(task, args.model, history, context)
        
        if llm_response:
            if args.patch:
                paste_response(llm_response)
            elif args.to_file is not None:
                Path(args.to_file).write_text(llm_response)
            elif args.to_clipboard:
                try:
                    import pyperclip
                    pyperclip.copy(llm_response)
                    console.print("✅ Copied to clipboard.", style="green")
                except ImportError:
                    console.print("❌ 'pyperclip' is required. `pip install pyperclip`", style="red")

def handle_voice_flow(args, scopes, parser):
    """Handles the voice-activated workflow."""
    try:
        from ..voice.listener import listen, speak
    except ImportError:
        console.print("❌ Voice dependencies are not installed.", style="red")
        console.print("   Install with: pip install 'patchllm[voice]'", style="cyan")
        return

    speak("Say your task instruction.")
    task = listen()
    if not task:
        speak("No instruction heard. Exiting.")
        return
    
    speak(f"You said: {task}. Should I proceed?")
    confirm = listen()
    if confirm and "yes" in confirm.lower():
        context_object = _collect_context(args, scopes)
        context = context_object.get("context") if context_object else None
        if context is None:
            speak("Context building failed. Exiting.")
            return

        system_prompt = get_system_prompt()
        history = [{"role": "system", "content": system_prompt}]
        
        llm_response = run_llm_query(task, args.model, history, context)
        if llm_response:
            paste_response(llm_response)
            speak("Changes applied.")
    else:
        speak("Cancelled.")

def handle_chat_flow(args, scopes, recipes):
    """Handles the interactive chat workflow."""
    try:
        from ..chat.chat import ChatSession
        session = ChatSession(args, scopes, recipes)
        session.start()
    except ImportError:
        console.print("❌ 'InquirerPy' is required for chat mode.", style="red")
        console.print("   Install it with: pip install 'patchllm[interactive]'", style="cyan")
    except KeyboardInterrupt:
        console.print("\n👋 Chat session ended by user.", style="bold yellow")
    except Exception as e:
        console.print(f"❌ An unexpected error occurred in chat mode: {e}", style="red")

# --- START OF WIZARD FUNCTIONS ---

def _wizard_main_menu():
    """The new goal-oriented main menu for the interactive wizard."""
    try:
        question = {
            "type": "list", "name": "action",
            "message": "What would you like to do?",
            "choices": [
                {"name": "Start a new task (guided mode)", "value": "new_task"},
                {"name": "Apply a patch from file/clipboard", "value": "apply_patch"},
                {"name": "Manage scopes", "value": "manage_scopes"},
                {"name": "Exit", "value": "exit"},
            ], "border": True, "cycle": False,
        }
        result = prompt([question])
        return result.get("action") if result else None
    except (InvalidArgument, IndexError, KeyError, TypeError):
        return "exit"

def _wizard_manage_scopes(args, scopes, scopes_file_path, parser):
    """Interactive sub-menu for managing scopes within the wizard."""
    while True:
        try:
            # Create a fresh, temporary args object for each action to avoid state pollution.
            action_args = argparse.Namespace(list_scopes=False, show_scope=None, add_scope=None, remove_scope=None, update_scope=None)

            question = {
                "type": "list", "name": "action", "message": "Scope Management",
                "choices": ["List scopes", "Show a scope", "Add a scope", "Remove a scope", {"name": "Back to main menu", "value": "back"}],
                "border": True,
            }
            result = prompt([question])
            action = result.get("action") if result else "back"

            if action == "back" or action is None:
                return

            if action == "List scopes":
                action_args.list_scopes = True
            elif action == "Show a scope":
                if not scopes:
                    console.print("⚠️ No scopes found to show.", style="yellow")
                    console.input("\n[grey50]Press Enter to continue...[/grey50]")
                    continue
                scope_q = {"type": "fuzzy", "name": "scope", "message": "Which scope to show?", "choices": sorted(scopes.keys())}
                scope_r = prompt([scope_q])
                if scope_r and scope_r.get("scope"):
                    action_args.show_scope = scope_r.get("scope")
                else:
                    continue
            elif action == "Add a scope":
                scope_q = {"type": "input", "name": "scope", "message": "Name for the new scope:", "validate": EmptyInputValidator()}
                scope_r = prompt([scope_q])
                if scope_r and scope_r.get("scope"):
                     action_args.add_scope = scope_r.get("scope")
                else:
                    continue
            elif action == "Remove a scope":
                if not scopes:
                    console.print("⚠️ No scopes found to remove.", style="yellow")
                    console.input("\n[grey50]Press Enter to continue...[/grey50]")
                    continue
                scope_q = {"type": "fuzzy", "name": "scope", "message": "Which scope to remove?", "choices": sorted(scopes.keys())}
                scope_r = prompt([scope_q])
                if scope_r and scope_r.get("scope"):
                    action_args.remove_scope = scope_r.get("scope")
                else:
                    continue

            handle_scope_management(action_args, scopes, scopes_file_path, parser)
            console.input("\n[grey50]Press Enter to continue...[/grey50]")

        except (InvalidArgument, IndexError, KeyError, TypeError):
            return

def _wizard_select_context_source(args, scopes):
    """Step 1: Asks the user how they want to build the context."""
    try:
        question = {
            "type": "list", "name": "source",
            "message": "How would you like to build the context?",
            "choices": [
                {"name": "Select from a list of saved scopes", "value": "saved"},
                {"name": "Use a dynamic scope (e.g., @git:staged, @search)", "value": "dynamic"},
                {"name": "Interactively select files/folders", "value": "interactive"},
                {"name": "Import from a context file", "value": "file"},
            ], "border": True,
        }
        result = prompt([question])
        source = result.get("source") if result else None
        if not source: return None

        if source == "saved":
            if not scopes:
                console.print("⚠️ No scopes found in 'scopes.py'.", style="yellow")
                return None
            scope_question = {"type": "fuzzy", "name": "scope", "message": "Select a scope:", "choices": sorted(scopes.keys())}
            scope_result = prompt([scope_question])
            scope_name = scope_result.get("scope") if scope_result else None
            if not scope_name: return None
            args.scope = scope_name
            return _collect_context(args, scopes)
            
        elif source == "dynamic":
            dynamic_choices = [
                {"name": "@git:staged - Files staged for commit", "value": "@git:staged"},
                {"name": "@git:unstaged - Files with uncommitted changes", "value": "@git:unstaged"},
                {"name": "@git:lastcommit - Files from the last commit", "value": "@git:lastcommit"},
                {"name": "@git:conflicts - Files with merge conflicts", "value": "@git:conflicts"},
                {"name": "@git:branch - Files changed in current branch vs. a base branch", "value": "git_branch"},
                {"name": "@recent - Recently modified files", "value": "@recent"},
                {"name": "@structure - High-level project structure overview", "value": "@structure"},
                {"name": "@dir - All files within a specific directory", "value": "dir"},
                {"name": "@related - Find files related to a specific file", "value": "related"},
                {"name": "@search - Find files containing a keyword", "value": "search"},
            ]
            scope_question = {"type": "list", "name": "scope_type", "message": "Select a dynamic scope type:", "choices": dynamic_choices, "border": True}
            scope_result = prompt([scope_question])
            scope_type = scope_result.get("scope_type") if scope_result else None
            
            if not scope_type: return None

            scope_name = None
            if scope_type in ["@git:staged", "@git:unstaged", "@git:lastcommit", "@git:conflicts", "@recent", "@structure"]:
                scope_name = scope_type
            elif scope_type == "git_branch":
                branch_q = {"type": "input", "name": "branch", "message": "Enter base branch to compare against (e.g., main, develop):", "default": "main"}
                branch_r = prompt([branch_q])
                base_branch = branch_r.get("branch") if branch_r else "main"
                scope_name = f"@git:branch:{base_branch}"
            elif scope_type == "dir":
                dir_q = {"type": "input", "name": "dir", "message": "Enter directory path relative to project root:", "validate": EmptyInputValidator()}
                dir_r = prompt([dir_q])
                dir_path = dir_r.get("dir") if dir_r else None
                if not dir_path: return None
                scope_name = f"@dir:{dir_path}"
            elif scope_type == "related":
                file_q = {"type": "input", "name": "file", "message": "Enter file path to find related files for:", "validate": EmptyInputValidator()}
                file_r = prompt([file_q])
                file_path = file_r.get("file") if file_r else None
                if not file_path: return None
                scope_name = f"@related:{file_path}"
            elif scope_type == "search":
                search_q = {"type": "input", "name": "term", "message": "Enter keyword to search for:", "validate": EmptyInputValidator()}
                search_r = prompt([search_q])
                search_term = search_r.get("term") if search_r else None
                if not search_term: return None
                scope_name = f'@search:"{search_term}"'

            if not scope_name: return None
            args.scope = scope_name
            return _collect_context(args, scopes)

        elif source == "interactive":
            args.interactive = True
            return _collect_context(args, scopes)
            
        elif source == "file":
            file_question = {"type": "input", "name": "file", "message": "Enter path to context file:"}
            file_result = prompt([file_question])
            file_path = file_result.get("file") if file_result else None
            if not file_path or not Path(file_path).exists():
                console.print("❌ File not found.", style="red")
                return None
            context = Path(file_path).read_text()
            return {"context": context, "files": []}

    except (InvalidArgument, IndexError, KeyError, TypeError):
        return None

def _wizard_refine_context(initial_files, base_path):
    """Step 2: Allows the user to add or remove files from the context."""
    current_files = set(initial_files)
    
    while True:
        if not current_files:
            console.print("Context is empty. Add some files.", style="yellow")
            action = "Add files"
        else:
            console.print(Panel(
                "\n".join(sorted(f"- {p.relative_to(base_path)}" for p in current_files)),
                title=f"[bold cyan]Current Context ({len(current_files)} files)[/bold cyan]"
            ))
            question = {"type": "list", "name": "action", "message": "Refine the context or proceed?", "choices": ["Proceed", "Add files", "Remove files", "Cancel"], "border": True}
            result = prompt([question])
            action = result.get("action") if result else None

        if action == "Proceed":
            return sorted(list(current_files))
        if action is None or action == "Cancel":
            return None
        elif action == "Add files":
            from ..interactive.selector import select_files_interactively
            new_files = select_files_interactively(base_path)
            current_files.update(new_files)
        elif action == "Remove files":
            remove_question = {
                "type": "checkbox", "name": "removed", "message": "Select files to remove:",
                "choices": sorted([f.relative_to(base_path).as_posix() for f in current_files]),
                "transformer": lambda res: f"{len(res)} file(s) selected to remove",
            }
            result = prompt([remove_question])
            files_to_remove = result.get("removed") if result else []
            if files_to_remove is not None:
                current_files = {f for f in current_files if f.relative_to(base_path).as_posix() not in files_to_remove}

def _wizard_start_new_task_flow(args, scopes, recipes, scopes_file_path):
    """The wizard flow for building context and running a task, with added actions."""
    base_path = Path(".").resolve()
    context_object = _wizard_select_context_source(args, scopes)
    if not context_object or not context_object.get("context"):
        console.print("Context building cancelled or failed.", style="yellow")
        return

    initial_files = context_object.get("files", [])
    final_files = initial_files
    if initial_files:
         final_files = _wizard_refine_context(initial_files, base_path)
         if final_files is None:
             console.print("Cancelled during context refinement.", style="yellow")
             return
    
    final_context_str = helpers._format_context(final_files, [], base_path)['context']

    while True:
        action_question = {
            "type": "list", "name": "action",
            "message": "What would you like to do with the final context?",
            "choices": [
                "Update code with LLM",
                "Save context to file",
                "Copy context to clipboard",
                "Save this context as a new scope",
                {"name": "Back to main menu", "value": "back"},
            ], "border": True,
        }
        result = prompt([action_question])
        action = result.get("action") if result else "back"

        if action == "Save context to file":
            path_question = {"type": "input", "name": "path", "message": "Enter filename:", "default": "context.md"}
            path_result = prompt([path_question])
            out_path = path_result.get("path") if path_result else None
            if not out_path: continue
            Path(out_path).write_text(final_context_str)
            console.print(f"✅ Context saved to '{out_path}'.", style="green")
        
        elif action == "Copy context to clipboard":
            try:
                import pyperclip
                pyperclip.copy(final_context_str)
                console.print("✅ Context copied to clipboard.", style="green")
            except ImportError:
                console.print("❌ 'pyperclip' is required. `pip install pyperclip`", style="red")
        
        elif action == "Save this context as a new scope":
            name_q = {"type": "input", "name": "name", "message": "Enter name for the new scope:"}
            name_r = prompt([name_q])
            scope_name = name_r.get("name") if name_r else None
            
            if not scope_name:
                console.print("⚠️ Scope name cannot be empty.", style="yellow")
                continue
            if scope_name in scopes:
                console.print(f"❌ Scope '[bold]{scope_name}[/]' already exists.", style="red")
                continue
            
            relative_paths = [f.relative_to(base_path).as_posix() for f in final_files]
            new_scope = {"path": ".", "include_patterns": relative_paths, "exclude_patterns": []}
            scopes[scope_name] = new_scope
            write_scopes_to_file(scopes_file_path, scopes)
            console.print(f"✅ Scope '[bold]{scope_name}[/]' saved to '{scopes_file_path}'.", style="green")

        elif action == "Update code with LLM":
            from ..chat.chat import ChatSession
            session = ChatSession(args, scopes, recipes)
            session.context = final_context_str
            session.run_llm_interaction_loop(task_prompt_method=session._prompt_for_task_or_recipe)
            break
        
        else: # Back to main menu or None
            break

def _wizard_apply_patch_flow():
    """Handles the wizard flow for applying an external patch."""
    try:
        source_question = {
            "type": "list", "name": "source",
            "message": "Where is the patch content located?",
            "choices": [
                {"name": "Clipboard", "value": "clipboard"},
                {"name": "File", "value": "file"},
                {"name": "Back to main menu", "value": "back"},
            ], "border": True,
        }
        result = prompt([source_question])
        source = result.get("source") if result else "back"

        content_to_patch = None
        if source == "clipboard":
            try:
                import pyperclip
                content_to_patch = pyperclip.paste()
                if not content_to_patch or not content_to_patch.strip():
                    console.print("⚠️ Clipboard is empty or contains only whitespace.", style="yellow")
                    return
            except ImportError:
                console.print("❌ 'pyperclip' is required for this action. `pip install pyperclip`", style="red")
                return
        elif source == "file":
            path_question = {"type": "input", "name": "path", "message": "Enter the path to the patch file:"}
            path_result = prompt([path_question])
            path_str = path_result.get("path") if path_result else None
            if not path_str:
                console.print("Cancelled.", style="yellow")
                return
            try:
                content_to_patch = Path(path_str).read_text(encoding="utf-8")
            except FileNotFoundError:
                 console.print(f"❌ File not found at '{path_str}'.", style="red")
                 return
            except Exception as e:
                console.print(f"❌ Failed to read file: {e}", style="red")
                return
        else: # back or None
            return

        if content_to_patch:
            base_path = Path(".").resolve()
            apply_external_patch(content_to_patch, base_path)

    except (InvalidArgument, IndexError, KeyError, TypeError):
        return # Go back to main menu

def handle_interactive_wizard_flow(args, scopes, recipes, scopes_file_path, parser):
    """Orchestrates a guided, interactive session when `patchllm` is run with no flags."""
    console.print("🤖 Welcome to the PatchLLM Interactive Wizard!", style="bold blue")
    
    try:
        while True:
            choice = _wizard_main_menu()
            if choice == "new_task":
                _wizard_start_new_task_flow(args, scopes, recipes, scopes_file_path)
            elif choice == "apply_patch":
                _wizard_apply_patch_flow()
            elif choice == "manage_scopes":
                _wizard_manage_scopes(args, scopes, scopes_file_path, parser)
            elif choice == "exit" or choice is None:
                break
        
        console.print("\n👋 Exiting PatchLLM Wizard. Goodbye!", style="bold yellow")

    except (KeyboardInterrupt, InvalidArgument, IndexError, KeyError, TypeError):
        console.print("\n👋 Wizard session ended by user.", style="bold yellow")
    except Exception as e:
        console.print(f"❌ An unexpected error occurred: {e}", style="red")
