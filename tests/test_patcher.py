import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import subprocess
import textwrap
import shutil

from patchllm.patcher import apply_external_patch

patch_installed = shutil.which("patch") is not None

@pytest.fixture
def temp_project_for_patching(tmp_path):
    proj = tmp_path / "patch_proj"
    proj.mkdir()
    (proj / "main.py").write_text("def hello():\n    print('old world')")
    (proj / "utils.py").write_text("# Initial utility file")
    
    subprocess.run(["git", "init"], cwd=proj, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=proj, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=proj, check=True, capture_output=True)
    return proj

@pytest.mark.skipif(not patch_installed, reason="The 'patch' command-line utility is not installed.")
def test_apply_patch_with_diff_format(temp_project_for_patching):
    diff_content = """--- a/main.py
+++ b/main.py
@@ -1,2 +1,2 @@
 def hello():
-    print('old world')
+    print('new world')
"""
    
    main_py = temp_project_for_patching / "main.py"
    original_content = main_py.read_text()
    
    apply_external_patch(diff_content, temp_project_for_patching)
    
    new_content = main_py.read_text()
    assert original_content != new_content
    assert "print('new world')" in new_content

def test_apply_patch_with_patchllm_format(temp_project_for_patching):
    main_py = temp_project_for_patching / "main.py"
    patchllm_content = f"<file_path:{main_py.as_posix()}>\n```python\ndef hello():\n    print('patched world')\n```"
    
    apply_external_patch(patchllm_content, temp_project_for_patching)
    
    assert "print('patched world')" in main_py.read_text()

@patch('patchllm.patcher.prompt')
def test_apply_patch_interactive_flow(mock_prompt, temp_project_for_patching):
    mock_prompt.side_effect = [
        {"file": "utils.py"},
        {"confirm": True}
    ]

    ambiguous_content = textwrap.dedent("""
        Sure, here is the code you requested for the utility file:
        ```python
        def new_utility_function():
            return True
        ```
        I hope this helps!
    """)
    utils_py = temp_project_for_patching / "utils.py"
    
    apply_external_patch(ambiguous_content, temp_project_for_patching)

    assert "def new_utility_function():" in utils_py.read_text()
    assert mock_prompt.call_count == 2