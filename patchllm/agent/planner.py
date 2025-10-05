import re
from ..llm import run_llm_query

def _get_planning_prompt(goal: str, context_tree: str) -> list[dict]:
    """Constructs the prompt for the planning phase."""
    
    system_prompt = (
        "You are an expert software architect and senior developer. Your task is to create a high-level, "
        "step-by-step plan to accomplish a user's goal. Focus on the necessary file modifications and creations. "
        "Do not write code or implementation details. Each step should be a single, clear, actionable instruction "
        "for a programmer to execute. The plan should be a numbered list."
    )
    
    user_prompt = (
        "Based on my goal and the project structure below, create your plan.\n\n"
        f"## Project Structure:\n```\n{context_tree}\n```\n\n"
        f"## Goal:\n{goal}"
    )
    
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

def generate_plan(goal: str, context_tree: str, model_name: str) -> list[str] | None:
    """
    Calls the LLM to generate a step-by-step plan.

    Args:
        goal (str): The user's high-level goal.
        context_tree (str): The file tree summary of the current context.
        model_name (str): The name of the LLM to use.

    Returns:
        A list of strings, where each string is a step in the plan, or None if failed.
    """
    messages = _get_planning_prompt(goal, context_tree)
    response_text = run_llm_query(messages, model_name)
    
    if not response_text:
        return None
        
    # Find all lines that start with a number and a period (e.g., "1.", "2.")
    # This is more robust than splitting by newline.
    plan = re.findall(r"^\s*\d+\.\s+(.*)", response_text, re.MULTILINE)
    
    return plan if plan else [response_text] # Fallback to the whole response if parsing fails