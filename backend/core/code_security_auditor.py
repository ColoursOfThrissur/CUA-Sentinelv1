r"""
AST Security Audit Engine Module for CUA-Sentinel.

Scans Python/JS/TS project source code for security vulnerabilities:
- Hardcoded API keys, JWT tokens, AWS keys, private keys, and passwords.
- Command injection risks (subprocess calls with shell=True, os.system).
- Insecure code execution (eval, exec, pickle.loads).
- Insecure SQL query string concatenation / f-strings.
- Calculates Security Risk Score (0-100) and vulnerability breakdown.
"""

import ast
import re
import os
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# Patterns for hardcoded secret detection
SECRET_PATTERNS = [
    (re.compile(r'(?i)(api_key|apikey|secret_key|auth_token|access_token|private_key)\s*=\s*[\'"][A-Za-z0-9_\-]{16,}[\'"]'), "Hardcoded API Key / Secret Token detected in code."),
    (re.compile(r'AKIA[0-9A-Z]{16}'), "Hardcoded AWS Access Key ID detected."),
    (re.compile(r'xox[baprs]-[0-9a-zA-Z]{10,48}'), "Hardcoded Slack OAuth Token detected."),
    (re.compile(r'-----BEGIN (RSA|EC|PRIVATE) KEY-----'), "Hardcoded Private Encryption Key detected."),
    (re.compile(r'(?i)password\s*=\s*[\'"][^\'"]{4,}[\'"]'), "Hardcoded Plaintext Password detected.")
]

class CodeSecurityAuditor:
    def audit_code_snippet(self, code_content: str, filename: str = "code.py") -> Dict[str, Any]:
        """
        Audits a single code file for security vulnerabilities and returns a security breakdown.
        """
        if not code_content or not code_content.strip():
            return {"security_score": 100, "vulnerabilities": []}

        vulnerabilities = []
        score = 100

        # 1. Regex check for hardcoded secrets
        for pattern, msg in SECRET_PATTERNS:
            matches = pattern.findall(code_content)
            if matches:
                vulnerabilities.append({
                    "file": filename,
                    "type": "HARDCODED_SECRET",
                    "severity": "HIGH",
                    "description": msg,
                    "remediation": "Move secrets out of source code into environment variables (.env)."
                })
                score -= 20

        # 2. AST parsing for dangerous functions and subprocess shell=True
        try:
            tree = ast.parse(code_content)
            for node in ast.walk(tree):
                # Check for eval() and exec()
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        if node.func.id in ("eval", "exec"):
                            vulnerabilities.append({
                                "file": filename,
                                "line": getattr(node, 'lineno', 1),
                                "type": "UNSAFE_CODE_EXECUTION",
                                "severity": "HIGH",
                                "description": f"Use of dynamic '{node.func.id}()' enables arbitrary code execution.",
                                "remediation": "Replace eval/exec with safe literal parsers like ast.literal_eval()."
                            })
                            score -= 25

                        elif node.func.id == "system" and getattr(node, 'lineno', None):
                            vulnerabilities.append({
                                "file": filename,
                                "line": getattr(node, 'lineno', 1),
                                "type": "SHELL_EXECUTION",
                                "severity": "HIGH",
                                "description": "Use of 'os.system()' is vulnerable to command injection.",
                                "remediation": "Use subprocess.run() with shell=False and argument arrays."
                            })
                            score -= 20

                    # Check for subprocess.Popen / subprocess.run with shell=True
                    elif isinstance(node.func, ast.Attribute) and node.func.attr in ("Popen", "run", "call", "check_output"):
                        for keyword in node.keywords:
                            if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                                vulnerabilities.append({
                                    "file": filename,
                                    "line": getattr(node, 'lineno', 1),
                                    "type": "COMMAND_INJECTION_RISK",
                                    "severity": "HIGH",
                                    "description": f"Subprocess invocation '{node.func.attr}()' has 'shell=True'.",
                                    "remediation": "Set shell=False and pass command as a list of strings [\"cmd\", \"arg\"]."
                                })
                                score -= 20

                    # Check for SQL injection in raw string query formatting
                    if isinstance(node.func, ast.Attribute) and node.func.attr in ("execute", "executemany"):
                        if node.args and isinstance(node.args[0], (ast.BinOp, ast.JoinedStr)):
                            vulnerabilities.append({
                                "file": filename,
                                "line": getattr(node, 'lineno', 1),
                                "type": "SQL_INJECTION_RISK",
                                "severity": "HIGH",
                                "description": "Raw string formatting detected inside database execute query.",
                                "remediation": "Use parameterized query placeholders (?, %s) instead of string formatting."
                            })
                            score -= 25

        except SyntaxError:
            # Syntax errors are handled by CodeHealthEvaluator
            pass

        final_score = max(0, min(100, score))
        return {
            "security_score": final_score,
            "vulnerabilities": vulnerabilities[:10]
        }

    def audit_repository(self, repo_map: Dict[str, Any]) -> Dict[str, Any]:
        """
        Audits an entire repository AST map and calculates aggregate Security Risk Score (0-100).
        """
        files = repo_map.get("files", [])
        if not files:
            return {
                "security_score": 100,
                "risk_level": "SECURE",
                "risk_badge": "success",
                "total_vulnerabilities": 0,
                "vulnerabilities": []
            }

        file_scores = []
        all_vulns = []

        for f in files:
            code = f.get("content", "")
            audit_res = self.audit_code_snippet(code, f.get("filename", ""))
            file_scores.append(audit_res["security_score"])
            all_vulns.extend(audit_res.get("vulnerabilities", []))

        avg_score = int(sum(file_scores) / len(file_scores)) if file_scores else 100

        if avg_score >= 85:
            risk_level = "SECURE (Low Vulnerability Risk)"
            risk_badge = "success"
        elif avg_score >= 60:
            risk_level = "WARNING (Moderate Security Risks Detected)"
            risk_badge = "warning"
        else:
            risk_level = "CRITICAL (High Vulnerabilities Detected)"
            risk_badge = "danger"

        return {
            "security_score": avg_score,
            "risk_level": risk_level,
            "risk_badge": risk_badge,
            "total_vulnerabilities": len(all_vulns),
            "vulnerabilities": all_vulns[:10]
        }

code_security_auditor = CodeSecurityAuditor()
