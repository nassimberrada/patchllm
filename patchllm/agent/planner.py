import re
from ..llm import run_llm_query

def _get_planning_prompt(goal: str, context_tree: str) -> list[dict]:
    """Constructs the initial prompt for the planning phase."""
    
    system_prompt = (
        "You are an expert software architect. Your task is to create a high-level, milestone-focused plan to "
        "accomplish a user's goal. Break down the goal into logical, sequential steps that represent significant "
        "pieces of functionality or architectural changes."
        "\n\n"
        "IMPORTANT RULES:\n"
        "- DO NOT list individual file modifications. Instead, group related changes into a single milestone.\n"
        "- For example, instead of a plan like '1. Add route to api.py, 2. Create logic in services.py', a better, "
        "milestone-focused step would be '1. Implement the user authentication endpoint, including routes and server actions'.\n"
        "- Do not write any code or implementation details in the plan.\n"
        "- Each step should be a clear, actionable instruction for a developer.\n"
        "- The final plan must be a numbered list."
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

def _get_refine_prompt(history: list[dict], feedback: str) -> list[dict]:
    """Constructs the prompt for refining an existing plan."""
    refine_instruction = (
        "The user has provided feedback or a new idea on the plan you created. "
        "Carefully review the entire conversation and their latest feedback. "
        "Your task is to generate a new, complete, and improved step-by-step plan that incorporates their feedback. "
        "The new plan should be a single, cohesive, numbered list. Do not just add to the old plan; create a new one from scratch."
        f"\n\n## User Feedback:\n{feedback}"
    )
    
    return history + [{"role": "user", "content": refine_instruction}]

def parse_plan_from_response(response_text: str) -> list[str] | None:
    """Finds all lines that start with a number and a period (e.g., "1.", "2.")."""
    if not response_text:
        return None
    # This is more robust than splitting by newline.
    plan = re.findall(r"^\s*\d+\.\s+(.*)", response_text, re.MULTILINE)
    return plan if plan else None

def generate_plan_and_history(goal: str, context_tree: str, model_name: str) -> tuple[list[dict], str | None]:
    """
    Calls the LLM to generate an initial plan and returns the history and response.

    Returns:
        A tuple containing the initial planning history (list of messages) and the LLM's raw response text.
    """
    messages = _get_planning_prompt(goal, context_tree)
    response_text = run_llm_query(messages, model_name)
    
    if response_text:
        messages.append({"role": "assistant", "content": response_text})
    
    return messages, response_text

def generate_refined_plan(history: list[dict], feedback: str, model_name: str) -> str | None:
    """
    Calls the LLM to refine a plan based on conversation history and new feedback.

    Returns:
        The LLM's raw response text containing the new plan.
    """
    messages = _get_refine_prompt(history, feedback)
    response_text = run_llm_query(messages, model_name)
    return response_text
