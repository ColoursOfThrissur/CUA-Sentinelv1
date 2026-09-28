"""Transform Path Diagnostic — Three-Level Chain Test.

Purpose: Determine whether the pipeline's transform bug is in:
(a) composition/emit, (b) Blender parenting, or (c) Stage 4 socket logic.

Every expected value is hand-computed. Do NOT fix tests to match pipeline output.
If they disagree, the disagreement IS the finding.
"""

import math
from dataclasses import dataclass
from typing import List, Tuple, Dict, Any, Optional

# Tolerance for comparisons
TOL = 1e-4

# Rotation matrices at 90 degrees
# Rx(90): Z->-Y, Y->+Z, X->X
# Ry(90): Z->+X, X->-Z, Y->Y  
# Rz(90): X->+Y, Y->-X, Z->Z


@dataclass
class ExpectedTransform:
    """Expected world-space transform for verification."""
    name: str
    position: Tuple[float, float, float]
    # World image of local X, Y, Z axes (columns of rotation matrix)
    axis_x: Tuple[float, float, float]
    axis_y: Tuple[float, float, float]
    axis_z: Tuple[float, float, float]
    # World AABB: ((xmin,xmax), (ymin,ymax), (zmin,zmax))
    aabb: Tuple[Tuple[float, float], Tuple[float, float], Tuple[float, float]]


@dataclass 
class NodeSpec:
    """Specification for a test node."""
    name: str
    primitive: str
    radius: float
    depth: float
    parent: Optional[str]
    local_offset: Tuple[float, float, float]
    local_rotation_deg: Tuple[float, float, float]


# =============================================================================
# ORACLE: Pure Python matrix math (Checkpoint 1)
# =============================================================================

def rx(deg: float) -> List[List[float]]:
    """Rotation matrix around X axis."""
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return [
        [1, 0, 0],
        [0, c, -s],
        [0, s, c],
    ]


def ry(deg: float) -> List[List[float]]:
    """Rotation matrix around Y axis."""
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return [
        [c, 0, s],
        [0, 1, 0],
        [-s, 0, c],
    ]


def rz(deg: float) -> List[List[float]]:
    """Rotation matrix around Z axis."""
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return [
        [c, -s, 0],
        [s, c, 0],
        [0, 0, 1],
    ]


def mat_mul(a: List[List[float]], b: List[List[float]]) -> List[List[float]]:
    """Multiply two 3x3 matrices."""
    return [
        [sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)]
        for i in range(3)
    ]


