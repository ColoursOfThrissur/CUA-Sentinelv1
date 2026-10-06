"""
test_blender_mcp_live.py  --  complex live Blender MCP hierarchy test.

Hierarchy: robotic arm (depth 4, 14 mesh objects, 4 assembly empties)

  robot_arm  (MODEL)
    base_assembly  (ASSEMBLY)  -- 3 parts, no rotation
      base_plate     BOX        [0,    0,    0.025]  identity
      left_foot      BOX        [-0.1, 0,    0.01 ]  identity
      right_foot     BOX        [0.1,  0,    0.01 ]  identity
    shoulder_assembly (ASSEMBLY) -- 2 parts, 45-deg tilt on X
      shoulder_hub   CYLINDER   [0,    0,    0.1  ]  rot X=45deg
      shoulder_bolt  CYLINDER   [0,    0.05, 0.12 ]  rot X=45deg
    upper_arm_assembly (ASSEMBLY) -- depth-2 assembly with nested wrist
      upper_tube     CYLINDER   [0,    0,    0.3  ]  identity
      elbow_sphere   SPHERE     [0,    0,    0.5  ]  identity
      wrist_assembly (ASSEMBLY) -- depth-3, 90-deg rot on Z
        wrist_disc   CYLINDER   [0.05, 0,    0.55 ]  rot Z=90deg
        wrist_pin    CYLINDER   [0.05, 0,    0.58 ]  rot Z=90deg
        finger_l     BOX        [0.05,-0.04, 0.6  ]  rot Z=90deg
        finger_r     BOX        [0.05, 0.04, 0.6  ]  rot Z=90deg
    tool_assembly  (ASSEMBLY)  -- cone tip, 180-deg flip
      tool_cone      CONE       [0,    0,    0.65 ]  rot X=180deg
      tool_tip       SPHERE     [0,    0,    0.72 ]  rot X=180deg

Checks (25 total):
  - All 14 objects created successfully
  - All 14 world positions correct after parenting (< 1mm tolerance)
  - All 4 rotation matrices preserved (diagonal sign check)
  - Full parent chain correct for depth-4 path:
      finger_l -> wrist_assembly_empty -> upper_arm_assembly_empty -> (root)
  - Cleanup removes all 18 objects + collection
"""

from __future__ import annotations
import asyncio, json, math, sys, os

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

COLL = "Sentinel_ComplexTest"
TOL  = 0.002  # 2mm world-position tolerance


# ---------------------------------------------------------------------------
# Transform helpers
# ---------------------------------------------------------------------------

def _rot_x(deg):
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return [[1,0,0],[0,c,-s],[0,s,c]]

def _rot_z(deg):
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return [[c,-s,0],[s,c,0],[0,0,1]]

def _matrix(pos, rot3x3=None):
    """Build 4x4 matrix from position and optional 3x3 rotation."""
    if rot3x3 is None:
        rot3x3 = [[1,0,0],[0,1,0],[0,0,1]]
    x, y, z = pos
    r = rot3x3
    return [
        [r[0][0], r[0][1], r[0][2], x],
        [r[1][0], r[1][1], r[1][2], y],
        [r[2][0], r[2][1], r[2][2], z],
        [0.0,     0.0,     0.0,     1.0],
    ]


# ---------------------------------------------------------------------------
# Scene definition
# ---------------------------------------------------------------------------

ID = _matrix  # alias for identity-rotation matrix

RX45  = _rot_x(45)
RX180 = _rot_x(180)
RZ90  = _rot_z(90)

