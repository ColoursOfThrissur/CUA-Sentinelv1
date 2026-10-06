from pathlib import Path

import pytest

from core.blender_pipeline.progressive_v2.status_literal_guard import assert_no_legacy_status_literals


def test_status_consumers_have_no_legacy_literals():
    assert_no_legacy_status_literals(Path(__file__).resolve().parents[3])


def test_guard_rejects_planted_legacy_literal(tmp_path):
    target = tmp_path / "core" / "scheduler.py"
    target.parent.mkdir(parents=True)
    target.write_text('if build_status == "failed": pass\n', encoding="utf-8")
    with pytest.raises(AssertionError, match="core/scheduler.py:1"):
        assert_no_legacy_status_literals(tmp_path)
