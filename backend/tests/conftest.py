"""Pytest configuration — makes test output actually informative.

Problems this solves:
1. Tests passing silently while the real pipeline fails
2. No visibility into what transforms/positions were computed
3. No indication that blender tests only exercise the simulated path
"""

import logging
import math
import sys
import os
import pytest

# Ensure `backend/` is on sys.path so `from core.*` works regardless of
# whether pytest is invoked from the repo root or from backend/ directly.
_backend_dir = os.path.join(os.path.dirname(__file__), "..")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))


# ---------------------------------------------------------------------------
# Logging: capture pipeline logs and show them on failure
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def capture_pipeline_logs(caplog):
    """Capture all blender pipeline logs at DEBUG level.

    On test failure, pytest prints the captured log output so you can see
    exactly what transforms, socket resolutions, and state transitions
    happened — instead of just "FAILED".
    """
    with caplog.at_level(logging.DEBUG, logger="core.blender_pipeline"):
        yield caplog


# ---------------------------------------------------------------------------
# Transform assertion helpers (available to all tests)
# ---------------------------------------------------------------------------

def assert_position_near(actual, expected, tolerance=0.005, label=""):
    """Assert two 3D positions are within tolerance, with a clear diff message."""
    for i, axis in enumerate("XYZ"):
        diff = abs(actual[i] - expected[i])
        assert diff <= tolerance, (
            f"{label} {axis}: expected {expected[i]:.4f}, got {actual[i]:.4f} "
            f"(diff={diff:.4f}m > tolerance={tolerance}m)"
        )


def assert_rotation_near_deg(actual_rad, expected_deg, tolerance_deg=1.0, label=""):
    """Assert rotation (in radians) matches expected degrees within tolerance."""
    for i, axis in enumerate("XYZ"):
        actual_deg = math.degrees(actual_rad[i])
        diff = abs(actual_deg - expected_deg[i])
        diff = min(diff, 360 - diff)  # handle wrap-around
        assert diff <= tolerance_deg, (
            f"{label} {axis}: expected {expected_deg[i]:.1f}°, got {actual_deg:.1f}° "
            f"(diff={diff:.1f}° > tolerance={tolerance_deg}°)"
        )


@pytest.fixture
def assert_pos():
    return assert_position_near


@pytest.fixture
def assert_rot():
    return assert_rotation_near_deg


# ---------------------------------------------------------------------------
# Pytest markers
# ---------------------------------------------------------------------------

def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "blender_real: test requires a live Blender MCP connection (skipped in CI)",
    )
    config.addinivalue_line(
        "markers",
        "blender_sim: test uses the simulated (no-MCP) path — does NOT test real pipeline",
    )


def pytest_collection_modifyitems(items):
    """Auto-mark blender pipeline tests that don't have blender_real as blender_sim."""
    for item in items:
        if "blender" in item.nodeid.lower() or "pipeline" in item.nodeid.lower():
            if not any(m.name == "blender_real" for m in item.iter_markers()):
                item.add_marker(pytest.mark.blender_sim)


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Print a summary showing how many pipeline tests are simulated vs real."""
    passed = terminalreporter.stats.get("passed", [])

    sim_count = sum(
        1 for r in passed
        if hasattr(r, "keywords") and "blender_sim" in r.keywords
    )
    real_count = sum(
        1 for r in passed
        if hasattr(r, "keywords") and "blender_real" in r.keywords
    )

    if sim_count or real_count:
        terminalreporter.write_sep("-", "Blender pipeline coverage")
        terminalreporter.write_line(
            f"  Simulated (no real Blender): {sim_count} — "
            f"these do NOT validate actual Blender output"
        )
        terminalreporter.write_line(
            f"  Real Blender (MCP):          {real_count}"
        )
        if not real_count:
            terminalreporter.write_line(
                "  ⚠  Zero real Blender tests ran. "
                "Pipeline failures in Blender won't be caught here."
            )