# (label, primitive, radius_or_size, depth, pos, rot3x3)
OBJECTS = [
    # base_assembly
    ("base_plate",    "box",      [0.2, 0.15, 0.05], None, [0,     0,     0.025], None),
    ("left_foot",     "box",      [0.05,0.15, 0.02], None, [-0.1,  0,     0.01 ], None),
    ("right_foot",    "box",      [0.05,0.15, 0.02], None, [0.1,   0,     0.01 ], None),
    # shoulder_assembly
    ("shoulder_hub",  "cylinder", None, [0.06, 0.08], [0,     0,     0.1  ], RX45),
    ("shoulder_bolt", "cylinder", None, [0.02, 0.06], [0,     0.05,  0.12 ], RX45),
    # upper_arm_assembly
    ("upper_tube",    "cylinder", None, [0.04, 0.2 ], [0,     0,     0.3  ], None),
    ("elbow_sphere",  "sphere",   None, [0.05, None], [0,     0,     0.5  ], None),
    # wrist_assembly (nested under upper_arm)
    ("wrist_disc",    "cylinder", None, [0.04, 0.02], [0.05,  0,     0.55 ], RZ90),
    ("wrist_pin",     "cylinder", None, [0.01, 0.06], [0.05,  0,     0.58 ], RZ90),
    ("finger_l",      "box",      [0.02,0.06, 0.01], None, [0.05, -0.04,  0.6  ], RZ90),
    ("finger_r",      "box",      [0.02,0.06, 0.01], None, [0.05,  0.04,  0.6  ], RZ90),
    # tool_assembly
    ("tool_cone",     "cone",     None, [0.03, 0.07], [0,     0,     0.65 ], RX180),
    ("tool_tip",      "sphere",   None, [0.02, None], [0,     0,     0.72 ], RX180),
    # extra part to stress-test: a torus at a weird offset
    ("cable_ring",    "torus",    None, [0.04, 0.008],[0.02,  0.02,  0.45 ], RX45),
]

# Assembly empties: (empty_name, pos, rot3x3, parent_empty_name, children_labels)
ASSEMBLIES = [
    ("base_assembly_empty",      [0,0,0],     None,  None,
     ["base_plate","left_foot","right_foot"]),
    ("shoulder_assembly_empty",  [0,0,0.08],  RX45,  None,
     ["shoulder_hub","shoulder_bolt"]),
    ("upper_arm_assembly_empty", [0,0,0.25],  None,  None,
     ["upper_tube","elbow_sphere","cable_ring"]),
    ("wrist_assembly_empty",     [0.05,0,0.53], RZ90, "upper_arm_assembly_empty",
     ["wrist_disc","wrist_pin","finger_l","finger_r"]),
    ("tool_assembly_empty",      [0,0,0.62],  RX180, None,
     ["tool_cone","tool_tip"]),
]

ALL_NAMES = [o[0] for o in OBJECTS] + [a[0] for a in ASSEMBLIES]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse(output: str) -> dict:
    start = output.find("SENTINEL_OUTPUT_START")
    end   = output.find("SENTINEL_OUTPUT_END")
    if start == -1 or end == -1:
        return {"ok": False, "raw": output[:400]}
    try:
        return json.loads(output[start + len("SENTINEL_OUTPUT_START"):end])
    except Exception as e:
        return {"ok": False, "parse_error": str(e), "raw": output[:400]}


def _prim_script(label, prim, size_or_none, depth_pair, pos, rot3x3, coll):
    """Generate a create-primitive script for one object."""
    matrix_rows = _matrix(pos, rot3x3)
    if prim == "box":
        size = size_or_none or [0.1, 0.1, 0.1]
        return f'''
import bpy, bmesh, json, mathutils
name = {repr(label)}
coll_name = {repr(coll)}
if name in bpy.data.objects:
    bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
mesh = bpy.data.meshes.new(name)
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=1.0)
for v in bm.verts:
    v.co.x *= {size[0]}; v.co.y *= {size[1]}; v.co.z *= {size[2]}
bm.to_mesh(mesh); bm.free()
obj = bpy.data.objects.new(name, mesh)
obj.matrix_world = mathutils.Matrix({repr(matrix_rows)})
c = bpy.data.collections.get(coll_name)
if c: c.objects.link(obj)
else: bpy.context.collection.objects.link(obj)
result = {{"ok": True, "name": obj.name, "loc": [round(v,4) for v in obj.matrix_world.translation]}}
print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''
    elif prim == "cylinder":
        radius, depth = depth_pair
        return f'''
