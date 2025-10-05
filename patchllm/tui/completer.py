from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

COMMAND_META = {
    # Agent Workflow
    "/task": "Sets the high-level goal for the agent.",
    "/plan": "Generates or manages the execution plan.",
    "/ask": "Ask a clarifying question about the current plan.",
    "/refine": "Refine the plan based on new feedback or ideas.",
    "/run": "Executes the current step and shows a summary of changes.",
    "/skip": "Skips the current step and moves to the next.",
    "/diff": "Shows the full diff for the proposed changes.",
    "/approve": "Applies the changes from the last run.",
    "/retry": "Retries the last step with new feedback.",
    # Context Management
    "/context": "Replaces the context with files from a scope.",
    "/add_context": "Adds files from a scope to the current context.",
    "/clear_context": "Empties the current context.",
    "/scopes": "Opens an interactive menu to manage your saved scopes.",
    # Utilities
    "/patch": "Apply a patch from the system clipboard.",
    "/test": "Runs `pytest` to check for regressions.",
    "/stage": "Stages all current changes with `git`.",
    # General
    "/settings": "Configure the model and API keys.",
    "/help": "Shows the detailed help message.",
    "/exit": "Exits the agent session.",
}


class PatchLLMCompleter(Completer):
    """
    A custom completer for prompt_toolkit that provides context-aware suggestions
    for commands and scopes, including descriptive metadata.
    """
    def __init__(self, commands: list[str], scopes: dict):
        self.commands = sorted(commands)
        self.COMMAND_META = COMMAND_META
        
        static_scopes = sorted(list(scopes.keys()))
        
        self.dynamic_scopes = [
            "@git", "@git:staged", "@git:unstaged", "@git:lastcommit",
            "@git:conflicts", "@git:branch:", "@recent", "@structure",
            "@dir:", "@related:", "@search:", "@error:"
        ]
        
        self.all_scopes = sorted(static_scopes + self.dynamic_scopes)
        self.static_scopes = static_scopes

        self.plan_sub_commands = ['--edit ', '--rm ', '--add ']

    def get_completions(self, document: Document, complete_event):
        """
        Yields completions based on the current user input.
        """
        text = document.text_before_cursor
        words = text.split()
        word_count = len(words)

        if not words:
            return

        # Case 1: We are typing the first word (the command)
        if word_count == 1 and not text.endswith(' '):
            command_to_complete = words[0]
            if command_to_complete.startswith('/'):
                for command in self.commands:
                    if command.startswith(command_to_complete):
                        meta_text = self.COMMAND_META.get(command, '')
                        yield Completion(
                            command, 
                            start_position=-len(command_to_complete),
                            display_meta=meta_text
                        )
            return

        # Case 2: We are in a "scope" context
        if words[0] in ['/context', '/add_context']:
            scope_to_complete = words[1] if word_count > 1 else ""
            
            # Subcase 2a: We have just typed the command and a space, show all scopes
            if word_count == 1 and text.endswith(' '):
                for scope in self.all_scopes:
                    meta = "Static scope" if scope in self.static_scopes else "Dynamic scope"
                    yield Completion(scope, start_position=0, display_meta=meta)
                return
            
            # Subcase 2b: We are typing the second word (the scope itself)
            if word_count == 2 and not text.endswith(' '):
                for scope in self.all_scopes:
                    if scope.startswith(scope_to_complete):
                        meta = "Static scope" if scope in self.static_scopes else "Dynamic scope"
                        yield Completion(scope, start_position=-len(scope_to_complete), display_meta=meta)
                return

        # Case 3: We are in a "plan" management context
        if words[0] == '/plan':
            # Subcase 3a: We have typed '/plan ' and want to see sub-commands
            if word_count == 1 and text.endswith(' '):
                for sub_cmd in self.plan_sub_commands:
                    yield Completion(sub_cmd, start_position=0)
                return
            
            # Subcase 3b: We are typing the sub-command
            if word_count == 2 and not text.endswith(' '):
                sub_cmd_to_complete = words[1]
                for sub_cmd in self.plan_sub_commands:
                    if sub_cmd.startswith(sub_cmd_to_complete):
                        yield Completion(sub_cmd, start_position=-len(sub_cmd_to_complete))
                return