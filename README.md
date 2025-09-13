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
PatchLLM is designed to be used directly from your terminal. The core workflow is to define a **scope** of files, provide a **task**, and choose an **action** (like patching files directly).

### 1. Initialize a Scope
The easiest way to get started is to run the interactive initializer. This will create a `scopes.py` file for you, which holds your saved scopes.

```bash
patchllm --init
```

This will guide you through creating your first scope, including setting a base path and file patterns. You can add multiple scopes to this file for different projects or tasks.

A generated `scopes.py` might look like this:
```python
# scopes.py
scopes = {
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
Use the `patchllm` command with a scope, a task, and an action flag like `--patch` (`-p`).

```bash
# Apply a change using the 'default' scope and the --patch action
patchllm -s default -t "Add type hints to the main function in main.py" -p
```

The tool will then:
1.  Build a context from the files and URLs matching your `default` scope.
2.  Send the context and your task to the configured LLM.
3.  Parse the response and automatically write the changes to the relevant files.

### All Commands & Options

#### Core Patching Flow
*   `-s, --scope <name>`: Name of the scope to use from your `scopes.py` file.
*   `-t, --task "<instruction>"`: The task instruction for the LLM.
*   `-p, --patch`: Query the LLM and directly apply the file updates from the response. **This is the main action flag.**

#### Scope Management
*   `-i, --init`: Create a new scope interactively.
*   `-sl, --list-scopes`: List all available scopes from your `scopes.py` file.
*   `-ss, --show-scope <name>`: Display the settings for a specific scope.

#### I/O & Context Management
*   `-co, --context-out [filename]`: Export the generated context to a file (defaults to `context.md`) instead of running a task.
*   `-ci, --context-in <filename>`: Use a previously saved context file as input for a task.
*   `-tf, --to-file [filename]`: Send the LLM response to a file (defaults to `response.md`) instead of patching directly.
*   `-tc, --to-clipboard`: Copy the LLM response to the clipboard.
*   `-ff, --from-file <filename>`: Apply patches from a local file instead of an LLM response.
*   `-fc, --from-clipboard`: Apply patches directly from your clipboard content.

#### General Options
*   `--model <model_name>`: Specify a different model (e.g., `gpt-4o`). Defaults to `gemini/gemini-1.5-flash`.
*   `--voice`: Enable voice recognition to provide the task instruction.

### Setup

PatchLLM uses [LiteLLM](https://github.com/BerriAI/litellm) under the hood. Please refer to their documentation for setting up API keys (e.g., `OPENAI_API_KEY`, `GEMINI_API_KEY`) in a `.env` file and for a full list of available models.

To use the voice feature (`--voice`), you will need to install extra dependencies:
```bash
pip install "speechrecognition>=3.10" "pyttsx3>=2.90"
# Note: speechrecognition may require PyAudio, which might have system-level dependencies.
```

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.