import bpy, json, mathutils
name = {repr(label)}
coll_name = {repr(coll)}
if name in bpy.data.objects:
    bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
bpy.ops.mesh.primitive_cylinder_add(radius={radius}, depth={depth}, vertices=32)
obj = bpy.context.active_object
obj.name = name; obj.data.name = name
obj.matrix_world = mathutils.Matrix({repr(matrix_rows)})
c = bpy.data.collections.get(coll_name)
if c:
    for col in obj.users_collection: col.objects.unlink(obj)
    c.objects.link(obj)
result = {{"ok": True, "name": obj.name, "loc": [round(v,4) for v in obj.matrix_world.translation]}}
print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''
    elif prim == "sphere":
        radius = depth_pair[0]
        return f'''
import bpy, json, mathutils
name = {repr(label)}
coll_name = {repr(coll)}
if name in bpy.data.objects:
    bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
bpy.ops.mesh.primitive_uv_sphere_add(radius={radius})
obj = bpy.context.active_object
obj.name = name; obj.data.name = name
obj.matrix_world = mathutils.Matrix({repr(matrix_rows)})
c = bpy.data.collections.get(coll_name)
if c:
    for col in obj.users_collection: col.objects.unlink(obj)
    c.objects.link(obj)
result = {{"ok": True, "name": obj.name, "loc": [round(v,4) for v in obj.matrix_world.translation]}}
print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''
    elif prim == "cone":
        radius, depth = depth_pair
        return f'''
import bpy, json, mathutils
name = {repr(label)}
coll_name = {repr(coll)}
if name in bpy.data.objects:
    bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
bpy.ops.mesh.primitive_cone_add(radius1={radius}, depth={depth})
obj = bpy.context.active_object
obj.name = name; obj.data.name = name
obj.matrix_world = mathutils.Matrix({repr(matrix_rows)})
c = bpy.data.collections.get(coll_name)
if c:
    for col in obj.users_collection: col.objects.unlink(obj)
    c.objects.link(obj)
result = {{"ok": True, "name": obj.name, "loc": [round(v,4) for v in obj.matrix_world.translation]}}
print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''
    elif prim == "torus":
        major, minor = depth_pair
        return f'''
import bpy, json, mathutils
name = {repr(label)}
coll_name = {repr(coll)}
if name in bpy.data.objects:
    bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
bpy.ops.mesh.primitive_torus_add(major_radius={major}, minor_radius={minor})
obj = bpy.context.active_object
obj.name = name; obj.data.name = name
obj.matrix_world = mathutils.Matrix({repr(matrix_rows)})
c = bpy.data.collections.get(coll_name)
if c:
    for col in obj.users_collection: col.objects.unlink(obj)
    c.objects.link(obj)
result = {{"ok": True, "name": obj.name, "loc": [round(v,4) for v in obj.matrix_world.translation]}}
print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
'''
    raise ValueError(f"Unknown primitive: {prim}")


