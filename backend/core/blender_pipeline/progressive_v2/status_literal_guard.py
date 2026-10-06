"""CI guard against reintroducing legacy V2 status comparisons in consumers."""

from __future__ import annotations

from pathlib import Path

_CONSUMERS = (
    "api/routes/blender.py",
    "core/tool_gateway.py",
    "core/scheduler.py",
    "agents/endpoint_agent.py",
)
_FORBIDDEN = ('== "SUCCESS"', '== "COMPLETED_DEGRADED"', 'build_status == "failed"')


def legacy_status_literals(root: Path) -> list[str]:
    findings: list[str] = []
    for relative in _CONSUMERS:
        path = root / relative
        if not path.exists():
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if any(literal in line for literal in _FORBIDDEN):
                findings.append(f"{relative}:{line_number}: {line.strip()}")
    return findings


def assert_no_legacy_status_literals(root: Path) -> None:
    findings = legacy_status_literals(root)
    assert not findings, "Legacy V2 status literal(s) outside outcome_policy.py:\n" + "\n".join(findings)
