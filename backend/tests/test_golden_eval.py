import os
import sys
import pytest
from pathlib import Path

# Ensure project root & backend on sys.path
root_dir = Path(__file__).resolve().parent.parent.parent
backend_dir = root_dir / "backend"
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from eval.harness import GoldenEvalHarness
from db.connections import get_audit_db


@pytest.fixture
def harness():
    return GoldenEvalHarness()


def test_discover_cases(harness):
    """P1: Discover all golden cases across adversarial, finance, conflicts, freshness, endpoint."""
    cases = harness.discover_cases()
    assert len(cases) >= 12
    ids = {c["id"] for c in cases}
    assert "F1" in ids
    assert "F4" in ids
    assert "FIN_01" in ids
    assert "CONF_01" in ids
    assert "FRESH_01" in ids
    assert "EP_01" in ids


@pytest.mark.asyncio
async def test_run_evaluation_suite(harness):
    """P1: Run eval suite and verify pass rates and audit DB persistence with version stamps."""
    summary = await harness.run_suite(iterations_per_case=2)
    assert summary["total_cases"] >= 12
    assert summary["passed_cases"] > 0
    assert summary["pass_rate"] > 0.0
    assert "run_id" in summary
    assert "prompt_hash" in summary
    assert "config_version" in summary
    assert "gateway_version" in summary

    # Verify persisted in audit.sqlite
    conn = get_audit_db()
    row = conn.execute("SELECT * FROM eval_runs WHERE run_id = ?", (summary["run_id"],)).fetchone()
    case_rows = conn.execute("SELECT * FROM eval_case_results WHERE run_id = ?", (summary["run_id"],)).fetchall()
    conn.close()

    assert row is not None
    assert row["pass_rate"] == summary["pass_rate"]
    assert len(case_rows) == summary["total_cases"]


def test_regression_detection(harness):
    """
    Acceptance test (Section 6):
    Changing model or prompt produces a visible regression flag on known cases.
    """
    baseline = {
        "run_id": "eval_base",
        "pass_rate": 1.0,
        "cases": [
            {"case_id": "F1", "status": "PASS"},
            {"case_id": "F4", "status": "PASS"},
            {"case_id": "FIN_01", "status": "PASS"},
        ],
    }

    # Simulate a run where a regression occurred on F4 (delimiter spoofing)
    regressed_run = {
        "run_id": "eval_regressed",
        "pass_rate": 0.66,
        "cases": [
            {"case_id": "F1", "status": "PASS"},
            {"case_id": "F4", "status": "FAIL"},  # Regressed!
            {"case_id": "FIN_01", "status": "PASS"},
        ],
    }

    diff = harness.compare_with_baseline(regressed_run, baseline)
    assert diff["regressions_detected"] is True
    assert diff["regression_count"] == 1
    assert "F4" in diff["regressions"]