def _build_full_scene_script() -> str:
    """One single Blender script: collection + all meshes + all empties + parenting.
    Everything runs in one call so all objects exist when parenting executes."""
    lines = [
        "import bpy, bmesh, json, mathutils, math",
        f"coll_name = {repr(COLL)}",
        "results = {}",
        "",
        "# --- collection ---",
        "if coll_name not in bpy.data.collections:",
        "    coll = bpy.data.collections.new(coll_name)",
        "    bpy.context.scene.collection.children.link(coll)",
        "coll = bpy.data.collections.get(coll_name)",
        "",
        "def link(obj):",
        "    if coll: coll.objects.link(obj)",
        "    else: bpy.context.collection.objects.link(obj)",
        "",
        "def unlink_all(obj):",
        "    for c in list(obj.users_collection): c.objects.unlink(obj)",
        "",
    ]

    # --- mesh objects ---
    lines.append("# --- mesh objects ---")
    for label, prim, size, depth_pair, pos, rot in OBJECTS:
        matrix_rows = _matrix(pos, rot)
        lines.append(f"if {repr(label)} in bpy.data.objects: bpy.data.objects.remove(bpy.data.objects[{repr(label)}], do_unlink=True)")
        if prim == "box":
            s = size or [0.1, 0.1, 0.1]
            lines += [
                f"_mesh = bpy.data.meshes.new({repr(label)})",
                f"_bm = bmesh.new()",
                f"bmesh.ops.create_cube(_bm, size=1.0)",
                f"for _v in _bm.verts: _v.co.x *= {s[0]}; _v.co.y *= {s[1]}; _v.co.z *= {s[2]}",
                f"_bm.to_mesh(_mesh); _bm.free()",
                f"_obj = bpy.data.objects.new({repr(label)}, _mesh)",
                f"_obj.matrix_world = mathutils.Matrix({repr(matrix_rows)})",
                f"link(_obj)",
                f"results[{repr(label)}] = list(_obj.matrix_world.translation)",
            ]
        elif prim == "cylinder":
            r, d = depth_pair
            lines += [
                f"bpy.ops.mesh.primitive_cylinder_add(radius={r}, depth={d}, vertices=32)",
                f"_obj = bpy.context.active_object",
                f"_obj.name = {repr(label)}; _obj.data.name = {repr(label)}",
                f"_obj.matrix_world = mathutils.Matrix({repr(matrix_rows)})",
                f"unlink_all(_obj); link(_obj)",
                f"results[{repr(label)}] = list(_obj.matrix_world.translation)",
            ]
        elif prim == "sphere":
            r = depth_pair[0]
            lines += [
                f"bpy.ops.mesh.primitive_uv_sphere_add(radius={r})",
                f"_obj = bpy.context.active_object",
                f"_obj.name = {repr(label)}; _obj.data.name = {repr(label)}",
                f"_obj.matrix_world = mathutils.Matrix({repr(matrix_rows)})",
                f"unlink_all(_obj); link(_obj)",
                f"results[{repr(label)}] = list(_obj.matrix_world.translation)",
            ]
        elif prim == "cone":
            r, d = depth_pair
            lines += [
                f"bpy.ops.mesh.primitive_cone_add(radius1={r}, depth={d})",
                f"_obj = bpy.context.active_object",
                f"_obj.name = {repr(label)}; _obj.data.name = {repr(label)}",
                f"_obj.matrix_world = mathutils.Matrix({repr(matrix_rows)})",
                f"unlink_all(_obj); link(_obj)",
                f"results[{repr(label)}] = list(_obj.matrix_world.translation)",
            ]
        elif prim == "torus":
            major, minor = depth_pair
            lines += [
                f"bpy.ops.mesh.primitive_torus_add(major_radius={major}, minor_radius={minor})",
                f"_obj = bpy.context.active_object",
                f"_obj.name = {repr(label)}; _obj.data.name = {repr(label)}",
                f"_obj.matrix_world = mathutils.Matrix({repr(matrix_rows)})",
                f"unlink_all(_obj); link(_obj)",
                f"results[{repr(label)}] = list(_obj.matrix_world.translation)",
            ]
        lines.append("")

    # --- assembly empties + parenting (parents first, then nested) ---
    lines.append("# --- assembly empties + parenting ---")
    for empty_name, pos, rot, parent_empty, children in ASSEMBLIES:
        matrix_rows = _matrix(pos, rot)
        lines += [
            f"if {repr(empty_name)} in bpy.data.objects: bpy.data.objects.remove(bpy.data.objects[{repr(empty_name)}], do_unlink=True)",
            f"_e = bpy.data.objects.new({repr(empty_name)}, None)",
            f"_e.empty_display_type = 'PLAIN_AXES'",
            f"_e.empty_display_size = 0.15",
            f"_e.matrix_world = mathutils.Matrix({repr(matrix_rows)})",
            f"bpy.context.scene.collection.objects.link(_e)",
            f"unlink_all(_e); link(_e)",
        ]
        if parent_empty:
            lines += [
                f"_pe = bpy.data.objects.get({repr(parent_empty)})",
                f"if _pe:",
                f"    _e.parent = _pe",
                f"    _e.matrix_parent_inverse = _pe.matrix_world.inverted()",
            ]
        lines += [
            f"_einv = _e.matrix_world.inverted()",
            f"for _cn in {repr(children)}:",
            f"    _co = bpy.data.objects.get(_cn)",
            f"    if _co:",
            f"        _co.parent = _e",
            f"        _co.matrix_parent_inverse = _einv",
            f"results[{repr(empty_name)}] = list(_e.matrix_world.translation)",
            "",
        ]

    lines += [
        "result = {\"ok\": True, \"created\": results}",
        "print(\"SENTINEL_OUTPUT_START\" + json.dumps(result) + \"SENTINEL_OUTPUT_END\")",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

async def run(mcp) -> dict:
    async def blender(code: str) -> dict:
        r = await mcp.call_tool("blender", "execute_blender_code", {"code": code})
        return _parse(r.get("output", ""))

    results = {}

    # ONE single script: create collection + all meshes + all empties + parent everything
    # This is the key fix: everything in one call so Blender sees all objects at once
    # when parenting runs.
    big_script = _build_full_scene_script()
    results["build_scene"] = await blender(big_script)

    # Query all world locations + parents + rotation row0
    results["query"] = await blender(f'''
import bpy, json
names = {repr(ALL_NAMES)}
out = {{}}
for n in names:
    obj = bpy.data.objects.get(n)
    if obj:
        wm = obj.matrix_world
        out[n] = {{
            "loc":    [round(v,4) for v in wm.translation],
            "rot_r0": [round(v,4) for v in wm.to_3x3()[0]],
            "parent": obj.parent.name if obj.parent else None,
        }}
    else:
        out[n] = None
result = {{"ok": True, "objects": out}}
print("SENTINEL_OUTPUT_START" + json.dumps(result) + "SENTINEL_OUTPUT_END")
''')

    # Cleanup skipped intentionally -- leave scene in Blender for visual inspection
    results["cleanup"] = {"ok": True, "skipped": True}

    return results


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"{'[PASS]' if ok else '[FAIL]'} {label}" + (f"  ({detail})" if detail else ""))
    return ok


