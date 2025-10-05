from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.markup import escape
from pathlib import Path
import argparse

from ..agent.session import AgentSession
from ..agent import actions
from ..interactive.selector import select_files_interactively
from ..patcher import apply_external_patch
from ..cli.handlers import handle_scope_management
from ..utils import write_scopes_to_file

def _print_help():
    """Prints the help message with available commands."""
    help_text = Text()
    help_text.append("PatchLLM Agent Commands\n\n", style="bold")
    
    help_text.append("Agent Workflow:\n", style="bold cyan")
    help_text.append("  /task <goal>\n", style="bold")
    help_text.append("    ↳ Sets the high-level goal for the agent.\n")
    help_text.append("  /plan\n", style="bold")
    help_text.append("    ↳ Generates a step-by-step plan to achieve the goal.\n")
    help_text.append("  /run\n", style="bold")
    help_text.append("    ↳ Executes the current step and shows a diff.\n")
    help_text.append("  /approve\n", style="bold")
    help_text.append("    ↳ Applies the changes from the last diff.\n")
    help_text.append("  /retry <feedback>\n", style="bold")
    help_text.append("    ↳ Retries the last step with new feedback.\n\n")

    help_text.append("Context Management:\n", style="bold cyan")
    help_text.append("  /context <scope>\n", style="bold")
    help_text.append("    ↳ Replaces context with a saved or dynamic scope.\n")
    help_text.append("  /add_context <scope>\n", style="bold")
    help_text.append("    ↳ Adds files from a scope to the current context.\n")
    help_text.append("  /add_context --interactive\n", style="bold")
    help_text.append("    ↳ Use a fuzzy finder to add files/folders to context.\n")
    help_text.append("  /clear_context\n", style="bold")
    help_text.append("    ↳ Empties the context.\n")
    help_text.append("  /scopes\n", style="bold")
    help_text.append("    ↳ Enter the interactive scope management menu.\n\n")

    help_text.append("Utilities:\n", style="bold cyan")
    help_text.append("  /patch --clipboard\n", style="bold")
    help_text.append("    ↳ Apply a patch from the system clipboard.\n")
    help_text.append("  /test\n", style="bold")
    help_text.append("    ↳ Run pytest to check for regressions.\n")
    help_text.append("  /stage\n", style="bold")
    help_text.append("    ↳ Stage all current changes with git.\n\n")
    
    help_text.append("General:\n", style="bold cyan")
    help_text.append("  /help\n", style="bold")
    help_text.append("    ↳ Shows this help message.\n")
    help_text.append("  /exit\n", style="bold")
    help_text.append("    ↳ Exits the agent session.\n")
    return Panel(help_text, title="Help", border_style="green")


def _display_execution_result(result, console):
    """Helper function to display diffs from an execution result."""
    if result and result.get("diffs"):
        for diff in result["diffs"]:
            panel_title = f"Diff: {Path(diff['file_path']).name}"
            console.print(Panel(diff["diff_text"], title=panel_title, border_style="yellow"))
    elif result:
        console.print("✅ Step finished, but no file changes were detected.", style="yellow")
    else:
        console.print(f"❌ Step failed.", style="red")

def _run_scope_management_tui(scopes, scopes_file_path, console):
    """A sub-TUI for managing scopes."""
    try:
        from InquirerPy import prompt
        from InquirerPy.validator import EmptyInputValidator
    except ImportError:
        console.print("❌ 'InquirerPy' is required for scope management.", style="red")
        console.print("   Install it with: pip install 'patchllm[interactive]'", style="cyan")
        return

    console.print("\n--- Scope Management ---", style="bold yellow")
    console.print("Type `back` or use Ctrl+C to return to the main agent.", style="dim")

    while True:
        try:
            action_q = {
                "type": "list", "name": "action", "message": "Select an action:",
                "choices": ["List scopes", "Show a scope", "Add a scope", "Remove a scope", "Back"],
                "border": True,
            }
            result = prompt([action_q])
            action = result.get("action") if result else "Back"

            if action == "Back":
                break

            action_args = argparse.Namespace(list_scopes=False, show_scope=None, add_scope=None, remove_scope=None, update_scope=None)
            
            if action == "List scopes":
                action_args.list_scopes = True
            elif action == "Show a scope":
                scope_q = {"type": "fuzzy", "name": "scope", "message": "Which scope to show?", "choices": sorted(scopes.keys())}
                scope_r = prompt([scope_q])
                if scope_r: action_args.show_scope = scope_r.get("scope")
            elif action == "Add a scope":
                scope_q = {"type": "input", "name": "scope", "message": "Name for the new scope:", "validate": EmptyInputValidator()}
                scope_r = prompt([scope_q])
                if scope_r: action_args.add_scope = scope_r.get("scope")
            elif action == "Remove a scope":
                scope_q = {"type": "fuzzy", "name": "scope", "message": "Which scope to remove?", "choices": sorted(scopes.keys())}
                scope_r = prompt([scope_q])
                if scope_r: action_args.remove_scope = scope_r.get("scope")
            
            handle_scope_management(action_args, scopes, scopes_file_path, None)

        except (KeyboardInterrupt, TypeError):
            break
    console.print("\n--- Exiting Scope Management ---", style="bold yellow")


