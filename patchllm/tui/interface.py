from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.markup import escape
from rich.json import JSON
from pathlib import Path
import argparse
import json
import os
import re
import pprint

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.completion import FuzzyCompleter
from litellm import model_list

from .completer import PatchLLMCompleter
from ..agent.session import AgentSession
from ..agent import actions
from ..interactive.selector import select_files_interactively
from ..patcher import apply_external_patch
from ..cli.handlers import handle_scope_management
from ..scopes.builder import helpers
from ..utils import write_scopes_to_file

SESSION_FILE_PATH = Path(".patchllm_session.json")

def _print_help():
    help_text = Text()
    help_text.append("PatchLLM Agent Commands\n\n", style="bold")
    help_text.append("Agent Workflow:\n", style="bold cyan")
    help_text.append("  /task <goal>", style="bold"); help_text.append("\n    ↳ Sets the high-level goal.\n")
    help_text.append("  /plan", style="bold"); help_text.append("\n    ↳ Generates a plan or opens interactive management if a plan exists.\n")
    help_text.append("  /ask <question>", style="bold"); help_text.append("\n    ↳ Ask a question about the current plan.\n")
    help_text.append("  /refine <feedback>", style="bold"); help_text.append("\n    ↳ Refine the plan with new feedback/ideas.\n")
    help_text.append("  /plan --edit <N> <text>", style="bold"); help_text.append("\n    ↳ Edits step N of the plan.\n")
    help_text.append("  /plan --rm <N>", style="bold"); help_text.append("\n    ↳ Removes step N from the plan.\n")
    help_text.append("  /plan --add <text>", style="bold"); help_text.append("\n    ↳ Adds a new step to the end of the plan.\n")
    help_text.append("  /run", style="bold"); help_text.append("\n    ↳ Executes all remaining steps as a single task.\n")
    help_text.append("  /run next", style="bold"); help_text.append("\n    ↳ Executes only the next step in the plan.\n")
    help_text.append("  /skip", style="bold"); help_text.append("\n    ↳ Skips the current step.\n")
    help_text.append("  /diff [all|filename]", style="bold"); help_text.append("\n    ↳ Shows the full diff for a file or all files.\n")
    help_text.append("  /approve", style="bold"); help_text.append("\n    ↳ Interactively select and apply changes from the last run.\n")
    help_text.append("  /retry <feedback>", style="bold"); help_text.append("\n    ↳ Retries the last step with new feedback.\n")
    help_text.append("  /revert", style="bold"); help_text.append("\n    ↳ Reverts the changes from the last /approve.\n\n")
    help_text.append("Context Management:\n", style="bold cyan")
    help_text.append("  /context <scope>\n", style="bold"); help_text.append("    ↳ Sets the context using a scope (e.g., @git:staged).\n")
    help_text.append("  /scopes\n", style="bold"); help_text.append("        ↳ Opens an interactive menu to create and manage scopes.\n\n")
    help_text.append("Menu & Session:\n", style="bold cyan")
    help_text.append("  /show [goal|plan|context|history|step]\n", style="bold"); help_text.append(" ↳ Shows session state.\n")
    help_text.append("  /settings\n", style="bold"); help_text.append("      ↳ Configure the model and API keys.\n")
    help_text.append("  /help\n", style="bold"); help_text.append("          ↳ Shows this help message.\n")
    help_text.append("  /exit\n", style="bold"); help_text.append("          ↳ Exits the agent session.\n")
    return Panel(help_text, title="Help", border_style="green")

def _display_execution_summary(result, console):
    if not result or not result.get("summary"):
        console.print("❌ Step failed to produce a result.", style="red"); return
    summary = result["summary"]
    modified = summary.get("modified", [])
    created = summary.get("created", [])
    if not modified and not created:
        console.print("✅ Step finished, but no file changes were detected.", style="yellow"); return
    summary_text = Text()
    if modified:
        summary_text.append("Modified:\n", style="bold yellow")
        for f in modified: summary_text.append(f"  - {f}\n")
    if created:
        summary_text.append("Created:\n", style="bold green")
        for f in created: summary_text.append(f"  - {f}\n")
    console.print(Panel(summary_text, title="Proposed Changes", border_style="cyan"))

