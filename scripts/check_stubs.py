"""Fail verification when production Python contains an empty implementation stub."""

from __future__ import annotations

import ast
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_ROOTS = ("backend/agents", "backend/api", "backend/core", "backend/tools")
EXCLUDED_PARTS = {"tests", "venv", ".venv", "__pycache__"}


def _body_without_docstring(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.stmt]:
    return [
        statement
        for statement in node.body
        if not (
            isinstance(statement, ast.Expr)
            and isinstance(getattr(statement, "value", None), ast.Constant)
            and isinstance(statement.value.value, str)
        )
    ]


def _is_stub(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    body = _body_without_docstring(node)
    if len(body) != 1:
        return False

    statement = body[0]
    if isinstance(statement, ast.Pass):
        return True
    if isinstance(statement, ast.Expr) and isinstance(getattr(statement, "value", None), ast.Constant):
        return statement.value.value is Ellipsis
    if isinstance(statement, ast.Raise):
        exc = statement.exc
        return isinstance(exc, ast.Call) and getattr(exc.func, "id", "") == "NotImplementedError"
    return False


def main() -> int:
    violations: list[str] = []

    for source_root in SOURCE_ROOTS:
        for path in (PROJECT_ROOT / source_root).rglob("*.py"):
            if EXCLUDED_PARTS.intersection(path.parts):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except SyntaxError as error:
                violations.append(f"syntax error: {path}:{error.lineno}: {error.msg}")
                continue

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_stub(node):
                    violations.append(f"implementation stub: {path}:{node.lineno}: {node.name}")

    if violations:
        print("Production stub check failed:", file=sys.stderr)
        print("\n".join(violations), file=sys.stderr)
        return 1

    print("Production stub check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