def run_tui(args, scopes, recipes, scopes_file_path):
    console = Console()
    session = AgentSession(args, scopes, recipes)
    console.print("🤖 Welcome to the PatchLLM Agent. Type `/help` for commands or `/exit` to quit.", style="bold blue")

    try:
        while True:
            text = console.input("[bold]>>> [/bold]").strip()
            if not text: continue
            
            command_parts = text.split()
            command = command_parts[0].lower()
            
            if command == '/exit': break
            elif command == '/help': console.print(_print_help())
            elif command == '/task':
                session.set_goal(" ".join(command_parts[1:]))
                console.print(f"✅ Goal set: \"{escape(session.goal)}\"", style="green")
            elif command == '/plan':
                if not session.goal: console.print("❌ No goal set. Use `/task` first.", style="red"); continue
                with console.status("[cyan]Generating plan..."): success = session.create_plan()
                if success:
                    plan_text = "\n".join(f"{i+1}. {step}" for i, step in enumerate(session.plan))
                    console.print(Panel(plan_text, title="Execution Plan", border_style="magenta"))
                else: console.print("❌ Failed to generate a plan.", style="red")
            
            elif command == '/run':
                if not session.plan: console.print("❌ No plan. Use `/plan` first.", style="red"); continue
                if session.current_step >= len(session.plan): console.print("✅ Plan complete.", style="green"); continue
                step_num, instruction = session.current_step + 1, session.plan[session.current_step]
                console.print(f"\n--- Executing Step {step_num}/{len(session.plan)} ---", style="bold yellow")
                console.print(f"[dim]{instruction}[/dim]")
                with console.status("[cyan]Agent is working..."): result = session.run_current_step()
                _display_execution_result(result, console)
                if result: console.print(f"✅ Step {step_num} previewed. Run `/approve` or `/retry <feedback>`.", style="green")

            elif command == '/approve':
                if not session.last_execution_result: console.print("❌ No changes to approve. Use `/run` first.", style="red"); continue
                with console.status("[cyan]Applying changes..."): success = session.approve_changes()
                if success: console.print("✅ Changes applied successfully.", style="green")
                else: console.print("❌ Failed to apply changes.", style="red")

            elif command == '/retry':
                if not session.last_execution_result: console.print("❌ Nothing to retry. Use `/run` first.", style="red"); continue
                feedback = " ".join(command_parts[1:])
                if not feedback: console.print("❌ Please provide feedback after `/retry`.", style="red"); continue
                console.print(f"\n--- Retrying Step {session.current_step + 1} with feedback ---", style="bold yellow")
                with console.status("[cyan]Agent is working..."): result = session.retry_step(feedback)
                _display_execution_result(result, console)
                if result: console.print("✅ Retry finished. You can now `/approve` these new changes.", style="green")
            
            elif command == '/context':
                with console.status("[cyan]Building context..."): summary = session.load_context_from_scope(" ".join(command_parts[1:]))
                console.print(Panel(summary, title="Context Summary", border_style="cyan", expand=False))
            elif command == '/add_context':
                scope_name = " ".join(command_parts[1:])
                if scope_name == '--interactive':
                    new_files = select_files_interactively(Path(".").resolve())
                    if new_files:
                        with console.status("[cyan]Updating context..."): summary = session.add_files_and_rebuild_context(new_files)
                        console.print(Panel(summary, title="Context Summary", border_style="cyan", expand=False))
                    else: console.print("No files selected.", style="yellow")
                else:
                    with console.status("[cyan]Updating context..."): summary = session.add_context_from_scope(scope_name)
                    console.print(Panel(summary, title="Context Summary", border_style="cyan", expand=False))
            
            elif command == '/clear_context':
                session.clear_context(); console.print("✅ Context cleared.", style="green")
            elif command == '/scopes':
                _run_scope_management_tui(session.scopes, scopes_file_path, console)
                # Ensure changes are reflected in the current session
                write_scopes_to_file(scopes_file_path, session.scopes)
            
            elif command == '/test': actions.run_tests()
            elif command == '/stage': actions.stage_files()
            elif command == '/patch':
                if len(command_parts) > 1 and command_parts[1] == '--clipboard':
                    try:
                        import pyperclip
                        content = pyperclip.paste()
                        if content: apply_external_patch(content, Path(".").resolve())
                        else: console.print("⚠️ Clipboard is empty.", style="yellow")
                    except ImportError: console.print("❌ 'pyperclip' is required. `pip install pyperclip`", style="red")
                else: console.print("Unknown `/patch` command. Did you mean `/patch --clipboard`?", style="yellow")
            else:
                console.print(f"Unknown command: '{text}'. Type `/help` for a list of commands.", style="yellow")
    except KeyboardInterrupt: console.print()
    except Exception as e: console.print(f"An unexpected error occurred: {e}", style="bold red")
    console.print("\n👋 Exiting agent session. Goodbye!", style="yellow")