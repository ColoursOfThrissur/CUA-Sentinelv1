import os
import re
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _safe_path(base_root: str, relative_path: str) -> Path:
    """
    Resolves path and ensures it stays within the allowed workspace root.
    Raises PermissionError on path traversal attempts.
    """
    base = Path(base_root).resolve()
    target = (base / relative_path).resolve()
    if not str(target).startswith(str(base)):
        raise PermissionError(f"Path traversal blocked: {relative_path}")
    return target


class FileIOTool:
    """
    All file operations are scoped to the workspace root.
    Agents never get raw filesystem access — they call this tool.
    """

    def __init__(self, workspace_root: str):
        self.root = Path(workspace_root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def read(self, relative_path: str) -> str:
        path = _safe_path(self.root, relative_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {relative_path}")
        return path.read_text(encoding="utf-8")

    def write(self, relative_path: str, content: str) -> None:
        path = _safe_path(self.root, relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        logger.info(f"Wrote file: {relative_path}")

    def list_dir(self, relative_path: str = "") -> list:
        path = _safe_path(self.root, relative_path)
        if not path.is_dir():
            raise NotADirectoryError(f"Not a directory: {relative_path}")
        return [str(p.relative_to(self.root)) for p in path.iterdir()]

    def delete(self, relative_path: str) -> None:
        path = _safe_path(self.root, relative_path)
        if path.is_file():
            path.unlink()
            logger.info(f"Deleted file: {relative_path}")
        else:
            raise FileNotFoundError(f"File not found: {relative_path}")
