from ..llm import run_llm_query
from ..parser import summarize_changes, get_diff_for_file, parse_change_summary

def execute_step(step_instruction: str, history: list[dict], context: str | None, context_images: list | None, model_name: str) -> dict | None:
    """
    Executes a single step of the plan by calling the LLM.

    Args:
        step_instruction (str): The instruction for the current step.
        history (list[dict]): The full conversation history.
        context (str | None): The file context for the LLM.
        context_images (list | None): A list of image data dictionaries for multimodal context.
        model_name (str): The name of the LLM to use.

    Returns:
        A dictionary containing the instruction, response, and diffs, or None if it fails.
    """
    
    prompt_text = f"## Current Task:\n{step_instruction}"
    if context:
        prompt_text = f"## Context:\n{context}\n\n---\n\n{prompt_text}"
    
    user_content = [{"type": "text", "text": prompt_text}]

    if context_images:
        for image_info in context_images:
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{image_info['mime_type']};base64,{image_info['content_base64']}"
                }
            })

    # Create a temporary message history for this specific call
    messages = history + [{"role": "user", "content": user_content}]
    
    llm_response = run_llm_query(messages, model_name)
    
    if not llm_response:
        return None
    
    change_summary = parse_change_summary(llm_response)
    summary = summarize_changes(llm_response)
    all_files = summary.get("modified", []) + summary.get("created", [])
    
    diffs = []
    for file_path in all_files:
        diff_text = get_diff_for_file(file_path, llm_response)
        diffs.append({"file_path": file_path, "diff_text": diff_text})
        
    return {
        "instruction": step_instruction,
        "llm_response": llm_response,
        "summary": summary,
        "diffs": diffs,
        "change_summary": change_summary,
    }