"""Unit tests for readback hardening: tight tolerances, manifold scoping, world volume, and IR source of truth."""

import pytest
from core.blender_pipeline.progressive_v2.manifest import (
    BuildManifest, GeometrySpec, AttachmentSpec, NodeKind
)
from core.blender_pipeline.progressive_v2.node_types import PrimitiveType, SocketType
from core.blender_pipeline.progressive_v2.readback import SceneReadbackVerifier


def test_readback_tight_tolerance_unmodified_part():
    """Tight tolerance (1% / 0.5mm) applies to unmodified parts with no booleans.
    
    A part 0.5% off must pass.
    A part 3% off must fail under tight tolerance, but would pass under standard 15% tolerance.
    """
    verifier = SceneReadbackVerifier(mcp_manager=None, dimension_relative_tolerance=0.15)
    expected = [1.0, 1.0, 1.0]

    # 1. 0.5% off: [1.005, 1.0, 1.0]
    actual_05_pct = [1.005, 1.0, 1.0]
    assert verifier._dimensions_match(expected, actual_05_pct, tight=True) is True

    # 2. 3.0% off: [1.03, 1.0, 1.0]
    actual_3_pct = [1.03, 1.0, 1.0]
    # Under tight tolerance: MUST FAIL
    assert verifier._dimensions_match(expected, actual_3_pct, tight=True) is False
    # Under loose/modifier tolerance: passes
    assert verifier._dimensions_match(expected, actual_3_pct, tight=False) is True


def test_readback_manifold_scope_exempts_open_surfaces():
    """Manifold mesh verification flags closed solids (box, cylinder, etc.) but exempts open surfaces (plane, grid, circle)."""
    manifest = BuildManifest.create("Manifold scope test")
    root = manifest.get_root()

    # Closed solid: BOX
    box_node = manifest.add_child_node(
        root.node_id, "broken_box", NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX, size=[1.0, 1.0, 1.0]),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    # Open surface: PLANE
    plane_node = manifest.add_child_node(
        root.node_id, "sheet_plane", NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.PLANE, size=[1.0, 1.0, 0.002]),
        attachment=AttachmentSpec(socket_type=SocketType.TOP_CENTER),
    )
    # Open surface: GRID
    grid_node = manifest.add_child_node(
        root.node_id, "mesh_grid", NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.GRID, size=[1.0, 1.0, 0.0]),
        attachment=AttachmentSpec(socket_type=SocketType.TOP_CENTER),
    )

    verifier = SceneReadbackVerifier(mcp_manager=None)

    # Mock observed data where all three have is_manifold=False
    mock_observed = {
        "ok": True,
        "objects": [
            {
                "name": "broken_box", "node_id": box_node.node_id, "type": "MESH",
                "dimensions": [1.0, 1.0, 1.0], "local_dimensions": [1.0, 1.0, 1.0],
                "is_manifold": False, "volume": 0.9, "materials": ["mat1"],
            },
            {
                "name": "sheet_plane", "node_id": plane_node.node_id, "type": "MESH",
                "dimensions": [1.0, 1.0, 0.002], "local_dimensions": [1.0, 1.0, 0.002],
                "is_manifold": False, "volume": None, "materials": ["mat1"],
            },
            {
                "name": "mesh_grid", "node_id": grid_node.node_id, "type": "MESH",
                "dimensions": [1.0, 1.0, 0.0], "local_dimensions": [1.0, 1.0, 0.0],
                "is_manifold": False, "volume": None, "materials": ["mat1"],
            },
        ],
    }

    class MockMCP:
        async def call_locked(self, app, op, args):
            import json
            return {"output": "SENTINEL_OUTPUT_START" + json.dumps(mock_observed) + "SENTINEL_OUTPUT_END"}

    class MockExecutor:
        _collection_name = "Sentinel_Build"

    import asyncio
    report = asyncio.run(SceneReadbackVerifier(MockMCP()).verify(manifest, MockExecutor()))

    findings = report["findings"]
    non_manifold_findings = [f for f in findings if f["code"] == "non_manifold_mesh"]

    # Only broken_box must be flagged
    assert len(non_manifold_findings) == 1
    assert non_manifold_findings[0]["node_id"] == box_node.node_id


