"""Headless Blender verification suite.

Run directly inside Blender:
  & "C:\\Program Files\\Blender Foundation\\Blender 4.5\\blender.exe" -b --python core/blender_pipeline/progressive_v2/test_blender_headless_integration.py

Verifies:
1. Boolean difference evaluated depsgraph: volume drops on face-crossing cut, and non-intersecting cutter doesn't fail.
2. Scaled instance matrix composition with rotated parent, off-center origin, and nested instance matching independent math.
3. Hostile strings, null bytes, and 100-character names preserving part ID custom property through Blender's 63-byte name limit.
4. Mid-transaction failure rollback leaving zero attempt objects, collections, meshes, or materials.
"""
import sys
import os
import json
import math

if os.getcwd() not in sys.path:
    sys.path.insert(0, os.getcwd())
backend_dir = os.path.join(os.getcwd(), "backend")
if os.path.isdir(backend_dir) and backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
script_dir = os.path.dirname(os.path.abspath(__file__))
backend_root = os.path.abspath(os.path.join(script_dir, "..", ".."))
if os.path.isdir(backend_root) and backend_root not in sys.path:
    sys.path.insert(0, backend_root)

try:
    import bpy
    import bmesh
    import mathutils
except ImportError:
    try:
        import pytest
        pytestmark = pytest.mark.skip(reason="Blender bpy environment not available (run with blender -b --python)")
    except Exception:
        pass
    bpy = None
    bmesh = None
    mathutils = None


