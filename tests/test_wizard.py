import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import os
import sys
import textwrap

pytest.importorskip("InquirerPy")
# --- MODIFICATION: Conditionally import pyperclip ---
try:
    import pyperclip
except ImportError:
    pyperclip = None

from patchllm.cli.entrypoint import main
from patchllm.utils import load_from_py_file

@pytest.fixture
def mock_wizard_prompts():
    """Fixture to mock all InquirerPy prompts in the handlers module."""
    with patch('patchllm.cli.handlers.prompt') as mock:
        yield mock

@pytest.fixture
def mock_llm_for_wizard():
    """Fixture to mock the LLM query function where it is called."""
    with patch('patchllm.chat.chat.run_llm_query') as mock:
        yield mock

# --- MODIFICATION: New fixture for a simple project to patch ---
@pytest.fixture
def patchable_project(tmp_path):
    proj = tmp_path / "patch_proj"
    proj.mkdir()
    (proj / "main.py").write_text("old content")
    return proj

def test_no_args_triggers_wizard_flow(temp_project):
    os.chdir(temp_project)
    with patch('patchllm.cli.entrypoint.handle_interactive_wizard_flow') as mock_handler:
        with patch.object(sys, 'argv', ['patchllm']):
            main()
    mock_handler.assert_called_once()

def test_wizard_full_update_code_flow(mock_wizard_prompts, mock_llm_for_wizard, temp_project, temp_scopes_file, temp_recipes_file):
    new_file = temp_project / "new_wizard_file.py"
    mock_llm_for_wizard.return_value = f"<file_path:{new_file.as_posix()}>\n```python\n# wizard code\n```"
    
    with patch('patchllm.chat.chat.prompt') as mock_chat_prompts:
        mock_wizard_prompts.side_effect = [
            {"action": "new_task"},
            {"source": "saved"},
            {"scope": "base"},
            {"action": "Proceed"},
            {"action": "Update code with LLM"},
            {"action": "exit"},
        ]

        mock_chat_prompts.side_effect = [
            {"choice": ("manual", None)},
            {"task": "create a new file"},
            {"confirm": True},
            {"action": "apply"}
        ]

        os.chdir(temp_project)
        with patch.dict('os.environ', {
            'PATCHLLM_SCOPES_FILE': temp_scopes_file.as_posix(),
            'PATCHLLM_RECIPES_FILE': temp_recipes_file.as_posix()
        }):
            with patch.object(sys, 'argv', ['patchllm']):
                main()

    assert mock_wizard_prompts.call_count == 6
    assert mock_chat_prompts.call_count == 4
    mock_llm_for_wizard.assert_called_once()
    assert new_file.exists()
    assert new_file.read_text() == "# wizard code"

def test_wizard_save_to_file_flow(mock_wizard_prompts, temp_project, temp_scopes_file):
    output_file = temp_project / "wizard_context.md"
    
    mock_wizard_prompts.side_effect = [
        {"action": "new_task"},
        {"source": "saved"},
        {"scope": "js_and_css"},
        {"action": "Proceed"},
        {"action": "Save context to file"},
        {"path": str(output_file)},
        {"action": "back"},
        {"action": "exit"},
    ]

    os.chdir(temp_project)
    with patch.dict('os.environ', {'PATCHLLM_SCOPES_FILE': temp_scopes_file.as_posix()}):
        with patch.object(sys, 'argv', ['patchllm']):
            main()

    assert output_file.exists()
    content = output_file.read_text()
    assert "src/component.js" in content
    assert "src/styles.css" in content
    assert "main.py" not in content

def test_wizard_scope_management_flow(mock_wizard_prompts, temp_scopes_file, capsys):
    mock_wizard_prompts.side_effect = [
        {"action": "manage_scopes"},
        {"action": "List scopes"},
        {"action": "exit"},
    ]

    with patch.dict('os.environ', {'PATCHLLM_SCOPES_FILE': temp_scopes_file.as_posix()}):
        with patch.object(sys, 'argv', ['patchllm']):
            main()

    captured = capsys.readouterr()
    assert "Available scopes" in captured.out
    assert "base" in captured.out
    assert "js_and_css" in captured.out

# --- MODIFICATION: New test for the external patch flow ---
@pytest.mark.skipif(pyperclip is None, reason="pyperclip is not installed")
@patch('patchllm.cli.handlers.prompt')
@patch('patchllm.patcher.prompt')
@patch('pyperclip.paste')
def test_wizard_apply_patch_from_clipboard_flow(mock_pyperclip_paste, mock_patcher_prompt, mock_wizard_prompts, patchable_project):
    # --- Mocks Setup ---
    os.chdir(patchable_project)
    main_py = patchable_project / "main.py"
    
    # Mock the wizard's main menu and the patch source selection
    mock_wizard_prompts.side_effect = [
        {"action": "apply_patch"},
        {"source": "clipboard"},
        {"action": "exit"},
    ]
    
    # Mock the clipboard content (ambiguous format)
    patch_content = textwrap.dedent(f"""
        Here is the update for main.py
        ```
        new content
        ```
    """)
    mock_pyperclip_paste.return_value = patch_content
    
    # Mock the prompts within the patcher itself (file selection and confirmation)
    mock_patcher_prompt.side_effect = [
        {"file": "main.py"},
        {"confirm": True}
    ]

    # --- Run Test ---
    with patch.object(sys, 'argv', ['patchllm']):
        main()

    # --- Assertions ---
    assert "new content" in main_py.read_text()
    mock_pyperclip_paste.assert_called_once()
    assert mock_wizard_prompts.call_count == 3
    assert mock_patcher_prompt.call_count == 2


def test_wizard_exit_flow(mock_wizard_prompts, capsys):
    mock_wizard_prompts.side_effect = [{"action": "exit"}]

    with patch.object(sys, 'argv', ['patchllm']):
        main()

    captured = capsys.readouterr()
    assert "Exiting PatchLLM Wizard" in captured.out
    assert "How would you like to build the context?" not in captured.out

def test_wizard_save_as_scope_flow(mock_wizard_prompts, temp_project, temp_scopes_file):
    os.chdir(temp_project)
    
    mock_wizard_prompts.side_effect = [
        {"action": "new_task"},
        {"source": "saved"},
        {"scope": "js_and_css"},
        {"action": "Proceed"},
        {"action": "Save this context as a new scope"},
        {"name": "my_web_files"},
        {"action": "back"},
        {"action": "exit"},
    ]

    with patch.dict('os.environ', {'PATCHLLM_SCOPES_FILE': temp_scopes_file.as_posix()}):
        with patch.object(sys, 'argv', ['patchllm']):
            main()

    updated_scopes = load_from_py_file(temp_scopes_file, "scopes")
    assert "my_web_files" in updated_scopes
    new_scope_data = updated_scopes["my_web_files"]
    assert new_scope_data["path"] == "."
    expected_files = sorted(['src/component.js', 'src/styles.css'])
    assert sorted(new_scope_data["include_patterns"]) == expected_files
    assert new_scope_data["exclude_patterns"] == []