from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

class PatchLLMCompleter(Completer):
    """
    A custom completer for prompt_toolkit that provides context-aware suggestions
    for commands and scopes.
    """
    def __init__(self, commands: list[str], scopes: dict):
        self.commands = sorted(commands)
        
        static_scopes = sorted(list(scopes.keys()))
        
        # --- FIX: Store dynamic_scopes as an instance attribute ---
        self.dynamic_scopes = [
            "@git", "@git:staged", "@git:unstaged", "@git:lastcommit",
            "@git:conflicts", "@git:branch:", "@recent", "@structure",
            "@dir:", "@related:", "@search:", "@error:"
        ]
        # --- End FIX ---
        
        self.all_scopes = sorted(static_scopes + self.dynamic_scopes)

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
                        yield Completion(command, start_position=-len(command_to_complete))
            return

        # Case 2: We are in a "scope" context
        if words[0] in ['/context', '/add_context']:
            # Subcase 2a: We have just typed the command and a space, show all scopes
            if word_count == 1 and text.endswith(' '):
                for scope in self.all_scopes:
                    yield Completion(scope, start_position=0)
                return
            
            # Subcase 2b: We are typing the second word (the scope itself)
            if word_count == 2 and not text.endswith(' '):
                scope_to_complete = words[1]
                for scope in self.all_scopes:
                    if scope.startswith(scope_to_complete):
                        yield Completion(scope, start_position=-len(scope_to_complete))
                return