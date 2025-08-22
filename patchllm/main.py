import sys

from .context import build_context
from .parser import paste_response
from .utils import load_from_py_file
import textwrap
import argparse
import litellm

from dotenv import load_dotenv

load_dotenv()

class Assistant:
    """
    An assistant that builds context, interacts with an LLM, and applies code changes.
    """
    def __init__(
            self, 
            model_name="gemini/gemini-2.5-flash",
            configs: dict = None,
            configs_file = "./configs.py",
        ):
        """
        Initializes the Assistant.
        Args:
            model_name (str): The alias for the generative model to use (must be a litellm supported model string).
            configs (Dict[str]): A dictionary of configurations to use for building the code context.
            configs_file (str): The path to the configurations file.
        """
        self.model_name = model_name
        if configs:
            self.configs = configs
        else:
            self.configs = load_from_py_file(configs_file, "configs")
        system_prompt = textwrap.dedent("""
            You are an expert pair programmer. Your purpose is to help users by modifying files based on their instructions.

            Follow these rules strictly:
            Your output should be a single file including all the updated files. For each file-block:
            1. Only include code for files that need to be updated / edited.
            2. For updated files, do not exclude any code even if it is unchanged code; assume the file code will be copy-pasted full in the file.
            3. Do not include verbose inline comments explaining what every small change does. Try to keep comments concise but informative, if any.
            4. Only update the relevant parts of each file relative to the provided task; do not make irrelevant edits even if you notice areas of improvements elsewhere.
            5. Do not use diffs.
            6. Make sure each file-block is returned in the following exact format. No additional text, comments, or explanations should be outside these blocks.

            Expected format for a modified or new file:
            <file_path:/absolute/path/to/your/file.py>
            ```python
            # The full, complete content of /absolute/path/to/your/file.py goes here.
            def example_function():
                return "Hello, World!"
            ```

            Example of multiple files:
            <file_path:/home/user/project/src/main.py>
            ```python
            print("Main application start")
            ```

            <file_path:/home/user/project/tests/test_main.py>
            ```python
            def test_main():
                assert True
            ```
        """)
        self.history = [{"role": "system", "content": system_prompt}]

    def collect(self, config_name):
        """Builds the code context from a provided configuration dictionary."""
        print("\n--- Building Code Context... ---")
        selected_config = self.configs.get(config_name)
        if selected_config is None:
            raise KeyError(f"Context config '{config_name}' not found in provided configs file.")
        context_object = build_context(selected_config)
        if context_object:
            tree, context = context_object.values()
            print("--- Context Building Finished. The following files were extracted ---", file=sys.stderr)
            print(tree)
            return context
        else:
            print("--- Context Building Failed (No files found) ---", file=sys.stderr)
            return None

    def update(self, task_instructions, context=None):
        """
        Assembles the final prompt and sends it to the LLM to generate code, 
        then in-place update the files from the response.
        Args:
            task_instructions (str): Specific instructions for this run.
            context (str, optional): The code context. If None, only the task is sent.
        """        
        print("\n--- Sending Prompt to LLM... ---")
        final_prompt = task_instructions
        if context:
            final_prompt = f"{context}\n\n{task_instructions}"
        
        self.history.append({"role": "user", "content": final_prompt})
        
        try:
            response = litellm.completion(model=self.model_name, messages=self.history)
            
            # Extract the message content from the response
            assistant_response_content = response.choices[0].message.content
            
            # Add the assistant's response to the history for future context
            self.history.append({"role": "assistant", "content": assistant_response_content})

            if not assistant_response_content or not assistant_response_content.strip():
                print("Response is empty. Nothing to paste.")
                return
            
            print("\n--- Updating files ---")
            paste_response(assistant_response_content)
            print("--- File Update Process Finished ---")

        except Exception as e:
            # If an error occurs, remove the last user message to keep history clean
            self.history.pop()
            raise RuntimeError(f"An error occurred while communicating with the LLM via litellm: {e}") from e

    def write(self, file_path, context):
        """Utility function to write the context to a file"""
        print("Exporting context..")
        with open(file_path, "w") as file:
            file.write(context)
        print(f'Context exported to {file_path.split("/")[-1]}')

    def read(self, file_path):
        """Utility function to read and return the content of a file."""
        print("Importing from file..")
        try:
            with open(file_path, "r") as file:
                print("Finished reading")
                content = file.read()
            return content
        except Exception as e:
            raise RuntimeError(f"Failed to read from file {file_path}: {e}") from e
        
def main():
    parser = argparse.ArgumentParser(
        description="Run the Assistant tool to apply code changes using an LLM."
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Name of the config key to use from the configs.py file."
    )
    parser.add_argument(
        "--task",
        type=str,
        default=None,
        help="The task instructions to guide the assistant."
    )
    parser.add_argument(
        "--context-out",
        type=str,
        default=None,
        help="Optional path to export the generated context to a file."
    )
    parser.add_argument(
        "--context-in",
        type=str,
        default=None,
        help="Optional path to import a previously saved context from a file."
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gemini/gemini-2.5-flash",
        help="Optional model name to override the default model."
    )
    parser.add_argument(
        "--from-file",
        type=str,
        default=None,
        help="File path for a file with pre-formatted updates."
    )
    parser.add_argument(
        "--update",
        type=str,
        default="True",
        help="Whether to pass the input context to the llm to update the files."
    )
    parser.add_argument(
        "--voice",
        type=str,
        default="False",
        help="Whether to interact with the script using voice commands."
    )

    args = parser.parse_args()

    assistant = Assistant(model_name=args.model)

    # Handle voice input
    if args.voice not in ["False", "false"]:
        from .listener import listen, speak

        speak("Say your task instruction.")
        task = listen()
        if not task:
            speak("No instruction heard. Exiting.")
            return

        speak(f"You said: {task}. Should I proceed?")
        confirm = listen()
        if confirm and "yes" in confirm.lower():
            context = assistant.collect(args.config)
            assistant.update(task_instructions=task, context=context)
            speak("Changes applied.")
        else:
            speak("Cancelled.")
        return

    # Parse updates from a local file
    if args.from_file:
        updates = assistant.read(args.from_file)
        paste_response(updates)
        return

    # Otherwise generate updates from llm response
    if args.context_in:
        context = assistant.read(args.context_in)
    else:
        context = assistant.collect(args.config)
        if args.context_out:
            assistant.write(args.context_out, context)
    if not args.update in ["False", "false"]:
        assistant.update(task_instructions=args.task, context=context)

if __name__ == "__main__":
    main()