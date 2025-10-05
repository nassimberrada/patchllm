from pathlib import Path
import json
import os

# Only import what's needed for initialization at the top level.
from ..cli.helpers import get_system_prompt

CONFIG_FILE_PATH = Path(".patchllm_config.json")

class AgentSession:
    """
    Manages the state for a continuous, interactive agent session.
    """
    def __init__(self, args, scopes: dict, recipes: dict):
        self.args = args
        self.goal: str | None = None
        self.plan: list[str] = []
        self.current_step: int = 0
        self.context: str | None = None
        self.context_files: list[Path] = []
        self.history: list[dict] = [{"role": "system", "content": get_system_prompt()}]
        self.scopes = scopes
        self.recipes = recipes
        self.last_execution_result: dict | None = None
        self.load_settings()

    def load_settings(self):
        """Loads settings from the config file and applies them."""
        if CONFIG_FILE_PATH.exists():
            try:
                with open(CONFIG_FILE_PATH, 'r') as f:
                    settings = json.load(f)
                
                # The config file overrides the initial default args
                if 'model' in settings:
                    self.args.model = settings['model']

            except (json.JSONDecodeError, IOError):
                # Ignore if the file is corrupted or unreadable
                pass

    def save_settings(self):
        """Saves current settings to the config file."""
        settings_to_save = {
            'model': self.args.model
        }
        with open(CONFIG_FILE_PATH, 'w') as f:
            json.dump(settings_to_save, f, indent=2)

    def to_dict(self) -> dict:
        """Serializes the session's state to a dictionary."""
        return {
            "goal": self.goal,
            "plan": self.plan,
            "current_step": self.current_step,
            "context_files": [p.as_posix() for p in self.context_files],
        }

    def from_dict(self, data: dict):
        """Restores the session's state from a dictionary."""
        self.goal = data.get("goal")
        self.plan = data.get("plan", [])
        self.current_step = data.get("current_step", 0)
        
        context_file_paths = data.get("context_files", [])
        if context_file_paths:
            self.add_files_and_rebuild_context([Path(p) for p in context_file_paths])

    def set_goal(self, goal: str):
        self.goal = goal
        self.plan = []
        self.current_step = 0

    def edit_plan_step(self, step_number: int, new_instruction: str) -> bool:
        """Edits an instruction in the current plan."""
        # step_number is 1-indexed for user-friendliness
        if 1 <= step_number <= len(self.plan):
            self.plan[step_number - 1] = new_instruction
            return True
        return False

    def remove_plan_step(self, step_number: int) -> bool:
        """Removes a step from the current plan."""
        # step_number is 1-indexed
        if 1 <= step_number <= len(self.plan):
            del self.plan[step_number - 1]
            # If we remove a step before the current one, adjust the current step index
            if step_number - 1 < self.current_step:
                self.current_step -=1
            return True
        return False

    def add_plan_step(self, instruction: str):
        """Adds a new instruction to the end of the plan."""
        self.plan.append(instruction)

    def skip_step(self) -> bool:
        """Skips the current step and moves to the next one."""
        if self.current_step < len(self.plan):
            self.current_step += 1
            self.last_execution_result = None # Clear any pending changes
            return True
        return False

    def create_plan(self) -> bool:
        # --- FIX: Moved imports inside the method ---
        from ..scopes.builder import helpers
        from . import planner
        
        if not self.goal: return False
        context_tree = helpers.generate_source_tree(Path(".").resolve(), self.context_files)
        plan = planner.generate_plan(self.goal, context_tree, self.args.model)
        if plan: self.plan = plan; return True
        return False

    def run_current_step(self, instruction_override: str | None = None) -> dict | None:
        # --- FIX: Moved import inside the method ---
        from . import executor
        
        if not self.plan or self.current_step >= len(self.plan): return None
        step_instruction = instruction_override or self.plan[self.current_step]
        result = executor.execute_step(step_instruction, self.history, self.context, self.args.model)
        if result: self.last_execution_result = result
        return result

    def approve_changes(self) -> bool:
        # --- FIX: Moved import inside the method ---
        from ..parser import paste_response
        
        if not self.last_execution_result: return False
        instruction_used = self.last_execution_result.get("instruction", self.plan[self.current_step])
        user_prompt = f"Context attached.\n\n---\n\nMy task was: {instruction_used}"
        self.history.append({"role": "user", "content": user_prompt})
        self.history.append({"role": "assistant", "content": self.last_execution_result["llm_response"]})
        paste_response(self.last_execution_result["llm_response"])
        self.current_step += 1
        self.last_execution_result = None
        return True

    def retry_step(self, feedback: str) -> dict | None:
        if self.current_step >= len(self.plan): return None 
        original_instruction = self.plan[self.current_step]
        refined_instruction = (
            f"My previous attempt was not correct. Here is my feedback: {feedback}\n\n"
            f"---\n\nMy original instruction was: {original_instruction}"
        )
        return self.run_current_step(instruction_override=refined_instruction)

    def reload_scopes(self, scopes_file_path: str):
        # --- FIX: Moved import inside the method ---
        from ..utils import load_from_py_file
        
        try:
            self.scopes = load_from_py_file(scopes_file_path, "scopes")
        except FileNotFoundError:
            self.scopes = {}
        except Exception as e:
            print(f"Warning: Could not reload scopes file: {e}")

    def load_context_from_scope(self, scope_name: str) -> str:
        # --- FIX: Moved import inside the method ---
        from ..scopes.builder import build_context
        
        context_object = build_context(scope_name, self.scopes, Path(".").resolve())
        if context_object:
            self.context = context_object.get("context")
            self.context_files = context_object.get("files", [])
            return context_object.get("tree", "Context loaded.")
        self.clear_context()
        return f"⚠️  Could not build context for scope '{scope_name}'. No files found."

    def add_files_and_rebuild_context(self, new_files: list[Path]) -> str:
        # --- FIX: Moved import inside the method ---
        from ..scopes.builder import build_context_from_files
        
        current_files_set = set(self.context_files)
        updated_files = sorted(list(current_files_set.union(set(new_files))))
        context_object = build_context_from_files(updated_files, Path(".").resolve())
        if context_object:
            self.context = context_object.get("context")
            self.context_files = context_object.get("files", [])
            return context_object.get("tree", "Context updated.")
        return "⚠️  Failed to rebuild context with new files."

    def add_context_from_scope(self, scope_name: str) -> str:
        # --- FIX: Moved import inside the method ---
        from ..scopes.builder import build_context
        
        context_object = build_context(scope_name, self.scopes, Path(".").resolve())
        if not context_object or not context_object.get("files"):
            return f"⚠️  Scope '{scope_name}' resolved to zero files. Context is unchanged."
        return self.add_files_and_rebuild_context(context_object.get("files", []))

    def clear_context(self):
        self.context = None
        self.context_files = []