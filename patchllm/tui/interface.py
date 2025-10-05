from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.markup import escape
from pathlib import Path
import argparse
import json
import os
import re

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

SESSION_FILE_PATH = Path(".patchllm_session.json")

def _print_help():
    help_text = Text()
    help_text.append("PatchLLM Agent Commands\n\n", style="bold")
    help_text.append("Agent Workflow:\n", style="bold cyan")
    help_text.append("  /task <goal>", style="bold"); help_text.append("\n    ↳ Sets the high-level goal.\n")
    help_text.append("  /plan", style="bold"); help_text.append("\n    ↳ Generates a plan to achieve the goal.\n")
    help_text.append("  /ask <question>", style="bold"); help_text.append("\n    ↳ Ask a question about the current plan.\n")
    help_text.append("  /refine <feedback>", style="bold"); help_text.append("\n    ↳ Refine the plan with new feedback/ideas.\n")
    help_text.append("  /plan --edit <N> <text>", style="bold"); help_text.append("\n    ↳ Edits step N of the plan.\n")
    help_text.append("  /plan --rm <N>", style="bold"); help_text.append("\n    ↳ Removes step N from the plan.\n")
    help_text.append("  /plan --add <text>", style="bold"); help_text.append("\n    ↳ Adds a new step to the end of the plan.\n")
    help_text.append("  /run", style="bold"); help_text.append("\n    ↳ Executes the current step and shows a summary.\n")
    help_text.append("  /skip", style="bold"); help_text.append("\n    ↳ Skips the current step.\n")
    help_text.append("  /diff [all|filename]", style="bold"); help_text.append("\n    ↳ Shows the full diff for a file or all files.\n")
    help_text.append("  /approve", style="bold"); help_text.append("\n    ↳ Applies the changes from the last run.\n")
    help_text.append("  /retry <feedback>", style="bold"); help_text.append("\n    ↳ Retries the last step with new feedback.\n\n")
    help_text.append("Context Management:\n", style="bold cyan")
    help_text.append("  /context <scope>\n", style="bold"); help_text.append("    ↳ Replaces context with a scope.\n")
    help_text.append("  /add_context <scope>\n", style="bold"); help_text.append("    ↳ Adds files from a scope to context.\n")
    help_text.append("  /add_context --interactive\n", style="bold"); help_text.append("    ↳ Use fuzzy finder to add files.\n")
    help_text.append("  /clear_context\n", style="bold"); help_text.append("    ↳ Empties the context.\n")
    help_text.append("  /scopes\n", style="bold"); help_text.append("        ↳ Enter the scope management menu.\n\n")
    help_text.append("Utilities:\n", style="bold cyan")
    help_text.append("  /patch --clipboard\n", style="bold"); help_text.append("    ↳ Apply a patch from the clipboard.\n")
    help_text.append("  /test\n", style="bold"); help_text.append("          ↳ Run pytest to check for regressions.\n")
    help_text.append("  /stage\n", style="bold"); help_text.append("         ↳ Stage all current changes with git.\n\n")
    help_text.append("General:\n", style="bold cyan")
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
    except ImportError:
        console.print("❌ 'InquirerPy' is required. `pip install 'patchllm[interactive]'`", style="red"); return

    console.print("\n--- Agent Settings ---", style="bold yellow")
    while True:
        try:
            current_model = session.args.model
            action_q = {
                "type": "list", 
                "name": "action", 
                "message": "Select a setting to configure:", 
                "choices": [
                    f"Change Model (current: {current_model})", 
                    "Set API Key (for this session)",
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

            elif action.startswith("Set API Key"):
                service_q = {
                    "type": "list", "name": "service",
                    "message": "Which API key do you want to set?",
                    "choices": ["OPENAI", "GEMINI", "ANTHROPIC", "COHERE", "GROQ", "Custom..."]
                }
                service_r = prompt([service_q])
                service = service_r.get("service") if service_r else None
                if not service: continue

                env_var_name = f"{service.upper()}_API_KEY"
                if service == "Custom...":
                    env_var_q = {"type": "input", "name": "env_var", "message": "Enter the environment variable name (e.g., MISTRAL_API_KEY):"}
                    env_var_r = prompt([env_var_q])
                    env_var_name = env_var_r.get("env_var") if env_var_r else None
                
                if not env_var_name: continue

                key_q = {"type": "password", "name": "key", "message": f"Enter the value for {env_var_name}:"}
                key_r = prompt([key_q])
                api_key = key_r.get("key") if key_r else None

                if api_key:
                    os.environ[env_var_name] = api_key
                    console.print(f"✅ '{env_var_name}' set for the current session.", style="green")
                    console.print("⚠️  This key is not saved and will be forgotten when you exit.", style="yellow")

        except (KeyboardInterrupt, InvalidArgument, IndexError, KeyError, TypeError): break
    console.print("\n--- Returning to Agent ---", style="bold yellow")

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
            action_q = {"type": "list", "name": "action", "message": "Select an action:", "choices": ["List scopes", "Show a scope", "Add a scope", "Remove a scope", "Back to agent"], "border": True, "cycle": False}
            result = prompt([action_q])
            action = result.get("action") if result else "Back to agent"
            if action == "Back to agent": break

            action_args = argparse.Namespace(list_scopes=False, show_scope=None, add_scope=None, remove_scope=None)
            if action == "List scopes": action_args.list_scopes = True
            elif action in ["Show a scope", "Remove a scope"]:
                if not scopes: console.print("No scopes found.", style="yellow"); continue
                scope_q = {"type": "fuzzy", "name": "scope", "message": f"Which scope to {action.lower().split()[0]}?", "choices": sorted(scopes.keys())}
                scope_r = prompt([scope_q])
                if scope_r and scope_r.get("scope"):
                    if action == "Show a scope": action_args.show_scope = scope_r.get("scope")
                    else: action_args.remove_scope = scope_r.get("scope")
                else: continue
            elif action == "Add a scope":
                scope_q = {"type": "input", "name": "scope", "message": "Name for new scope:", "validate": EmptyInputValidator()}
                scope_r = prompt([scope_q])
                if scope_r and scope_r.get("scope"): action_args.add_scope = scope_r.get("scope")
                else: continue
            
            handle_scope_management(action_args, scopes, scopes_file_path, None)

        except (KeyboardInterrupt, InvalidArgument, IndexError, KeyError, TypeError): break
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
            # Update the completer's state before showing the prompt
            completer.set_session_state(
                has_goal=bool(session.goal),
                has_plan=bool(session.plan),
                has_pending_changes=bool(session.last_execution_result)
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
                    if not session.goal: console.print("❌ No goal set.", style="red"); continue
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
                console.print(f"\n--- Executing Step {session.current_step + 1}/{len(session.plan)} ---", style="bold yellow")
                with console.status("[cyan]Agent is working..."): result = session.run_current_step()
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
                with console.status("[cyan]Applying..."): success = session.approve_changes()
                if success: console.print("✅ Changes applied.", style="green"); _save_session(session)
                else: console.print("❌ Failed to apply.", style="red")
            
            elif command == '/retry':
                if not session.last_execution_result: console.print("❌ Nothing to retry.", style="red"); continue
                if not arg_string: console.print("❌ Please provide feedback.", style="red"); continue
                console.print(f"\n--- Retrying Step {session.current_step + 1} ---", style="bold yellow")
                with console.status("[cyan]Agent is working..."): result = session.retry_step(arg_string)
                _display_execution_summary(result, console)

            elif command == '/context':
                with console.status("[cyan]Building..."): summary = session.load_context_from_scope(arg_string)
                console.print(Panel(summary, title="Context Summary", border_style="cyan")); _save_session(session)
            
            elif command == '/add_context':
                if arg_string == '--interactive':
                    new_files = select_files_interactively(Path(".").resolve())
                    if new_files:
                        with console.status("[cyan]Updating..."): summary = session.add_files_and_rebuild_context(new_files)
                        console.print(Panel(summary, title="Context Summary", border_style="cyan")); _save_session(session)
                else:
                    with console.status("[cyan]Updating..."): summary = session.add_context_from_scope(arg_string)
                    console.print(Panel(summary, title="Context Summary", border_style="cyan")); _save_session(session)
            
            elif command == '/clear_context':
                session.clear_context(); console.print("✅ Context cleared.", style="green"); _save_session(session)
            
            elif command == '/scopes':
                _run_scope_management_tui(session.scopes, scopes_file_path, console)
                session.reload_scopes(scopes_file_path)
                # No longer need to update completer scopes here, it's static
            
            elif command == '/settings':
                _run_settings_tui(session, console)

            elif command == '/test': actions.run_tests()
            elif command == '/stage': actions.stage_files()
            
            elif command == '/patch':
                if arg_string == '--clipboard':
                    try:
                        import pyperclip
                        content = pyperclip.paste()
                        if content: apply_external_patch(content, Path(".").resolve())
                        else: console.print("⚠️ Clipboard is empty.", style="yellow")
                    except ImportError: console.print("❌ 'pyperclip' is required.", style="red")
            else:
                console.print(f"Unknown command: '{text}'.", style="yellow")
    except (KeyboardInterrupt, EOFError): console.print()
    except Exception as e: console.print(f"An unexpected error occurred: {e}", style="bold red")
    console.print("\n👋 Exiting agent session. Goodbye!", style="yellow")