def _save_session(session: AgentSession):
    with open(SESSION_FILE_PATH, 'w') as f: json.dump(session.to_dict(), f, indent=2)

def _clear_session():
    if SESSION_FILE_PATH.exists(): os.remove(SESSION_FILE_PATH)

def _run_settings_tui(session: AgentSession, console: Console):
    """A sub-TUI for managing agent settings."""
    try:
        from InquirerPy import prompt
        from InquirerPy.exceptions import InvalidArgument
        from InquirerPy.validator import EmptyInputValidator
    except ImportError:
        console.print("❌ 'InquirerPy' is required. `pip install 'patchllm[interactive]'`", style="red"); return

    console.print("\n--- Agent Settings ---", style="bold yellow")
    while True:
        try:
            current_model = session.args.model
            api_keys_count = len(session.api_keys)
            action_q = {
                "type": "list", 
                "name": "action", 
                "message": "Select a setting to configure:", 
                "choices": [
                    f"Change Model (current: {current_model})", 
                    f"Manage API Keys ({api_keys_count} saved)",
                    "Back to agent"
                ], 
                "border": True, "cycle": False
            }
            result = prompt([action_q])
            action = result.get("action") if result else "Back to agent"
            
            if action == "Back to agent": break

            if action.startswith("Change Model"):
                model_q = {
                    "type": "fuzzy", 
                    "name": "model", 
                    "message": "Fuzzy search for a model:",
                    "choices": model_list,
                    "default": current_model
                }
                model_r = prompt([model_q])
                new_model = model_r.get("model") if model_r else None
                if new_model:
                    session.args.model = new_model
                    session.save_settings()
                    console.print(f"✅ Default model set to '[bold]{new_model}[/bold]'. This will be saved.", style="green")

            elif action.startswith("Manage API Keys"):
                while True:
                    saved_keys = list(session.api_keys.keys())
                    key_choices = ["Add/Update a saved API Key"]
                    if saved_keys:
                        key_choices.append("Remove a saved API Key")
                    key_choices.append("Back")
                    
                    key_action_q = {"type": "list", "name": "key_action", "message": "Manage your saved API keys", "choices": key_choices}
                    key_action_r = prompt([key_action_q])
                    key_action = key_action_r.get("key_action") if key_action_r else "Back"

                    if key_action == "Back": break

                    if key_action.startswith("Add/Update"):
                        env_var_q = {"type": "input", "name": "env_var", "message": "Enter the environment variable name (e.g., OPENAI_API_KEY):", "validate": EmptyInputValidator()}
                        env_var_r = prompt([env_var_q])
                        env_var_name = env_var_r.get("env_var") if env_var_r else None
                        if not env_var_name: continue

                        key_q = {"type": "password", "name": "key", "message": f"Enter the value for {env_var_name}:"}
                        key_r = prompt([key_q])
                        api_key = key_r.get("key") if key_r else None
                        if api_key:
                            session.set_api_key(env_var_name, api_key)
                            console.print(f"✅ Key '{env_var_name}' has been saved and applied to the current session.", style="green")

                    elif key_action.startswith("Remove"):
                        remove_q = {"type": "checkbox", "name": "keys", "message": "Select keys to remove:", "choices": saved_keys}
                        remove_r = prompt([remove_q])
                        keys_to_remove = remove_r.get("keys") if remove_r else []
                        if keys_to_remove:
                            for key in keys_to_remove:
                                session.remove_api_key(key)
                            console.print(f"✅ Removed {len(keys_to_remove)} key(s).", style="green")

        except (KeyboardInterrupt, InvalidArgument, IndexError, KeyError, TypeError): break
    console.print("\n--- Returning to Agent ---", style="bold yellow")

