import litellm
from rich.console import Console

# CORRECTED: The relative import path is now correct for this file's location.
from .scopes.constants import DEFAULT_EXCLUDE_EXTENSIONS, STRUCTURE_EXCLUDE_DIRS

console = Console()

def run_llm_query(task_instructions, model_name, history, context=None):
    """Assembles the final prompt and sends it to the LLM."""
    console.print("\n--- Sending Prompt to LLM... ---", style="bold")
    final_prompt = f"{context}\n\n{task_instructions}" if context else task_instructions
    history.append({"role": "user", "content": final_prompt})
    
    try:
        with console.status("[bold cyan]Waiting for LLM response..."):
            response = litellm.completion(model=model_name, messages=history)
        
        assistant_response = response.choices[0].message.content
        if not assistant_response or not assistant_response.strip():
            console.print("⚠️  Response is empty.", style="yellow")
            return None
        
        history.append({"role": "assistant", "content": assistant_response})
        return assistant_response
    except Exception as e:
        history.pop()
        raise RuntimeError(f"LLM communication error: {e}") from e