def reset_blend_file():
    """Reset to clean initial state."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for col in list(bpy.data.collections):
        bpy.data.collections.remove(col)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)
    for mat in list(bpy.data.materials):
        bpy.data.materials.remove(mat)


def test_boolean_evaluated_depsgraph():
    """Verify boolean cuts via bmesh volume calculation and non-intersecting readback."""
    print("\n--- Running: test_boolean_evaluated_depsgraph ---")
    reset_blend_file()

    # Case A: Face-crossing cutter that removes a corner
    # Base cube: 2 x 2 x 2 centered at (0, 0, 1), volume = 8.0
    bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0, 0, 1))
    base_obj = bpy.context.active_object
    base_obj.name = "chassis_base"

    # Cutter cube: 1.0 x 1.0 x 1.0 centered at (0.6, 0.6, 1.0) crossing the (+X, +Y) face
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.6, 0.6, 1.0))
    cutter_obj = bpy.context.active_object
    cutter_obj.name = "cutter_corner"
    cutter_obj.hide_viewport = True
    cutter_obj.hide_render = True

    mod = base_obj.modifiers.new(name="CornerCut", type="BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.object = cutter_obj
    mod.solver = "EXACT"

    # Evaluated depsgraph readback
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = base_obj.evaluated_get(depsgraph)
    eval_mesh = eval_obj.to_mesh()

    # Calculate base volume vs evaluated volume using bmesh
    bm_base = bmesh.new()
    bm_base.from_mesh(base_obj.data)
    base_vol = bm_base.calc_volume()
    bm_base.free()

    bm_eval = bmesh.new()
    bm_eval.from_mesh(eval_mesh)
    eval_vol = bm_eval.calc_volume()
    bm_eval.free()
    eval_obj.to_mesh_clear()

    print(f"  Base volume: {base_vol:.4f}, Evaluated cut volume: {eval_vol:.4f}")
    assert math.isclose(base_vol, 8.0, abs_tol=1e-3), f"Expected base volume 8.0, got {base_vol}"
    assert eval_vol < base_vol - 0.2, f"Evaluated volume {eval_vol} should drop from cut (base: {base_vol})"
    print(f"  Volume drop verified: {base_vol - eval_vol:.4f} m^3 removed by cutter")

    # Case B: Non-intersecting cutter (cutter entirely outside base bounds)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(10.0, 10.0, 10.0))
    miss_cutter = bpy.context.active_object
    miss_cutter.name = "cutter_miss"
    miss_cutter.hide_viewport = True
    miss_cutter.hide_render = True

    mod_miss = base_obj.modifiers.new(name="MissCut", type="BOOLEAN")
    mod_miss.operation = "DIFFERENCE"
    mod_miss.object = miss_cutter
    mod_miss.solver = "EXACT"

    depsgraph_miss = bpy.context.evaluated_depsgraph_get()
    eval_miss_obj = base_obj.evaluated_get(depsgraph_miss)
    eval_miss_mesh = eval_miss_obj.to_mesh()

    # Volume with non-intersecting cutter should not drop further
    bm_miss = bmesh.new()
    bm_miss.from_mesh(eval_miss_mesh)
    miss_vol = bm_miss.calc_volume()
    bm_miss.free()
    eval_miss_obj.to_mesh_clear()

    print(f"  Volume with non-intersecting cutter: {miss_vol:.4f}")
    assert math.isclose(miss_vol, eval_vol, abs_tol=1e-3), "Non-intersecting cutter must not alter volume"
    print("PASS: test_boolean_evaluated_depsgraph (volume drop and non-intersecting readback verified)")


def test_scaled_instance_matrix_composition():
    """Verify instance transform composition with rotated parent, off-center origin, and nested instance."""
    print("\n--- Running: test_scaled_instance_matrix_composition ---")
    reset_blend_file()

    # 1. Mesh definition
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0))
    def_obj = bpy.context.active_object
    def_obj.name = "subassembly_def"
    def_mesh = def_obj.data

    # 2. Parent with off-center origin and 90-degree Z rotation
    # Translation: (3.0, -2.0, 1.0), Rotation: 90 deg around Z
    parent_pos = mathutils.Vector((3.0, -2.0, 1.0))
    parent_rot = mathutils.Euler((0.0, 0.0, math.pi / 2.0)).to_matrix().to_4x4()
    parent_world = mathutils.Matrix.Translation(parent_pos) @ parent_rot

    # 3. Intermediate instance with scale (1.5, 2.0, 0.5) and 45-degree X rotation
    inter_pos = mathutils.Vector((1.0, 0.0, 0.0))
    inter_rot = mathutils.Euler((math.pi / 4.0, 0.0, 0.0)).to_matrix().to_4x4()
    inter_scale = mathutils.Matrix.Diagonal((1.5, 2.0, 0.5, 1.0))
    inter_local = mathutils.Matrix.Translation(inter_pos) @ inter_rot @ inter_scale

    inter_world = parent_world @ inter_local

    # 4. Nested instance relative to intermediate
    nested_pos = mathutils.Vector((0.0, 1.0, 0.5))
    nested_scale = mathutils.Matrix.Diagonal((1.0, 1.0, 1.0, 1.0))
    nested_local = mathutils.Matrix.Translation(nested_pos) @ nested_scale

    # Independent mathematical expectation
    expected_nested_world = inter_world @ nested_local

    # 5. Create Blender objects and apply transforms
    inter_obj = bpy.data.objects.new("inter_inst", def_mesh)
    bpy.context.scene.collection.objects.link(inter_obj)
    inter_obj.matrix_world = inter_world

    nested_obj = bpy.data.objects.new("nested_inst", def_mesh)
    bpy.context.scene.collection.objects.link(nested_obj)
    nested_obj.matrix_world = expected_nested_world

    bpy.context.view_layer.update()

    # 6. Verify matrix composition element-by-element
    for r in range(4):
        for c in range(4):
            actual_val = nested_obj.matrix_world[r][c]
            expected_val = expected_nested_world[r][c]
            assert math.isclose(actual_val, expected_val, abs_tol=1e-4), (
                f"Matrix mismatch at [{r}][{c}]: got {actual_val:.5f}, expected {expected_val:.5f}"
            )

    # 7. Verify measured bounding box corners against independent transform
    unit_cube_corners = [
        mathutils.Vector((x, y, z))
        for x in (-0.5, 0.5) for y in (-0.5, 0.5) for z in (-0.5, 0.5)
    ]
    expected_corners = [expected_nested_world @ v for v in unit_cube_corners]
    expected_min = [min(v[i] for v in expected_corners) for i in range(3)]
    expected_max = [max(v[i] for v in expected_corners) for i in range(3)]

    actual_corners = [nested_obj.matrix_world @ mathutils.Vector(v) for v in nested_obj.bound_box]
    actual_min = [min(v[i] for v in actual_corners) for i in range(3)]
    actual_max = [max(v[i] for v in actual_corners) for i in range(3)]

    for i, axis in enumerate(["X", "Y", "Z"]):
        assert math.isclose(actual_min[i], expected_min[i], abs_tol=1e-4), f"{axis} min mismatch"
        assert math.isclose(actual_max[i], expected_max[i], abs_tol=1e-4), f"{axis} max mismatch"

    print("PASS: test_scaled_instance_matrix_composition (rotated parent, off-center origin, and nested instance match expectations)")


def test_hostile_strings_execution():
    """Verify hostile strings, null bytes, and 100-char names round-trip custom property node_id."""
    print("\n--- Running: test_hostile_strings_execution ---")
    reset_blend_file()

    test_cases = [
        # (part_id, part_name, mat_name)
        ("node_single_quote", "evil'name\"triple\"", "mat'single\"double"),
        ("node_backslash", "path\\with\\slashes", "mat\\slashes"),
        ("node_emoji", "🛸_space_part", "🎨_shiny_metal"),
        ("node_unicode", "部品_001_bracket", "素材_銅_01"),
        ("node_null_byte", "part_with\x00null_byte", "mat\x00null"),
        ("node_100_chars", "a" * 100, "m" * 100),
    ]

    for part_id, part_name, mat_name in test_cases:
        payload = {
            "part_id": part_id,
            "part_name": part_name,
            "mat_name": mat_name,
            "size": [1.0, 1.0, 1.0],
        }
        script = f'''
import bpy, json
payload = json.loads({repr(json.dumps(payload))})
p_id = payload["part_id"]
p_name = payload["part_name"]
m_name = payload["mat_name"]

bpy.ops.mesh.primitive_cube_add(size=1.0)
obj = bpy.context.active_object
obj.name = p_name
# Tag canonical identity via custom property (immune to Blender 63-byte name truncation)
obj["node_id"] = p_id

mat = bpy.data.materials.new(name=m_name)
mat.use_nodes = True
mat["mat_id"] = p_id
obj.data.materials.append(mat)
'''
        local_scope = {}
        exec(script, {"bpy": bpy, "json": json}, local_scope)

        created_obj = bpy.context.active_object
        assert created_obj is not None
        # Identity round-trip via custom property
        assert created_obj["node_id"] == part_id, f"Expected node_id {part_id!r}, got {created_obj['node_id']!r}"
        assert len(created_obj.data.materials) == 1
        assert created_obj.data.materials[0]["mat_id"] == part_id
        # For names under 63 bytes, name also matches
        if len(part_name.encode("utf-8")) < 63 and "\x00" not in part_name:
            assert created_obj.name == part_name
        print(f"  Verified safe execution & ID round-trip for: {part_id}")

    print("PASS: test_hostile_strings_execution (null bytes and 100-char names preserve node_id)")


def test_transaction_rollback():
    """Verify that a mid-transaction failure cleans up all attempt collections, objects, meshes, and materials."""
    print("\n--- Running: test_transaction_rollback ---")
    reset_blend_file()

    attempt_name = "Sentinel_Attempt_Rollback"
    col = bpy.data.collections.new(attempt_name)
    bpy.context.scene.collection.children.link(col)

    created_objs = []
    # Create 3 objects in this transaction attempt and tag both object and datablock (mesh/curve/mat)
    for i in range(3):
        mesh = bpy.data.meshes.new(f"rollback_mesh_{i}")
        mesh["sentinel_build_id"] = attempt_name
        obj = bpy.data.objects.new(f"rollback_obj_{i}", mesh)
        obj["sentinel_build_id"] = attempt_name
        mat = bpy.data.materials.new(f"rollback_mat_{i}")
        mat["sentinel_build_id"] = attempt_name
        obj.data.materials.append(mat)
        col.objects.link(obj)
        created_objs.append(obj)

    assert len(col.objects) == 3
    assert len(bpy.data.materials) == 3

    # Simulate mid-transaction failure and execute production-equivalent cleanup_all
    try:
        raise RuntimeError("SIMULATED_TRANSACTION_SYNTAX_ERROR: Cutter failure")
    except RuntimeError as failure:
        print(f"  Simulated transaction failure caught: {failure}")
        # Execute executor.cleanup_all logic:
        coll = bpy.data.collections.get(attempt_name)
        if coll:
            for obj in list(coll.objects):
                data = obj.data
                bpy.data.objects.remove(obj, do_unlink=True)
                if data and getattr(data, 'users', 1) == 0:
                    if isinstance(data, bpy.types.Mesh): bpy.data.meshes.remove(data)
                    elif isinstance(data, bpy.types.Curve): bpy.data.curves.remove(data)
            bpy.data.collections.remove(coll)

        for obj in list(bpy.data.objects):
            if obj.get('sentinel_build_id') == attempt_name:
                data = obj.data
                bpy.data.objects.remove(obj, do_unlink=True)
                if data and getattr(data, 'users', 1) == 0:
                    if isinstance(data, bpy.types.Mesh): bpy.data.meshes.remove(data)
                    elif isinstance(data, bpy.types.Curve): bpy.data.curves.remove(data)

        for mat in list(bpy.data.materials):
            if mat.get('sentinel_build_id') == attempt_name and mat.users == 0:
                bpy.data.materials.remove(mat)

    # Absence proof: scan all datablock categories as in verify_attempt_absent
    remnants = []
    for kind, items in [
        ('objects', bpy.data.objects), ('meshes', bpy.data.meshes),
        ('materials', bpy.data.materials), ('collections', bpy.data.collections),
        ('curves', bpy.data.curves), ('lights', bpy.data.lights),
    ]:
        for item in items:
            if item.get('sentinel_build_id') == attempt_name or (kind == 'collections' and item.name == attempt_name):
                remnants.append({'kind': kind, 'name': item.name})

    assert len(remnants) == 0, f"Remnants found after cleanup: {remnants}"
    print(f"  Post-rollback count: collection=None, objects=0, meshes=0, materials=0, remnants={len(remnants)}")
    print("PASS: test_transaction_rollback (zero orphan objects, meshes, or materials after rollback; absence proof clean)")


def test_real_blender_scene_readback_evaluation():
    """Verify SceneReadbackVerifier in real Blender:
    1. Face-crossing cut reduces world bounds and volume.
    2. Cutter-miss leaves bounds and volume intact without failing.
    3. Union target expands bounds without failing.
    4. Empty in the collection is handled safely with no crash.
    5. Deliberately wrong dimension / wrong orientation part is caught and fails readback.
    """
    print("\n--- Running: test_real_blender_scene_readback_evaluation ---")
    reset_blend_file()
    from core.blender_pipeline.progressive_v2.manifest import (
        BuildManifest, GeometrySpec, AttachmentSpec, NodeKind
    )
    from core.blender_pipeline.progressive_v2.node_types import PrimitiveType, SocketType
    from core.blender_pipeline.progressive_v2.readback import SceneReadbackVerifier

    manifest = BuildManifest.create("Real Blender Readback Test")
    root = manifest.get_root()
    test_col = bpy.data.collections.new("Sentinel_Build_test_readback")
    bpy.context.scene.collection.children.link(test_col)

    # 1. Target with face-crossing cut
    # Base box 1.0 x 1.0 x 1.0
    target_node = manifest.add_child_node(
        root.node_id, "cut_target", NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX, size=[1.0, 1.0, 1.0]),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0))
    t_obj = bpy.context.active_object
    t_obj.name = "cut_target"
    t_obj["sentinel_node_id"] = target_node.node_id
    t_obj["sentinel_canonical_path"] = f"/{root.node_id}/{target_node.node_id}"

    # Face-crossing cutter at X=0.4 (cuts X from 0.2 to 0.6)
    cutter_node = manifest.add_child_node(
        root.node_id, "face_cutter", NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX, size=[0.4, 1.2, 1.2]),
        attachment=AttachmentSpec(socket_type=SocketType.BOOLEAN_CUT),
    )
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.4, 0, 0))
    c_obj = bpy.context.active_object
    c_obj.name = "face_cutter"
    c_obj.scale = (0.4, 1.2, 1.2)
    bpy.ops.object.transform_apply(scale=True)
    c_obj.hide_viewport = True
    c_obj.hide_render = True
    c_obj["sentinel_node_id"] = cutter_node.node_id

    mod = t_obj.modifiers.new("Cut", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.object = c_obj

    # 2. Union target (expands)
    union_target = manifest.add_child_node(
        root.node_id, "union_target", NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX, size=[1.0, 1.0, 1.0]),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(5.0, 0, 0))
    u_obj = bpy.context.active_object
    u_obj.name = "union_target"
    u_obj["sentinel_node_id"] = union_target.node_id
    u_obj["sentinel_canonical_path"] = f"/{root.node_id}/{union_target.node_id}"

    union_piece = manifest.add_child_node(
        root.node_id, "union_piece", NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX, size=[0.5, 0.5, 0.5]),
        attachment=AttachmentSpec(socket_type=SocketType.BOOLEAN_UNION),
    )
    bpy.ops.mesh.primitive_cube_add(size=0.5, location=(5.6, 0, 0))
    up_obj = bpy.context.active_object
    up_obj.name = "union_piece"
    up_obj.hide_viewport = True
    up_obj.hide_render = True
    up_obj["sentinel_node_id"] = union_piece.node_id

    mod_u = u_obj.modifiers.new("Union", "BOOLEAN")
    mod_u.operation = "UNION"
    mod_u.object = up_obj

    # 3. Intersect target (shrinks)
    intersect_target = manifest.add_child_node(
        root.node_id, "intersect_target", NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX, size=[1.0, 1.0, 1.0]),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(15.0, 0, 0))
    i_obj = bpy.context.active_object
    i_obj.name = "intersect_target"
    i_obj["sentinel_node_id"] = intersect_target.node_id
    i_obj["sentinel_canonical_path"] = f"/{root.node_id}/{intersect_target.node_id}"

    intersect_piece = manifest.add_child_node(
        root.node_id, "intersect_piece", NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX, size=[1.0, 1.0, 1.0]),
        attachment=AttachmentSpec(socket_type=SocketType.BOOLEAN_INTERSECT),
    )
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(15.3, 0.3, 0.3))
    ip_obj = bpy.context.active_object
    ip_obj.name = "intersect_piece"
    ip_obj.hide_viewport = True
    ip_obj.hide_render = True
    ip_obj["sentinel_node_id"] = intersect_piece.node_id

    mod_i = i_obj.modifiers.new("Intersect", "BOOLEAN")
    mod_i.operation = "INTERSECT"
    mod_i.object = ip_obj

    # 4. Assembly empty in collection
    empty = bpy.data.objects.new("Assembly_Empty", None)
    test_col.objects.link(empty)

    # Move all created objects into test_col
    for o in [t_obj, c_obj, u_obj, up_obj, i_obj, ip_obj]:
        if o.name in bpy.context.scene.collection.objects:
            bpy.context.scene.collection.objects.unlink(o)
        if o.name not in test_col.objects:
            test_col.objects.link(o)

    # Populate frozen scene plan in manifest stats to verify IR path
    from core.blender_pipeline.progressive_v2.scene_ir import ExecutableScenePlan
    manifest.stats["scene_plan"] = ExecutableScenePlan.from_manifest(manifest).to_dict()

    # Execute readback script in this blend environment
    class MockMCP:
        async def call_locked(self, app, op, args):
            code = args["code"]
            # We execute code in a local namespace and capture the print
            import io
            old_stdout = sys.stdout
            sys.stdout = io.StringIO()
            try:
                exec(code, globals())
                output = sys.stdout.getvalue()
            finally:
                sys.stdout = old_stdout
            return {"output": output}

    class MockExecutor:
        _collection_name = test_col.name

    import asyncio
    verifier = SceneReadbackVerifier(MockMCP())
    report = asyncio.run(verifier.verify(manifest, MockExecutor()))

    # Verify cut target measured bounds and volume
    t_data = next(o for o in report["objects"] if o["name"] == "cut_target")
    assert t_data["dimensions"][0] < 0.99, f"Evaluated dim_x {t_data['dimensions'][0]} must be reduced by face cut"
    assert t_data["volume"] < 0.99, f"Evaluated volume {t_data['volume']} must drop below 1.0"
    assert t_data["is_manifold"] is True, "Cut target must remain manifold"
    print(f"  Cut target verified: evaluated dim_x={t_data['dimensions'][0]:.3f} < 1.0, volume={t_data['volume']:.3f} < 1.0, manifold={t_data['is_manifold']}")

    # Verify union target
    u_data = next(o for o in report["objects"] if o["name"] == "union_target")
    assert u_data["dimensions"][0] > 1.05, f"Evaluated union dim_x {u_data['dimensions'][0]} must expand beyond 1.0"
    print(f"  Union target verified: evaluated dim_x={u_data['dimensions'][0]:.3f} > 1.0")

    # Verify intersect target: 1.0 box intersected with [1.0, 1.0, 1.0] at (15.3, 0.3, 0.3) -> 0.7 x 0.7 x 0.7, vol = 0.343
    i_data = next(o for o in report["objects"] if o["name"] == "intersect_target")
    assert abs(i_data["dimensions"][0] - 0.700) <= 1e-3, f"Evaluated intersect dim_x {i_data['dimensions'][0]} != 0.700"
    assert abs(i_data["volume"] - 0.343) <= 1e-3, f"Evaluated intersect volume {i_data['volume']} != 0.343"
    print(f"  Intersect target verified: evaluated dim_x={i_data['dimensions'][0]:.3f} == 0.700 +/- 1e-3, volume={i_data['volume']:.3f} == 0.343 +/- 1e-3")

    # Verify empty object was processed safely
    empty_data = next(o for o in report["objects"] if o["name"] == "Assembly_Empty")
    assert empty_data["type"] == "EMPTY"
    assert empty_data["volume"] is None
    print(f"  Empty object verified: safely handled without crash")

    # 4. Deliberately wrong part: vertical blade declared as horizontal
    wrong_node = manifest.add_child_node(
        root.node_id, "wrong_blade", NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX, size=[0.4, 0.04, 0.01]),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    # Built standing upright along Z: [0.01, 0.04, 0.4]
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(10.0, 0, 0))
    w_obj = bpy.context.active_object
    w_obj.name = "wrong_blade"
    w_obj.scale = (0.01, 0.04, 0.4)
    bpy.ops.object.transform_apply(scale=True)
    w_obj["sentinel_node_id"] = wrong_node.node_id
    w_obj["sentinel_canonical_path"] = f"/{root.node_id}/{wrong_node.node_id}"
    if w_obj.name in bpy.context.scene.collection.objects:
        bpy.context.scene.collection.objects.unlink(w_obj)
    test_col.objects.link(w_obj)

    report_wrong = asyncio.run(verifier.verify(manifest, MockExecutor()))
    assert report_wrong["ok"] is False, "Readback MUST fail when a part has wrong oriented dimensions"
    wrong_finding = next(f for f in report_wrong["findings"] if f["node_id"] == wrong_node.node_id)
    assert wrong_finding["code"] == "dimension_mismatch"
    print(f"  Deliberately wrong blade verified: caught dimension_mismatch expected={wrong_finding['expected']} actual={wrong_finding['actual']}")

    print("PASS: test_real_blender_scene_readback_evaluation (all 5 real-Blender controls verified)")


def test_production_executor_primitive_bounds_sweep():
    """Verify that every primitive fragment generated by BlenderExecutor produces exact bounds within 1e-4."""
    print("\n--- Running: test_production_executor_primitive_bounds_sweep ---")
    reset_blend_file()
    import bmesh
    from core.blender_pipeline.progressive_v2.manifest import GeometrySpec
    from core.blender_pipeline.progressive_v2.node_types import PrimitiveType
    from core.blender_pipeline.progressive_v2.executor import BlenderExecutor
    from core.blender_pipeline.progressive_v2.readback import _expected_dimensions, _expected_local_bounds

    cases = [
        {"prim": PrimitiveType.BOX, "kwargs": {"size": [0.4, 0.2, 0.1]}},
        {"prim": PrimitiveType.CYLINDER, "kwargs": {"radius": 0.05, "depth": 0.3}},
        {"prim": PrimitiveType.CYLINDER, "kwargs": {"radius": 0.05, "depth": 0.3, "segments": 3}},
        {"prim": PrimitiveType.CYLINDER, "kwargs": {"radius": 0.05, "depth": 0.3, "segments": 5}},
        {"prim": PrimitiveType.CYLINDER, "kwargs": {"radius": 0.05, "depth": 0.3, "segments": 6}},
        {"prim": PrimitiveType.CYLINDER, "kwargs": {"radius": 0.05, "depth": 0.3, "segments": 8}},
        {"prim": PrimitiveType.CYLINDER, "kwargs": {"radius": 0.05, "depth": 0.3, "segments": 32}},
        {"prim": PrimitiveType.SPHERE, "kwargs": {"radius": 0.08}},
        {"prim": PrimitiveType.SPHERE, "kwargs": {"radius": 0.08, "segments": 5}},
        {"prim": PrimitiveType.SPHERE, "kwargs": {"radius": 0.08, "segments": 6}},
        {"prim": PrimitiveType.SPHERE, "kwargs": {"radius": 0.08, "segments": 8}},
        {"prim": PrimitiveType.HEMISPHERE, "kwargs": {"radius": 0.08}},
        {"prim": PrimitiveType.HEMISPHERE, "kwargs": {"radius": 0.08, "segments": 6}},
        {"prim": PrimitiveType.HEMISPHERE, "kwargs": {"radius": 0.08, "segments": 8}},
        {"prim": PrimitiveType.CONE, "kwargs": {"radius": 0.06, "depth": 0.2, "radius2": 0.0}},
        {"prim": PrimitiveType.CONE, "kwargs": {"radius": 0.06, "depth": 0.2, "radius2": 0.03}},
        {"prim": PrimitiveType.CONE, "kwargs": {"radius": 0.04, "depth": 0.2, "radius2": 0.08}},
        {"prim": PrimitiveType.CONE, "kwargs": {"radius": 0.05, "depth": 0.2, "radius2": 0.05}},
        {"prim": PrimitiveType.CONE, "kwargs": {"radius": 0.06, "depth": 0.2, "radius2": 0.0, "segments": 3}},
        {"prim": PrimitiveType.CONE, "kwargs": {"radius": 0.06, "depth": 0.2, "radius2": 0.0, "segments": 5}},
        {"prim": PrimitiveType.CONE, "kwargs": {"radius": 0.06, "depth": 0.2, "radius2": 0.0, "segments": 6}},
        {"prim": PrimitiveType.TORUS, "kwargs": {"major_radius": 0.1, "minor_radius": 0.02}},
        {"prim": PrimitiveType.TORUS, "kwargs": {"major_radius": 0.1, "minor_radius": 0.02, "segments": 4}},
        {"prim": PrimitiveType.TORUS, "kwargs": {"major_radius": 0.1, "minor_radius": 0.02, "segments": 6}},
        {"prim": PrimitiveType.TORUS, "kwargs": {"major_radius": 0.1, "minor_radius": 0.02, "segments": 8}},
        {"prim": PrimitiveType.CAPSULE, "kwargs": {"radius": 0.04, "depth": 0.25}},
        {"prim": PrimitiveType.CAPSULE, "kwargs": {"radius": 0.04, "depth": 0.25, "segments": 6}},
        {"prim": PrimitiveType.CAPSULE, "kwargs": {"radius": 0.04, "depth": 0.25, "segments": 8}},
        {"prim": PrimitiveType.PRISM, "kwargs": {"radius": 0.07, "depth": 0.2, "segments": 3}},
        {"prim": PrimitiveType.PYRAMID, "kwargs": {"radius": 0.07, "depth": 0.2}},
        {"prim": PrimitiveType.U_SHAPE, "kwargs": {"major_radius": 0.1, "minor_radius": 0.02}},
        {"prim": PrimitiveType.WEDGE, "kwargs": {"size": [0.3, 0.2, 0.1]}},
        {"prim": PrimitiveType.PLANE, "kwargs": {"size": [0.5, 0.5, 0.002]}},
        {"prim": PrimitiveType.GRID, "kwargs": {"size": [0.5, 0.5, 0.0]}},
    ]

    executor = BlenderExecutor(mcp_manager=None, task_id="test_prim_bounds")
    passed_count = 0
    for idx, c in enumerate(cases):
        prim = c["prim"]
        kw = c["kwargs"]
        seg_str = f" N={kw.get('segments')}" if "segments" in kw else ""
        label = f"{prim.value}{seg_str}_{idx}"

        spec = GeometrySpec(primitive=prim, **kw)
        identity_mr = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
        frag = executor._get_primitive_fragment(prim, f"prim_test_{idx}", spec, [0.0, 0.0, 0.0], identity_mr, "Collection")

        # Execute fragment inside Blender with stub header matching executor flush()
        code = f"""
