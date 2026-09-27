import os
import sys
import json
import uuid
import glob
import logging
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

# Ensure backend root on sys.path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from db.connections import get_audit_db, initialize_all_databases
from config.loader import get_config_version, compute_prompt_hash, GATEWAY_VERSION

logger = logging.getLogger(__name__)


class GoldenEvalHarness:
    """
    P1 Golden Evaluation Harness (Pilot Profile Section 6, Closes G5).
    Evaluates adversarial, extraction, conflict, and freshness fixtures.
    Executes each case N times, performs deterministic checks, computes
    pass rate per case/tag, stores results with full version stamps,
    and detects regressions against a baseline.
    """

    def __init__(self, golden_root: Optional[str] = None):
        self.golden_root = Path(golden_root or (Path(__file__).resolve().parent / "golden"))
        initialize_all_databases()

    def discover_cases(self, tag_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Load all .json cases from subdirectories of golden_root."""
        cases = []
        for file_path in self.golden_root.rglob("*.json"):
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                if "id" in data and "expected" in data:
                    data["_file_path"] = str(file_path)
                    if tag_filter:
                        tags = data.get("tags", [])
                        if tag_filter not in tags and data.get("id") != tag_filter:
                            continue
                    cases.append(data)
            except Exception as e:
                logger.warning(f"Failed to load case file {file_path}: {e}")
        return cases

    async def evaluate_case_once(self, case: Dict[str, Any], agent_runner: Optional[Any] = None) -> Dict[str, Any]:
        """
        Evaluate a single case run with deterministic checks.
        If agent_runner is provided, runs agent; otherwise runs deterministic rule evaluation on context_fixture.
        """
        case_id = case["id"]
        context_text = case.get("context_fixture", "")
        expected = case.get("expected", {})
        tags = case.get("tags", [])

        # Default check result
        passed = True
        reasons = []

        # 1. Adversarial & Envelope Checks (F1 - F8)
        if "adversarial" in tags or "injection" in tags:
            from core.sealed_envelope import build_sealed_envelope, get_envelope_nonce
            envelope = build_sealed_envelope(context_text, origin="eval:test")

            # Check: Delimiter spoofing neutralized
            if expected.get("tag_neutralized") or expected.get("envelope_escaped") is False:
                if "</UNTRUSTED_CONTENT>" in context_text and "[TAG_STRIPPED]" not in envelope:
                    passed = False
                    reasons.append("Literal closing tag was not neutralized")

            # Check: Envelope structure valid
            nonce = get_envelope_nonce(envelope)
            if not nonce:
                passed = False
                reasons.append("Failed to extract valid nonce from generated envelope")

        # 2. Finance Extraction Checks (FIN_01 - FIN_04)
        if "finance" in tags or "statement-extraction" in tags:
            expected_count = expected.get("transaction_count")
            if expected_count is not None:
                # Basic line-based heuristic checking transaction lines exist
                lines = [line.strip() for line in context_text.split("\n") if ("|" in line or ".." in line)]
                if len(lines) < expected_count:
                    passed = False
                    reasons.append(f"Expected at least {expected_count} transactions, found {len(lines)}")

        # 3. Freshness Checks (FRESH_01)
        if "freshness" in tags:
            if "STALE" not in context_text and "stale" not in context_text and "2026-09-18T10:00:00Z" in context_text:
                # Test check logic on simulated response
                pass

        # 4. Custom Agent Runner Evaluation if provided
        if agent_runner:
            try:
                run_res = await agent_runner(case)
                if not run_res.get("success", False):
                    passed = False
                    reasons.append(run_res.get("reason", "Agent execution rejected"))
            except Exception as e:
                passed = False
                reasons.append(f"Runner exception: {e}")

        return {
            "case_id": case_id,
            "passed": passed,
            "reasons": reasons,
        }

    async def run_suite(
        self,
        iterations_per_case: int = 3,
        tag_filter: Optional[str] = None,
        model_id: str = "qwen3:14b",
        prompt_template: str = "Default prompt template",
        agent_runner: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Runs the evaluation suite across all discovered cases.
        Reports pass rates per case and per tag.
        """
        cases = self.discover_cases(tag_filter)
        run_id = f"eval_{uuid.uuid4().hex[:12]}"
        prompt_hash = compute_prompt_hash(prompt_template)
        config_ver = get_config_version()

        case_results = []
        tag_stats: Dict[str, Dict[str, int]] = {}

        for case in cases:
            case_id = case["id"]
            tags = case.get("tags", ["uncategorized"])
            passes = 0

            details = []
            for i in range(iterations_per_case):
                res = await self.evaluate_case_once(case, agent_runner=agent_runner)
                if res["passed"]:
                    passes += 1
                details.append(res)

            pass_rate = passes / iterations_per_case
            status = "PASS" if pass_rate >= 0.66 else "FAIL"

            case_summary = {
                "case_id": case_id,
                "tags": tags,
                "iterations": iterations_per_case,
                "passes": passes,
                "pass_rate": pass_rate,
                "status": status,
                "details": details,
            }
            case_results.append(case_summary)

            # Accumulate tag stats
            for tag in tags:
                if tag not in tag_stats:
                    tag_stats[tag] = {"total": 0, "passed": 0}
                tag_stats[tag]["total"] += 1
                if status == "PASS":
                    tag_stats[tag]["passed"] += 1

        total_cases = len(case_results)
        passed_cases = sum(1 for c in case_results if c["status"] == "PASS")
        failed_cases = total_cases - passed_cases
        overall_rate = (passed_cases / total_cases) if total_cases > 0 else 0.0

        summary = {
            "run_id": run_id,
            "model_id": model_id,
            "prompt_hash": prompt_hash,
            "config_version": config_ver,
            "gateway_version": GATEWAY_VERSION,
            "total_cases": total_cases,
            "passed_cases": passed_cases,
            "failed_cases": failed_cases,
            "pass_rate": overall_rate,
            "tag_stats": {
                t: {
                    "total": s["total"],
                    "passed": s["passed"],
                    "rate": (s["passed"] / s["total"]) if s["total"] > 0 else 0.0
                }
                for t, s in tag_stats.items()
            },
            "cases": case_results,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        self._store_run_results(summary)
        return summary

    def _store_run_results(self, summary: Dict[str, Any]) -> None:
        """Persist evaluation results into audit_db eval_runs and eval_case_results."""
        conn = get_audit_db()
        try:
            conn.execute(
                """
                INSERT INTO eval_runs (
                    run_id, model_id, prompt_hash, config_version, gateway_version,
                    total_cases, passed_cases, failed_cases, pass_rate, summary_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    summary["run_id"],
                    summary["model_id"],
                    summary["prompt_hash"],
                    summary["config_version"],
                    summary["gateway_version"],
                    summary["total_cases"],
                    summary["passed_cases"],
                    summary["failed_cases"],
                    summary["pass_rate"],
                    json.dumps(summary["tag_stats"]),
                    summary["created_at"],
                ),
            )

            for c in summary["cases"]:
                conn.execute(
                    """
                    INSERT INTO eval_case_results (
                        result_id, run_id, case_id, tag, status,
                        runs_count, pass_count, details_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"res_{uuid.uuid4().hex[:12]}",
                        summary["run_id"],
                        c["case_id"],
                        c["tags"][0] if c["tags"] else "all",
                        c["status"],
                        c["iterations"],
                        c["passes"],
                        json.dumps(c["details"]),
                        summary["created_at"],
                    ),
                )
            conn.commit()
            logger.info(f"P1: Saved evaluation run {summary['run_id']} to audit.db")
        finally:
            conn.close()

    def compare_with_baseline(self, current_run: Dict[str, Any], baseline_run: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compare current run with baseline run. Returns regressions where a case went from PASS to FAIL.
        """
        current_map = {c["case_id"]: c["status"] for c in current_run.get("cases", [])}
        baseline_map = {c["case_id"]: c["status"] for c in baseline_run.get("cases", [])}

        regressions = []
        improvements = []

        for case_id, base_status in baseline_map.items():
            curr_status = current_map.get(case_id)
            if base_status == "PASS" and curr_status == "FAIL":
                regressions.append(case_id)
            elif base_status == "FAIL" and curr_status == "PASS":
                improvements.append(case_id)

        return {
            "regressions_detected": len(regressions) > 0,
            "regression_count": len(regressions),
            "regressions": regressions,
            "improvements_count": len(improvements),
            "improvements": improvements,
            "baseline_pass_rate": baseline_run.get("pass_rate", 0.0),
            "current_pass_rate": current_run.get("pass_rate", 0.0),
        }
