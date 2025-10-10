from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

# A structured definition for all commands, including their display name,
# description, and the states in which they are available.
COMMAND_DEFINITIONS = [
    # Agent Workflow
    {"command": "/approve", "display": "agent - approve changes", "meta": "Applies the changes from the last run.", "states": ["has_pending_changes"]},
    {"command": "/diff", "display": "agent - view diff", "meta": "Shows the full diff for the proposed changes.", "states": ["has_pending_changes"]},
    {"command": "/retry", "display": "agent - retry with feedback", "meta": "Retries the last step with new feedback.", "states": ["has_pending_changes"]},
    {"command": "/revert", "display": "agent - revert last approval", "meta": "Reverts the changes from the last /approve.", "states": ["can_revert"]},
    {"command": "/run", "display": "agent - run step", "meta": "Executes the current plan step.", "states": ["has_plan"]},
    {"command": "/skip", "display": "agent - skip step", "meta": "Skips the current step and moves to the next.", "states": ["has_plan"]},
    # Context Management
    {"command": "/context", "display": "context - set context", "meta": "Replaces the context with files from a scope.", "states": ["initial", "has_goal", "has_plan"]},
    {"command": "/scopes", "display": "context - manage scopes", "meta": "Opens an interactive menu to manage your saved scopes.", "states": ["initial", "has_goal", "has_plan"]},
    # Planning Workflow
    {"command": "/ask", "display": "plan - ask question", "meta": "Ask a clarifying question about the current plan.", "states": ["has_plan"]},
    {"command": "/plan", "display": "plan - generate or manage", "meta": "Generates a plan or manages the existing one.", "states": ["has_goal", "has_plan"]},
    {"command": "/refine", "display": "plan - refine with feedback", "meta": "Refine the plan based on new feedback or ideas.", "states": ["has_plan"]},
    # Task Management
    {"command": "/task", "display": "task - set goal", "meta": "Sets the high-level goal for the agent.", "states": ["initial", "has_goal", "has_plan"]},
    # Menu / Session Management
    {"command": "/exit", "display": "menu - exit session", "meta": "Exits the agent session.", "states": ["initial", "has_goal", "has_plan"]},
    {"command": "/help", "display": "menu - help", "meta": "Shows the detailed help message.", "states": ["initial", "has_goal", "has_plan"]},
    {"command": "/show", "display": "menu - show state", "meta": "Shows the current goal, plan, context, or history.", "states": ["initial", "has_goal", "has_plan"]},
    {"command": "/settings", "display": "menu - settings", "meta": "Configure the model and API keys.", "states": ["initial", "has_goal", "has_plan"]},
]


class PatchLLMCompleter(Completer):
    """
    A custom completer for prompt_toolkit that provides context-aware suggestions
    for commands and scopes, including descriptive metadata.
    """
    def __init__(self, scopes: dict):
        self.all_command_defs = sorted(COMMAND_DEFINITIONS, key=lambda x: x['display'])
        self.scopes = scopes
        self.static_scopes = sorted(list(scopes.keys()))
        self.dynamic_scopes = [
            "@git", "@git:staged", "@git:unstaged", "@git:lastcommit",
            "@git:conflicts", "@git:branch:", "@recent", "@structure",
            "@dir:", "@related:", "@search:", "@error:"
        ]
        self.all_scopes = sorted(self.static_scopes + self.dynamic_scopes)
        self.plan_sub_commands = ['--edit ', '--rm ', '--add ']
        self.show_sub_commands = ['goal', 'plan', 'context', 'history']
        
        # State flags
        self.has_goal = False
        self.has_plan = False
        self.has_pending_changes = False
        self.can_revert = False

    def set_session_state(self, has_goal: bool, has_plan: bool, has_pending_changes: bool, can_revert: bool):
        """Updates the completer's state from the agent session."""
        self.has_goal = has_goal
        self.has_plan = has_plan
        self.has_pending_changes = has_pending_changes
        self.can_revert = can_revert

    def get_completions(self, document: Document, complete_event):
        """
        Yields completions based on the current user input and agent state.
        """
        text = document.text_before_cursor
        words = text.lstrip().split()
        word_count = len(words)
        
        active_states = {"initial"}
        if self.has_goal:
            active_states.add("has_goal")
        if self.has_plan:
            active_states.add("has_plan")
        if self.has_pending_changes:
            active_states.add("has_pending_changes")
        if self.can_revert:
            active_states.add("can_revert")

        # Case 1: We are typing the first word (the command)
        if word_count == 0 or (word_count == 1 and not text.endswith(' ')):
            command_to_complete = words[0] if words else "/"
            if command_to_complete.startswith('/'):
                for definition in self.all_command_defs:
                    is_valid_state = any(s in active_states for s in definition["states"])

                    if is_valid_state and definition["command"].startswith(command_to_complete):
                        yield Completion(
                            definition["command"], 
                            start_position=-len(command_to_complete),
                            display=definition["display"],
                            display_meta=definition["meta"]
                        )
            return

        # Case 2: We are in a "scope" context
        if words and words[0] in ['/context']: # Removed /add_context
            scope_to_complete = words[1] if word_count > 1 else ""
            
            if word_count == 1 and text.endswith(' '):
                for scope in self.all_scopes:
                    meta = "Static scope" if scope in self.static_scopes else "Dynamic scope"
                    yield Completion(scope, start_position=0, display_meta=meta)
                return
            
            if word_count == 2 and not text.endswith(' '):
                for scope in self.all_scopes:
                    if scope.startswith(scope_to_complete):
                        meta = "Static scope" if scope in self.static_scopes else "Dynamic scope"
                        yield Completion(scope, start_position=-len(scope_to_complete), display_meta=meta)
                return

        # Case 3: We are in a "plan" management context
        if words and words[0] == '/plan':
            if word_count == 1 and text.endswith(' '):
                for sub_cmd in self.plan_sub_commands:
                    yield Completion(sub_cmd, start_position=0)
                return
            
            if word_count == 2 and not text.endswith(' '):
                sub_cmd_to_complete = words[1]
                for sub_cmd in self.plan_sub_commands:
                    if sub_cmd.startswith(sub_cmd_to_complete):
                        yield Completion(sub_cmd, start_position=-len(sub_cmd_to_complete))
                return
        
        # Case 4: We are in a "show" context
        if words and words[0] == '/show':
            if word_count == 1 and text.endswith(' '):
                for sub_cmd in self.show_sub_commands:
                    yield Completion(sub_cmd, start_position=0)
                return
            
            if word_count == 2 and not text.endswith(' '):
                sub_cmd_to_complete = words[1]
                for sub_cmd in self.show_sub_commands:
                    if sub_cmd.startswith(sub_cmd_to_complete):
                        yield Completion(sub_cmd, start_position=-len(sub_cmd_to_complete))
                return