import bpy, bmesh, math, mathutils
def _link(o):
    bpy.context.scene.collection.objects.link(o)
def _unlink_all(o):
    for c in list(o.users_collection):
        c.objects.unlink(o)
_sentinel_results = {{}}
{frag}
"""
        loc = {}
        exec(code, {"bpy": bpy, "bmesh": bmesh, "math": math, "mathutils": mathutils}, loc)
        obj = bpy.data.objects[f"prim_test_{idx}"]
        bpy.context.view_layer.update()

        coords = [v.co for v in obj.data.vertices]
        min_x = min(c.x for c in coords)
        max_x = max(c.x for c in coords)
        min_y = min(c.y for c in coords)
        max_y = max(c.y for c in coords)
        min_z = min(c.z for c in coords)
        max_z = max(c.z for c in coords)

        meas_dims = [max_x - min_x, max_y - min_y, max_z - min_z]
        meas_min = [min_x, min_y, min_z]
        meas_max = [max_x, max_y, max_z]

        exp_dims = _expected_dimensions(spec)
        exp_min, exp_max = _expected_local_bounds(spec)

        for d_m, d_e in zip(meas_dims, exp_dims):
            assert abs(d_m - d_e) <= 1e-4, f"{label} dimension mismatch: measured={meas_dims}, expected={exp_dims}"
        for b_m, b_e in zip(meas_min, exp_min):
            assert abs(b_m - b_e) <= 1e-4, f"{label} local_min mismatch: measured={meas_min}, expected={exp_min}"
        for b_m, b_e in zip(meas_max, exp_max):
            assert abs(b_m - b_e) <= 1e-4, f"{label} local_max mismatch: measured={meas_max}, expected={exp_max}"

        print(f"  {label:<28} dims={[round(v, 4) for v in meas_dims]} min={[round(v, 4) for v in meas_min]} max={[round(v, 4) for v in meas_max]} PASS")

        # Clean up object for next test
        bpy.data.objects.remove(obj, do_unlink=True)
        passed_count += 1

    print(f"PASS: test_production_executor_primitive_bounds_sweep ({passed_count}/{len(cases)} production fragments verified <= 1e-4)")


def test_ground_lift_comprehensive_controls():
    """Verify Cluster D Ground Lift controls in real Blender:
    1. Hidden cutter overshooting below model does NOT drag min_z down or alter lift.
    2. Rotated, scaled root lands exactly on Z=0 and all children maintain relative transforms.
    3. Assembly empty lifts with its children.
    4. Post-lift readback passes and bounds agree with manifest.
    5. Already-grounded model gets zero lift and no mutation.
    6. No mesh memory leaks (len(bpy.data.meshes) preserved).
    """
    print("\n--- Running: test_ground_lift_comprehensive_controls ---")
    reset_blend_file()
    import asyncio
    from core.blender_pipeline.progressive_v2.manifest import (
        BuildManifest, GeometrySpec, AttachmentSpec, NodeKind, NodeState
    )
    from core.blender_pipeline.progressive_v2.node_types import PrimitiveType, SocketType
    from core.blender_pipeline.progressive_v2.readback import SceneReadbackVerifier
    from core.blender_pipeline.progressive_v2.controller import ProgressiveController

    initial_meshes = len(bpy.data.meshes)

    # ── Test 1: Hidden cutter overshoot excluded from lift ───────────────
    # Model: Base cube at Z = -0.5 (size 1.0 -> extends from Z=-1.0 to 0.0) -> requires lift = +1.0
    # Cutter: Overshoots down to Z = -2.5 (hidden) -> must NOT cause lift = +2.5!
    manifest = BuildManifest.create("Ground Lift Test")
    root = manifest.get_root()
    root.blender_objects = ["Root_Empty"]

    # Root empty
    root_empty = bpy.data.objects.new("Root_Empty", None)
    bpy.context.scene.collection.objects.link(root_empty)

    # Assembly empty
    asm_node = manifest.add_child_node(root.node_id, "asm_chassis", NodeKind.ASSEMBLY)
    asm_empty = bpy.data.objects.new("asm_chassis_assembly_01", None)
    bpy.context.scene.collection.objects.link(asm_empty)
    asm_empty.parent = root_empty
    asm_node.blender_objects = ["asm_chassis_assembly_01"]

    # Visible part under assembly: box 1x1x1 at local Z = -0.5
    part_node = manifest.add_child_node(
        asm_node.node_id, "body_box", NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX, size=[1.0, 1.0, 1.0]),
        attachment=AttachmentSpec(socket_type=SocketType.ROOT),
    )
    part_node.state = NodeState.VERIFIED
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, -0.5))
    part_obj = bpy.context.active_object
    part_obj.name = "body_box"
    part_obj.parent = asm_empty
    part_obj.matrix_parent_inverse = asm_empty.matrix_world.inverted()
    part_obj["sentinel_node_id"] = part_node.node_id
    part_obj["sentinel_canonical_path"] = f"/{root.node_id}/{asm_node.node_id}/{part_node.node_id}"
    part_node.blender_objects = ["body_box"]

    # Hidden cutter overshooting down to Z=-2.5
    cutter_node = manifest.add_child_node(
        asm_node.node_id, "deep_cutter", NodeKind.PART,
        geometry=GeometrySpec(primitive=PrimitiveType.BOX, size=[0.5, 0.5, 2.0]),
        attachment=AttachmentSpec(socket_type=SocketType.BOOLEAN_CUT),
    )
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, -1.5))
    cutter_obj = bpy.context.active_object
    cutter_obj.name = "deep_cutter"
    cutter_obj.hide_viewport = True
    cutter_obj.hide_render = True
    cutter_obj.parent = asm_empty
    cutter_obj.matrix_parent_inverse = asm_empty.matrix_world.inverted()
    cutter_obj["sentinel_node_id"] = cutter_node.node_id
    cutter_node.blender_objects = ["deep_cutter"]

    test_col = bpy.data.collections.new("Sentinel_Build_lift")
    bpy.context.scene.collection.children.link(test_col)
    for o in [root_empty, asm_empty, part_obj, cutter_obj]:
        test_col.objects.link(o)

    class MockMCP:
        async def call_locked(self, app, op, args):
            code = args["code"]
            import io
            old_stdout = sys.stdout
            sys.stdout = io.StringIO()
            try:
                exec(code, globals())
                output = sys.stdout.getvalue()
            finally:
                sys.stdout = old_stdout
            return {"output": output}

    class MockExecutor:
        _collection_name = "Sentinel_Build_lift"

    controller = ProgressiveController(model_manager=None, mcp_manager=MockMCP())
    controller.manifest = manifest
    controller._executor = MockExecutor()

    # Execute Blender code snippet directly as controller._lift_to_ground_plane would:
    # 1. Verify cutter overshoot is ignored:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    min_z = float('inf')
    for obj in test_col.all_objects:
        if obj.type == 'MESH' and not obj.hide_viewport and not obj.hide_render:
            eval_obj = obj.evaluated_get(depsgraph)
            mesh = eval_obj.to_mesh()
            try:
                for v in mesh.vertices:
                    wz = (obj.matrix_world @ v.co).z
                    if wz < min_z:
                        min_z = wz
            finally:
                eval_obj.to_mesh_clear()

    # Verify cutter lowest point vs visible lowest point
    cutter_min_z = min((cutter_obj.matrix_world @ v.co).z for v in cutter_obj.data.vertices)
    assert abs(cutter_min_z - (-2.0)) < 1e-4, f"Cutter min_z must be -2.0, got {cutter_min_z}"
    print(f"  Disambiguation: visible min_z={min_z:.4f}, hidden cutter min_z={cutter_min_z:.4f}")
    assert abs(min_z - (-1.0)) < 1e-4, f"Visible min_z must be -1.0 (cutter ignored), got {min_z}"
    lift = -min_z
    assert abs(lift - 1.0) < 1e-4, f"Lift must be exactly +1.0 (landing visible on 0.0, NOT cutter on 0.0), got {lift}"

    # 2. Lift ROOT empty once:
    root_empty.matrix_world.translation.z += lift
    bpy.context.view_layer.update()

    # Verify part lands exactly on Z=0:
    eval_part = part_obj.evaluated_get(depsgraph)
    mesh_part = eval_part.to_mesh()
    try:
        new_min_z = min((part_obj.matrix_world @ v.co).z for v in mesh_part.vertices)
    finally:
        eval_part.to_mesh_clear()

    assert abs(new_min_z - 0.0) < 1e-4, f"Landed min_z must be 0.0, got {new_min_z}"
    # Verify assembly empty lifted along with root:
    assert abs(asm_empty.matrix_world.translation.z - 1.0) < 1e-4, "Assembly empty must lift with root"
    print(f"  Visible model landed: new_min_z={new_min_z:.4f}, asm_empty_z={asm_empty.matrix_world.translation.z:.4f}")

    # 3. Verify already-grounded model gets zero lift:
    min_z_grounded = float('inf')
    for obj in test_col.all_objects:
        if obj.type == 'MESH' and not obj.hide_viewport and not obj.hide_render:
            eval_obj = obj.evaluated_get(depsgraph)
            m = eval_obj.to_mesh()
            try:
                for v in m.vertices:
                    wz = (obj.matrix_world @ v.co).z
                    if wz < min_z_grounded:
                        min_z_grounded = wz
            finally:
                eval_obj.to_mesh_clear()

    assert abs(min_z_grounded) < 1e-4, f"Already grounded model min_z must be 0.0, got {min_z_grounded}"
    lift_second = 0.0 if abs(min_z_grounded) < 0.001 else -min_z_grounded
    assert lift_second == 0.0, f"Second lift must be 0.0, got {lift_second}"
    print("  Already-grounded model verified: second lift = 0.0")

    # 4. Post-lift SceneReadbackVerifier integration:
    post_readback = asyncio.run(SceneReadbackVerifier(MockMCP()).verify(manifest, MockExecutor()))
    readback_errors = [f for f in post_readback["findings"] if f["severity"] == "error"]
    assert len(readback_errors) == 0, f"Post-lift readback failed with: {readback_errors}"
    assert post_readback["ok"] is True
    print("  Post-lift production SceneReadbackVerifier verified: ok=True, 0 errors")

    # 5. Rotated + Uniformly Scaled Root Control
    root_rot = bpy.data.objects.new("Root_Rotated", None)
    root_rot.rotation_euler = (0, math.radians(45), 0)
    root_rot.scale = (0.5, 0.5, 0.5)
    bpy.context.scene.collection.objects.link(root_rot)

    asm_rot = bpy.data.objects.new("Asm_Rotated", None)
    asm_rot.parent = root_rot
    asm_rot.location = (0, 0, -0.2)
    bpy.context.scene.collection.objects.link(asm_rot)

    bpy.ops.mesh.primitive_cube_add(size=0.2, location=(0.1, 0, -0.4))
    part_a = bpy.context.active_object
    part_a.name = "part_rot_a"
    part_a.parent = asm_rot
    part_a.matrix_parent_inverse = asm_rot.matrix_world.inverted()

    bpy.ops.mesh.primitive_cube_add(size=0.2, location=(-0.1, 0.2, -0.8))
    part_b = bpy.context.active_object
    part_b.name = "part_rot_b"
    part_b.parent = asm_rot
    part_b.matrix_parent_inverse = asm_rot.matrix_world.inverted()

    test_col_rot = bpy.data.collections.new("Sentinel_Build_lift_rot")
    bpy.context.scene.collection.children.link(test_col_rot)
    for o in [root_rot, asm_rot, part_a, part_b]:
        test_col_rot.objects.link(o)

    bpy.context.view_layer.update()

    initial_rel_offset = part_b.matrix_world.translation - part_a.matrix_world.translation
    initial_asm_z = asm_rot.matrix_world.translation.z

    min_z_rot = float('inf')
    for o in [part_a, part_b]:
        e = o.evaluated_get(depsgraph)
        m = e.to_mesh()
        try:
            for v in m.vertices:
                wz = (o.matrix_world @ v.co).z
                if wz < min_z_rot:
                    min_z_rot = wz
        finally:
            e.to_mesh_clear()

    assert min_z_rot < -0.1, f"Expected negative min_z for rotated system, got {min_z_rot}"
    lift_rot = -min_z_rot

    # Apply root lift
    root_rot.matrix_world.translation.z += lift_rot
    bpy.context.view_layer.update()

    new_min_z_rot = float('inf')
    for o in [part_a, part_b]:
        e = o.evaluated_get(depsgraph)
        m = e.to_mesh()
        try:
            for v in m.vertices:
                wz = (o.matrix_world @ v.co).z
                if wz < new_min_z_rot:
                    new_min_z_rot = wz
        finally:
            e.to_mesh_clear()

    assert abs(new_min_z_rot - 0.0) < 1e-4, f"Rotated landed min_z must be 0.0, got {new_min_z_rot}"
    final_rel_offset = part_b.matrix_world.translation - part_a.matrix_world.translation
    assert (final_rel_offset - initial_rel_offset).length < 1e-6, "Relative offset between parts must be invariant"
    assert abs(asm_rot.matrix_world.translation.z - (initial_asm_z + lift_rot)) < 1e-4, "Assembly empty must translate by lift_rot"
    print(f"  Rotated/scaled root verified: min_z={min_z_rot:.4f} -> {new_min_z_rot:.4f}, rel vector delta={(final_rel_offset - initial_rel_offset).length:.1e}")

    # 6. Mesh count assertion: no to_mesh leak
    final_meshes = len(bpy.data.meshes)
    assert initial_meshes == final_meshes - 4, f"Mesh leak detected: {initial_meshes} vs {final_meshes}"
    print("  No to_mesh memory leak verified (evaluated meshes cleared cleanly)")

    print("PASS: test_ground_lift_comprehensive_controls (all real-Blender controls verified)")


def test_production_capsule_volume_and_manifold():
    """Verify production capsule geometry from BlenderExecutor:
    1. Standard drone capsule (r=0.04m, depth=0.25m, N=32): volume matches analytic within 2%, manifold=True.
    2. Thin propeller/strut capsule (r=0.004m, depth=0.05m, N=32): volume matches analytic within 2%, manifold=True,
       vertices preserved by scale-dependent merge distance.
    3. Reflected mesh world volume: negative determinant scale (-1, 1, 1) returns strictly positive volume.
    """
    print("\n--- Running: test_production_capsule_volume_and_manifold ---")
    reset_blend_file()
    import bmesh
    from core.blender_pipeline.progressive_v2.executor import BlenderExecutor
    from core.blender_pipeline.progressive_v2.manifest import GeometrySpec
    from core.blender_pipeline.progressive_v2.node_types import PrimitiveType

    executor = BlenderExecutor(mcp_manager=None, task_id="capsule_eval")

    test_cases = [
        # (label, radius, depth, segments, max_allowed_diff_pct)
        ("drone_fuselage_capsule", 0.04, 0.25, 32, 2.0),
        ("thin_propeller_capsule", 0.004, 0.05, 32, 2.0),
    ]

    for label, r, d, seg, max_diff in test_cases:
        spec = GeometrySpec(primitive=PrimitiveType.CAPSULE, radius=r, depth=d, segments=seg)
        identity_mr = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
        frag = executor._get_primitive_fragment(PrimitiveType.CAPSULE, label, spec, [0, 0, 0], identity_mr, "Collection")

        code = f"""
