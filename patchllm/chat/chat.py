import textwrap
from pathlib import Path
from rich.console import Console
from InquirerPy import prompt
from InquirerPy.validator import EmptyInputValidator
from InquirerPy.exceptions import InvalidArgument

from ..cli.handlers import get_system_prompt, _collect_context
from ..llm import run_llm_query
from ..parser import paste_response, summarize_changes, display_diff

console = Console()

class ChatSession:
    def __init__(self, args, scopes):
        self.args = args
        self.scopes = scopes
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
            return prompt(question, vi_mode=True)[0]
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
            return prompt(question, vi_mode=True)[0]
        except (InvalidArgument, IndexError, KeyError):
            return None # User cancelled

    def _confirm_proceed(self):
        try:
            return prompt({
                "type": "confirm",
                "message": "Proceed to query the LLM?",
                "default": True
            })[0]
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
            return prompt(question, vi_mode=True)[0]
        except (InvalidArgument, IndexError, KeyError):
            return "cancel" # User cancelled

    def start(self):
        console.print("🤖 Welcome to PatchLLM Chat Mode!", style="bold blue")
        
        scope_name = self._prompt_for_scope()
        if not scope_name: return
        self.args.scope = scope_name

        self.context = _collect_context(self.args, self.scopes)
        if self.context is None: return

        while True:
            task = self._prompt_for_task()
            if not task: break

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
                else: # This now correctly handles the "cancel" case
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