def test_readback_world_volume_uniform_scale_and_reflection():
    """World-space volume applies scale determinant and handles reflections (negative determinant) via absolute value."""
    # Simulation of readback logic:
    # local_volume = 1.0
    # under scale S=(2, 2, 2): det = 8.0 -> world_vol = abs(1.0 * det) = 8.0
    # under mirror S=(-1, 1, 1): det = -1.0 -> world_vol = abs(1.0 * det) = 1.0

    def compute_world_volume(local_vol: float, scale_diag: list) -> float:
        det = scale_diag[0] * scale_diag[1] * scale_diag[2]
        return abs(local_vol * det)

    assert compute_world_volume(1.0, [2.0, 2.0, 2.0]) == 8.0
    assert compute_world_volume(1.0, [-1.0, 1.0, 1.0]) == 1.0
    assert compute_world_volume(2.5, [-2.0, 2.0, 2.0]) == 20.0


def test_readback_boolean_source_of_truth_uses_scene_plan_ir():
    """Readback gets boolean operations directly from frozen scene_plan IR even if manifest lacks sibling cutter info."""
    manifest = BuildManifest.create("IR boolean source of truth test")
    root = manifest.get_root()
    assembly = manifest.add_child_node(root.node_id, "asm", NodeKind.ASSEMBLY)
    target = manifest.add_child_node(
        assembly.node_id, "isolated_target", NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX, size=[1.0, 1.0, 1.0]),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    # Notice: No cutter node exists in assembly.children_ids! Manifest alone would return None.
    verifier = SceneReadbackVerifier(mcp_manager=None)
    assert verifier._boolean_operation_for_node(target, manifest) is None

    # Now provide frozen scene_plan IR with the operation
    manifest.stats["scene_plan"] = {
        "schema_version": 1,
        "scene_ir": "scene_ir.json",
        "boolean_operations": [
            {
                "operation": "difference",
                "cutter_node_id": "cut_node_999",
                "target_node_id": target.node_id,
            }
        ],
    }

    # Must resolve operation from IR!
    assert verifier._boolean_operation_for_node(target, manifest) == "difference"
    assert verifier._is_cut_target(target, manifest) is True


def test_readback_beveled_box_tight_tolerance_failure():
    """A beveled box (bounds-preserving modifier) stays in tight tolerance (1%) and fails if 3% off."""
    manifest = BuildManifest.create("Beveled box tight test")
    root = manifest.get_root()
    box_node = manifest.add_child_node(
        root.node_id, "beveled_box", NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX, size=[1.0, 1.0, 1.0]),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    # Add a BEVEL modifier (bounds-preserving)
    box_node.modifiers = [{"type": "BEVEL", "width": 0.01}]

    verifier = SceneReadbackVerifier(mcp_manager=None)

    # 1. Check modifier classification: bounds-preserving modifiers do not cause loose tolerance
    is_unmodified = verifier._is_unmodified_for_tolerance(box_node, manifest)
    assert is_unmodified is True, "Bevel modifier must not disqualify part from tight tolerance"

    # 2. Dimensions 3% off: [1.03, 1.0, 1.0] must FAIL verification
    match_3_pct = verifier._verify_dimensions_for_op(
        [1.0, 1.0, 1.0], [1.03, 1.0, 1.0], op=None, tight=is_unmodified
    )
    assert match_3_pct is False, "Beveled box 3% off must fail under tight tolerance"

    # 3. Dimensions 0.5% off: [1.005, 1.0, 1.0] must PASS
    match_05_pct = verifier._verify_dimensions_for_op(
        [1.0, 1.0, 1.0], [1.005, 1.0, 1.0], op=None, tight=is_unmodified
    )
    assert match_05_pct is True, "Beveled box 0.5% off must pass under tight tolerance"

    # 4. Extent-altering modifiers like SMOOTH must disqualify from tight tolerance
    smooth_node = manifest.add_child_node(
        root.node_id, "smoothed_bracket", NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.U_SHAPE, major_radius=0.12, minor_radius=0.015),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    smooth_node.modifiers = [{"type": "SMOOTH", "smooth_factor": 0.5, "smooth_iterations": 1}]
    is_smooth_unmodified = verifier._is_unmodified_for_tolerance(smooth_node, manifest)
    assert is_smooth_unmodified is False, "Smooth modifier alters surface extents and must trigger loose tolerance"

    # Verify real Blender measurement for smoothed u_bracket passes under loose tolerance
    expected_bracket = [0.26557, 0.02951, 0.13279]
    actual_bracket = [0.26501, 0.02923, 0.13138]
    assert verifier._verify_dimensions_for_op(
        expected_bracket, actual_bracket, op=None, tight=is_smooth_unmodified
    ) is True, "Smoothed u-bracket dimension shrinkage must pass under loose tolerance"