def _edit_string_list_interactive(current_list: list[str], item_name: str, console: Console) -> list[str] | None:
    """Helper TUI to add/remove items from a simple list of strings."""
    try:
        from InquirerPy import prompt
        from InquirerPy.validator import EmptyInputValidator
    except ImportError: return None

    edited_list = current_list[:]
    while True:
        console.print(Panel(f"[bold]Current {item_name}s:[/]\n" + "\n".join(f"- {i}" for i in edited_list) if edited_list else "  (empty)", expand=False))
        action_q = {"type": "list", "name": "action", "message": f"Manage {item_name}s", "choices": [f"Add a {item_name}", f"Remove a {item_name}", "Done"], "border": True}
        action_r = prompt([action_q])
        action = action_r.get("action") if action_r else "Done"

        if action == "Done": return edited_list
        if action == f"Add a {item_name}":
            item_q = {"type": "input", "name": "item", "message": "Enter new item:", "validate": EmptyInputValidator()}
            item_r = prompt([item_q])
            new_item = item_r.get("item") if item_r else None
            if new_item: edited_list.append(new_item)
        elif action == f"Remove a {item_name}":
            if not edited_list: console.print(f"No {item_name}s to remove.", style="yellow"); continue
            remove_q = {"type": "checkbox", "name": "items", "message": "Select items to remove", "choices": edited_list}
            remove_r = prompt([remove_q])
            to_remove = remove_r.get("items", []) if remove_r else []
            edited_list = [item for item in edited_list if item not in to_remove]

def _edit_patterns_interactive(current_list: list[str], pattern_type: str, console: Console) -> list[str] | None:
    """Helper TUI to add/remove glob patterns, with an option for interactive selection."""
    try:
        from InquirerPy import prompt
        from InquirerPy.validator import EmptyInputValidator
    except ImportError: return None

    edited_list = current_list[:]
    while True:
        console.print(Panel(f"[bold]Current {pattern_type} Patterns:[/]\n" + "\n".join(f"- {i}" for i in edited_list) if edited_list else "  (empty)", expand=False))
        choices = ["Add pattern manually", "Remove a pattern", "Add from interactive selector", "Done"]
        action_q = {"type": "list", "name": "action", "message": "Manage patterns", "choices": choices, "border": True}
        action_r = prompt([action_q])
        action = action_r.get("action") if action_r else "Done"

        if action == "Done": return edited_list
        elif action == "Add pattern manually":
            item_q = {"type": "input", "name": "item", "message": "Enter glob pattern (e.g., 'src/**/*.py'):", "validate": EmptyInputValidator()}
            item_r = prompt([item_q])
            new_item = item_r.get("item") if item_r else None
            if new_item: edited_list.append(new_item)
        elif action == "Remove a pattern":
            if not edited_list: console.print("No patterns to remove.", style="yellow"); continue
            remove_q = {"type": "checkbox", "name": "items", "message": "Select patterns to remove", "choices": edited_list}
            remove_r = prompt([remove_q])
            to_remove = remove_r.get("items", []) if remove_r else []
            edited_list = [item for item in edited_list if item not in to_remove]
        elif action == "Add from interactive selector":
            base_path = Path(".").resolve()
            selected_files = select_files_interactively(base_path)
            if selected_files:
                new_patterns = [p.relative_to(base_path).as_posix() for p in selected_files]
                edited_list.extend(new_patterns)
                console.print(f"✅ Added {len(new_patterns)} file/folder pattern(s).", style="green")