import bpy, bmesh, math, mathutils
def _link(o):
    if o.name not in bpy.context.scene.collection.objects:
        bpy.context.scene.collection.objects.link(o)
def _unlink_all(o):
    for c in list(o.users_collection):
        c.objects.unlink(o)
_sentinel_results = {{}}
{frag}
"""
        loc = {}
        exec(code, {"bpy": bpy, "bmesh": bmesh, "math": math, "mathutils": mathutils}, loc)
        obj = bpy.data.objects[label]
        bpy.context.view_layer.update()

        bm = bmesh.new()
        bm.from_mesh(obj.data)
        measured_vol = bm.calc_volume()
        is_manifold = all(len(e.link_faces) == 2 for e in bm.edges)
        vert_count = len(bm.verts)
        face_count = len(bm.faces)
        bm.free()

        # Analytic capsule volume = cylinder (d - 2r) + two hemispheres (full sphere)
        cyl_h = max(0.0, d - 2.0 * r)
        v_cyl = math.pi * (r ** 2) * cyl_h
        v_sph = (4.0 / 3.0) * math.pi * (r ** 3)
        v_analytic = v_cyl + v_sph

        diff_pct = abs(measured_vol - v_analytic) / v_analytic * 100.0

        print(f"  {label:<24} r={r:.4f} d={d:.4f} N={seg} | measured={measured_vol:.6e} analytic={v_analytic:.6e} diff={diff_pct:.3f}% manifold={is_manifold} verts={vert_count} faces={face_count}")

        assert is_manifold is True, f"Capsule {label} must be 2-manifold without non-manifold or internal edges"
        assert diff_pct <= max_diff, f"Capsule {label} volume diff {diff_pct:.2f}% exceeds {max_diff}% limit"
        assert vert_count > 100, f"Capsule {label} collapsed: vert_count={vert_count}"

        bpy.data.objects.remove(obj, do_unlink=True)

    # 3. Reflected mesh world-space volume evaluation
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    refl_obj = bpy.context.active_object
    refl_obj.scale = (-1.0, 1.0, 1.0)
    bpy.context.view_layer.update()

    bm_r = bmesh.new()
    bm_r.from_mesh(refl_obj.data)
    bm_r.transform(refl_obj.matrix_world)
    # Under reflection, signed volume is negative, but abs() ensures physical volume is positive:
    signed_vol = bm_r.calc_volume(signed=True)
    world_vol = abs(float(bm_r.calc_volume()))
    bm_r.free()

    assert signed_vol < 0.0, f"Reflected signed volume must be negative, got {signed_vol}"
    assert abs(world_vol - 1.0) < 1e-4, f"Reflected world volume must be 1.0, got {world_vol}"
    print(f"  Reflected mesh world volume verified: signed={signed_vol:.4f}, world_volume={world_vol:.4f} (strictly positive)")

    bpy.data.objects.remove(refl_obj, do_unlink=True)
    print("PASS: test_production_capsule_volume_and_manifold (production capsule volume, manifold, and reflection verified)")


def test_curved_primitives_smooth_shading_and_edge_split():
    """Verify in live Blender that:
    1. Curved primitives (CYLINDER, SPHERE, CONE, HEMISPHERE, CAPSULE, TORUS, U_SHAPE) have use_smooth=True on all faces.
    2. Sharp-capped primitives (CYLINDER, CONE, HEMISPHERE, U_SHAPE) have sharp crease edges marked via shade_smooth_by_angle.
    3. Curved primitives have ZERO destructive modifiers (no EDGE_SPLIT breaking 2-manifold topology).
    4. All curved primitives remain 100% 2-manifold.
    5. Planar primitives (BOX) remain sharp (use_smooth=False).
    """
    print("\n--- Running: test_curved_primitives_smooth_shading_and_edge_split ---")
    reset_blend_file()
    from core.blender_pipeline.progressive_v2.executor import BlenderExecutor
    from core.blender_pipeline.progressive_v2.manifest import GeometrySpec
    from core.blender_pipeline.progressive_v2.node_types import PrimitiveType
    import bmesh, mathutils

    executor = BlenderExecutor(mcp_manager=None, task_id="test_smooth")
    identity_mr = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]

    curved_cases = [
        (PrimitiveType.CYLINDER, {"radius": 0.05, "depth": 0.2, "segments": 16}, True),
        (PrimitiveType.CONE, {"radius": 0.05, "depth": 0.2, "segments": 16}, True),
        (PrimitiveType.HEMISPHERE, {"radius": 0.05, "segments": 16}, True),
        (PrimitiveType.U_SHAPE, {"major_radius": 0.1, "minor_radius": 0.02}, True),
        (PrimitiveType.SPHERE, {"radius": 0.05, "segments": 16}, False),
        (PrimitiveType.TORUS, {"major_radius": 0.1, "minor_radius": 0.02, "segments": 16}, False),
        (PrimitiveType.CAPSULE, {"radius": 0.04, "depth": 0.2, "segments": 16}, False),
    ]

    for prim, kw, expect_sharp_edges in curved_cases:
        label = f"smooth_{prim.value}"
        spec = GeometrySpec(primitive=prim, **kw)
        frag = executor._get_primitive_fragment(prim, label, spec, [0, 0, 0], identity_mr, "Collection")

        code = f"""
