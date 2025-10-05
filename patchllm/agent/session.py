from pathlib import Path

from ..cli.helpers import get_system_prompt
from ..scopes.builder import build_context, build_context_from_files, helpers
from ..parser import paste_response
from . import planner, executor

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

    def set_goal(self, goal: str):
        self.goal = goal
        self.plan = []
        self.current_step = 0

    def create_plan(self) -> bool:
        if not self.goal:
            return False
        context_tree = helpers.generate_source_tree(Path(".").resolve(), self.context_files)
        plan = planner.generate_plan(self.goal, context_tree, self.args.model)
        if plan:
            self.plan = plan
            return True
        return False

    def run_current_step(self, instruction_override: str | None = None) -> dict | None:
        """
        Runs the current step instruction through the executor.
        Does not advance the session state; only generates a result for review.
        """
        if not self.plan or self.current_step >= len(self.plan):
            return None
        
        step_instruction = instruction_override or self.plan[self.current_step]
        
        result = executor.execute_step(
            step_instruction, self.history, self.context, self.args.model
        )
        
        if result:
            self.last_execution_result = result
        
        return result

    def approve_changes(self) -> bool:
        """
        Commits the last execution result: applies changes, updates history, and advances the plan.
        """
        if not self.last_execution_result:
            return False

        instruction_used = self.last_execution_result.get("instruction", self.plan[self.current_step])
        user_prompt = f"Context attached.\n\n---\n\nMy task was: {instruction_used}"
        self.history.append({"role": "user", "content": user_prompt})
        self.history.append({"role": "assistant", "content": self.last_execution_result["llm_response"]})
        
        paste_response(self.last_execution_result["llm_response"])
        
        self.current_step += 1
        self.last_execution_result = None
        return True

    def retry_step(self, feedback: str) -> dict | None:
        """
        Retries the current step with additional user feedback.
        """
        if self.current_step >= len(self.plan):
            return None 

        original_instruction = self.plan[self.current_step]
        refined_instruction = (
            f"My previous attempt was not correct. Here is my feedback: {feedback}\n\n"
            f"---\n\nMy original instruction was: {original_instruction}"
        )
        return self.run_current_step(instruction_override=refined_instruction)

    def load_context_from_scope(self, scope_name: str) -> str:
        context_object = build_context(scope_name, self.scopes, Path(".").resolve())
        if context_object:
            self.context = context_object.get("context")
            self.context_files = context_object.get("files", [])
            return context_object.get("tree", "Context loaded.")
        self.clear_context()
        return f"⚠️  Could not build context for scope '{scope_name}'. No files found."

    def add_files_and_rebuild_context(self, new_files: list[Path]) -> str:
        current_files_set = set(self.context_files)
        updated_files = sorted(list(current_files_set.union(set(new_files))))
        context_object = build_context_from_files(updated_files, Path(".").resolve())
        if context_object:
            self.context = context_object.get("context")
            self.context_files = context_object.get("files", [])
            return context_object.get("tree", "Context updated.")
        return "⚠️  Failed to rebuild context with new files."

    def add_context_from_scope(self, scope_name: str) -> str:
        context_object = build_context(scope_name, self.scopes, Path(".").resolve())
        if not context_object or not context_object.get("files"):
            return f"⚠️  Scope '{scope_name}' resolved to zero files. Context is unchanged."
        return self.add_files_and_rebuild_context(context_object.get("files", []))

    def clear_context(self):
        self.context = None
        self.context_files = []