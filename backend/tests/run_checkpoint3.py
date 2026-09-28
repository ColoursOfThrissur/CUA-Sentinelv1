"""Run Checkpoint 3 - Blender Readback via HTTP API.

This script builds each test case in Blender and reads back the transforms.
Run with: python tests/run_checkpoint3.py

Requires:
- Backend server running on localhost:8000
- Blender MCP connected

Pre-flight notes:
- Skips verification/rollback (chains are deliberately non-physical)
- Clears scene between cases
- Calls view_layer.update() before reads
"""

import sys
import asyncio
import math
import json
import aiohttp
sys.path.insert(0, '.')

from tests.test_transform_chain import (
    CASE_A_NODES, CASE_A_EXPECTED,
    CASE_B_NODES, CASE_B_EXPECTED, 
    CASE_C_NODES, CASE_C_EXPECTED,
    NodeSpec, ExpectedTransform,
    build_test_assembly_graph,
    generate_blender_readback_script,
    diagnose_failure,
    TOL,
)
from core.assembly_spec import graph_to_blender_steps
from core import blender_ops as b_ops

BASE_URL = "http://localhost:8000"


# =============================================================================
# CASE E: Hemisphere on rotated arm (cutter rotation test)
# =============================================================================

CASE_E_NODES = [
    NodeSpec("base", "cylinder", radius=0.5, depth=0.2, parent=None,
             local_offset=(0, 0, 0.1), local_rotation_deg=(0, 0, 0)),
    NodeSpec("arm", "cylinder", radius=0.05, depth=1.0, parent="base",
             local_offset=(0, 0, 0.4), local_rotation_deg=(0, 90, 0)),
    NodeSpec("dome", "hemisphere", radius=0.2, depth=0.0, parent="arm",
             local_offset=(0, 0, 0.5), local_rotation_deg=(0, 0, 0)),
]

CASE_E_EXPECTED = [
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
        axis_x=(0, 0, -1),
        axis_y=(0, 1, 0),
        axis_z=(1, 0, 0),
        aabb=((-0.5, 0.5), (-0.05, 0.05), (0.45, 0.55)),
    ),
    ExpectedTransform(
        name="dome",
        position=(0.5, 0, 0.5),
        axis_x=(0, 0, -1),
        axis_y=(0, 1, 0),
        axis_z=(1, 0, 0),
        aabb=((0.5, 0.7), (-0.2, 0.2), (0.3, 0.7)),
    ),
]


async def execute_blender_code(session: aiohttp.ClientSession, code: str) -> dict:
    """Execute Blender code via the API."""
    payload = {"code": code}
    async with session.post(f"{BASE_URL}/api/blender/execute", json=payload) as resp:
        result = await resp.json()
        if not result.get("ok"):
            raise Exception(result.get("error", "Unknown error"))
        return result


