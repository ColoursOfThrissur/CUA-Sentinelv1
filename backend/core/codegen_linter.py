"""CodegenLinter — Static AST pre-flight linter for scripts generated for Blender execution.

Ensures that before any Python script string is dispatched to Blender via MCP (execute_script),
it is statically validated for:
1. Valid Python syntax (ast.parse)
2. Undefined names / missing imports (e.g. math.radians called without import math)

Prevents runtime Blender crashes from reaching the user as opaque NameError tracebacks.
"""

import ast
import builtins
from typing import List, Set, Optional


class CodegenLintError(Exception):
    def __init__(self, missing_names: List[str], script: str):
        self.missing_names = missing_names
        self.script = script
        super().__init__(
            f"Pre-flight codegen lint failed: undefined name(s) {missing_names} used without import."
        )


def lint(script_body: str, allowed_globals: Optional[Set[str]] = None) -> List[str]:
    """Parse script_body into an AST and return list of undefined names (used without import or definition)."""
    try:
        tree = ast.parse(script_body)
    except SyntaxError as e:
        return [f"SyntaxError: {e}"]

    # Standard builtins
    builtin_names = set(dir(builtins))

    # Known injected Blender/Sentinel runtime globals
    known_globals = {"PARAMS_JSON", "bpy", "SENTINEL_OUTPUT_START", "SENTINEL_OUTPUT_END"}
    if allowed_globals:
        known_globals.update(allowed_globals)

    defined_names: Set[str] = set(builtin_names) | known_globals
    loaded_names: List[str] = []

    class ScopeVisitor(ast.NodeVisitor):
        def visit_Import(self, node: ast.Import):
            for alias in node.names:
                # e.g. import math as m -> m, import math -> math
                name = alias.asname or alias.name.split('.')[0]
                defined_names.add(name)
            self.generic_visit(node)

        def visit_ImportFrom(self, node: ast.ImportFrom):
            for alias in node.names:
                name = alias.asname or alias.name
                defined_names.add(name)
            self.generic_visit(node)

        def visit_FunctionDef(self, node: ast.FunctionDef):
            defined_names.add(node.name)
            # Add parameters to defined names in scope
            for arg in node.args.args:
                defined_names.add(arg.arg)
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
            defined_names.add(node.name)
            for arg in node.args.args:
                defined_names.add(arg.arg)
            self.generic_visit(node)

        def visit_ClassDef(self, node: ast.ClassDef):
            defined_names.add(node.name)
            self.generic_visit(node)

        def visit_Name(self, node: ast.Name):
            if isinstance(node.ctx, (ast.Store, ast.Param)):
                defined_names.add(node.id)
            elif isinstance(node.ctx, ast.Load):
                loaded_names.append(node.id)
            self.generic_visit(node)

        def visit_For(self, node: ast.For):
            if isinstance(node.target, ast.Name):
                defined_names.add(node.target.id)
            elif isinstance(node.target, (ast.Tuple, ast.List)):
                for elt in node.target.elts:
                    if isinstance(elt, ast.Name):
                        defined_names.add(elt.id)
            self.generic_visit(node)

        def visit_ListComp(self, node: ast.ListComp):
            for gen in node.generators:
                if isinstance(gen.target, ast.Name):
                    defined_names.add(gen.target.id)
            self.generic_visit(node)

    visitor = ScopeVisitor()
    visitor.visit(tree)

    # Check which loaded names are never defined or imported
    missing = []
    for name in loaded_names:
        if name not in defined_names and name not in missing:
            missing.append(name)

    return missing