def _interactive_scope_editor(console: Console, existing_scope: dict | None = None) -> dict | None:
    """A TUI for creating or editing a single scope dictionary."""
    try:
        from InquirerPy import prompt
    except ImportError:
        console.print("❌ 'InquirerPy' is required. `pip install 'patchllm[interactive]'`", style="red"); return None

    if existing_scope:
        scope_data = existing_scope.copy()
    else: # Default for a new scope
        scope_data = {"path": ".", "include_patterns": ["**/*"], "exclude_patterns": [], "search_words": [], "urls": [], "exclude_extensions": []}

    while True:
        console.print(Panel(JSON(json.dumps(scope_data)), title="Current Scope Configuration", border_style="blue"))
        
        choices = [
            f"Edit base path",
            f"Manage include patterns ({len(scope_data.get('include_patterns', []))})",
            f"Manage exclude patterns ({len(scope_data.get('exclude_patterns', []))})",
            f"Manage search keywords ({len(scope_data.get('search_words', []))})",
            f"Manage URLs ({len(scope_data.get('urls', []))})",
            f"Manage excluded extensions ({len(scope_data.get('exclude_extensions', []))})",
            "Save and Return",
            "Cancel and Discard"
        ]
        action_q = {"type": "list", "name": "action", "message": "Select field to edit", "choices": choices, "border": True}
        action_r = prompt([action_q])
        action = action_r.get("action") if action_r else "Cancel and Discard"

        if action == "Save and Return": return scope_data
        if action == "Cancel and Discard": return None
        
        if action.startswith("Edit base path"):
            path_q = {"type": "input", "name": "path", "message": "Enter new base path:", "default": scope_data.get('path', '.')}
            path_r = prompt([path_q])
            if path_r and path_r.get("path") is not None: scope_data['path'] = path_r.get("path")
        elif action.startswith("Manage include patterns"):
            new_list = _edit_patterns_interactive(scope_data.get('include_patterns', []), "Include", console)
            if new_list is not None: scope_data['include_patterns'] = new_list
        elif action.startswith("Manage exclude patterns"):
            new_list = _edit_patterns_interactive(scope_data.get('exclude_patterns', []), "Exclude", console)
            if new_list is not None: scope_data['exclude_patterns'] = new_list
        elif action.startswith("Manage search keywords"):
            new_list = _edit_string_list_interactive(scope_data.get('search_words', []), "keyword", console)
            if new_list is not None: scope_data['search_words'] = new_list
        elif action.startswith("Manage URLs"):
            new_list = _edit_string_list_interactive(scope_data.get('urls', []), "URL", console)
            if new_list is not None: scope_data['urls'] = new_list
        elif action.startswith("Manage excluded extensions"):
            new_list = _edit_string_list_interactive(scope_data.get('exclude_extensions', []), "extension", console)
            if new_list is not None: scope_data['exclude_extensions'] = new_list

def _run_scope_management_tui(scopes, scopes_file_path, console):
    """A sub-TUI for managing scopes, reusing the core handler logic."""
    try:
        from InquirerPy import prompt
        from InquirerPy.validator import EmptyInputValidator
        from InquirerPy.exceptions import InvalidArgument
    except ImportError:
        console.print("❌ 'InquirerPy' is required. `pip install 'patchllm[interactive]'`", style="red"); return

    console.print("\n--- Scope Management ---", style="bold yellow")
    while True:
        try:
            choices = ["List scopes", "Show a scope", "Add a new scope", "Update a scope", "Remove a scope", "Back to agent"]
            action_q = {"type": "list", "name": "action", "message": "Select an action:", "choices": choices, "border": True, "cycle": False}
            result = prompt([action_q])
            action = result.get("action") if result else "Back to agent"
            if action == "Back to agent": break

            if action == "List scopes":
                handle_scope_management(argparse.Namespace(list_scopes=True), scopes, scopes_file_path, None)
            
            elif action == "Show a scope":
                if not scopes: console.print("No scopes to show.", style="yellow"); continue
                scope_q = {"type": "fuzzy", "name": "scope", "message": "Which scope to show?", "choices": sorted(scopes.keys())}
                scope_r = prompt([scope_q])
                if scope_r and scope_r.get("scope"):
                    handle_scope_management(argparse.Namespace(show_scope=scope_r.get("scope")), scopes, scopes_file_path, None)
            
            elif action == "Remove a scope":
                if not scopes: console.print("No scopes to remove.", style="yellow"); continue
                scope_q = {"type": "fuzzy", "name": "scope", "message": "Which scope to remove?", "choices": sorted(scopes.keys())}
                scope_r = prompt([scope_q])
                if scope_r and scope_r.get("scope"):
                    handle_scope_management(argparse.Namespace(remove_scope=scope_r.get("scope")), scopes, scopes_file_path, None)
            
            elif action == "Add a new scope":
                name_q = {"type": "input", "name": "name", "message": "Enter name for the new scope:", "validate": EmptyInputValidator()}
                name_r = prompt([name_q])
                scope_name = name_r.get("name") if name_r else None
                if not scope_name: continue
                if scope_name in scopes: console.print(f"❌ Scope '{scope_name}' already exists.", style="red"); continue
                
                new_scope_data = _interactive_scope_editor(console, existing_scope=None)
                if new_scope_data:
                    scopes[scope_name] = new_scope_data
                    write_scopes_to_file(scopes_file_path, scopes)
                    console.print(f"✅ Scope '{scope_name}' created.", style="green")

            elif action == "Update a scope":
                if not scopes: console.print("No scopes to update.", style="yellow"); continue
                scope_q = {"type": "fuzzy", "name": "scope", "message": "Which scope to update?", "choices": sorted(scopes.keys())}
                scope_r = prompt([scope_q])
                scope_name = scope_r.get("scope") if scope_r else None
                if not scope_name: continue
                
                updated_scope_data = _interactive_scope_editor(console, existing_scope=scopes[scope_name])
                if updated_scope_data:
                    scopes[scope_name] = updated_scope_data
                    write_scopes_to_file(scopes_file_path, scopes)
                    console.print(f"✅ Scope '{scope_name}' updated.", style="green")

        except (KeyboardInterrupt, InvalidArgument, IndexError, KeyError, TypeError): break
    console.print("\n--- Returning to Agent ---", style="bold yellow")

