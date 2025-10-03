from patchllm.parser import paste_response
from pathlib import Path

def test_paste_response_create_new_file(tmp_path):
    """Test creating a new file from a response block."""
    new_file_path = tmp_path / "new_file.py"
    content = "print('hello world')"
    response = f"<file_path:{new_file_path.as_posix()}>\n```python\n{content}\n```"
    
    assert not new_file_path.exists()
    paste_response(response)
    assert new_file_path.exists()
    assert new_file_path.read_text() == content

def test_paste_response_update_existing_file(tmp_path):
    """Test updating an existing file."""
    existing_file = tmp_path / "existing.py"
    existing_file.write_text("old content")
    
    new_content = "new content"
    response = f"<file_path:{existing_file.as_posix()}>\n```python\n{new_content}\n```"
    
    paste_response(response)
    assert existing_file.read_text() == new_content

def test_paste_response_skip_unchanged_file(tmp_path, capsys):
    """Test that a file is skipped if the content is identical."""
    file_path = tmp_path / "unchanged.txt"
    content = "no changes here"
    file_path.write_text(content)
    
    response = f"<file_path:{file_path.as_posix()}>\n```\n{content}\n```"
    paste_response(response)
    
    captured = capsys.readouterr()
    assert "No changes for" in captured.out
    assert "skipping" in captured.out

def test_paste_response_create_in_new_directory(tmp_path):
    """Test creating a file where the parent directory does not exist."""
    new_dir = tmp_path / "new_dir"
    new_file = new_dir / "file.txt"
    content = "some text"
    
    assert not new_dir.exists()
    response = f"<file_path:{new_file.as_posix()}>\n```\n{content}\n```"
    paste_response(response)
    
    assert new_dir.is_dir()
    assert new_file.read_text() == content

def test_paste_response_multiple_files(tmp_path):
    """Test handling a response with multiple file blocks."""
    file1 = tmp_path / "file1.py"
    content1 = "a = 1"
    file2 = tmp_path / "file2.py"
    content2 = "b = 2"
    
    response = (
        f"<file_path:{file1.as_posix()}>\n```python\n{content1}\n```\n\n"
        f"<file_path:{file2.as_posix()}>\n```python\n{content2}\n```"
    )
    
    paste_response(response)
    assert file1.read_text() == content1
    assert file2.read_text() == content2

def test_paste_response_no_matches(capsys):
    """Test a response with no valid file blocks."""
    response = "Here is some code:\n```python\nprint('hi')\n```\nBut no file path."
    paste_response(response)
    captured = capsys.readouterr()
    assert "No file paths and code blocks matching the expected format" in captured.out