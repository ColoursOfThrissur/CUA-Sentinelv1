"""Unit tests for the extracted ProjectWriteService."""

import os
import sys
import tempfile
import pytest

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from core.project_write_service import ProjectWriteService
from core.path_security import PathSecurityViolation


@pytest.fixture
def write_service():
    return ProjectWriteService()


@pytest.fixture
def temp_project():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create minimal project structure
        src_dir = os.path.join(tmpdir, "src")
        os.makedirs(src_dir, exist_ok=True)
        yield tmpdir


def test_parse_file_plan(write_service):
    """Parses code blocks with filepath directives correctly."""
    text = """
Here is the code:

```python
# filepath: src/main.py
def hello():
    return "world"
```

And another file:

```tsx
// filepath: src/App.tsx
export const App = () => <div>Hello</div>;
```
"""
    ops = write_service.parse_file_plan(text)
    assert len(ops) == 2
    assert ops[0]["rel_path"] == "src/main.py"
    assert "def hello():" in ops[0]["content"]
    assert ops[1]["rel_path"] == "src/App.tsx"
    assert "export const App" in ops[1]["content"]


def test_execute_write_plan_creates_and_verifies_files(write_service, temp_project):
    """Executes write plan, verifies files on disk, and heals missing relative CSS imports."""
    file_ops = [
        {
            "rel_path": "src/utils.py",
            "content": "def add(a, b):\n    return a + b",
        },
        {
            "rel_path": "src/styles.tsx",
            "content": "import './theme.css';\nexport const theme = {};",
        },
    ]

    written = write_service.execute_write_plan(temp_project, file_ops)
    assert "src/utils.py" in written
    assert "src/styles.tsx" in written

    # Verify physical file existence
    utils_path = os.path.join(temp_project, "src", "utils.py")
    assert os.path.exists(utils_path)
    with open(utils_path, "r", encoding="utf-8") as f:
        assert "def add(a, b):" in f.read()

    # Verify auto-repaired CSS file
    css_path = os.path.join(temp_project, "src", "theme.css")
    assert os.path.exists(css_path)


def test_rollback_on_partial_failure(write_service, temp_project):
    """Rolls back newly created files when a write operation fails security boundary."""
    # Write initial file
    initial_ops = [{"rel_path": "src/safe.py", "content": "SAFE = True"}]
    write_service.execute_write_plan(temp_project, initial_ops)
    safe_path = os.path.join(temp_project, "src", "safe.py")
    assert os.path.exists(safe_path)

    # Attempt to write a valid file AND a path traversal attempt
    failing_ops = [
        {"rel_path": "src/new_file.py", "content": "NEW = True"},
        {"rel_path": "../../evil.py", "content": "MALICIOUS = True"},
    ]

    written = write_service.execute_write_plan(temp_project, failing_ops, enable_rollback=True)
    assert written == []

    # Verify newly created file was rolled back and deleted
    new_file_path = os.path.join(temp_project, "src", "new_file.py")
    assert not os.path.exists(new_file_path)

    # Original safe file still exists intact
    assert os.path.exists(safe_path)