def _run_plan_management_tui(session: AgentSession, console: Console):
    """A sub-TUI for interactively managing the execution plan."""
    try:
        from InquirerPy import prompt
        from InquirerPy.validator import EmptyInputValidator
        from InquirerPy.exceptions import InvalidArgument
    except ImportError:
        console.print("❌ 'InquirerPy' is required. `pip install 'patchllm[interactive]'`", style="red"); return

    console.print("\n--- Interactive Plan Management ---", style="bold yellow")
    while True:
        try:
            if not session.plan:
                console.print("The plan is now empty.", style="yellow")
                break

            choices = [f"{i+1}. {step}" for i, step in enumerate(session.plan)]
            
            action_q = {
                "type": "list", "name": "action", "message": "Select a step to manage or an action:",
                "choices": choices + ["Add a new step", "Reorder steps", "Done"],
                "border": True, "cycle": False,
                "long_instruction": "Use arrow keys. Select a step to Edit/Remove it."
            }
            result = prompt([action_q])
            action_choice = result.get("action") if result else "Done"

            if action_choice == "Done": break
            
            if action_choice == "Add a new step":
                add_q = {"type": "input", "name": "text", "message": "Enter the new step instruction:", "validate": EmptyInputValidator()}
                add_r = prompt([add_q])
                if add_r and add_r.get("text"):
                    session.add_plan_step(add_r.get("text"))
                    console.print("✅ Step added to the end of the plan.", style="green")

            elif action_choice == "Reorder steps":
                if len(session.plan) < 2:
                    console.print("⚠️ Not enough steps to reorder.", style="yellow"); continue
                
                reorder_choices = [f"{i+1}. {step}" for i, step in enumerate(session.plan)]
                
                from_q = {
                    "type": "list", "name": "from", "message": "Select the step to move:",
                    "choices": reorder_choices, "cycle": False
                }
                from_r = prompt([from_q])
                if not from_r or not from_r.get("from"): continue
                from_index = int(from_r.get("from").split('.')[0]) - 1

                to_choices = [f"Move to position {i+1}" for i in range(len(session.plan))]
                to_q = {
                    "type": "list", "name": "to", "message": f"Where should '{session.plan[from_index]}' move?",
                    "choices": to_choices, "cycle": False
                }
                to_r = prompt([to_q])
                if not to_r or not to_r.get("to"): continue
                to_index = int(re.search(r'\d+', to_r.get("to")).group()) - 1
                
                item_to_move = session.plan.pop(from_index)
                session.plan.insert(to_index, item_to_move)
                console.print(f"✅ Step moved from position {from_index + 1} to {to_index + 1}.", style="green")

            else:
                step_index = int(action_choice.split('.')[0]) - 1
                step_text = session.plan[step_index]

                edit_or_rm_q = {
                    "type": "list", "name": "sub_action", "message": f"Step {step_index + 1}: {step_text}",
                    "choices": ["Edit", "Remove", "Cancel"]
                }
                edit_or_rm_r = prompt([edit_or_rm_q])
                sub_action = edit_or_rm_r.get("sub_action") if edit_or_rm_r else "Cancel"

                if sub_action == "Edit":
                    edit_q = {"type": "input", "name": "text", "message": "Enter the new instruction:", "default": step_text, "validate": EmptyInputValidator()}
                    edit_r = prompt([edit_q])
                    if edit_r and edit_r.get("text"):
                        session.edit_plan_step(step_index + 1, edit_r.get("text"))
                        console.print(f"✅ Step {step_index + 1} updated.", style="green")
                
                elif sub_action == "Remove":
                    session.remove_plan_step(step_index + 1)
                    console.print(f"✅ Step {step_index + 1} removed.", style="green")
        
        except (KeyboardInterrupt, InvalidArgument, IndexError, KeyError, TypeError): break

    _save_session(session)
    console.print("\n--- Returning to Agent ---", style="bold yellow")

