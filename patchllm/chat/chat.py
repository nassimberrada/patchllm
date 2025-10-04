import textwrap
from pathlib import Path
from rich.console import Console
from InquirerPy import prompt
from InquirerPy.validator import EmptyInputValidator
from InquirerPy.exceptions import InvalidArgument

# MODIFICATION: Import 'run_llm_query' from llm module directly
from ..llm import run_llm_query
from ..parser import paste_response, summarize_changes, display_diff
# MODIFICATION: Import helpers from handlers is no longer needed here
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
            question = {
                "type": "fuzzy",
                "message": "Which scope would you like to work with?",
                "choices": choices,
                "validate": EmptyInputValidator(),
                "border": True,
            }
            # --- CORRECTION: InquirerPy returns the value directly, not in a list ---
            return prompt(question, vi_mode=True)
        except (InvalidArgument, IndexError, KeyError):
            return None # User cancelled

    def _prompt_for_task(self):
        try:
            question = {
                "type": "input",
                "message": "What is your task?",
                "long_instruction": "You can press Enter to open your default editor for a longer message.",
                "multiline": True,
                "validate": EmptyInputValidator(),
                "border": True,
            }
            # --- CORRECTION: InquirerPy returns the value directly ---
            return prompt(question, vi_mode=True)
        except (InvalidArgument, IndexError, KeyError):
            return None # User cancelled

    def _prompt_for_task_or_recipe(self):
        """Allows user to select a recipe or enter a manual task."""
        if not self.recipes:
            return self._prompt_for_task()

        try:
            choices = [{"name": f"[Recipe] {name}", "value": ("recipe", name)} for name in self.recipes.keys()]
            choices.append({"name": "[Manual] Enter a new task instruction", "value": ("manual", None)})
            
            question = {
                "type": "list",
                "message": "How would you like to define the task?",
                "choices": choices,
                "border": True,
            }
            task_type, value = prompt(question, vi_mode=True)

            if task_type == "recipe":
                return self.recipes.get(value)
            return self._prompt_for_task()
            
        except (InvalidArgument, IndexError, KeyError):
            return None # User cancelled

    def _confirm_proceed(self):
        try:
            # --- CORRECTION: confirm prompt returns a boolean directly ---
            return prompt({
                "type": "confirm",
                "message": "Proceed to query the LLM?",
                "default": True
            })
        except (InvalidArgument, IndexError, KeyError):
            return False # User cancelled

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
            question = {
                "type": "list",
                "message": "What would you like to do?",
                "choices": [
                    {"name": "[A]pply changes", "value": "apply"},
                    {"name": "[D]isplay diff", "value": "diff"},
                    {"name": "[S]ave response to file", "value": "save"},
                    {"name": "[R]etry with new instructions", "value": "retry"},
                    {"name": "[C]ancel", "value": "cancel"},
                ],
                "border": True,
            }
            # --- CORRECTION: list prompt returns the value directly ---
            return prompt(question, vi_mode=True)
        except (InvalidArgument, IndexError, KeyError):
            return "cancel" # User cancelled

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

        while True:
            task = task_prompt_method()
            if not task:
                console.print("Cancelled.", style="yellow")
                break

            if not self._confirm_proceed():
                console.print("Cancelled.", style="yellow")
                break

            llm_response = run_llm_query(task, self.args.model, self.history, self.context)

            if not llm_response:
                console.print("The LLM returned an empty response. Please try again.", style="yellow")
                continue

            summary = summarize_changes(llm_response)
            action = self._prompt_for_action(summary)

            if action == "apply":
                paste_response(llm_response)
                break
            elif action == "diff":
                display_diff(llm_response)
                # After showing diff, re-ask what to do.
                nested_action = self._prompt_for_action(summary)
                if nested_action == "apply":
                    paste_response(llm_response)
                    break
                elif nested_action == "retry":
                    continue
                else:
                    console.print("Cancelled.", style="yellow")
                    break
            elif action == "save":
                Path("response.md").write_text(llm_response)
                console.print("✅ Response saved to 'response.md'.", style="green")
                break
            elif action == "retry":
                continue
            else: # cancel
                console.print("Cancelled.", style="yellow")
                break

    def start(self):
        """The original entry point for the `--chat` flag."""
        console.print("🤖 Welcome to PatchLLM Chat Mode!", style="bold blue")
        
        self.context = self._select_and_build_context()
        if self.context is None:
            return

        self.run_llm_interaction_loop()