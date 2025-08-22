<p align="center">
  <picture>
    <source srcset="./assets/logo_dark.png" media="(prefers-color-scheme: dark)">
    <source srcset="./assets/logo_light.png" media="(prefers-color-scheme: light)">
    <img src="./assets/logo_light.png" alt="PatchLLM Logo" height="200">
  </picture>
</p>

## About
PatchLLM lets you flexibly build LLM context from your codebase using search patterns, and automatically edit files from the LLM response in a couple lines of code. 

## Usage
Here's a basic example of how to use the `Assistant` class:

```python
from main import Assistant

assistant = Assistant()

context = assistant.collect(config_name="default")
>> The following files were extracted:
>> my_project
>> ├── README.md
>> ├── configs.py
>> ├── context.py
>> ├── main.py
>> ├── parser.py
>> ├── requirements.txt
>> ├── systems.py
>> └── utils.py

assistant.update("Fix any bug in these files", context=context)
>> Wrote 5438 bytes to '/my_project/context.py'
>> Wrote 1999 bytes to '/my_project/utils.py'
>> Wrote 2345 bytes to '/my_project/main.py'
```

You can decide which files to include / exclude from the prompt by adding a config in `configs.py`, specifying:
 - `path`: The root path from which to perform the file search
 - `include_patterns`: A list of glob patterns for files to include. e.g `[./**/*]`
 - `exclude_patterns`: A list of glob patterns for files to exlucde. e.g `[./*.md]`
 - `search_word`: A list of keywords included in the target files. e.g  `["config"]`
 - `exclude_extensions`: A list of file extensions to exclude. e.g `[.jpg]`

### Setup

PatchLLM uses [LiteLLM](https://github.com/BerriAI/litellm) under the hood. Please refer to their documentation for environment variable naming and available models.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.