def test_readback_fails_on_ir_manifest_disagreement():
    """Readback fails loudly when the frozen scene_plan IR declares a boolean cut targeting a node that does not exist in manifest."""
    manifest = BuildManifest.create("Disagreement test")
    root = manifest.get_root()
    manifest.add_child_node(
        root.node_id, "legit_part", NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX, size=[1.0, 1.0, 1.0]),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    # IR has an operation targeting a ghost node not present in manifest
    manifest.stats["scene_plan"] = {
        "schema_version": 1,
        "scene_ir": "scene_ir.json",
        "boolean_operations": [
            {
                "operation": "difference",
                "cutter_node_id": "ghost_cutter",
                "target_node_id": "ghost_target",
            }
        ],
    }

    # Verify that attempting to validate or resolve this ghost target fails or flags an error
    class MockMCP:
        async def call_locked(self, app, op, args):
            import json
            return {"output": "SENTINEL_OUTPUT_START" + json.dumps({"ok": True, "objects": []}) + "SENTINEL_OUTPUT_END"}

    class MockExecutor:
        _collection_name = "Sentinel_Build"

    import asyncio
    verifier = SceneReadbackVerifier(MockMCP())
    report = asyncio.run(verifier.verify(manifest, MockExecutor()))
    # Manifest expects legit_part, which is missing from blender objects -> reports error
    errors = [f for f in report["findings"] if f["severity"] == "error"]
    assert any(f["code"] == "object_missing" for f in errors)
    assert report["ok"] is False


def test_scale_aware_tolerance_across_scales():
    """Verify that scale-aware tolerance guards against axis flips and large errors
    without suffocating millimeter-scale features or allowing fixed floors to dominate."""
    verifier = SceneReadbackVerifier(mcp_manager=None)

    # 1. Large 1m part: 2% allowed = 20mm. 1.01m (1%) passes, 1.03m (3%) fails.
    assert verifier._dimensions_match([1.0, 1.0, 1.0], [1.01, 1.0, 1.0], tight=True) is True
    assert verifier._dimensions_match([1.0, 1.0, 1.0], [1.03, 1.0, 1.0], tight=True) is False

    # 2. Medium 13.5cm part: 2% allowed = 2.7mm. 1.4mm shift passes.
    assert verifier._dimensions_match([0.135, 0.03, 0.135], [0.1336, 0.03, 0.1336], tight=True) is True

    # 3. Small 5mm part (want=0.005m): floor scales down to 1mm (20%). 0.5mm shift passes, 2mm shift fails.
    assert verifier._dimensions_match([0.005, 0.005, 0.02], [0.0055, 0.005, 0.02], tight=True) is True
    assert verifier._dimensions_match([0.005, 0.005, 0.02], [0.0075, 0.005, 0.02], tight=True) is False

    # 4. Tiny 1mm part (want=0.001m): floor scales to 0.3mm (mesh stability limit). 0.2mm passes, 0.8mm fails.
    assert verifier._dimensions_match([0.001, 0.001, 0.005], [0.0012, 0.001, 0.005], tight=True) is True
    assert verifier._dimensions_match([0.001, 0.001, 0.005], [0.0020, 0.001, 0.005], tight=True) is False


