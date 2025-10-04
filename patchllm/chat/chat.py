import textwrap
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from InquirerPy import prompt
from InquirerPy.validator import EmptyInputValidator
from InquirerPy.exceptions import InvalidArgument

from ..llm import run_llm_query
from ..parser import paste_response, summarize_changes, get_diff_for_file, paste_response_selectively
from ..cli.handlers import get_system_prompt, _collect_context

console = Console()

class ChatSession:
    def __init__(self, args, scopes, recipes):
        self.args = args
        self.scopes = scopes
        self.recipes = recipes
        self.history = [{"role": "system", "content": get_system_prompt()}]
        self.context = None

    def _prompt_for_scope(self):
        if not self.scopes:
            console.print("⚠️ No scopes found. Please create a 'scopes.py' file first with 'patchllm --init'.", style="yellow")
            return None
        
        choices = sorted(self.scopes.keys())
        try:
            question = {"type": "fuzzy", "name": "scope", "message": "Which scope would you like to work with?", "choices": choices, "validate": EmptyInputValidator(), "border": True}
            result = prompt([question], vi_mode=True)
            return result.get("scope")
        except (InvalidArgument, IndexError, KeyError):
            return None

    def _prompt_for_task(self, default: str = ""):
        """Prompts for a task, allowing a default value to be pre-filled for editing."""
        try:
            question = {
                "type": "input", 
                "name": "task", 
                "message": "What is your task?", 
                "long_instruction": "You can press Enter to open your default editor for a longer message.", 
                "multiline": True, 
                "validate": EmptyInputValidator(), 
                "border": True,
                "default": default
            }
            result = prompt([question], vi_mode=True)
            return result.get("task")
        except (InvalidArgument, IndexError, KeyError):
            return None
    
    def _prompt_for_feedback(self):
        """Asks the user for feedback on the previous LLM response."""
        try:
            question = {
                "type": "input",
                "name": "feedback",
                "message": "What was wrong with the last response? (Optional, press Enter to skip)",
                "long_instruction": "Provide feedback to guide the next attempt.",
                "multiline": True,
                "border": True,
            }
            result = prompt([question], vi_mode=True)
            return result.get("feedback") if result else None
        except (InvalidArgument, IndexError, KeyError):
            return None

    def _prompt_for_task_or_recipe(self):
        """Allows user to select a recipe or enter a manual task."""
        if not self.recipes:
            return self._prompt_for_task()

        try:
            choices = [{"name": f"[Recipe] {name}", "value": ("recipe", name)} for name in self.recipes.keys()]
            choices.append({"name": "[Manual] Enter a new task instruction", "value": ("manual", None)})
            
            question = {"type": "list", "name": "choice", "message": "How would you like to define the task?", "choices": choices, "border": True}
            result = prompt([question], vi_mode=True)
            if not result: return None
            task_type, value = result.get("choice")

            if task_type == "recipe":
                return self.recipes.get(value)
            return self._prompt_for_task()
            
        except (InvalidArgument, IndexError, KeyError, TypeError):
            return None

    def _confirm_proceed(self):
        try:
            question = {"type": "confirm", "name": "confirm", "message": "Proceed to query the LLM?", "default": True}
            result = prompt([question])
            return result.get("confirm", False)
        except (InvalidArgument, IndexError, KeyError):
            return False

    def _prompt_for_action(self, summary):
        num_modified = len(summary.get("modified", []))
        num_created = len(summary.get("created", []))
        
        console.print("\n✅ LLM response received.", style="bold green")
        console.print(f"   The model wants to:")
        if num_modified > 0:
            console.print(f"   - Modify {num_modified} file(s)")
        if num_created > 0:
            console.print(f"   - Create {num_created} new file(s)")

        try:
            question = {"type": "list", "name": "action", "message": "What would you like to do?", "choices": [
                {"name": "[A]pply all changes", "value": "apply"},
                {"name": "[I]nteractively apply changes", "value": "interactive_apply"},
                {"name": "[D]isplay diff (Interactive)", "value": "diff"},
                {"name": "[S]ave response to file", "value": "save"},
                {"name": "[R]efine task & retry", "value": "retry"},
                {"name": "[C]ancel", "value": "cancel"},
            ], "border": True}
            result = prompt([question], vi_mode=True)
            return result.get("action")
        except (InvalidArgument, IndexError, KeyError):
            return "cancel"

    def _prompt_for_files_to_apply(self, summary) -> list[str] | None:
        """Shows a checkbox prompt for the user to select which files to apply changes to."""
        all_files = sorted(summary.get("modified", []) + summary.get("created", []))
        if not all_files:
            console.print("No file changes were proposed by the LLM.", style="yellow")
            return []

        try:
            question = {
                "type": "checkbox",
                "name": "selected_files",
                "message": "Select which files to apply changes to:",
                "choices": [{"name": Path(f).as_posix(), "value": f, "enabled": True} for f in all_files],
                "transformer": lambda res: f"{len(res)} file(s) selected",
                "border": True,
                "cycle": False,
            }
            result = prompt([question], vi_mode=True)
            return result.get("selected_files") if result else None
        except (InvalidArgument, IndexError, KeyError):
            return None

    def _interactive_diff_viewer(self, llm_response: str):
        """Creates a toggleable accordion-style menu to view diffs for each file."""
        summary = summarize_changes(llm_response)
        all_files = summary.get("modified", []) + summary.get("created", [])
        
        if not all_files:
            console.print("No file changes detected in the response.", style="yellow")
            return
            
        choices = [Path(f).as_posix() for f in all_files]
        choices.append({"name": "--- [Done Reviewing] ---", "value": "done"})

        while True:
            question = {"type": "fuzzy", "name": "file", "message": "Select a file to view its diff (or select Done):", "choices": choices, "border": True}
            result = prompt([question], vi_mode=True)
            selected_file = result.get("file") if result else "done"

            if selected_file == "done":
                break
                
            console.print(f"\n--- Displaying diff for [bold]{selected_file}[/bold] ---")
            diff_text = get_diff_for_file(selected_file, llm_response)
            console.print(Panel(diff_text, title=f"[bold cyan]Diff: {Path(selected_file).name}[/bold cyan]", border_style="yellow", expand=True))
            console.input("\n[grey50]Press Enter to continue...[/grey50]")

    def _select_and_build_context(self):
        """Handles the initial scope selection and context building for the original chat flow."""
        scope_name = self._prompt_for_scope()
        if not scope_name: 
            return None
        self.args.scope = scope_name
        context_object = _collect_context(self.args, self.scopes)
        return context_object.get("context") if context_object else None

    def run_llm_interaction_loop(self, task_prompt_method=None):
        """The core loop for getting a task, querying the LLM, and handling the response."""
        if self.context is None:
            console.print("Cannot start LLM interaction without a context.", style="red")
            return

        task_prompt_method = task_prompt_method or self._prompt_for_task
        task = ""

        while True:
            if not task: # Only ask for a new task if the current one has been completed or cancelled
                task = task_prompt_method()
                if not task:
                    console.print("Cancelled.", style="yellow")
                    break

            if not self._confirm_proceed():
                console.print("Cancelled.", style="yellow")
                task = "" # Reset task so we ask for a new one
                continue

            llm_response = run_llm_query(task, self.args.model, self.history, self.context)

            if not llm_response:
                console.print("The LLM returned an empty response. Please try again.", style="yellow")
                continue

            summary = summarize_changes(llm_response)
            action = self._prompt_for_action(summary)

            if action == "apply":
                paste_response(llm_response)
                break
            elif action == "interactive_apply":
                files_to_apply = self._prompt_for_files_to_apply(summary)
                if files_to_apply is not None:
                    paste_response_selectively(llm_response, files_to_apply)
                else:
                    console.print("Cancelled.", style="yellow")
                break
            elif action == "diff":
                self._interactive_diff_viewer(llm_response)
                nested_action = self._prompt_for_action(summary)
                if nested_action == "apply":
                    paste_response(llm_response)
                elif nested_action == "interactive_apply":
                    files_to_apply = self._prompt_for_files_to_apply(summary)
                    if files_to_apply is not None:
                         paste_response_selectively(llm_response, files_to_apply)
                    else:
                         console.print("Cancelled.", style="yellow")
                elif nested_action != "retry":
                    console.print("Cancelled.", style="yellow")
                if nested_action == "retry":
                     # This will trigger the retry logic below
                     action = "retry"
                else:
                    break # Exit after applying or cancelling
            
            if action == "save":
                Path("response.md").write_text(llm_response)
                console.print("✅ Response saved to 'response.md'.", style="green")
                break

            if action == "retry":
                # Remove the last user prompt and the failed assistant response from history
                if len(self.history) >= 2:
                    self.history.pop() # Assistant response
                    self.history.pop() # User prompt

                console.print("\n--- Refining Task ---", style="bold yellow")
                feedback = self._prompt_for_feedback()
                refined_task = self._prompt_for_task(default=task)

                if not refined_task:
                    console.print("Cancelled.", style="yellow")
                    break
                
                task = refined_task
                if feedback and feedback.strip():
                    task = f"Feedback on previous attempt: {feedback}\n\n---\n\nMy refined task is:\n{refined_task}"
                
                continue # Loop back to query the LLM with the new task
            
            # If action is 'cancel' or another exit condition
            console.print("Cancelled.", style="yellow")
            break

    def start(self):
        """The original entry point for the `--chat` flag."""
        console.print("🤖 Welcome to PatchLLM Chat Mode!", style="bold blue")
        
        self.context = self._select_and_build_context()
        if self.context is None:
            return

        self.run_llm_interaction_loop()