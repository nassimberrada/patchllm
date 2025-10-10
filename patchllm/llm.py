import litellm
from rich.console import Console

console = Console()

def run_llm_query(messages: list[dict], model_name: str) -> str | None:
    """
    Sends a list of messages to the LLM and returns the response.
    This function is stateless and does not modify any history object.

    Args:
        messages (list[dict]): The full list of messages for the API call.
        model_name (str): The name of the model to query.

    Returns:
        The text content of the assistant's response, or None if an error occurs.
    """
    console.print("\n--- Sending Prompt to LLM... ---", style="bold")
    
    try:
        # Using litellm's built-in retry and timeout features.
        # This helps prevent getting stuck if the connection drops.
        response = litellm.completion(
            model=model_name, 
            messages=messages,
            timeout=120,  # 120-second timeout for the API call
            max_retries=3  # Retry up to 3 times on failure
        )
        
        assistant_response = response.choices[0].message.content
        if not assistant_response or not assistant_response.strip():
            console.print("⚠️  Response is empty.", style="yellow")
            return None
        
        return assistant_response
    except Exception as e:
        # Using rich.print to handle complex exception objects better
        console.print(f"❌ LLM communication error after retries: {e}", style="bold red")
        return None
