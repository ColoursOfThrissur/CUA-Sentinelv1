import os
import sys
import pytest

# Ensure backend root is on sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from core.path_security import PathSecurityGuardrail, PathSecurityViolation
from core.code_health_evaluator import CodeHealthEvaluator
from core.code_security_auditor import CodeSecurityAuditor
from core.governance import GovernanceEngine
from core.intent_classifier import IntentClassifier
from core.code_diff_engine import CodeDiffEngine
from core.verification_gate import VerificationGate
from config.loader import load_system_config, load_policy_rules, load_model_registry


# ---------------------------------------------------------------------------
# Path Security Tests
# ---------------------------------------------------------------------------
def test_path_security_blocks_c_drive_mutations():
    """Verify that any write targeting C:\\ system dirs outside project workspace is blocked."""
    guard = PathSecurityGuardrail()
    with pytest.raises(PathSecurityViolation):
        guard.validate_write_permission(r"C:\Windows\System32\evil.dll")

    with pytest.raises(PathSecurityViolation):
        guard.validate_write_permission(r"C:\secret.txt")


def test_path_security_blocks_directory_traversal():
    """Verify that path traversal sequences escaping designated boundary are blocked."""
    guard = PathSecurityGuardrail()
    with pytest.raises(PathSecurityViolation):
        guard.canonicalize_path(r"D:\Projects\SafeApp\..\..\..\Windows\evil.exe", root_boundary=r"D:\Projects\SafeApp")


def test_path_security_allows_safe_project_paths():
    """Verify that authorized project paths on D: or G: are permitted."""
    guard = PathSecurityGuardrail()
    safe_path = r"D:\Projects\DemoApp\src\main.py"
    assert guard.validate_write_permission(safe_path) is True


# ---------------------------------------------------------------------------
# Code Health Evaluator Tests
# ---------------------------------------------------------------------------
def test_code_health_evaluator_python_clean():
    """A well-typed, documented Python function should score high."""
    evaluator = CodeHealthEvaluator()
    code = '''
def calculate_area(width: float, height: float) -> float:
    """Calculate the area of a rectangle."""
    return width * height
'''
    res = evaluator.evaluate_code_snippet(code, "area.py")
    assert res["health_score"] >= 85
    assert res["total_functions"] == 1


def test_code_health_evaluator_python_penalties():
    """Functions with bare excepts receive penalties."""
    evaluator = CodeHealthEvaluator()
    code = '''
def bad_func():
    try:
        x = 1 / 0
    except:
        pass
'''
    res = evaluator.evaluate_code_snippet(code, "bad.py")
    assert res["health_score"] < 95
    assert len(res["issues"]) > 0


def test_code_health_evaluator_js_ts():
    """TypeScript/JavaScript evaluation detects console.logs and any types."""
    evaluator = CodeHealthEvaluator()
    ts_code = '''
const doWork = (param: any) => {
    console.log("debug log");
    return param;
}
'''
    res = evaluator.evaluate_code_snippet(ts_code, "handler.ts")
    assert res["health_score"] < 100
    assert any("console.log" in issue for issue in res["issues"])
    assert any("any" in issue for issue in res["issues"])


# ---------------------------------------------------------------------------
# Code Security Auditor Tests
# ---------------------------------------------------------------------------
def test_security_auditor_detects_eval():
    """Dangerous dynamic execution functions must be flagged."""
    auditor = CodeSecurityAuditor()
    code = 'user_input = "2+2"; result = eval(user_input)'
    res = auditor.audit_code_snippet(code, "runner.py")
    assert res["security_score"] < 100
    assert any(v.get("type") == "UNSAFE_CODE_EXECUTION" for v in res["vulnerabilities"])


def test_security_auditor_detects_hardcoded_keys():
    """Hardcoded API tokens, private keys, or passwords must be detected."""
    auditor = CodeSecurityAuditor()
    code = 'api_key = "sk-proj-abc12345678901234567890abcdef123"'
    res = auditor.audit_code_snippet(code, "config.py")
    assert res["security_score"] < 100
    assert len(res["vulnerabilities"]) > 0


def test_security_auditor_passes_clean_code():
    """Clean, standard code should produce 100 security score."""
    auditor = CodeSecurityAuditor()
    code = '''
import os

def get_env_variable(name: str) -> str:
    return os.environ.get(name, "")
'''
    res = auditor.audit_code_snippet(code, "env.py")
    assert res["security_score"] == 100
    assert len(res["vulnerabilities"]) == 0


