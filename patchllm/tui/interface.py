from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.markup import escape
from pathlib import Path
import argparse
import json
import os

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.completion import FuzzyCompleter

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
    help_text.append("  /run", style="bold"); help_text.append("\n    ↳ Executes the current step and shows a summary.\n")
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
    help_text.append("  /help\n", style="bold"); help_text.append("          ↳ Shows this help message.\n")
    help_text.append("  /exit\n", style="bold"); help_text.append("          ↳ Exits the agent session.\n")
    return Panel(help_text, title="Help", border_style="green")

def _display_execution_summary(result, console):
    if not result or not result.get("summary"):
        console.print("❌ Step failed to produce a result.", style="red"); return
    summary, modified, created = result["summary"], result["summary"].get("modified", []), result["summary"].get("created", [])
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

def run_tui(args, scopes, recipes, scopes_file_path):
    console = Console()
    session = AgentSession(args, scopes, recipes)

    if SESSION_FILE_PATH.exists():
        resume = console.input(f"Found a saved session. [bold]Resume?[/bold] (Y/n) ").lower()
        if resume in ['y', 'yes', '']:
            try:
                with open(SESSION_FILE_PATH, 'r') as f: session.from_dict(json.load(f))
                console.print("✅ Session resumed.", style="green")
            except Exception as e: console.print(f"⚠️  Could not resume session: {e}", style="yellow"); _clear_session()

    completer = PatchLLMCompleter(commands=["/task", "/plan", "/run", "/approve", "/retry", "/context", "/add_context", "/clear_context", "/scopes", "/patch", "/test", "/stage", "/help", "/exit", "/diff"], scopes=session.scopes)
    prompt_session = PromptSession(history=FileHistory(Path("~/.patchllm_history").expanduser()))

    console.print("🤖 Welcome to the PatchLLM Agent. Type `/` and [TAB] for commands. `/exit` to quit.", style="bold blue")

    try:
        while True:
            text = prompt_session.prompt(">>> ", completer=FuzzyCompleter(completer)).strip()
            if not text: continue
            
            # --- FIX: More robust command and argument parsing ---
            command, _, arg_string = text.partition(' ')
            command = command.lower()
            # --- End FIX ---
            
            if command == '/exit': _clear_session(); break
            elif command == '/help': console.print(_print_help())
            elif command == '/task':
                session.set_goal(arg_string); console.print(f"✅ Goal set.", style="green"); _save_session(session)
            elif command == '/plan':
                if not session.goal: console.print("❌ No goal set.", style="red"); continue
                with console.status("[cyan]Generating plan..."): success = session.create_plan()
                if success:
                    plan_text = "\n".join(f"{i+1}. {step}" for i, step in enumerate(session.plan))
                    console.print(Panel(plan_text, title="Execution Plan", border_style="magenta")); _save_session(session)
                else: console.print("❌ Failed to generate a plan.", style="red")
            
            elif command == '/run':
                if not session.plan: console.print("❌ No plan.", style="red"); continue
                if session.current_step >= len(session.plan): console.print("✅ Plan complete.", style="green"); continue
                console.print(f"\n--- Executing Step {session.current_step + 1}/{len(session.plan)} ---", style="bold yellow")
                with console.status("[cyan]Agent is working..."): result = session.run_current_step()
                _display_execution_summary(result, console)
                if result: console.print(f"✅ Preview ready. Use `/diff` to review.", style="green")

            elif command == '/diff':
                if not session.last_execution_result or not session.last_execution_result.get("diffs"): console.print("❌ No diff to display.", style="red"); continue
                diffs_to_show = session.last_execution_result["diffs"]
                if arg_string and arg_string != 'all':
                    diffs_to_show = [d for d in diffs_to_show if Path(d['file_path']).name == arg_string]
                for diff in diffs_to_show: console.print(Panel(diff["diff_text"], title=f"Diff: {Path(diff['file_path']).name}", border_style="yellow"))

            elif command == '/approve':
                if not session.last_execution_result: console.print("❌ No changes to approve.", style="red"); continue
                with console.status("[cyan]Applying changes..."): success = session.approve_changes()
                if success: console.print("✅ Changes applied.", style="green"); _save_session(session)
                else: console.print("❌ Failed to apply changes.", style="red")
            
            elif command == '/retry':
                if not session.last_execution_result: console.print("❌ Nothing to retry.", style="red"); continue
                if not arg_string: console.print("❌ Please provide feedback.", style="red"); continue
                console.print(f"\n--- Retrying Step {session.current_step + 1} ---", style="bold yellow")
                with console.status("[cyan]Agent is working..."): result = session.retry_step(arg_string)
                _display_execution_summary(result, console)

            elif command == '/context':
                with console.status("[cyan]Building context..."): summary = session.load_context_from_scope(arg_string)
                console.print(Panel(summary, title="Context Summary", border_style="cyan", expand=False)); _save_session(session)
            
            elif command == '/add_context':
                if arg_string == '--interactive':
                    new_files = select_files_interactively(Path(".").resolve())
                    if new_files:
                        with console.status("[cyan]Updating context..."): summary = session.add_files_and_rebuild_context(new_files)
                        console.print(Panel(summary, title="Context Summary", border_style="cyan", expand=False)); _save_session(session)
                else:
                    with console.status("[cyan]Updating context..."): summary = session.add_context_from_scope(arg_string)
                    console.print(Panel(summary, title="Context Summary", border_style="cyan", expand=False)); _save_session(session)
            
            elif command == '/clear_context':
                session.clear_context(); console.print("✅ Context cleared.", style="green"); _save_session(session)
            
            elif command == '/scopes':
                # Reusing your original wizard logic is a great way to be robust
                from .handlers import _wizard_manage_scopes
                _wizard_manage_scopes(args, session.scopes, scopes_file_path, None)
                session.reload_scopes(scopes_file_path)
                completer.all_scopes = sorted(list(session.scopes.keys()) + completer.dynamic_scopes)
            
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