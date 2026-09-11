"""
AST Verification Gate Module for CUA-Sentinel.

Executes non-AI deterministic code checking using Python's AST parser to prevent
token morphing bugs (e.g. sMile1 vs smile1), hallucinated signatures, and syntax errors.
"""

import ast
import logging
from typing import Dict, Any, List, Tuple

logger = logging.getLogger(__name__)

class VerificationGate:
    def __init__(self, max_retries: int = 5):
        self.max_retries = max_retries
        self.retry_counts: Dict[str, int] = {}

    def verify_python_code(self, code_snippet: str, expected_symbols: List[str] = None) -> Tuple[bool, List[str]]:
        """
        Parses Python code snippet via AST and checks for syntax errors & case-sensitive symbols.
        Returns (is_valid, error_messages).
        """
        errors = []
        if not code_snippet or not code_snippet.strip():
            return False, ["Code snippet is empty."]

        # 1. Check AST Syntax Validity
        try:
            tree = ast.parse(code_snippet)
        except SyntaxError as se:
            logger.warning(f"AST SyntaxError detected: {se}")
            return False, [f"AST SyntaxError at line {se.lineno}: {se.msg}"]

        # 2. Extract defined functions, classes, and assigned variables
        defined_symbols = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                defined_symbols.add(node.name)
            elif isinstance(node, ast.AsyncFunctionDef):
                defined_symbols.add(node.name)
            elif isinstance(node, ast.ClassDef):
                defined_symbols.add(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        defined_symbols.add(target.id)

        # 3. Check Case-Sensitive Expected Symbols
        if expected_symbols:
            for expected in expected_symbols:
                # Check exact case match
                if expected not in defined_symbols:
                    # Check if lowercased match exists (case morphing bug)
                    case_mismatches = [s for s in defined_symbols if s.lower() == expected.lower()]
                    if case_mismatches:
                        errors.append(
                            f"Symbol Case Morphing Error: Expected '{expected}', but found '{case_mismatches[0]}'. Case must match exactly."
                        )
                    else:
                        errors.append(f"Missing Required Symbol: Expected '{expected}' was not defined in generated code.")

        is_valid = len(errors) == 0
        return is_valid, errors

    def evaluate_tapered_retry(self, task_id: str) -> Dict[str, Any]:
        """
        Tracks retry count for a task and applies tapered retry guardrails.
        """
        current_retries = self.retry_counts.get(task_id, 0) + 1
        self.retry_counts[task_id] = current_retries

        if current_retries == 1 or current_retries == 2:
            return {
                "action": "retry_standard",
                "attempt": current_retries,
                "prompt_injection": None
            }
        elif current_retries in (3, 4):
            return {
                "action": "retry_tapered",
                "attempt": current_retries,
                "prompt_injection": "ATTENTION: Previous attempts failed verification. Discard current approach and write a completely clean implementation adhering strictly to symbol names."
            }
        else:
            # Reached max retries (5) -> Hard Halt
            return {
                "action": "hard_halt",
                "attempt": current_retries,
                "prompt_injection": "FATAL: Maximum retry limit (5) reached. Task halted gracefully to preserve system resources."
            }

    def reset_retry(self, task_id: str):
        if task_id in self.retry_counts:
            del self.retry_counts[task_id]

verification_gate = VerificationGate()