def run_tui(args, scopes, recipes, scopes_file_path):
    console = Console()
    session = AgentSession(args, scopes, recipes)

    if SESSION_FILE_PATH.exists():
        if console.input("Found saved session. [bold]Resume?[/bold] (Y/n) ").lower() in ['y', 'yes', '']:
            try:
                with open(SESSION_FILE_PATH, 'r') as f: session.from_dict(json.load(f))
                console.print("✅ Session resumed.", style="green")
            except Exception as e: console.print(f"⚠️ Could not resume session: {e}", style="yellow"); _clear_session()
        else: _clear_session()

    completer = PatchLLMCompleter(scopes=session.scopes)
    prompt_session = PromptSession(history=FileHistory(Path("~/.patchllm_history").expanduser()))

    console.print("🤖 Welcome to the PatchLLM Agent. Type `/` and [TAB] for commands. `/exit` to quit.", style="bold blue")

    try:
        while True:
            completer.set_session_state(
                has_goal=bool(session.goal),
                has_plan=bool(session.plan),
                has_pending_changes=bool(session.last_execution_result),
                can_revert=bool(session.last_revert_state)
            )
            
            text = prompt_session.prompt(">>> ", completer=FuzzyCompleter(completer)).strip()
            if not text: continue
            
            command, _, arg_string = text.partition(' ')
            command = command.lower()
            
            if command == '/exit': _clear_session(); break
            elif command == '/help': console.print(_print_help())
            elif command == '/task':
                session.set_goal(arg_string); console.print("✅ Goal set.", style="green"); _save_session(session)
            
            elif command == '/ask':
                if not session.plan: console.print("❌ No plan to ask about. Generate one with `/plan` first.", style="red"); continue
                if not arg_string: console.print("❌ Please provide a question.", style="red"); continue
                with console.status("[cyan]Asking assistant..."): response = session.ask_about_plan(arg_string)
                if response:
                    console.print(Panel(response, title="Assistant's Answer", border_style="blue"))
                else: console.print("❌ Failed to get a response.", style="red")

            elif command == '/refine':
                if not session.plan: console.print("❌ No plan to refine. Generate one with `/plan` first.", style="red"); continue
                if not arg_string: console.print("❌ Please provide feedback or an idea.", style="red"); continue
                with console.status("[cyan]Refining plan..."): success = session.refine_plan(arg_string)
                if success:
                    console.print(Panel("\n".join(f"{i+1}. {s}" for i, s in enumerate(session.plan)), title="Refined Execution Plan", border_style="magenta"))
                    _save_session(session)
                else: console.print("❌ Failed to refine the plan.", style="red")

            elif command == '/plan':
                if not arg_string:
                    if not session.goal and not session.plan:
                        console.print("❌ No goal set. Set one with `/task <your goal>`.", style="red"); continue
                    
                    if session.plan:
                        _run_plan_management_tui(session, console)
                        if session.plan:
                            console.print(Panel("\n".join(f"{i+1}. {s}" for i, s in enumerate(session.plan)), title="Current Execution Plan", border_style="magenta"))
                        continue

                    with console.status("[cyan]Generating plan..."): success = session.create_plan()
                    if success:
                        console.print(Panel("\n".join(f"{i+1}. {s}" for i, s in enumerate(session.plan)), title="Execution Plan", border_style="magenta")); _save_session(session)
                    else: console.print("❌ Failed to generate a plan.", style="red")
                else:
                    if not session.plan:
                        console.print("❌ No plan to manage. Generate one with `/plan` first.", style="red"); continue
                    
                    edit_match = re.match(r"--edit\s+(\d+)\s+(.*)", arg_string, re.DOTALL)
                    rm_match = re.match(r"--rm\s+(\d+)", arg_string)
                    add_match = re.match(r"--add\s+(.*)", arg_string, re.DOTALL)

                    if edit_match:
                        step_num, new_text = int(edit_match.group(1)), edit_match.group(2)
                        if session.edit_plan_step(step_num, new_text):
                            console.print(f"✅ Step {step_num} updated.", style="green"); _save_session(session)
                        else: console.print(f"❌ Invalid step number: {step_num}.", style="red")
                    elif rm_match:
                        step_num = int(rm_match.group(1))
                        if session.remove_plan_step(step_num):
                            console.print(f"✅ Step {step_num} removed.", style="green"); _save_session(session)
                        else: console.print(f"❌ Invalid step number: {step_num}.", style="red")
                    elif add_match:
                        new_text = add_match.group(1)
                        session.add_plan_step(new_text)
                        console.print("✅ New step added to the end of the plan.", style="green"); _save_session(session)
                    else:
                        console.print(f"❌ Unknown argument for /plan: '{arg_string}'. Use --edit, --rm, or --add.", style="red")

                    console.print(Panel("\n".join(f"{i+1}. {s}" for i, s in enumerate(session.plan)), title="Updated Execution Plan", border_style="magenta"))
            
            elif command == '/run':
                if not session.plan: console.print("❌ No plan.", style="red"); continue
                if session.current_step >= len(session.plan): console.print("✅ Plan complete.", style="green"); continue
                
                if arg_string == 'next':
                    console.print(f"\n--- Executing Step {session.current_step + 1}/{len(session.plan)} ---", style="bold yellow")
                    with console.status("[cyan]Agent is working..."): result = session.run_next_step()
                else:
                    remaining_count = len(session.plan) - session.current_step
                    console.print(f"\n--- Executing all {remaining_count} remaining steps ---", style="bold yellow")
                    with console.status("[cyan]Agent is working..."): result = session.run_all_remaining_steps()

                _display_execution_summary(result, console)
                if result: console.print("✅ Preview ready. Use `/diff` to review.", style="green")

            elif command == '/skip':
                if not session.plan: console.print("❌ No plan to skip from.", style="red"); continue
                if session.skip_step():
                    console.print(f"✅ Step {session.current_step} skipped. Now at step {session.current_step + 1}.", style="green")
                    _save_session(session)
                else:
                    console.print("✅ Plan already complete. Nothing to skip.", style="green")

            elif command == '/diff':
                if not session.last_execution_result or not session.last_execution_result.get("diffs"): console.print("❌ No diff to display.", style="red"); continue
                diffs = session.last_execution_result["diffs"]
                if arg_string and arg_string != 'all': diffs = [d for d in diffs if Path(d['file_path']).name == arg_string]
                for diff in diffs: console.print(Panel(diff["diff_text"], title=f"Diff: {Path(diff['file_path']).name}", border_style="yellow"))

            elif command == '/approve':
                if not session.last_execution_result: console.print("❌ No changes to approve.", style="red"); continue
                
                try:
                    from InquirerPy import prompt
                    summary = session.last_execution_result.get("summary", {})
                    all_files = summary.get("modified", []) + summary.get("created", [])
                    
                    if not all_files:
                        console.print("✅ No file changes were proposed to approve.", style="yellow")
                        session.last_execution_result = None
                        continue

                    approve_q = {
                        "type": "checkbox", "name": "files", "message": "Select the changes you wish to apply:",
                        "choices": all_files, "validate": lambda r: len(r) > 0,
                        "invalid_message": "You must select at least one file to apply.",
                        "transformer": lambda r: f"{len(r)} file(s) selected."
                    }
                    result = prompt([approve_q])
                    files_to_approve = result.get("files") if result else []

                    if not files_to_approve:
                        console.print("Approval cancelled.", style="yellow"); continue

                    with console.status("[cyan]Applying..."):
                        is_full_approval = session.approve_changes(files_to_approve)
                    
                    if is_full_approval:
                        console.print("✅ All changes applied. Moving to the next step.", style="green")
                    else:
                        console.print("✅ Partial changes applied.", style="green")
                        console.print("👉 Use `/retry <feedback>` to fix the remaining files, or `/skip` to move on.", style="cyan")
                    
                    _save_session(session)

                except (KeyboardInterrupt, ImportError):
                    console.print("Approval cancelled.", style="yellow")

            elif command == '/retry':
                if not session.plan or session.current_step >= len(session.plan):
                    console.print("❌ Nothing to retry.", style="red"); continue
                if not arg_string: console.print("❌ Please provide feedback for the retry.", style="red"); continue
                console.print(f"\n--- Retrying Step {session.current_step + 1} ---", style="bold yellow")
                with console.status("[cyan]Agent is working..."): result = session.retry_step(arg_string)
                _display_execution_summary(result, console)

            elif command == '/revert':
                if not session.last_revert_state: console.print("❌ No approved changes to revert.", style="red"); continue
                with console.status("[cyan]Reverting changes..."): success = session.revert_last_approval()
                if success:
                    console.print("✅ Last approved changes have been reverted.", style="green"); _save_session(session)
                else: console.print("❌ Failed to revert changes.", style="red")

            elif command == '/show':
                if arg_string == 'goal':
                    if not session.goal: console.print("No goal set.", style="yellow")
                    else: console.print(Panel(escape(session.goal), title="Current Goal", border_style="blue"))
                elif arg_string == 'plan':
                    if not session.plan: console.print("No plan exists.", style="yellow")
                    else: console.print(Panel("\n".join(f"{i+1}. {s}" for i, s in enumerate(session.plan)), title="Execution Plan", border_style="magenta"))
                elif arg_string == 'step':
                    if not session.plan:
                        console.print("No plan exists.", style="yellow")
                    elif session.current_step >= len(session.plan):
                        console.print("✅ Plan is complete.", style="green")
                    else:
                        step_text = Text()
                        step_text.append(f"Current Step ({session.current_step + 1}/{len(session.plan)}):\n", style="bold green")
                        step_text.append(f"  -> {escape(session.plan[session.current_step])}\n")
                        if session.current_step + 1 < len(session.plan):
                            step_text.append(f"\nNext Step ({session.current_step + 2}/{len(session.plan)}):\n", style="bold blue")
                            step_text.append(f"  -> {escape(session.plan[session.current_step + 1])}")
                        console.print(Panel(step_text, title="Current Step", border_style="magenta"))
                elif arg_string == 'context':
                    if not session.context_files: console.print("Context is empty.", style="yellow")
                    else:
                        tree = helpers.generate_source_tree(Path(".").resolve(), session.context_files)
                        console.print(Panel(tree, title="Context Tree", border_style="cyan"))
                elif arg_string == 'history':
                    if not session.action_history: console.print("No actions recorded yet.", style="yellow")
                    else:
                        history_text = Text()
                        for i, entry in enumerate(session.action_history): history_text.append(f"{i+1}. {escape(entry)}\n")
                        console.print(Panel(history_text, title="Session History", border_style="blue"))
                else:
                    console.print("Usage: /show [goal|plan|context|history|step]", style="yellow")

            elif command == '/context':
                with console.status("[cyan]Building..."): summary = session.load_context_from_scope(arg_string)
                console.print(Panel(summary, title="Context Summary", border_style="cyan")); _save_session(session)
            
            elif command == '/scopes':
                _run_scope_management_tui(session.scopes, scopes_file_path, console)
                session.reload_scopes(scopes_file_path)
            
            elif command == '/settings':
                _run_settings_tui(session, console)
            
            else:
                console.print(f"Unknown command: '{text}'.", style="yellow")
    except (KeyboardInterrupt, EOFError): console.print()
    except Exception as e: console.print(f"An unexpected error occurred: {e}", style="bold red")
    console.print("\n👋 Exiting agent session. Goodbye!", style="yellow")