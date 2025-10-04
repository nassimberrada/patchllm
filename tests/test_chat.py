import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import os

pytest.importorskip("InquirerPy")

from patchllm.cli.entrypoint import main
from patchllm.chat.chat import ChatSession
from patchllm.utils import load_from_py_file
from patchllm.scopes.builder import build_context
# --- MODIFICATION: Import the new selective paste function for patching ---
from patchllm.parser import paste_response_selectively

@pytest.fixture
def mock_prompts():
    """Fixture to mock all InquirerPy prompts."""
    with patch('patchllm.chat.chat.prompt') as mock:
        yield mock

@pytest.fixture
def mock_llm():
    """Fixture to mock the LLM query function."""
    with patch('patchllm.chat.chat.run_llm_query') as mock:
        yield mock

def test_chat_session_full_flow(mock_prompts, mock_llm, temp_project, temp_scopes_file):
    # Mocks must now return dictionaries
    mock_prompts.side_effect = [
        {"task": "add a new feature"}, # Task input
        {"confirm": True},             # Confirmation to proceed
        {"action": "apply"}            # Action selection
    ]

    new_file = temp_project / "new_feature.py"
    mock_llm.return_value = f"<file_path:{new_file.as_posix()}>\n```python\n# new feature code\n```"

    os.chdir(temp_project)
    
    args = MagicMock(scope='base', model='mock-model', interactive=False)
    scopes = load_from_py_file(temp_scopes_file, "scopes")
    
    session = ChatSession(args, scopes, {})
    context_obj = build_context("base", scopes, Path(".").resolve())
    session.context = context_obj["context"]
    
    session.run_llm_interaction_loop()

    assert mock_prompts.call_count == 3
    mock_llm.assert_called_once()
    assert new_file.exists()
    assert new_file.read_text() == "# new feature code"

def test_chat_session_diff_and_cancel(mock_prompts, mock_llm, temp_project, temp_scopes_file, capsys):
    # Mocks must now return dictionaries
    mock_prompts.side_effect = [
        {"task": "update main.py"},
        {"confirm": True},
        {"action": "diff"},
        {"file": "done"}, # User exits the interactive diff viewer
        {"action": "cancel"}
    ]

    main_py = temp_project / "main.py"
    original_content = main_py.read_text()
    new_content = original_content + "\n# new line"
    mock_llm.return_value = f"<file_path:{main_py.as_posix()}>\n```python\n{new_content}\n```"

    os.chdir(temp_project)
    
    args = MagicMock(scope='base', model='mock-model', interactive=False)
    scopes = load_from_py_file(temp_scopes_file, "scopes")
    
    session = ChatSession(args, scopes, {})
    context_obj = build_context("base", scopes, Path(".").resolve())
    session.context = context_obj["context"]

    session.run_llm_interaction_loop()

    assert mock_prompts.call_count == 5
    mock_llm.assert_called_once()
    assert main_py.read_text() == original_content
    
    captured = capsys.readouterr()
    assert "Cancelled." in captured.out

# --- NEW TEST CASE ---
def test_chat_session_interactive_apply_flow(mock_prompts, mock_llm, temp_project, temp_scopes_file):
    main_py = temp_project / "main.py"
    utils_py = temp_project / "utils.py"
    main_py_original_content = main_py.read_text()
    utils_py_original_content = utils_py.read_text()

    # Define the LLM response that modifies two files
    llm_response = (
        f"<file_path:{main_py.as_posix()}>\n```python\n# main.py updated\n```\n"
        f"<file_path:{utils_py.as_posix()}>\n```python\n# utils.py updated\n```"
    )
    mock_llm.return_value = llm_response

    # Simulate the user's prompt journey
    mock_prompts.side_effect = [
        {"task": "update two files"},
        {"confirm": True},
        {"action": "interactive_apply"},
        # This is the checkbox prompt: user selects ONLY main.py
        {"selected_files": [main_py.as_posix()]},
    ]

    os.chdir(temp_project)
    
    args = MagicMock(scope='base', model='mock-model', interactive=False)
    scopes = load_from_py_file(temp_scopes_file, "scopes")
    
    session = ChatSession(args, scopes, {})
    context_obj = build_context("base", scopes, Path(".").resolve())
    session.context = context_obj["context"]

    # We patch the selective paste function directly to ensure it's called correctly
    with patch('patchllm.chat.chat.paste_response_selectively') as mock_paste:
        session.run_llm_interaction_loop()
        
        # Verify the selective paste function was called with the right arguments
        mock_paste.assert_called_once_with(llm_response, [main_py.as_posix()])

    # To be absolutely sure, we can also test the underlying function
    paste_response_selectively(llm_response, [main_py.as_posix()])

    # Assert that only the selected file was changed
    assert main_py.read_text() == "# main.py updated"
    # Assert that the unselected file remains unchanged
    assert utils_py.read_text() == utils_py_original_content
    assert mock_prompts.call_count == 4


def test_chat_flag_initiates_chat_flow(temp_project, temp_scopes_file):
    os.chdir(temp_project)
    with patch('patchllm.cli.entrypoint.handle_chat_flow') as mock_handler:
        with patch.dict('os.environ', {'PATCHLLM_SCOPES_FILE': temp_scopes_file.as_posix()}):
            with patch('sys.argv', ['patchllm', '--chat']):
                 main()
    
    mock_handler.assert_called_once()