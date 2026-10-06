import os
import json
import pytest
from core.blender_pipeline.progressive_v2.manifest import BuildManifest, CompletionStatus, NodeState, prune_old_builds
from core.blender_pipeline.progressive_v2.controller import ProgressiveResult, ProgressiveController

def test_degraded_result_has_success_false():
    result = ProgressiveResult(
        success=False,
        manifest=BuildManifest.create("test"),
        completion_status=CompletionStatus.COMPLETED_DEGRADED
    )
    assert result.to_dict()["success"] is False

def test_planned_only_when_no_mcp():
    controller = ProgressiveController(model_manager=None, mcp_manager=None)
    controller.manifest = BuildManifest.create("test")
    result = controller._build_result(0.0, [])
    assert result.completion_status == CompletionStatus.PLANNED_ONLY
    assert result.success is False

def test_committed_unverified_when_readback_missing():
    # Simulate a controller with mcp, successful build, but no readback
    controller = ProgressiveController(model_manager=None, mcp_manager="fake_mcp")
    manifest = BuildManifest.create("test")
    
    # Mark root node as VERIFIED
    root = manifest.get_root()
    root.state = NodeState.VERIFIED
    controller.manifest = manifest
    
    # Assert scene_readback stat is missing
    assert "scene_readback" not in manifest.stats
    
    result = controller._build_result(0.0, [])
    assert result.completion_status == CompletionStatus.COMMITTED_UNVERIFIED
    assert result.success is False

def test_prune_by_age_keeps_recent_and_failures(tmp_path):
    builds_dir = tmp_path / "builds"
    builds_dir.mkdir()
    
    def create_build(name, age_seconds, status):
        build_dir = builds_dir / name
        build_dir.mkdir()
        manifest = {
            "root_id": "root",
            "stats": {},
            "completion_status": status,
            "nodes": {}
        }
        manifest_file = build_dir / "manifest.json"
        manifest_file.write_text(json.dumps(manifest), encoding="utf-8")
        
        # modify mtime to simulate age
        mtime = os.path.getmtime(build_dir) - age_seconds
        os.utime(build_dir, (mtime, mtime))
        os.utime(manifest_file, (mtime, mtime))
        return build_dir
    
    # 1 recent success (10s old)
    recent_success = create_build("recent_success", 10, "success")
    # 2 old successes (3 days old)
    old_success_1 = create_build("old_success_1", 3600 * 24 * 3, "success")
    old_success_2 = create_build("old_success_2", 3600 * 24 * 3, "success")
    # 1 failed build (3 days old)
    old_failure = create_build("old_failure", 3600 * 24 * 3, "failed")
    
    # prune older than 2 days
    prune_old_builds(retention_days=2, data_root=builds_dir)
    
    assert recent_success.exists()
    assert old_failure.exists()
    assert not old_success_1.exists()
    assert not old_success_2.exists()

def test_prune_does_not_remove_failed_builds(tmp_path):
    builds_dir = tmp_path / "builds"
    builds_dir.mkdir()
    
    build_dir = builds_dir / "very_old_failure"
    build_dir.mkdir()
    manifest = {
        "root_id": "root",
        "stats": {},
        "completion_status": "failed",
        "nodes": {}
    }
    manifest_file = build_dir / "manifest.json"
    manifest_file.write_text(json.dumps(manifest), encoding="utf-8")
    
    mtime = os.path.getmtime(build_dir) - (3600 * 24 * 30) # 30 days
    os.utime(build_dir, (mtime, mtime))
    os.utime(manifest_file, (mtime, mtime))
    
    prune_old_builds(retention_days=2, data_root=builds_dir)
    
    assert build_dir.exists()