async def run_case_in_blender(session: aiohttp.ClientSession, nodes, case_name, expected):
    """Build a test case in Blender and read back transforms."""
    
    print(f"\n{'='*60}")
    print(f"Building {case_name} in Blender")
    print(f"{'='*60}")
    
    # Build the graph
    graph = build_test_assembly_graph(nodes, case_name)
    steps = graph_to_blender_steps(graph)
    
    # Filter to only geometry and parenting steps (skip modifiers for this test)
    build_steps = []
    for tool_name, args in steps:
        if tool_name in (
            "blender:clear_scene",
            "blender:create_cylinder",
            "blender:create_sphere", 
            "blender:create_box",
            "blender:create_cone",
            "blender:apply_boolean",
            "blender:parent_object",
        ):
            build_steps.append((tool_name, args))
    
    print(f"Executing {len(build_steps)} steps...")
    
    OP_MAP = {
        "clear_scene": (b_ops.ClearSceneParams, b_ops._CLEAR_SCENE_TEMPLATE),
        "create_cylinder": (b_ops.CreateCylinderParams, b_ops._CREATE_CYLINDER_TEMPLATE),
        "create_sphere": (b_ops.CreateSphereParams, b_ops._CREATE_SPHERE_TEMPLATE),
        "create_box": (b_ops.CreateBoxParams, b_ops._CREATE_BOX_TEMPLATE),
        "create_cone": (b_ops.CreateConeParams, b_ops._CREATE_CONE_TEMPLATE),
        "apply_boolean": (b_ops.ApplyBooleanParams, b_ops._APPLY_BOOLEAN_TEMPLATE),
        "parent_object": (b_ops.ParentObjectParams, b_ops._PARENT_OBJECT_TEMPLATE),
    }
    
    # Execute each step
    for tool_name, args in build_steps:
        op_name = tool_name.split(":", 1)[1]
        
        if op_name not in OP_MAP:
            print(f"  Skipping unknown op: {op_name}")
            continue
        
        param_cls, template = OP_MAP[op_name]
        try:
            params = param_cls(**args)
            script = b_ops.render_op_script(template, params)
            result = await execute_blender_code(session, script)
            output = b_ops.parse_op_output(result.get("output", ""))
            if output.get("ok"):
                print(f"  {op_name}: OK")
            else:
                print(f"  {op_name}: FAILED - {output.get('error')}")
        except Exception as e:
            print(f"  {op_name}: ERROR - {e}")
    
    # Readback
    print("\nReading back transforms...")
    names = [n.name for n in nodes]
    script = generate_blender_readback_script(names)
    
    result = await execute_blender_code(session, script)
    readback = b_ops.parse_op_output(result.get("output", ""))
    readback_data = readback.get("readback", {})
    
    # Print results
    print("\nReadback results:")
    for name in names:
        if name in readback_data:
            rb = readback_data[name]
            if "error" in rb:
                print(f"  {name}: ERROR - {rb['error']}")
            else:
                print(f"  {name}:")
                print(f"    position: {rb.get('position')}")
                print(f"    axes.z: {rb.get('axes', {}).get('z')}")
                print(f"    aabb: {rb.get('aabb')}")
                print(f"    parent: {rb.get('parent')}")
                print(f"    parent_inverse_is_identity: {rb.get('parent_inverse_is_identity')}")
    
    # Compare to expected
    print("\nComparison to expected:")
    errors = []
    for exp in expected:
        if exp.name not in readback_data:
            errors.append(f"{exp.name}: not found in readback")
            continue
        
        rb = readback_data[exp.name]
        if "error" in rb:
            errors.append(f"{exp.name}: {rb['error']}")
            continue
        
        # Check position
        pos = rb.get("position", [0, 0, 0])
        for i, axis in enumerate(["x", "y", "z"]):
            diff = abs(pos[i] - exp.position[i])
            if diff > TOL:
                errors.append(f"{exp.name} position.{axis}: expected {exp.position[i]:.4f}, got {pos[i]:.4f}")
        
        # Check Z axis
        z_axis = rb.get("axes", {}).get("z", [0, 0, 0])
        for i in range(3):
            diff = abs(z_axis[i] - exp.axis_z[i])
            if diff > TOL:
                errors.append(f"{exp.name} axis_z: expected {exp.axis_z}, got {tuple(z_axis)}")
                break
        
        # Check AABB (with larger tolerance for booleans)
        aabb = rb.get("aabb", {})
        aabb_tol = 0.02  # 2cm tolerance for AABB
        for axis_name, exp_range in [("x", exp.aabb[0]), ("y", exp.aabb[1]), ("z", exp.aabb[2])]:
            actual_range = aabb.get(axis_name, [0, 0])
            if abs(actual_range[0] - exp_range[0]) > aabb_tol:
                errors.append(f"{exp.name} aabb.{axis_name}.min: expected {exp_range[0]:.3f}, got {actual_range[0]:.3f}")
            if abs(actual_range[1] - exp_range[1]) > aabb_tol:
                errors.append(f"{exp.name} aabb.{axis_name}.max: expected {exp_range[1]:.3f}, got {actual_range[1]:.3f}")
    
    if errors:
        print("  ERRORS:")
        for e in errors:
            print(f"    - {e}")
    else:
        print("  ALL CHECKS PASSED")
    
    # Diagnose failures
    case_letter = case_name.split("_")[1]
    diagnoses = diagnose_failure(case_letter, readback_data)
    if diagnoses:
        print(f"\n  FAILURE SIGNATURES DETECTED:")
        for d in diagnoses:
            print(f"    - {d}")
    
    # Special diagnosis for Case E (hemisphere)
    if case_name == "Case_E":
        dome = readback_data.get("dome", {})
        dome_aabb = dome.get("aabb", {})
        dome_x = dome_aabb.get("x", [0, 0])
        dome_z = dome_aabb.get("z", [0, 0])
        
        # Check for unrotated cutter signature
        if abs(dome_x[0] - 0.3) < 0.05 and abs(dome_z[0] - 0.5) < 0.05:
            print("    - HEMISPHERE BUG: Unrotated cutter (vertical dome)")
        
        # Check for centered half-extent signature
        if abs(dome_x[0] - 0.7) < 0.05:
            print("    - HEMISPHERE BUG: Centered half-extent (dome floating off arm)")
    
    return readback_data, errors


