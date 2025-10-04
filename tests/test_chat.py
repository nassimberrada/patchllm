import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import os

pytest.importorskip("InquirerPy")

from patchllm.cli.entrypoint import main
from patchllm.chat.chat import ChatSession
from patchllm.utils import load_from_py_file
from patchllm.scopes.builder import build_context

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
    # --- CORRECTION: side_effect now returns single values ---
    mock_prompts.side_effect = [
        "add a new feature", # Task input
        True,                # Confirmation to proceed
        "apply"              # Action selection
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
    # --- CORRECTION: side_effect now returns single values ---
    mock_prompts.side_effect = [
        "update main.py", # Task input
        True,             # Confirm proceed
        "diff",           # First action: display diff
        "cancel"          # Second action: cancel
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

    assert mock_prompts.call_count == 4
    mock_llm.assert_called_once()
    assert main_py.read_text() == original_content
    
    captured = capsys.readouterr()
    assert "--- Proposed Changes (Diff) ---" in captured.out
    assert "+# new line" in captured.out
    assert "Cancelled." in captured.out

def test_chat_flag_initiates_chat_flow(temp_project, temp_scopes_file):
    os.chdir(temp_project)
    with patch('patchllm.cli.entrypoint.handle_chat_flow') as mock_handler:
        with patch.dict('os.environ', {'PATCHLLM_SCOPES_FILE': temp_scopes_file.as_posix()}):
            with patch('sys.argv', ['patchllm', '--chat']):
                 main()
    
    mock_handler.assert_called_once()