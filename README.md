<p align="center">
  <picture>
    <source srcset="./assets/logo_dark.png" media="(prefers-color-scheme: dark)">
    <source srcset="./assets/logo_light.png" media="(prefers-color-scheme: light)">
    <img src="./assets/logo_light.png" alt="PatchLLM Logo" height="200">
  </picture>
</p>

## About
PatchLLM is a command-line tool that lets you flexibly build LLM context from your codebase using glob patterns, URLs, and keyword searches. It then automatically applies file edits directly from the LLM's response.

## Usage
PatchLLM is designed to be used directly from your terminal.

### 1. Initialize a Configuration
The easiest way to get started is to run the interactive initializer. This will create a `configs.py` file for you.

```bash
patchllm --init
```

This will guide you through creating your first context configuration, including setting a base path and file patterns. You can add multiple configurations to this file.

A generated `configs.py` might look like this:
```python
# configs.py
configs = {
    "default": {
        "path": ".",
        "include_patterns": ["**/*.py"],
        "exclude_patterns": ["**/tests/*", "venv/*"],
        "urls": ["https://docs.python.org/3/library/argparse.html"]
    },
    "docs": {
        "path": "./docs",
        "include_patterns": ["**/*.md"],
    }
}
```

### 2. Run a Task
Use the `patchllm` command with a configuration name and a task instruction.

```bash
# Apply a change using the 'default' configuration
patchllm --config default --task "Add type hints to the main function in main.py"
```

The tool will then:
1.  Build a context from the files and URLs matching your configuration.
2.  Send the context and your task to the configured LLM.
3.  Parse the response and automatically write the changes to the relevant files.

### All Commands & Options

#### Configuration Management
*   `--init`: Create a new configuration interactively.
*   `--list-configs`: List all available configurations from your `configs.py`.
*   `--show-config <name>`: Display the settings for a specific configuration.

#### Core Task Execution
*   `--config <name>`: The name of the configuration to use for building context.
*   `--task "<instruction>"`: The task instruction for the LLM.
*   `--model <model_name>`: Specify a different model (e.g., `claude-3-opus`). Defaults to `gemini/gemini-1.5-flash`.

#### Context Handling
*   `--context-out [filename]`: Save the generated context to a file (defaults to `context.md`) instead of sending it to the LLM.
*   `--context-in <filename>`: Use a previously saved context file directly, skipping context generation.
*   `--update False`: A flag to prevent sending the prompt to the LLM. Useful when you only want to generate and save the context with `--context-out`.

#### Alternative Inputs
*   `--from-file <filename>`: Apply file patches directly from a local file instead of from an LLM response.
*   `--from-clipboard`: Apply file patches directly from your clipboard content.
*   `--voice True`: Use voice recognition to provide the task instruction. Requires extra dependencies.

### Setup

PatchLLM uses [LiteLLM](https://github.com/BerriAI/litellm) under the hood. Please refer to their documentation for setting up API keys (e.g., `OPENAI_API_KEY`, `GEMINI_API_KEY`) in a `.env` file and for a full list of available models.

To use the voice feature (`--voice True`), you will need to install extra dependencies:
```bash
pip install "speechrecognition>=3.10" "pyttsx3>=2.90"
# Note: speechrecognition may require PyAudio, which might have system-level dependencies.
```

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.