def mat_vec(m: List[List[float]], v: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """Multiply 3x3 matrix by vector."""
    return (
        m[0][0]*v[0] + m[0][1]*v[1] + m[0][2]*v[2],
        m[1][0]*v[0] + m[1][1]*v[1] + m[1][2]*v[2],
        m[2][0]*v[0] + m[2][1]*v[1] + m[2][2]*v[2],
    )


def euler_to_matrix(deg: Tuple[float, float, float]) -> List[List[float]]:
    """Convert Euler XYZ (degrees) to rotation matrix.
    
    Blender order: R = Rz * Ry * Rx (X applied first).
    """
    return mat_mul(rz(deg[2]), mat_mul(ry(deg[1]), rx(deg[0])))


def identity() -> List[List[float]]:
    """3x3 identity matrix."""
    return [[1, 0, 0], [0, 1, 0], [0, 0, 1]]


def get_column(m: List[List[float]], col: int) -> Tuple[float, float, float]:
    """Get column vector from matrix."""
    return (m[0][col], m[1][col], m[2][col])


def vec_add(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """Add two vectors."""
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


# =============================================================================
# CASE A: Rotated arm, end disc (single rotated level)
# =============================================================================

CASE_A_NODES = [
    NodeSpec("base", "cylinder", radius=0.5, depth=0.2, parent=None,
             local_offset=(0, 0, 0.1), local_rotation_deg=(0, 0, 0)),
    NodeSpec("arm", "cylinder", radius=0.05, depth=1.0, parent="base",
             local_offset=(0, 0, 0.4), local_rotation_deg=(0, 90, 0)),
    NodeSpec("disc", "cylinder", radius=0.15, depth=0.02, parent="arm",
             local_offset=(0, 0, 0.51), local_rotation_deg=(0, 0, 0)),
]

# Hand-computed expected values for Case A:
# - arm world position = (0,0,0.1) + (0,0,0.4) = (0, 0, 0.5)
#   Base has identity rotation, so offset not rotated.
# - arm world rotation = Ry90: local Z maps to world +X
# - disc offset in arm frame (0,0,0.51) -> world: Ry90*(0,0,0.51) = (0.51, 0, 0)
# - disc world position = (0,0,0.5) + (0.51,0,0) = (0.51, 0, 0.5)
# - disc world rotation = Ry90 * I = Ry90: axis +X

CASE_A_EXPECTED = [
    ExpectedTransform(
        name="base",
        position=(0, 0, 0.1),
        axis_x=(1, 0, 0),
        axis_y=(0, 1, 0),
        axis_z=(0, 0, 1),
        aabb=((-0.5, 0.5), (-0.5, 0.5), (0, 0.2)),
    ),
    ExpectedTransform(
        name="arm",
        position=(0, 0, 0.5),
        axis_x=(0, 0, -1),  # Ry90: X -> -Z
        axis_y=(0, 1, 0),   # Ry90: Y -> Y
        axis_z=(1, 0, 0),   # Ry90: Z -> +X
        aabb=((-0.5, 0.5), (-0.05, 0.05), (0.45, 0.55)),
    ),
    ExpectedTransform(
        name="disc",
        position=(0.51, 0, 0.5),
        axis_x=(0, 0, -1),  # Inherits Ry90
        axis_y=(0, 1, 0),
        axis_z=(1, 0, 0),
        aabb=((0.50, 0.52), (-0.15, 0.15), (0.35, 0.65)),
    ),
]


# =============================================================================
# CASE B: Compound rotation (Euler-order sensitivity)
# =============================================================================

CASE_B_NODES = [
    NodeSpec("base", "cylinder", radius=0.5, depth=0.2, parent=None,
             local_offset=(0, 0, 0.1), local_rotation_deg=(0, 0, 0)),
    NodeSpec("arm_b", "cylinder", radius=0.05, depth=1.0, parent="base",
             local_offset=(0, 0, 0.4), local_rotation_deg=(90, 0, 90)),
    NodeSpec("cap", "sphere", radius=0.10, depth=0.0, parent="arm_b",
             local_offset=(0, 0, 0.6), local_rotation_deg=(0, 0, 0)),
]

# Hand-computed: R = Rz90 * Ry0 * Rx90 = Rz90 * Rx90
# Local Z: Rx90->(0,-1,0), then Rz90->(1,0,0). Axis +X.
# Local X: Rx90->(1,0,0), Rz90->(0,1,0).
# Local Y: Rx90->(0,0,1), Rz90->(0,0,1).
# cap world offset = R*(0,0,0.6) = (0.6, 0, 0) -> cap position (0.6, 0, 0.5)

CASE_B_EXPECTED = [
    ExpectedTransform(
        name="base",
        position=(0, 0, 0.1),
        axis_x=(1, 0, 0),
        axis_y=(0, 1, 0),
        axis_z=(0, 0, 1),
        aabb=((-0.5, 0.5), (-0.5, 0.5), (0, 0.2)),
    ),
    ExpectedTransform(
        name="arm_b",
        position=(0, 0, 0.5),
        axis_x=(0, 1, 0),   # Rz90*Rx90: X -> +Y
        axis_y=(0, 0, 1),   # Rz90*Rx90: Y -> +Z
        axis_z=(1, 0, 0),   # Rz90*Rx90: Z -> +X
        aabb=((-0.5, 0.5), (-0.05, 0.05), (0.45, 0.55)),
    ),
    ExpectedTransform(
        name="cap",
        position=(0.6, 0, 0.5),
        axis_x=(0, 1, 0),   # Inherits parent rotation
        axis_y=(0, 0, 1),
        axis_z=(1, 0, 0),
        aabb=((0.5, 0.7), (-0.1, 0.1), (0.4, 0.6)),
    ),
]


# =============================================================================
# CASE C: Two rotated levels (accumulation, Euler-addition trap)
# =============================================================================

CASE_C_NODES = [
    NodeSpec("base", "cylinder", radius=0.5, depth=0.2, parent=None,
             local_offset=(0, 0, 0.1), local_rotation_deg=(0, 0, 0)),
    NodeSpec("link1", "cylinder", radius=0.05, depth=1.0, parent="base",
             local_offset=(0, 0, 0.4), local_rotation_deg=(90, 0, 0)),
    NodeSpec("link2", "cylinder", radius=0.05, depth=0.5, parent="link1",
             local_offset=(0, 0, 0.75), local_rotation_deg=(0, 90, 0)),
    NodeSpec("tip", "sphere", radius=0.05, depth=0.0, parent="link2",
             local_offset=(0, 0, 0.30), local_rotation_deg=(0, 0, 0)),
]

# Hand-computed:
# link1 world position (0,0,0.5). Rx90: local Z -> -Y.
# link2 offset Rx90*(0,0,0.75) = (0,-0.75,0) -> position (0, -0.75, 0.5)
# link2 composed rotation Rx90*Ry90:
#   local Z: Ry90->(1,0,0), Rx90->(1,0,0). Axis +X.
#   Columns X/Y/Z = (0,1,0) / (0,0,1) / (1,0,0)
# tip offset (Rx90*Ry90)*(0,0,0.3) = (0.3,0,0) -> position (0.3, -0.75, 0.5)

# NOTE: Case C's composed matrix equals Case B's. This is a cross-check:
# two different Euler routes reach one matrix.

CASE_C_EXPECTED = [
    ExpectedTransform(
        name="base",
        position=(0, 0, 0.1),
        axis_x=(1, 0, 0),
        axis_y=(0, 1, 0),
        axis_z=(0, 0, 1),
        aabb=((-0.5, 0.5), (-0.5, 0.5), (0, 0.2)),
    ),
    ExpectedTransform(
        name="link1",
        position=(0, 0, 0.5),
        axis_x=(1, 0, 0),   # Rx90: X -> X
        axis_y=(0, 0, 1),   # Rx90: Y -> +Z
        axis_z=(0, -1, 0),  # Rx90: Z -> -Y
        aabb=((-0.05, 0.05), (-0.5, 0.5), (0.45, 0.55)),
    ),
    ExpectedTransform(
        name="link2",
        position=(0, -0.75, 0.5),
        axis_x=(0, 1, 0),   # Rx90*Ry90: X -> +Y
        axis_y=(0, 0, 1),   # Rx90*Ry90: Y -> +Z
        axis_z=(1, 0, 0),   # Rx90*Ry90: Z -> +X
        aabb=((-0.25, 0.25), (-0.80, -0.70), (0.45, 0.55)),
    ),
    ExpectedTransform(
        name="tip",
        position=(0.3, -0.75, 0.5),
        axis_x=(0, 1, 0),   # Inherits link2 rotation
        axis_y=(0, 0, 1),
        axis_z=(1, 0, 0),
        aabb=((0.25, 0.35), (-0.80, -0.70), (0.45, 0.55)),
    ),
]


# =============================================================================
# CHECKPOINT 1: Oracle verification (pure Python)
# =============================================================================

def compute_world_transforms(nodes: List[NodeSpec]) -> Dict[str, Dict[str, Any]]:
    """Compute world transforms using the oracle math.
    
    Convention: world = parent_world @ local
    Child with identity rotation inherits parent's orientation.
    """
    results = {}
    
    for node in nodes:
        if node.parent is None:
            # Root node: local = world
            world_pos = node.local_offset
            world_rot = euler_to_matrix(node.local_rotation_deg)
        else:
            # Get parent's world transform
            parent = results[node.parent]
            parent_pos = parent["position"]
            parent_rot = parent["rotation_matrix"]
            
            # Rotate local offset by parent's rotation
            rotated_offset = mat_vec(parent_rot, node.local_offset)
            world_pos = vec_add(parent_pos, rotated_offset)
            
            # Compose rotations: world = parent @ local
            local_rot = euler_to_matrix(node.local_rotation_deg)
            world_rot = mat_mul(parent_rot, local_rot)
        
        results[node.name] = {
            "position": world_pos,
            "rotation_matrix": world_rot,
            "axis_x": get_column(world_rot, 0),
            "axis_y": get_column(world_rot, 1),
            "axis_z": get_column(world_rot, 2),
        }
    
    return results


def verify_oracle_against_expected(
    nodes: List[NodeSpec],
    expected: List[ExpectedTransform],
    case_name: str,
) -> List[str]:
    """Verify oracle computation matches hand-computed expected values.
    
    Returns list of error messages (empty if all pass).
    """
    errors = []
    computed = compute_world_transforms(nodes)
    
    for exp in expected:
        if exp.name not in computed:
            errors.append(f"{case_name}/{exp.name}: not in computed results")
            continue
        
        comp = computed[exp.name]
        
        # Check position
        for i, axis in enumerate(["x", "y", "z"]):
            diff = abs(comp["position"][i] - exp.position[i])
            if diff > TOL:
                errors.append(
                    f"{case_name}/{exp.name} position.{axis}: "
                    f"expected {exp.position[i]:.4f}, got {comp['position'][i]:.4f}"
                )
        
        # Check axes
        for axis_name, exp_axis, comp_key in [
            ("X", exp.axis_x, "axis_x"),
            ("Y", exp.axis_y, "axis_y"),
            ("Z", exp.axis_z, "axis_z"),
        ]:
            comp_axis = comp[comp_key]
            for i in range(3):
                diff = abs(comp_axis[i] - exp_axis[i])
                if diff > TOL:
                    errors.append(
                        f"{case_name}/{exp.name} axis_{axis_name}: "
                        f"expected {exp_axis}, got {tuple(round(v,4) for v in comp_axis)}"
                    )
                    break
    
    return errors


# =============================================================================
# CHECKPOINT 3: Blender readback script
# =============================================================================

def generate_blender_build_script(nodes: List[NodeSpec], case_name: str) -> str:
    """Generate Blender script to build the test case."""
    lines = [
        "import bpy",
        "import json",
        "import math",
        "from mathutils import Vector, Matrix",
        "",
        "# Clear scene",
        "bpy.ops.object.select_all(action='SELECT')",
        "bpy.ops.object.delete()",
        "",
        f"# Build {case_name}",
    ]
    
    for node in nodes:
        if node.primitive == "cylinder":
            lines.append(f"bpy.ops.mesh.primitive_cylinder_add(")
            lines.append(f"    radius={node.radius},")
            lines.append(f"    depth={node.depth},")
        elif node.primitive == "sphere":
            lines.append(f"bpy.ops.mesh.primitive_uv_sphere_add(")
            lines.append(f"    radius={node.radius},")
        
        lines.append(f"    location=(0, 0, 0),")
        lines.append(f")")
        lines.append(f"obj = bpy.context.active_object")
        lines.append(f"obj.name = '{node.name}'")
        lines.append("")
    
    lines.append("# Now we need to set transforms and parent")
    lines.append("# This is where we test the pipeline's approach")
    lines.append("")
    
    return "\n".join(lines)


def generate_blender_readback_script(names: List[str]) -> str:
    """Generate Blender script to read back transforms."""
    script = '''
import bpy
import json
from mathutils import Vector, Matrix

bpy.context.view_layer.update()  # Ensure matrix_world is current

results = {}
names = ''' + repr(names) + '''

for name in names:
    obj = bpy.data.objects.get(name)
    if not obj:
        results[name] = {"error": "not found"}
        continue
    
    mw = obj.matrix_world
    r = mw.to_3x3()
    corners = [mw @ Vector(c) for c in obj.bound_box]
    
    results[name] = {
        "position": [round(v, 6) for v in mw.translation],
        "axes": {
            "x": [round(v, 6) for v in r.col[0]],
            "y": [round(v, 6) for v in r.col[1]],
            "z": [round(v, 6) for v in r.col[2]],
        },
        "aabb": {
            "x": [round(min(c.x for c in corners), 6), round(max(c.x for c in corners), 6)],
            "y": [round(min(c.y for c in corners), 6), round(max(c.y for c in corners), 6)],
            "z": [round(min(c.z for c in corners), 6), round(max(c.z for c in corners), 6)],
        },
        "scale": [round(v, 6) for v in obj.scale],
        "parent": obj.parent.name if obj.parent else None,
        "parent_inverse_is_identity": (
            obj.matrix_parent_inverse == Matrix.Identity(4)
        ) if obj.parent else None,
    }

res = {"ok": True, "readback": results}
print("SENTINEL_OUTPUT_START" + json.dumps(res) + "SENTINEL_OUTPUT_END")
'''
    return script


# =============================================================================
# FAILURE SIGNATURES (Case A reference values)
# =============================================================================

FAILURE_SIGNATURES = {
    "F1_offset_not_rotated": {
        "description": "Offset not rotated by parent (naive add)",
        "disc_position": (0, 0, 1.01),
    },
    "F2_rotation_double_applied": {
        "description": "Rotation double-applied (disc given Ry90 explicitly plus inheritance)",
        "disc_position": (0.51, 0, 0.5),  # Position correct
        "disc_axis_z": (0, 0, -1),  # But axis wrong
    },
    "F3_rotation_not_inherited": {
        "description": "Rotation not inherited (identity emitted as world rotation)",
        "disc_position": (0.51, 0, 0.5),  # Position correct
        "disc_axis_z": (0, 0, 1),  # Axis points wrong way (not rotated)
    },
    "F4_parenting_double_transform": {
        "description": "Parenting double-transform (world values emitted, parent set with identity inverse)",
        "arm_position": (0, 0, 0.6),  # Base position added again
        "disc_position": (0.5, 0, 0.09),
        "disc_axis_z": (0, 0, -1),
    },
    "F5_euler_order_error": {
        "description": "Euler-order error (Case B)",
        "arm_b_axis_z": (0, -1, 0),  # -Y instead of +X
        "cap_position": (0, -0.6, 0.5),
    },
    "F6_euler_addition": {
        "description": "Euler addition instead of composition (Case C)",
        "link2_axis_z": (0, -1, 0),  # -Y instead of +X
        "tip_position": (0, -1.05, 0.5),
    },
}


def diagnose_failure(case: str, readback: Dict[str, Any]) -> List[str]:
    """Attempt to match readback against known failure signatures."""
    diagnoses = []
    
    if case == "A":
        disc = readback.get("disc", {})
        arm = readback.get("arm", {})
        
        disc_pos = tuple(disc.get("position", [0, 0, 0]))
        disc_z = tuple(disc.get("axes", {}).get("z", [0, 0, 0]))
        arm_pos = tuple(arm.get("position", [0, 0, 0]))
        
        # F1: disc at wrong position (offset not rotated)
        if abs(disc_pos[2] - 1.01) < 0.05:
            diagnoses.append("F1: Offset not rotated by parent rotation")
        
        # F4: arm at wrong position (double transform)
        if abs(arm_pos[2] - 0.6) < 0.05:
            diagnoses.append("F4: Parenting double-transform detected")
        
        # F2 vs F3: position correct but axis wrong
        if abs(disc_pos[0] - 0.51) < 0.05 and abs(disc_pos[2] - 0.5) < 0.05:
            if abs(disc_z[2] - (-1)) < 0.1:
                diagnoses.append("F2: Rotation double-applied (axis inverted)")
            elif abs(disc_z[2] - 1) < 0.1:
                diagnoses.append("F3: Rotation not inherited (axis not rotated)")
    
    elif case == "B":
        arm_b = readback.get("arm_b", {})
        cap = readback.get("cap", {})
        
        arm_z = tuple(arm_b.get("axes", {}).get("z", [0, 0, 0]))
        cap_pos = tuple(cap.get("position", [0, 0, 0]))
        
        # F5: Euler order error
        if abs(arm_z[1] - (-1)) < 0.1:  # Z axis points -Y
            diagnoses.append("F5: Euler-order error (XYZ vs ZYX)")
        if abs(cap_pos[1] - (-0.6)) < 0.05:
            diagnoses.append("F5: Cap position confirms Euler-order error")
    
    elif case == "C":
        link2 = readback.get("link2", {})
        tip = readback.get("tip", {})
        
        link2_z = tuple(link2.get("axes", {}).get("z", [0, 0, 0]))
        tip_pos = tuple(tip.get("position", [0, 0, 0]))
        
        # F6: Euler addition instead of composition
        if abs(link2_z[1] - (-1)) < 0.1:  # Z axis points -Y
            diagnoses.append("F6: Euler addition instead of matrix composition")
        if abs(tip_pos[1] - (-1.05)) < 0.05:
            diagnoses.append("F6: Tip position confirms Euler addition bug")
    
    return diagnoses


# =============================================================================
# TEST RUNNER
# =============================================================================

def run_checkpoint_1():
    """Checkpoint 1: Verify oracle against hand-computed expected values."""
    print("=" * 60)
    print("CHECKPOINT 1: Oracle Verification")
    print("=" * 60)
    
    all_errors = []
    
    for case_name, nodes, expected in [
        ("Case_A", CASE_A_NODES, CASE_A_EXPECTED),
        ("Case_B", CASE_B_NODES, CASE_B_EXPECTED),
        ("Case_C", CASE_C_NODES, CASE_C_EXPECTED),
    ]:
        print(f"\n{case_name}:")
        errors = verify_oracle_against_expected(nodes, expected, case_name)
        if errors:
            for e in errors:
                print(f"  ERROR: {e}")
            all_errors.extend(errors)
        else:
            print("  PASS: Oracle matches expected values")
            
            # Print computed values for reference
            computed = compute_world_transforms(nodes)
            for exp in expected:
                comp = computed[exp.name]
                print(f"    {exp.name}:")
                print(f"      pos: {tuple(round(v,4) for v in comp['position'])}")
                print(f"      Z-axis: {tuple(round(v,4) for v in comp['axis_z'])}")
    
    print("\n" + "=" * 60)
    if all_errors:
        print(f"CHECKPOINT 1 FAILED: {len(all_errors)} errors")
        print("FIX THE ORACLE OR EXPECTED VALUES BEFORE PROCEEDING")
    else:
        print("CHECKPOINT 1 PASSED: Oracle is correct")
    print("=" * 60)
    
    return len(all_errors) == 0


def print_readback_script():
    """Print the Blender readback script for manual execution."""
    print("\n" + "=" * 60)
    print("BLENDER READBACK SCRIPT")
    print("=" * 60)
    print("Run this in Blender after building each case:")
    print()
    
    all_names = ["base", "arm", "disc", "arm_b", "cap", "link1", "link2", "tip"]
    print(generate_blender_readback_script(all_names))


if __name__ == "__main__":
    import sys
    
    # Always run Checkpoint 1 first
    oracle_ok = run_checkpoint_1()
    
    if not oracle_ok:
        print("\nStopping: Oracle verification failed")
        sys.exit(1)
    
    # Print instructions for Checkpoint 2 and 3
    print("\n" + "=" * 60)
    print("NEXT STEPS")
    print("=" * 60)
    print("""
1. CHECKPOINT 2 - Emit Check:
   Capture the location/rotation args from graph_to_blender_steps
   for each case. Record whether they are world or local values.

2. CHECKPOINT 3 - Blender Readback:
   Build each case in Blender and run the readback script.
   Compare against expected values above.

3. Use diagnose_failure() to identify which failure signature matches.
""")
    
    print_readback_script()


# =============================================================================
# CHECKPOINT 2 & 3: Pipeline integration test
# =============================================================================

def build_test_assembly_graph(nodes: List[NodeSpec], case_name: str):
    """Build an AssemblyGraph from test node specs.
    
    This bypasses LLM/Stage 4 and directly creates the graph
    to test graph_to_blender_steps in isolation.
    """
    from core.assembly_spec import (
        AssemblyGraph, AssemblyNode, AttachmentSpec, 
        JoinMode, PartParadigm
    )
    
    node_map = {}
    root_node = None
    
    for spec in nodes:
        sub_spec = {"primitive": spec.primitive}
        if spec.primitive == "cylinder":
            sub_spec["radius"] = spec.radius
            sub_spec["depth"] = spec.depth
        elif spec.primitive in ("sphere", "hemisphere"):
            sub_spec["radius"] = spec.radius
        
        # Convert degrees to radians for the graph
        rot_rad = tuple(math.radians(d) for d in spec.local_rotation_deg)
        
        attachment = AttachmentSpec(
            parent_node_id=f"node_{spec.parent}" if spec.parent else None,
            socket_name=f"{spec.parent}.child" if spec.parent else "root",
            local_offset=spec.local_offset,
            local_rotation_euler=rot_rad,
            join_mode=JoinMode.PARENT_ONLY,
        )
        
        node = AssemblyNode(
            node_id=f"node_{spec.name}",
            label=spec.name,
            paradigm=PartParadigm.PRIMITIVE,
            sub_spec=sub_spec,
            attachment=attachment,
            children=[],
        )
        
        node_map[spec.name] = node
        
        if spec.parent is None:
            root_node = node
        else:
            node_map[spec.parent].children.append(node)
    
    return AssemblyGraph(
        schema_version="2.0",
        task_id=f"test_{case_name}",
        root=root_node,
        description=case_name,
        rests_on_surface=True,
    )


def capture_emit_values(nodes: List[NodeSpec], case_name: str) -> Dict[str, Any]:
    """Capture the values that graph_to_blender_steps would emit.
    
    Returns dict mapping object name to emitted location/rotation.
    """
    from core.assembly_spec import graph_to_blender_steps
    
    graph = build_test_assembly_graph(nodes, case_name)
    steps = graph_to_blender_steps(graph)
    
    emit_values = {}
    
    for tool_name, args in steps:
        if tool_name.startswith("blender:create_"):
            name = args.get("name")
            if name:
                emit_values[name] = {
                    "location": args.get("location"),
                    "rotation_deg": args.get("rotation"),
                }
    
    return emit_values


def compare_emit_to_expected(
    emit_values: Dict[str, Any],
    expected: List[ExpectedTransform],
    case_name: str,
) -> Tuple[List[str], str]:
    """Compare emitted values to expected.
    
    Returns (errors, frame_type) where frame_type is 'world' or 'local' or 'mixed'.
    """
    errors = []
    frame_votes = {"world": 0, "local": 0}
    
    # Get the node specs to compare against local values
    if case_name == "Case_A":
        nodes = CASE_A_NODES
    elif case_name == "Case_B":
        nodes = CASE_B_NODES
    else:
        nodes = CASE_C_NODES
    
    node_by_name = {n.name: n for n in nodes}
    
    for exp in expected:
        if exp.name not in emit_values:
            errors.append(f"{case_name}/{exp.name}: not in emit values")
            continue
        
        emit = emit_values[exp.name]
        emit_loc = tuple(emit["location"]) if emit["location"] else (0, 0, 0)
        
        # Check if emit matches world expected
        world_match = all(
            abs(emit_loc[i] - exp.position[i]) < TOL 
            for i in range(3)
        )
        
        # Check if emit matches local offset
        local_spec = node_by_name.get(exp.name)
        local_match = False
        if local_spec:
            local_match = all(
                abs(emit_loc[i] - local_spec.local_offset[i]) < TOL
                for i in range(3)
            )
        
        if world_match:
            frame_votes["world"] += 1
        elif local_match:
            frame_votes["local"] += 1
        else:
            errors.append(
                f"{case_name}/{exp.name}: emit location {emit_loc} "
                f"matches neither world {exp.position} nor local {local_spec.local_offset if local_spec else 'N/A'}"
            )
    
    # Determine frame type
    if frame_votes["world"] > 0 and frame_votes["local"] == 0:
        frame_type = "world"
    elif frame_votes["local"] > 0 and frame_votes["world"] == 0:
        frame_type = "local"
    elif frame_votes["world"] > 0 and frame_votes["local"] > 0:
        frame_type = "mixed"
    else:
        frame_type = "unknown"
    
    return errors, frame_type


async def run_checkpoint_2_and_3(mcp_manager) -> Dict[str, Any]:
    """Run Checkpoints 2 and 3 with actual Blender connection.
    
    Returns full diagnostic results.
    """
    from core.assembly_spec import graph_to_blender_steps
    from core.blender_ops import parse_op_output
    
    results = {
        "checkpoint_2": {},
        "checkpoint_3": {},
        "diagnoses": {},
    }
    
    for case_name, nodes, expected in [
        ("Case_A", CASE_A_NODES, CASE_A_EXPECTED),
        ("Case_B", CASE_B_NODES, CASE_B_EXPECTED),
        ("Case_C", CASE_C_NODES, CASE_C_EXPECTED),
    ]:
        print(f"\n{'='*60}")
        print(f"Testing {case_name}")
        print(f"{'='*60}")
        
        # Checkpoint 2: Capture emit values
        emit_values = capture_emit_values(nodes, case_name)
        errors, frame_type = compare_emit_to_expected(emit_values, expected, case_name)
        
        results["checkpoint_2"][case_name] = {
            "emit_values": emit_values,
            "frame_type": frame_type,
            "errors": errors,
        }
        
        print(f"\nCheckpoint 2 - Emit values ({frame_type} frame):")
        for name, vals in emit_values.items():
            print(f"  {name}: loc={vals['location']}, rot={vals['rotation_deg']}")
        
        if errors:
            print(f"  ERRORS: {errors}")
        
        # Checkpoint 3: Build in Blender and readback
        if mcp_manager:
            graph = build_test_assembly_graph(nodes, case_name)
            steps = graph_to_blender_steps(graph)
            
            # Execute steps
            for tool_name, args in steps:
                if tool_name.startswith("blender:"):
                    op_name = tool_name.split(":", 1)[1]
                    # Would execute via MCP here
            
            # Readback
            names = [n.name for n in nodes]
            script = generate_blender_readback_script(names)
            
            try:
                result = await mcp_manager.call_locked(
                    "blender", "execute_blender_code", {"code": script}
                )
                readback = parse_op_output(result.get("output", ""))
                readback_data = readback.get("readback", {})
                
                results["checkpoint_3"][case_name] = readback_data
                
                print(f"\nCheckpoint 3 - Blender readback:")
                for name in names:
                    if name in readback_data:
                        rb = readback_data[name]
                        print(f"  {name}:")
                        print(f"    pos: {rb.get('position')}")
                        print(f"    Z-axis: {rb.get('axes', {}).get('z')}")
                
                # Diagnose failures
                case_letter = case_name.split("_")[1]
                diagnoses = diagnose_failure(case_letter, readback_data)
                results["diagnoses"][case_name] = diagnoses
                
                if diagnoses:
                    print(f"\n  DIAGNOSES: {diagnoses}")
                    
            except Exception as e:
                print(f"  Blender readback failed: {e}")
                results["checkpoint_3"][case_name] = {"error": str(e)}
    
    return results