async def main():
    """Run checkpoint 3 via HTTP API to the running backend server."""
    
    try:
        async with aiohttp.ClientSession() as session:
            # Check if Blender is connected
            async with session.get(f"{BASE_URL}/api/apps") as resp:
                apps = await resp.json()
                blender_app = next((a for a in apps.get("apps", []) if a["app_id"] == "blender"), None)
                if not blender_app or blender_app.get("status") != "connected":
                    print("ERROR: Blender MCP not connected.")
                    print(f"Status: {blender_app.get('status') if blender_app else 'not found'}")
                    return
                print(f"Blender connected with {blender_app.get('tools_count')} tools")
            
            results = {}
            all_passed = True
            
            # Run Case A first - if it fails, diagnose before continuing
            print("\n" + "="*60)
            print("CHECKPOINT 3: Blender Readback Test")
            print("="*60)
            print("\nRunning Case A first to check parenting behavior...")
            
            readback_a, errors_a = await run_case_in_blender(
                session, CASE_A_NODES, "Case_A", CASE_A_EXPECTED
            )
            results["Case_A"] = readback_a
            
            # Check for F4 (parenting double-transform)
            arm = readback_a.get("arm", {})
            arm_pos = arm.get("position", [0, 0, 0])
            parent_inv_identity = arm.get("parent_inverse_is_identity")
            
            print(f"\n  KEY DIAGNOSTIC:")
            print(f"    arm.position.z = {arm_pos[2]:.4f} (expected 0.5)")
            print(f"    arm.parent_inverse_is_identity = {parent_inv_identity}")
            
            if abs(arm_pos[2] - 0.6) < 0.05:
                print("\n  *** F4 DETECTED: Parenting double-transform ***")
                print("  The parenting path is the bug. World values are emitted,")
                print("  but parent_inverse is identity, causing double-transform.")
                all_passed = False
            elif parent_inv_identity:
                print("\n  WARNING: parent_inverse_is_identity=True is suspicious")
                print("  When world values are emitted, inverse should be non-identity")
            
            if errors_a:
                all_passed = False
            
            # Continue with other cases
            for case_name, nodes, expected in [
                ("Case_B", CASE_B_NODES, CASE_B_EXPECTED),
                ("Case_C", CASE_C_NODES, CASE_C_EXPECTED),
                ("Case_E", CASE_E_NODES, CASE_E_EXPECTED),
            ]:
                readback, errors = await run_case_in_blender(session, nodes, case_name, expected)
                results[case_name] = readback
                if errors:
                    all_passed = False
            
            # Print summary
            print("\n" + "="*60)
            print("CHECKPOINT 3 SUMMARY")
            print("="*60)
            
            if all_passed:
                print("\n  ALL CASES PASSED")
            else:
                print("\n  SOME CASES FAILED - see errors above")
            
            print("\nRaw readback JSON:")
            print(json.dumps(results, indent=2))
        
    except aiohttp.ClientError as e:
        print(f"ERROR: Could not connect to backend server: {e}")
        print("Make sure the backend is running on localhost:8000")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
