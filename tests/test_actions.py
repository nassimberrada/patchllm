import pytest
from unittest.mock import patch, MagicMock
from patchllm.agent.actions import run_tests, stage_files

@patch('subprocess.run')
def test_run_tests_passed(mock_subprocess_run):
    """
    Tests the run_tests function when pytest returns a success code.
    """
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "== 1 passed in 0.1s =="
    mock_result.stderr = ""
    mock_subprocess_run.return_value = mock_result
    
    run_tests()
    
    mock_subprocess_run.assert_called_once_with(
        ["pytest"], capture_output=True, text=True, check=False
    )

@patch('subprocess.run')
def test_run_tests_failed(mock_subprocess_run):
    """
    Tests the run_tests function when pytest returns a failure code.
    """
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = "== 1 failed in 0.2s =="
    mock_result.stderr = ""
    mock_subprocess_run.return_value = mock_result
    
    run_tests()
    
    mock_subprocess_run.assert_called_once()

@patch('subprocess.run')
def test_stage_files_all(mock_subprocess_run):
    """
    Tests staging all files with `git add .`.
    """
    mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    
    stage_files()
    
    mock_subprocess_run.assert_called_once_with(
        ["git", "add", "."], capture_output=True, text=True, check=True
    )

@patch('subprocess.run')
def test_stage_files_specific(mock_subprocess_run):
    """
    Tests staging a specific list of files.
    """
    mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    files = ["main.py", "utils.py"]
    
    stage_files(files)
    
    mock_subprocess_run.assert_called_once_with(
        ["git", "add", "main.py", "utils.py"], capture_output=True, text=True, check=True
    )