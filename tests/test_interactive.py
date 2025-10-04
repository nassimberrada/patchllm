import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import os
import re

pytest.importorskip("InquirerPy")

from patchllm.cli.entrypoint import main
from patchllm.interactive.selector import _build_choices_recursively

def test_build_choices_recursively(temp_project):
    choices = _build_choices_recursively(temp_project, temp_project)
    path_extraction_pattern = re.compile(r"([📁📄]\s.*)")
    plain_choices = set()
    for choice in choices:
        match = path_extraction_pattern.search(choice)
        if match:
            plain_choices.add(match.group(1).strip())

    assert "📁 src/" in plain_choices
    assert "📄 main.py" in plain_choices
    assert "📄 src/component.js" in plain_choices
    assert not any("data.log" in choice for choice in plain_choices)

@patch('patchllm.interactive.selector.prompt', new_callable=MagicMock)
def test_interactive_flag_flow_files_with_fuzzy(mock_prompt, temp_project):
    selected_items = ['├── 📄 main.py', '│   └── 📄 src/styles.css']
    mock_prompt.return_value = {"selected_items": selected_items}
    
    output_file = temp_project / "context_output.md"
    original_cwd = os.getcwd()
    os.chdir(temp_project)
    try:
        with patch('sys.argv', ['patchllm', '--interactive', '--context-out', str(output_file)]):
            main()
    finally:
        os.chdir(original_cwd)
        
    assert output_file.exists()
    content = output_file.read_text()
    assert "<file_path:" + (temp_project / 'main.py').as_posix() in content
    assert "<file_path:" + (temp_project / 'src/styles.css').as_posix() in content
    assert "utils.py" not in content

@patch('patchllm.interactive.selector.prompt', new_callable=MagicMock)
def test_interactive_flag_flow_folder_with_fuzzy(mock_prompt, temp_project):
    selected_items = ['└── 📁 src/']
    mock_prompt.return_value = {"selected_items": selected_items}
    
    output_file = temp_project / "context_output.md"
    original_cwd = os.getcwd()
    os.chdir(temp_project)
    try:
        with patch('sys.argv', ['patchllm', '--interactive', '--context-out', str(output_file)]):
            main()
    finally:
        os.chdir(original_cwd)
        
    assert output_file.exists()
    content = output_file.read_text()
    assert "<file_path:" + (temp_project / 'src/component.js').as_posix() in content
    assert "<file_path:" + (temp_project / 'src/styles.css').as_posix() in content
    assert "main.py" not in content