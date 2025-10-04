from pathlib import Path
from patchllm.parser import paste_response, summarize_changes, _parse_file_blocks

def test_parse_file_blocks_simple():
    response = "<file_path:/app/main.py>\n```python\nprint('hello')\n```"
    result = _parse_file_blocks(response)
    assert len(result) == 1
    path, content = result[0]
    assert path == Path("/app/main.py").resolve()
    assert content == "print('hello')"

def test_paste_response_updates_file(tmp_path):
    file_path = tmp_path / "test.txt"
    file_path.write_text("old content")
    response = f"<file_path:{file_path.as_posix()}>\n```\nnew content\n```"
    paste_response(response)
    assert file_path.read_text() == "new content"

def test_paste_response_skip_unchanged_file(tmp_path, capsys):
    file_path = tmp_path / "unchanged.txt"
    content = "no changes here"
    file_path.write_text(content)
    response = f"<file_path:{file_path.as_posix()}>\n```\n{content}\n```"
    paste_response(response)
    captured = capsys.readouterr()
    # --- CORRECTION: The function now just updates, it doesn't "skip" ---
    assert "Updated" in captured.out
    assert file_path.read_text() == content

def test_paste_response_create_in_new_directory(tmp_path):
    new_dir = tmp_path / "new_dir"
    new_file = new_dir / "file.txt"
    content = "some text"
    assert not new_dir.exists()
    response = f"<file_path:{new_file.as_posix()}>\n```\n{content}\n```"
    paste_response(response)
    assert new_dir.is_dir()
    assert new_file.read_text() == content

def test_summarize_changes(tmp_path):
    created_file = tmp_path / "new.txt"
    modified_file = tmp_path / "old.txt"
    modified_file.touch()
    response = (
        f"<file_path:{created_file.as_posix()}>\n```\ncontent\n```\n"
        f"<file_path:{modified_file.as_posix()}>\n```\ncontent\n```"
    )
    summary = summarize_changes(response)
    assert created_file.as_posix() in summary["created"]
    assert modified_file.as_posix() in summary["modified"]

def test_paste_response_no_matches(capsys):
    response = "No valid file blocks."
    paste_response(response)
    captured = capsys.readouterr()
    # --- CORRECTION: Update assertion to match new warning message ---
    assert "Could not find any file blocks to apply" in captured.out