<p align="center">
  <picture>
    <source srcset="./assets/logo_dark.png" media="(prefers-color-scheme: dark)">
    <source srcset="./assets/logo_light.png" media="(prefers-color-scheme: light)">
    <img src="./assets/logo_light.png" alt="PatchLLM Logo" height="200">
  </picture>
</p>

## About
PatchLLM is a command-line tool that lets you flexibly build LLM context from your codebase using search patterns and automatically apply file edits from the LLM response.

## Usage
PatchLLM is designed to be used directly from your terminal.

### 1. Define a Context
First, define which files to include in `configs.py`. You can have multiple configurations.

```python
# configs.py
configs = {
    "default": {
        "path": ".",
        "include_patterns": ["**/*.py"],
        "exclude_patterns": ["**/tests/*"],
    },
    "docs": {
        "path": ".",
        "include_patterns": ["**/*.md"],
    }
}
```

### 2. Run the Tool
Use the `patchllm` command with a config and a task instruction.

```bash
# Apply a change using the 'default' configuration
patchllm --config default --task "Add type hints to the main function in main.py"
```

The tool will then:
1.  Build a context from the files matching your configuration.
2.  Send the context and your task to the configured LLM.
3.  Parse the response and automatically write the changes to the relevant files.

### Other Commands

```bash
# List all available configurations from your configs.py
patchllm --list-configs

# Run a task using a different LLM model
patchllm --config default --task "Refactor for clarity" --model "anthropic/claude-3-haiku"

# Save the generated context to a file without sending it to the LLM
patchllm --config default --context-out context.md --update False
```

### Setup

PatchLLM uses [LiteLLM](https://github.com/BerriAI/litellm) under the hood. Please refer to their documentation for setting up API keys (e.g., `OPENAI_API_KEY`) in a `.env` file and for a full list of available models.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.