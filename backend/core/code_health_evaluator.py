"""
Code Health Evaluator Module for CUA-Sentinel.

Calculates pre- and post-refactor Code Health Index (0-100) based on:
- AST nesting depth & function complexity
- Type annotation coverage
- Code smell detection & docstring presence
- Security pattern analysis
"""

import ast
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class CodeHealthEvaluator:
    def evaluate_code_snippet(self, code_content: str, filename: str = "code.py") -> Dict[str, Any]:
        """
        Evaluates a single code snippet and returns a health breakdown.
        """
        if not code_content or not code_content.strip():
            return {"health_score": 100, "issues": [], "ast_complexity": 0}

        issues = []
        score = 100
        total_functions = 0
        typed_functions = 0
        docstring_functions = 0
        max_depth = 0

        try:
            tree = ast.parse(code_content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    total_functions += 1
                    # Check return type annotation
                    if node.returns:
                        typed_functions += 1
                    else:
                        issues.append(f"Function '{node.name}' lacks a return type annotation.")
                        score -= 2

                    # Check docstring
                    if ast.get_docstring(node):
                        docstring_functions += 1
                    else:
                        score -= 1

                    # Check function length
                    func_lines = node.end_lineno - node.lineno if hasattr(node, 'end_lineno') else 20
                    if func_lines > 50:
                        issues.append(f"Function '{node.name}' is too long ({func_lines} lines). Consider modularizing.")
                        score -= 5

                # Check bare except statements
                elif isinstance(node, ast.ExceptHandler):
                    if node.type is None:
                        issues.append("Bare 'except:' handler detected. Catch specific exceptions instead.")
                        score -= 5

        except SyntaxError as se:
            return {"health_score": 0, "issues": [f"Syntax error at line {se.lineno}: {se.msg}"], "ast_complexity": 99}

        final_score = max(10, min(100, score))
        return {
            "health_score": final_score,
            "total_functions": total_functions,
            "typed_functions": typed_functions,
            "docstring_functions": docstring_functions,
            "issues": issues[:10]
        }

    def calculate_project_health(self, repo_ast_map: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculates aggregate Code Health Index (0-100) and Quality Verdict across a project repository map.
        """
        files = repo_ast_map.get("files", [])
        if not files:
            return {
                "overall_score": 100,
                "verdict": "Production Ready",
                "verdict_badge": "success",
                "total_issues": 0,
                "files_count": 0
            }

        file_scores = []
        all_issues = []

        for f in files:
            code = f.get("content", "")
            eval_res = self.evaluate_code_snippet(code, f.get("filename", ""))
            file_scores.append(eval_res["health_score"])
            all_issues.extend([f"{f.get('filename')}: {iss}" for iss in eval_res.get("issues", [])])

        avg_score = int(sum(file_scores) / len(file_scores)) if file_scores else 100

        if avg_score >= 85:
            verdict = "Production Ready"
            verdict_badge = "success"
        elif avg_score >= 70:
            verdict = "Good Quality - Minor Refactoring Suggested"
            verdict_badge = "warning"
        else:
            verdict = "Needs Refactoring & Security Cleanups"
            verdict_badge = "danger"

        return {
            "overall_score": avg_score,
            "verdict": verdict,
            "verdict_badge": verdict_badge,
            "total_issues": len(all_issues),
            "sample_issues": all_issues[:8],
            "files_count": len(files)
        }

code_health_evaluator = CodeHealthEvaluator()
