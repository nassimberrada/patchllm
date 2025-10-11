<p align="center">
  <picture>
    <source srcset="./assets/logo_dark.png" media="(prefers-color-scheme: dark)">
    <source srcset="./assets/logo_light.png" media="(prefers-color-scheme: light)">
    <img src="./assets/logo_light.png" alt="PatchLLM Logo" height="200">
  </picture>
</p>

## About
PatchLLM is an interactive command-line agent that helps you modify your codebase. It uses an LLM to plan and execute changes, allowing you to review and approve every step.

## Key Features
- **Interactive Planning:** The agent proposes a step-by-step plan before writing any code. You stay in control.
- **Dynamic Context:** Build and modify the code context on-the-fly using powerful scope definitions (`@git:staged`, `@dir:src`, etc.).
- **Mobile-First TUI:** A clean, command-driven interface with autocompletion makes it easy to use on any device.
- **Resilient Sessions:** Automatically saves your progress so you can resume if you get disconnected.

## Getting Started

**1. Initialize a configuration file (optional):**
This creates a `scopes.py` file to define reusable file collections.
```bash
patchllm --init
```

**2. Start the Agent:**
Running `patchllm` with no arguments drops you into the interactive agentic TUI.
```bash
patchllm
```

**3. Follow the Agent Workflow:**
Inside the TUI, you direct the agent with simple slash commands.

```bash
# 1. Set the goal
>>> /task Add a health check endpoint to the API

# 2. Build the context
>>> /context @dir:src/api

# 3. Ask the agent to generate a plan
>>> /plan
1. Add a new route `/health` to `src/api/routes.py`.
2. Implement the health check logic to return a 200 OK status.

# 4. Execute the first step and review the proposed changes
>>> /run

# 5. If the changes look good, approve them
>>> /approve
```

## Agent Commands (TUI)
| Command | Description |
|---|---|
| `/task <goal>` | Sets the high-level goal for the agent. |
| `/plan [management]` | Generates a plan, or opens an interactive TUI to edit/add/remove steps. |
| `/run [all]` | Executes the next step, or all remaining steps with `/run all`. |
| `/approve` | Interactively select and apply changes from the last run. |
| `/diff [all \| file]`| Shows the full diff for the proposed changes. |
| `/retry <feedback>`| Retries the last step with new feedback. |
| `/skip` | Skips the current step and moves to the next. |
| `/revert` | Reverts the changes from the last `/approve`. |
| `/context <scope>` | Replaces the context with files from a scope. |
| `/scopes` | Opens an interactive menu to manage your saved scopes. |
| `/ask <question>` | Ask a question about the plan or code context. |
| `/refine <feedback>`| Refine the plan based on new feedback or ideas. |
| `/show [state]` | Shows the current state (goal, plan, context, history, step). |
| `/settings` | Configure the model and API keys. |
| `/help` | Shows the detailed help message. |
| `/exit` | Exits the agent session. |

## Headless Mode Flags
For scripting or single-shot edits, you can still use the original flags.

| Flag | Alias | Description |
|---|---|---|
| `-p`, `--patch` | **Main action:** Query the LLM and apply file changes. |
| `-t`, `--task` | Provide a specific instruction to the LLM. |
| `-s`, `--scope` | Use a static scope from `scopes.py` or a dynamic one. |
| `-r`, `--recipe` | Use a predefined task from `recipes.py`. |
| `-in`, `--interactive` | Interactively build the context by selecting files. |
| `-i`, `--init` | Create a new `scopes.py` file. |
| `-sl`, `--list-scopes`| List all available scopes. |
| `-ff`, `--from-file` | Apply patches from a local file. |
| `-fc`, `--from-clipboard` | Apply patches from the system clipboard. |
| `-m`, `--model` | Specify a different model (default: `gemini/gemini-1.5-flash`). |
| `-v`, `--voice` | Enable voice interaction (requires voice dependencies). |

## Setup
PatchLLM uses [LiteLLM](https://github.com/BerriAI/litellm). Set up your API keys (e.g., `OPENAI_API_KEY`, `GEMINI_API_KEY`) in a `.env` file.

The interactive TUI requires `prompt_toolkit` and `InquirerPy`. You can install all core dependencies with:```bash
pip install -r requirements.txt
```

Optional features require extra dependencies:
```bash
# For URL support in scopes
pip install "patchllm[url]"

# For voice commands (in headless mode)
pip install "patchllm[voice]"
```

## License
This project is licensed under the MIT License.