# ---------------------------------------------------------------------------
# Governance & Risk Tier Tests
# ---------------------------------------------------------------------------
def test_governance_risk_levels():
    """Verify tool risk classification: read is L0, local write is L1."""
    policy = load_policy_rules()
    config = load_system_config()
    gov = GovernanceEngine(policy, config)

    p_read = gov.check_tool_permission("file_read", "task-1")
    assert p_read["risk_level"] == "L0"

    p_write = gov.check_tool_permission("file_write", "task-1")
    assert p_write["risk_level"] == "L1"


def test_governance_hitl_trigger():
    """L3 destructive actions must raise HITLRequired."""
    from core.governance import HITLRequired
    from core.queue import TaskQueue
    policy = load_policy_rules()
    config = load_system_config()
    queue = TaskQueue(config)
    gov = GovernanceEngine(policy, config)

    task_id = queue.enqueue("TEST", "HITL Test", {})
    try:
        with pytest.raises(HITLRequired):
            gov.check_tool_permission("git_push", task_id)
    finally:
        from db.connections import get_operational_db
        conn = get_operational_db()
        conn.execute("DELETE FROM hitl_pending WHERE task_id = ?", (task_id,))
        conn.execute("DELETE FROM operations WHERE task_id = ?", (task_id,))
        conn.execute("DELETE FROM task_steps WHERE task_id = ?", (task_id,))
        conn.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
        conn.commit()
        conn.close()


# ---------------------------------------------------------------------------
# Intent Classifier Tests
# ---------------------------------------------------------------------------
def test_intent_classifier_finance():
    """Finance-related queries should resolve to FINANCE intent."""
    classifier = IntentClassifier()
    res = classifier.classify("What is the current stock price of Apple ($AAPL)?")
    assert res["intent"] == "FINANCE"


def test_intent_classifier_refactor():
    """Coding/refactoring queries should resolve to REFACTOR intent."""
    classifier = IntentClassifier()
    res = classifier.classify("Refactor the database schema and improve code")
    assert res["intent"] in ("REFACTOR", "CODE_REFACTOR")


def test_intent_classifier_bookmark():
    """Bookmarking links should resolve to BOOKMARK intent."""
    classifier = IntentClassifier()
    res = classifier.classify("Bookmark this URL https://github.com/fastapi/fastapi for research")
    assert res["intent"] == "BOOKMARK"


# ---------------------------------------------------------------------------
# Code Diff Engine Tests
# ---------------------------------------------------------------------------
def test_code_diff_engine_unified_diff():
    """Diff engine should produce correct unified diff text with +/- counts."""
    engine = CodeDiffEngine()
    original = "line 1\nline 2\nline 3\n"
    modified = "line 1\nline 2 updated\nline 3\nline 4\n"
    diff_data = engine.compute_diff(original, modified, "test.txt")
    assert diff_data["additions"] >= 1
    assert "test.txt" in diff_data["diff"]


# ---------------------------------------------------------------------------
# Verification Gate Tests
# ---------------------------------------------------------------------------
def test_verification_gate_detects_syntax_error():
    """Syntax errors must fail verification with clear diagnostics."""
    gate = VerificationGate()
    broken_code = "def broken(\n  return 1"
    valid, errors = gate.verify_python_code(broken_code)
    assert valid is False
    assert len(errors) > 0


def test_verification_gate_detects_empty_stubs():
    """Incomplete stubs like NotImplementedError or pass in empty bodies should be flagged."""
    gate = VerificationGate()
    stub_code = '''
def incomplete_feature():
    raise NotImplementedError("TODO: implement later")
'''
    valid, errors = gate.verify_python_code(stub_code)
    assert valid is False
    assert any("NotImplementedError" in err or "stub" in err.lower() for err in errors)


def test_verification_gate_passes_clean_code():
    """Clean, complete code should pass verification."""
    gate = VerificationGate()
    clean_code = '''
def greet(name: str) -> str:
    return f"Hello, {name}!"
'''
    valid, errors = gate.verify_python_code(clean_code, expected_symbols=["greet"])
    assert valid is True
    assert len(errors) == 0