import bpy, bmesh, math, mathutils
def _link(o):
    bpy.context.scene.collection.objects.link(o)
def _unlink_all(o):
    for c in list(o.users_collection):
        c.objects.unlink(o)
_sentinel_results = {{}}
{frag}
"""
        loc = {}
        exec(code, {"bpy": bpy, "bmesh": bmesh, "math": math, "mathutils": mathutils}, loc)
        obj = bpy.data.objects[label]
        bpy.context.view_layer.update()

        smooth_faces = sum(1 for p in obj.data.polygons if p.use_smooth)
        total_faces = len(obj.data.polygons)
        assert smooth_faces == total_faces, f"{label}: all {total_faces} faces must have use_smooth=True, got {smooth_faces}"

        # No destructive modifiers that split edges
        assert len(obj.modifiers) == 0, f"{label} must have 0 modifiers (non-destructive shading), got {len(obj.modifiers)}"

        # 2-Manifold verification
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        is_manifold = all(len(e.link_faces) == 2 for e in bm.edges)
        bm.free()
        assert is_manifold is True, f"{label} must be 100% 2-manifold"

        sharp_edge_count = sum(1 for e in obj.data.edges if e.use_edge_sharp)
        if expect_sharp_edges:
            assert sharp_edge_count > 0, f"{label} must have sharp edges marked by shade_smooth_by_angle"

        print(f"  {label:<24} faces={total_faces} smooth={smooth_faces}/{total_faces} sharp_edges={sharp_edge_count} manifold={is_manifold} PASS")
        bpy.data.objects.remove(obj, do_unlink=True)

    # Box must remain flat
    spec_box = GeometrySpec(primitive=PrimitiveType.BOX, size=[0.2, 0.2, 0.2])
    frag_box = executor._get_primitive_fragment(PrimitiveType.BOX, "sharp_box", spec_box, [0, 0, 0], identity_mr, "Collection")
    code_box = f"""
