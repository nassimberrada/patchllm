import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import os
import re

# Skip all tests in this file if the optional dependency is not installed.
pytest.importorskip("InquirerPy")

from patchllm.main import main
from patchllm.interactive import _build_choices_recursively

# Unit test for the choice generation logic
def test_build_choices_recursively(temp_project):
    """
    Tests that the choice builder creates a correct tree structure.
    """
    choices = _build_choices_recursively(temp_project, temp_project)
    
    # CORRECTED: Use a regex to extract only the relevant part (icon + path)
    # This makes the test independent of the tree-drawing characters.
    path_extraction_pattern = re.compile(r"([📁📄]\s.*)")
    plain_choices = set()
    for choice in choices:
        match = path_extraction_pattern.search(choice)
        if match:
            plain_choices.add(match.group(1).strip())

    # Check for specific files and folders with full relative paths
    assert "📁 src/" in plain_choices
    assert "📄 main.py" in plain_choices
    assert "📄 src/component.js" in plain_choices
    
    # Check that excluded files are not present
    assert not any("data.log" in choice for choice in plain_choices)

# Integration test for the main --interactive flow with file selections
@patch('patchllm.interactive.prompt', new_callable=MagicMock)
def test_interactive_flag_flow_files(mock_prompt, temp_project, capsys):
    """
    Tests the full --interactive flag flow by mocking the user prompt
    with individual file selections.
    """
    # The mocked choices must match the tree format the user would see.
    selected_items = ['├── 📄 main.py', '│   └── 📄 src/styles.css']
    mock_prompt.return_value = [selected_items]
    
    output_file = temp_project / "context_output.md"
    
    original_cwd = os.getcwd()
    os.chdir(temp_project)
    
    try:
        with patch('sys.argv', ['patchllm', '--interactive', '--context-out', str(output_file)]):
            main()
    finally:
        os.chdir(original_cwd)
        
    # Assertions
    assert output_file.exists()
    content = output_file.read_text()
    
    assert "<file_path:" + (temp_project / 'main.py').as_posix() in content
    assert "<file_path:" + (temp_project / 'src/styles.css').as_posix() in content
    assert "def hello():" in content
    assert "body { color: red; }" in content
    assert "utils.py" not in content # Unselected file
    
    captured = capsys.readouterr()
    assert "Interactive File Selection" in captured.out

# Integration test for the main --interactive flow with folder selection
@patch('patchllm.interactive.prompt', new_callable=MagicMock)
def test_interactive_flag_flow_folder(mock_prompt, temp_project):
    """
    Tests that selecting a folder in the interactive prompt correctly includes
    all the files within that folder.
    """
    # Mock the selection of the folder path as it would appear in the tree
    selected_items = ['└── 📁 src/']
    mock_prompt.return_value = [selected_items]
    
    output_file = temp_project / "context_output.md"
    
    original_cwd = os.getcwd()
    os.chdir(temp_project)
    
    try:
        with patch('sys.argv', ['patchllm', '--interactive', '--context-out', str(output_file)]):
            main()
    finally:
        os.chdir(original_cwd)
        
    # Assertions
    assert output_file.exists()
    content = output_file.read_text()
    
    # Check that both files from the 'src' directory are in the context
    assert "<file_path:" + (temp_project / 'src/component.js').as_posix() in content
    assert "<file_path:" + (temp_project / 'src/styles.css').as_posix() in content
    assert "console.log('component');" in content
    assert "body { color: red; }" in content
    
    # Check that a file outside the selected folder is NOT present
    assert "main.py" not in content