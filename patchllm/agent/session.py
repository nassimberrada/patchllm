from pathlib import Path
import json
import os

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
        self.planning_history: list[dict] = []
        self.scopes = scopes
        self.recipes = recipes
        self.last_execution_result: dict | None = None
        self.action_history: list[str] = []
        self.last_revert_state: list[dict] = []
        self.api_keys: dict = {}
        self.load_settings()

    def load_settings(self):
        """Loads settings from the config file and applies them."""
        if CONFIG_FILE_PATH.exists():
            try:
                with open(CONFIG_FILE_PATH, 'r') as f:
                    settings = json.load(f)
                
                if 'model' in settings:
                    self.args.model = settings['model']

                self.api_keys = settings.get('api_keys', {})
                for key, value in self.api_keys.items():
                    if key not in os.environ:
                        os.environ[key] = value

            except (json.JSONDecodeError, IOError):
                pass

    def save_settings(self):
        """Saves current settings to the config file."""
        settings_to_save = {
            'model': self.args.model,
            'api_keys': self.api_keys
        }
        with open(CONFIG_FILE_PATH, 'w') as f:
            json.dump(settings_to_save, f, indent=2)

    def set_api_key(self, key_name: str, key_value: str):
        """Sets an API key, applies it to the environment, and saves it."""
        self.api_keys[key_name] = key_value
        os.environ[key_name] = key_value
        self.save_settings()

    def remove_api_key(self, key_name: str):
        """Removes an API key and saves the settings."""
        if key_name in self.api_keys:
            del self.api_keys[key_name]
            self.save_settings()

    def to_dict(self) -> dict:
        """Serializes the session's state to a dictionary."""
        return {
            "goal": self.goal,
            "plan": self.plan,
            "current_step": self.current_step,
            "context_files": [p.as_posix() for p in self.context_files],
            "action_history": self.action_history,
            "last_revert_state": self.last_revert_state,
        }

    def from_dict(self, data: dict):
        """Restores the session's state from a dictionary."""
        self.goal = data.get("goal")
        self.plan = data.get("plan", [])
        self.current_step = data.get("current_step", 0)
        self.action_history = data.get("action_history", [])
        self.last_revert_state = data.get("last_revert_state", [])
        
        context_file_paths = data.get("context_files", [])
        if context_file_paths:
            self.add_files_and_rebuild_context([Path(p) for p in context_file_paths])

    def set_goal(self, goal: str):
        self.goal = goal
        self.plan = []
        self.current_step = 0
        self.planning_history = []
        self.action_history.append(f"Goal set: {goal}")

    def edit_plan_step(self, step_number: int, new_instruction: str) -> bool:
        """Edits an instruction in the current plan."""
        if 1 <= step_number <= len(self.plan):
            self.plan[step_number - 1] = new_instruction
            return True
        return False

    def remove_plan_step(self, step_number: int) -> bool:
        """Removes a step from the current plan."""
        if 1 <= step_number <= len(self.plan):
            del self.plan[step_number - 1]
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
            self.last_execution_result = None
            return True
        return False

    def create_plan(self) -> bool:
        from ..scopes.builder import helpers
        from . import planner
        
        if not self.goal: return False
        context_tree = helpers.generate_source_tree(Path(".").resolve(), self.context_files)
        
        self.planning_history, plan_response = planner.generate_plan_and_history(self.goal, context_tree, self.args.model)
        
        if plan_response:
            parsed_plan = planner.parse_plan_from_response(plan_response)
            if parsed_plan:
                self.plan = parsed_plan
                self.action_history.append("Plan generated.")
                return True
        return False

    def ask_about_plan(self, question: str) -> str | None:
        """Asks a clarifying question about the plan without changing it."""
        from ..llm import run_llm_query

        self.planning_history.append({"role": "user", "content": question})
        response = run_llm_query(self.planning_history, self.args.model)
        if response:
            self.planning_history.append({"role": "assistant", "content": response})
        else:
            self.planning_history.pop()
        return response

    def refine_plan(self, feedback: str) -> bool:
        """Refines the existing plan based on user feedback."""
        from . import planner

        new_plan_response = planner.generate_refined_plan(self.planning_history, feedback, self.args.model)
        if new_plan_response:
            parsed_plan = planner.parse_plan_from_response(new_plan_response)
            if parsed_plan:
                self.planning_history.append({"role": "user", "content": feedback})
                self.planning_history.append({"role": "assistant", "content": new_plan_response})
                self.plan = parsed_plan
                return True
        return False

    def run_next_step(self, instruction_override: str | None = None) -> dict | None:
        from . import executor
        
        if not self.plan or self.current_step >= len(self.plan): return None
        step_instruction = instruction_override or self.plan[self.current_step]
        result = executor.execute_step(step_instruction, self.history, self.context, self.args.model)
        if result: self.last_execution_result = result
        return result

    def run_all_remaining_steps(self) -> dict | None:
        """Combines all remaining steps into a single execution call."""
        from . import executor

        if not self.plan or self.current_step >= len(self.plan): return None
        
        remaining_steps = self.plan[self.current_step:]
        if not remaining_steps: return None

        formatted_steps = "\n".join(f"{i + 1}. {step}" for i, step in enumerate(remaining_steps))
        combined_instruction = (
            "Please execute the following remaining steps of the plan in a single pass. "
            "Ensure you provide the full, final content for every file you modify.\n\n"
            f"--- Remaining Steps ---\n{formatted_steps}"
        )

        result = executor.execute_step(combined_instruction, self.history, self.context, self.args.model)
        
        if result:
            self.last_execution_result = result
            self.last_execution_result['is_multi_step'] = True 
        return result

    def approve_changes(self, files_to_approve: list[str]) -> bool:
        """
        Applies changes from the last execution, either fully or partially.
        Returns True if all changes were applied, False otherwise.
        """
        from ..parser import paste_response_selectively, _parse_file_blocks
        
        if not self.last_execution_result: return False

        all_proposed_files = self.last_execution_result.get("summary", {}).get("modified", []) + \
                             self.last_execution_result.get("summary", {}).get("created", [])
        
        revert_state = []
        parsed_blocks = _parse_file_blocks(self.last_execution_result["llm_response"])

        for file_path_str in files_to_approve:
            file_path = Path(file_path_str)
            if file_path.exists():
                try:
                    original_content = file_path.read_text(encoding="utf-8")
                    revert_state.append({"file_path": file_path.as_posix(), "content": original_content, "action": "modify"})
                except Exception:
                    pass
            else:
                revert_state.append({"file_path": file_path.as_posix(), "content": None, "action": "create"})
        
        self.last_revert_state = revert_state
        
        paste_response_selectively(self.last_execution_result["llm_response"], files_to_approve)
        
        is_multi_step = self.last_execution_result.get('is_multi_step', False)
        step_log_msg = f"steps {self.current_step + 1}-{len(self.plan)}" if is_multi_step else f"step {self.current_step + 1}"
        self.action_history.append(f"Approved {len(files_to_approve)} file(s) for {step_log_msg}.")
        
        is_full_approval = len(files_to_approve) == len(all_proposed_files)

        if is_full_approval:
            instruction_used = self.last_execution_result.get("instruction", self.plan[self.current_step])
            user_prompt = f"Context attached.\n\n---\n\nMy task was: {instruction_used}"
            self.history.append({"role": "user", "content": user_prompt})
            self.history.append({"role": "assistant", "content": self.last_execution_result["llm_response"]})
            
            if is_multi_step:
                self.current_step = len(self.plan)
            else:
                self.current_step += 1
            
            self.last_execution_result = None
        else:
            self.last_execution_result['approved_files'] = files_to_approve
        
        return is_full_approval

    def revert_last_approval(self) -> bool:
        """Writes the stored original content back to the files from the last approval."""
        if not self.last_revert_state:
            return False

        for state in self.last_revert_state:
            file_path = Path(state["file_path"])
            action = state["action"]

            try:
                if action == "modify":
                    file_path.write_text(state["content"], encoding="utf-8")
                elif action == "create":
                    if file_path.exists():
                        file_path.unlink()
            except Exception as e:
                print(f"Warning: Could not revert {file_path}: {e}")
        
        self.action_history.append("Reverted last approval.")
        self.last_revert_state = []
        return True

    def retry_step(self, feedback: str) -> dict | None:
        """
        Retries the current step. If a partial approval occurred, it constructs
        a more detailed prompt informing the LLM of what was approved and rejected.
        """
        from . import executor

        if self.current_step >= len(self.plan): return None 
        
        is_multi_step = self.last_execution_result and self.last_execution_result.get('is_multi_step', False)
        
        original_instruction = "to complete the rest of the plan" if is_multi_step else self.plan[self.current_step]
        
        if self.last_execution_result and 'approved_files' in self.last_execution_result:
            approved = self.last_execution_result['approved_files']
            all_proposed = self.last_execution_result.get("summary", {}).get("modified", []) + \
                           self.last_execution_result.get("summary", {}).get("created", [])
            rejected = [f for f in all_proposed if f not in approved]

            refined_instruction = (
                f"Your previous attempt was partially correct. I have **approved** the changes for the following files:\n"
                f"- {', '.join(Path(f).name for f in approved)}\n\n"
                f"However, I **rejected** the changes for these files:\n"
                f"- {', '.join(Path(f).name for f in rejected)}\n\n"
                f"Here is my feedback on the rejected files: {feedback}\n\n"
                f"Please provide a new, corrected version of **only the rejected files** based on this feedback.\n\n"
                f"---\n\nMy original overall instruction for this step was: {original_instruction}"
            )
        else:
            refined_instruction = (
                f"My previous attempt was not correct. Here is my feedback: {feedback}\n\n"
                f"---\n\nMy original instruction was: {original_instruction}"
            )
            
        result = executor.execute_step(refined_instruction, self.history, self.context, self.args.model)
        if result:
            self.last_execution_result = result
            if is_multi_step:
                self.last_execution_result['is_multi_step'] = True
        return result

    def reload_scopes(self, scopes_file_path: str):
        from ..utils import load_from_py_file
        
        try:
            self.scopes = load_from_py_file(scopes_file_path, "scopes")
        except FileNotFoundError:
            self.scopes = {}
        except Exception as e:
            print(f"Warning: Could not reload scopes file: {e}")

    def load_context_from_scope(self, scope_name: str) -> str:
        from ..scopes.builder import build_context
        
        context_object = build_context(scope_name, self.scopes, Path(".").resolve())
        if context_object:
            self.context = context_object.get("context")
            self.context_files = context_object.get("files", [])
            return context_object.get("tree", "Context loaded.")
        self.clear_context()
        return f"⚠️  Could not build context for scope '{scope_name}'. No files found."

    def add_files_and_rebuild_context(self, new_files: list[Path]) -> str:
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
        from ..scopes.builder import build_context
        
        context_object = build_context(scope_name, self.scopes, Path(".").resolve())
        if not context_object or not context_object.get("files"):
            return f"⚠️  Scope '{scope_name}' resolved to zero files. Context is unchanged."
        return self.add_files_and_rebuild_context(context_object.get("files", []))

    def clear_context(self):
        self.context = None
        self.context_files = []