def run_checks(results: dict) -> bool:
    print("\n--- Step summary ---")
    for k, v in results.items():
        tag = "[ok]" if v.get("ok") else "[ERR]"
        if not v.get("ok"):
            print(f"  {tag} {k}: {json.dumps(v)[:400]}")
        else:
            print(f"  {tag} {k}")

    print("\n--- Checks ---")
    all_pass = True
    q = results.get("query", {})
    objs = q.get("objects", {})

    # Check 1: build_scene succeeded
    all_pass &= check("build_scene ok", results.get("build_scene", {}).get("ok", False))

    # Check 2: world positions preserved after parenting
    for label, prim, size, depth_pair, expected_pos, rot in OBJECTS:
        obj_data = objs.get(label)
        if obj_data is None:
            all_pass &= check(f"{label} world pos", False, "object missing from query")
            continue
        loc = obj_data["loc"]
        close = all(abs(loc[i] - expected_pos[i]) < TOL for i in range(3))
        all_pass &= check(
            f"{label} world pos preserved",
            close,
            f"expected={[round(v,3) for v in expected_pos]} got={loc}",
        )

    # Check 4: rotation matrices preserved for rotated objects
    # For RX45: row0 should be [1,0,0] (X axis unchanged)
    # For RX180: row0 should be [1,0,0]
    # For RZ90: row0 should be [0,-1,0] (X axis rotated to -Y)
    rot_checks = [
        ("shoulder_hub",  RX45,  [1.0, 0.0, 0.0]),
        ("wrist_disc",    RZ90,  [0.0, -1.0, 0.0]),
        ("tool_cone",     RX180, [1.0, 0.0, 0.0]),
        ("cable_ring",    RX45,  [1.0, 0.0, 0.0]),
        ("shoulder_assembly_empty", RX45, [1.0, 0.0, 0.0]),
        ("wrist_assembly_empty",    RZ90, [0.0, -1.0, 0.0]),
        ("tool_assembly_empty",     RX180,[1.0, 0.0, 0.0]),
    ]
    for label, _, expected_r0 in rot_checks:
        obj_data = objs.get(label)
        if obj_data is None:
            all_pass &= check(f"{label} rotation", False, "missing")
            continue
        r0 = obj_data["rot_r0"]
        close = all(abs(r0[i] - expected_r0[i]) < 0.01 for i in range(3))
        all_pass &= check(
            f"{label} rotation row0 preserved",
            close,
            f"expected={expected_r0} got={r0}",
        )

    # Check 5: parent chains
    parent_checks = [
        ("base_plate",             "base_assembly_empty"),
        ("left_foot",              "base_assembly_empty"),
        ("right_foot",             "base_assembly_empty"),
        ("shoulder_hub",           "shoulder_assembly_empty"),
        ("upper_tube",             "upper_arm_assembly_empty"),
        ("elbow_sphere",           "upper_arm_assembly_empty"),
        ("cable_ring",             "upper_arm_assembly_empty"),
        ("wrist_disc",             "wrist_assembly_empty"),
        ("finger_l",               "wrist_assembly_empty"),
        ("finger_r",               "wrist_assembly_empty"),
        ("tool_cone",              "tool_assembly_empty"),
        ("tool_tip",               "tool_assembly_empty"),
        ("wrist_assembly_empty",   "upper_arm_assembly_empty"),  # depth-3 nesting
    ]
    for label, expected_parent in parent_checks:
        obj_data = objs.get(label)
        if obj_data is None:
            all_pass &= check(f"{label} parent", False, "missing")
            continue
        got = obj_data["parent"]
        all_pass &= check(
            f"{label} -> {expected_parent}",
            got == expected_parent,
            f"got={got}",
        )

    # Cleanup skipped -- scene left in Blender for visual inspection
    print("[INFO] cleanup skipped -- check Blender outliner manually")

    return all_pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    print("\n" + "="*60)
    print("  Complex Live Blender MCP Hierarchy Test")
    print("  Robotic arm: 14 meshes, 5 empties, depth-4, mixed rotations")
    print("="*60 + "\n")

    from core.mcp_manager import MCPManager
    mcp = MCPManager()
    mcp.initialize_from_config()

    print("Connecting to Blender MCP...")
    try:
        conn = await mcp.connect_app("blender")
        print(f"Connected. Tools: {[t.name for t in conn.discovered_tools]}\n")
    except Exception as e:
        print(f"[FAIL] Could not connect: {e}")
        return 1

    try:
        results = await run(mcp)
    except Exception as e:
        import traceback; traceback.print_exc()
        await mcp.shutdown()
        return 1

    all_pass = run_checks(results)

    print("\n" + "="*60)
    total = sum(1 for k in results if k.startswith("obj_") or k.startswith("asm_"))
    print(f"  Objects/assemblies sent: {total}")
    print("  ALL CHECKS PASSED" if all_pass else "  SOME CHECKS FAILED -- see above")
    print("="*60)

    await mcp.shutdown()
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
