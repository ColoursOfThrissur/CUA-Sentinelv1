"""
Dry-run probe: simulates what _build_graph_from_decomp + graph_to_blender_steps
produce for the tower, using the exact decomp JSON the LLM returned last time
(all local_offset:[0,0,0] for children).

Run from backend/:
    python ..\scripts\probe_stacking.py
"""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)) + "/backend")

# Patch out DB calls so DimensionResolver doesn't need live DBs
import unittest.mock as mock
sys.modules.setdefault("db.connections", mock.MagicMock())

from core.graph_compiler import GraphCompiler
from core.assembly_spec import graph_to_blender_steps

# Exact shape of what the LLM returned last run — all offsets zero
MOCK_DECOMP = {
    "rests_on_surface": True,
    "root": {
        "label": "base",
        "shape": {"primitive": "cylinder", "radius": 10.0, "depth": 2.0, "vertices": 32},
        "dimension_confidence": {},
        "attachment": {"local_offset": [0, 0, 1.0]}
    },
    "parts": [
        {
            "label": "pillar",
            "parent_label": "base",
            "socket_name": "top_center",
            "shape": {"primitive": "cylinder", "radius": 1.5, "depth": 20.0, "vertices": 6},
            "dimension_confidence": {},
            "local_offset": [0, 0, 0],   # LLM returned zero
            "local_rotation_euler": [0, 0, 0],
            "join_mode": "parent_only"
        },
        {
            "label": "radar_dish",
            "parent_label": "pillar",
            "socket_name": "top_center",
            "shape": {"primitive": "hemisphere", "radius": 6.0},
            "dimension_confidence": {},
            "local_offset": [0, 0, 0],   # LLM returned zero
            "local_rotation_euler": [0, 0, 0],
            "join_mode": "parent_only"
        },
        {
            "label": "antenna",
            "parent_label": "radar_dish",
            "socket_name": "top_center",
            "shape": {"primitive": "cone", "radius1": 0.5, "depth": 8.0},
            "dimension_confidence": {},
            "local_offset": [0, 0, 0],   # LLM returned zero
            "local_rotation_euler": [0, 0, 0],
            "join_mode": "parent_only"
        },
        {
            "label": "support_strut_1",
            "parent_label": "pillar",
            "socket_name": "side",
            "shape": {"primitive": "cylinder", "radius": 0.3, "depth": 5.0, "vertices": 32},
            "dimension_confidence": {},
            "local_offset": [4.8, 0, -1.0],  # LLM gave non-zero X, negative Z
            "local_rotation_euler": [0, 0, 0],
            "join_mode": "parent_only"
        },
        {
            "label": "support_strut_2",
            "parent_label": "pillar",
            "socket_name": "side",
            "shape": {"primitive": "cylinder", "radius": 0.3, "depth": 5.0, "vertices": 32},
            "dimension_confidence": {},
            "local_offset": [0, 4.8, -1.0],
            "local_rotation_euler": [0, 0, 0],
            "join_mode": "parent_only"
        },
        {
            "label": "support_strut_3",
            "parent_label": "pillar",
            "socket_name": "side",
            "shape": {"primitive": "cylinder", "radius": 0.3, "depth": 5.0, "vertices": 32},
            "dimension_confidence": {},
            "local_offset": [-4.8, 0, -1.0],
            "local_rotation_euler": [0, 0, 0],
            "join_mode": "parent_only"
        },
        {
            "label": "support_strut_4",
            "parent_label": "pillar",
            "socket_name": "side",
            "shape": {"primitive": "cylinder", "radius": 0.3, "depth": 5.0, "vertices": 32},
            "dimension_confidence": {},
            "local_offset": [0, -4.8, -1.0],
            "local_rotation_euler": [0, 0, 0],
            "join_mode": "parent_only"
        },
    ]
}

graph = GraphCompiler._build_graph_from_decomp(MOCK_DECOMP, "sci-fi tower", "probe_tid")
steps = graph_to_blender_steps(graph)

print("=== WORLD POSITIONS FROM graph_to_blender_steps ===\n")
for tool, args in steps:
    loc = args.get("location")
    name = args.get("name", "")
    size = args.get("size")
    if loc:
        print(f"  {tool:<30} {name:<22} loc={loc}  {'size='+str(size) if size else ''}")
    else:
        print(f"  {tool:<30} {name}")

print("\n=== EXPECTED (correct geometry) ===")
print("  base          Z=1.0   (depth/2=1)")
print("  pillar        Z=12.0  (base_Z=1 + base_half=1 + pillar_half=10)")
print("  radar_dish    Z=28.0  (pillar_Z=12 + pillar_half=10 + dish_half=6)")
print("  antenna       Z=38.0  (dish_Z=28 + dish_half=6 + antenna_half=4)")
print("  struts        Z=?     (should be on pillar sides, NOT overridden to top)")
print("  hemi_cutter   Z=22.0  (dish_Z=28 - dish_r/2=3 = 25... check)")

print("\n=== STRUT OFFSET LOGIC CHECK ===")
for part in MOCK_DECOMP["parts"]:
    if "strut" in part["label"]:
        off = part["local_offset"]
        has_nonzero_xy = abs(off[0]) > 0.01 or abs(off[1]) > 0.01
        z_near_zero = abs(off[2]) < 0.01
        print(f"  {part['label']}: offset={off}  nonzero_XY={has_nonzero_xy}  z_near_zero={z_near_zero}")
        print(f"    -> current fix would override Z: {z_near_zero}  (WRONG if nonzero_XY)")