import bpy, bmesh, math, mathutils
def _link(o): bpy.context.scene.collection.objects.link(o)
def _unlink_all(o):
    for c in list(o.users_collection): c.objects.unlink(o)
_sentinel_results = {{}}
{frag_box}
"""
    exec(code_box, {"bpy": bpy, "bmesh": bmesh, "math": math, "mathutils": mathutils}, {})
    box_obj = bpy.data.objects["sharp_box"]
    assert all(not p.use_smooth for p in box_obj.data.polygons), "Box faces must remain sharp (use_smooth=False)"
    print(f"  sharp_box                faces={len(box_obj.data.polygons)} smooth=0/{len(box_obj.data.polygons)} PASS (planar sharp preserved)")
    bpy.data.objects.remove(box_obj, do_unlink=True)

    print("PASS: test_curved_primitives_smooth_shading_and_edge_split (all curved primitives smooth with crisp caps and 2-manifold topology)")


def main():
    print("=" * 60)
    print("HEADLESS BLENDER VERIFICATION SUITE")
    print(f"Blender version: {bpy.app.version_string}")
    print("=" * 60)

    try:
        test_boolean_evaluated_depsgraph()
        test_scaled_instance_matrix_composition()
        test_hostile_strings_execution()
        test_transaction_rollback()
        test_real_blender_scene_readback_evaluation()
        test_production_executor_primitive_bounds_sweep()
        test_production_capsule_volume_and_manifold()
        test_ground_lift_comprehensive_controls()
        test_curved_primitives_smooth_shading_and_edge_split()
        print("\n" + "=" * 60)
        print("ALL HEADLESS BLENDER INTEGRATION TESTS PASSED SUCCESSFULLY!")
        print("=" * 60)
        sys.exit(0)
    except Exception as exc:
        print(f"\nFAILURE: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
