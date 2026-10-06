"""Deterministic defect detection gates suite.

Tests against the frozen bad drone fixture to verify that:
1. Attachment gap check fails on the floating status dome (5.4 mm gap vs tolerance).
2. Contact graph connectivity check fails on disconnected floating arm guards.
3. Orientation invariant check fails on vertical blade cones.
4. Duplicate assembly check fails on overlapping redundant arm trees.
5. Material requirement traceability check fails on generic grey fallback.
6. Ground lift precondition check blocks lifting scenes with disconnected floating parts.
7. Completion status is strictly capped at COMMITTED_UNVERIFIED / FAILED when checks fail.

These tests run purely deterministically with NO LLM involved.
"""

import json
from pathlib import Path
import pytest

_FIXTURES_DIR = Path(__file__).parent / "fixtures"
_MANIFEST_PATH = _FIXTURES_DIR / "bad_drone_manifest.json"
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_MEASURED_BOUNDS_PATH = _REPO_ROOT / "data" / "measured_bounds.json"


@pytest.fixture
def bad_drone_manifest():
    with open(_MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def measured_bounds():
    if not _MEASURED_BOUNDS_PATH.exists():
        pytest.skip(f"Measured bounds file {_MEASURED_BOUNDS_PATH} not found")
    with open(_MEASURED_BOUNDS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Check 1: Attachment Gap and Penetration Check
# ---------------------------------------------------------------------------
def check_attachment_gap(parent_bounds, child_bounds, min_dimension):
    """Compute contact gap between parent top and child bottom.
    
    Relative tolerance: max(0.0005m (0.5mm), 1% of smaller part dimension).
    """
    parent_top = parent_bounds["max"][2]
    child_bottom = child_bounds["min"][2]
    gap = child_bottom - parent_top
    tolerance = max(0.0005, 0.01 * min_dimension)
    
    if abs(gap) > tolerance:
        raise AssertionError(
            f"ATTACHMENT_GAP_EXCEEDED: child bottom {child_bottom:.5f}m vs parent top "
            f"{parent_top:.5f}m, gap={gap*1000:.2f}mm exceeds tolerance {tolerance*1000:.2f}mm"
        )
    return True


def test_attachment_gap_detects_floating_status_dome(measured_bounds):
    """Verify that the 5.4 mm floating dome gap is detected and rejected."""
    chassis = measured_bounds["chassis_base_3d1a2c"]["world_bounds"]
    dome = measured_bounds["status_dome_67b3cb"]["world_bounds"]
    dome_min_dim = min(chassis["span_z"], dome["span_z"])  # 24.47mm
    
    with pytest.raises(AssertionError, match="ATTACHMENT_GAP_EXCEEDED"):
        check_attachment_gap(chassis, dome, dome_min_dim)


# ---------------------------------------------------------------------------
# Check 2: Contact Graph Connectivity (No Floating Components)
# ---------------------------------------------------------------------------
def check_contact_connectivity(objects, declared_clearance_pairs=None):
    """Build AABB contact graph and verify single connected component."""
    declared = declared_clearance_pairs or set()
    mesh_names = [k for k in objects.keys() if k != "Cube"]
    
    # Adjacency list
    adj = {k: set() for k in mesh_names}
    
    for i, name_a in enumerate(mesh_names):
        a_min = objects[name_a]["world_bounds"]["min"]
        a_max = objects[name_a]["world_bounds"]["max"]
        for j in range(i + 1, len(mesh_names)):
            name_b = mesh_names[j]
            b_min = objects[name_b]["world_bounds"]["min"]
            b_max = objects[name_b]["world_bounds"]["max"]
            
            # Check declared clearance pair (e.g. lens inside gimbal fork)
            if (name_a, name_b) in declared or (name_b, name_a) in declared:
                adj[name_a].add(name_b)
                adj[name_b].add(name_a)
                continue
                
            # AABB overlap with 2mm contact threshold
            thresh = 0.002
            overlap_x = (a_min[0] - thresh <= b_max[0]) and (a_max[0] + thresh >= b_min[0])
            overlap_y = (a_min[1] - thresh <= b_max[1]) and (a_max[1] + thresh >= b_min[1])
            overlap_z = (a_min[2] - thresh <= b_max[2]) and (a_max[2] + thresh >= b_min[2])
            
            if overlap_x and overlap_y and overlap_z:
                adj[name_a].add(name_b)
                adj[name_b].add(name_a)
                
    # Traverse from root (chassis_base)
    visited = set()
    start_node = next((k for k in mesh_names if "chassis_base" in k), mesh_names[0])
    queue = [start_node]
    visited.add(start_node)
    while queue:
        curr = queue.pop(0)
        for nbr in adj[curr]:
            if nbr not in visited:
                visited.add(nbr)
                queue.append(nbr)
                
    disconnected = set(mesh_names) - visited
    if disconnected:
        floating_guards = [k for k in disconnected if "rotor_guard" in k]
        raise AssertionError(
            f"DISCONNECTED_FLOATING_COMPONENTS: {len(disconnected)} objects disconnected from root. "
            f"Floating guards: {floating_guards}"
        )
    return True


def test_contact_graph_detects_floating_rotor_guards(measured_bounds):
    """Verify that floating disconnected guards from duplicate arm_assembly fail connectivity."""
    with pytest.raises(AssertionError, match="DISCONNECTED_FLOATING_COMPONENTS"):
        check_contact_connectivity(measured_bounds)


# ---------------------------------------------------------------------------
# Check 3: Orientation Invariant Verification
# ---------------------------------------------------------------------------
def check_orientation_invariant(part_name, world_matrix, declared_plane):
    """Verify that a part declared to rotate in an XY plane has its principal axis coplanar.
    
    For a cone pointing along its local length axis:
    If local length is along Z, and the rotor disk is in XY, the part's world Z
    must lie in XY (i.e. world_z dot (0, 0, 1) approx 0).
    """
    matrix = world_matrix["matrix"]
    # World direction of local Z axis (column 2 of rotation matrix)
    world_z = [matrix[0][2], matrix[1][2], matrix[2][2]]
    
    if declared_plane == "xy":
        # Must lie in XY plane -> vertical component matrix[2][2] must be near 0
        vertical_alignment = abs(world_z[2])
        if vertical_alignment > 0.1:  # Not coplanar
            raise AssertionError(
                f"ORIENTATION_MISMATCH: {part_name} principal axis has vertical component "
                f"{vertical_alignment:.3f} (expected ~0.0 in horizontal {declared_plane} plane)"
            )
    return True


def test_orientation_invariant_detects_vertical_blades(bad_drone_manifest):
    """Verify that vertical cone blades fail the orientation invariant check."""
    blade_node = bad_drone_manifest["nodes"]["m_f4b618e2bc_propeller_blade_front_1_25"]
    world_mat = blade_node["transform_state"]["world_matrix"]
    
    with pytest.raises(AssertionError, match="ORIENTATION_MISMATCH"):
        check_orientation_invariant("propeller_blade_front_1", world_mat, declared_plane="xy")


# ---------------------------------------------------------------------------
# Check 4: Duplicate Sibling Assembly Detection
# ---------------------------------------------------------------------------
def check_sibling_duplicate_assemblies(manifest):
    """Detect assemblies that duplicate functional roles across the manifest."""
    nodes = manifest["nodes"]
    
    # Collect all assembly labels
    assembly_labels = [n.get("label", "") for n in nodes.values() if n.get("kind") in ("assembly", "model")]
    
    # Check if both generic arm_assembly and directional arm assemblies exist
    has_generic_arm = any(l == "arm_assembly" for l in assembly_labels)
    directional_arms = [l for l in assembly_labels if l in ("arm_front", "arm_back", "arm_left", "arm_right")]
    
    # Also count functional parts: rotor guards
    guards = [n.get("label", "") for n in nodes.values() if "rotor_guard" in n.get("label", "") or "guard_" in n.get("label", "")]
    
    if has_generic_arm and len(directional_arms) >= 4:
        raise AssertionError(
            f"DUPLICATE_ASSEMBLY_ROLE: manifest contains redundant 'arm_assembly' alongside "
            f"4 directional arm assemblies {directional_arms}. Total guards defined: {len(guards)} (expected 4)."
        )
    return True


def test_duplicate_assembly_check_detects_redundant_arm_trees(bad_drone_manifest):
    """Verify that duplicate arm trees are detected before build."""
    with pytest.raises(AssertionError, match="DUPLICATE_ASSEMBLY_ROLE"):
        check_sibling_duplicate_assemblies(bad_drone_manifest)


# ---------------------------------------------------------------------------
# Check 5: Prompt-to-Manifest Material Traceability
# ---------------------------------------------------------------------------
def check_material_traceability(manifest, prompt_requirements):
    """Audit manifest material specs against structured prompt requirements."""
    nodes = manifest["nodes"]
    unmet = []
    
    for req in prompt_requirements:
        target_label = req["target_label"]
        node = next((n for n in nodes.values() if target_label in n.get("label", "")), None)
        if not node:
            unmet.append(f"Missing node for {req['id']} ({target_label})")
            continue
            
        mat = node.get("material") or {}
        for prop, expected_min in req.get("min_properties", {}).items():
            actual_val = mat.get(prop, 0.0)
            if actual_val < expected_min:
                unmet.append(
                    f"{req['id']} ({node['label']}): {prop}={actual_val} < required {expected_min}"
                )
                
    if unmet:
        raise AssertionError(f"MATERIAL_REQUIREMENT_UNMET: {'; '.join(unmet)}")
    return True


def test_material_traceability_detects_generic_grey_fallback(bad_drone_manifest):
    """Verify that unpopulated glass transmission and emissive LEDs fail traceability."""
    requirements = [
        {
            "id": "REQ_DOME_GLASS",
            "target_label": "status_dome",
            "min_properties": {"transmission": 0.8},
        },
        {
            "id": "REQ_LED_EMISSION",
            "target_label": "led_1",
            "min_properties": {"emission_strength": 5.0},
        }
    ]
    with pytest.raises(AssertionError, match="MATERIAL_REQUIREMENT_UNMET"):
        check_material_traceability(bad_drone_manifest, requirements)


# ---------------------------------------------------------------------------
# Check 6: Ground Lift Precondition (Connectivity Before Lift)
# ---------------------------------------------------------------------------
def perform_ground_lift_safe(objects, declared_clearance_pairs=None):
    """Ensure ground lift is rejected if scene has disconnected floating parts."""
    # Run connectivity first
    check_contact_connectivity(objects, declared_clearance_pairs)
    
    # If passed, calculate z_min and lift
    z_min = min(obj["world_bounds"]["min"][2] for k, obj in objects.items() if k != "Cube")
    return -z_min


def test_ground_lift_blocked_by_disconnected_components(measured_bounds):
    """Verify that ground lift refuses to run on disconnected scenes."""
    with pytest.raises(AssertionError, match="DISCONNECTED_FLOATING_COMPONENTS"):
        perform_ground_lift_safe(measured_bounds)


# ---------------------------------------------------------------------------
# Check 7: Completion Status Capping at COMMITTED_UNVERIFIED
# ---------------------------------------------------------------------------
def compute_build_status(passed_gates: dict) -> str:
    """Cap completion status: cannot be SUCCESS unless all required gates pass."""
    required_gates = [
        "attachment_gap", "connectivity", "orientation_invariant",
        "duplicate_assemblies", "material_traceability", "scene_readback"
    ]
    all_passed = all(passed_gates.get(g, False) for g in required_gates)
    if not all_passed:
        return "committed_unverified"
    return "success"


def test_status_capped_at_committed_unverified_when_gates_fail():
    """Verify that failing any visual or physical gate prevents SUCCESS."""
    gates_state = {
        "scene_readback": True,  # Old readback passed 58/58!
        "attachment_gap": False, # Fails on dome gap
        "connectivity": False,   # Fails on floating guards
        "orientation_invariant": False, # Fails on vertical blades
        "duplicate_assemblies": False,  # Fails on duplicate arm trees
        "material_traceability": False, # Fails on generic grey
    }
    status = compute_build_status(gates_state)
    assert status == "committed_unverified"
    assert status != "success"


# ---------------------------------------------------------------------------
# Negative Control Tests: Reference Artist Model Passes Gates
# ---------------------------------------------------------------------------
_ARTIST_BOUNDS_PATH = _REPO_ROOT / "data" / "artist_measured_bounds.json"


@pytest.fixture
def artist_measured_bounds():
    if not _ARTIST_BOUNDS_PATH.exists():
        pytest.skip(f"Artist measured bounds file {_ARTIST_BOUNDS_PATH} not found")
    with open(_ARTIST_BOUNDS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_reference_model_attachment_gap_passes(artist_measured_bounds):
    """Negative control: Reference artist model status dome sits flush on top panel (0.0mm gap)."""
    top_panel = artist_measured_bounds["chassis_top_panel"]["world_bounds"]
    dome = artist_measured_bounds["status_dome"]["world_bounds"]
    min_dim = min(top_panel["span_z"], dome["span_z"])  # 4mm
    assert check_attachment_gap(top_panel, dome, min_dim) is True


def test_reference_model_orientation_invariant_passes(artist_measured_bounds):
    """Negative control: Reference artist model blades are rotated coplanar to horizontal plane."""
    blade_mat = artist_measured_bounds["blade_1_1"]["matrix_world"]
    world_mat_dict = {"matrix": blade_mat}
    assert check_orientation_invariant("blade_1_1", world_mat_dict, declared_plane="xy") is True


# ---------------------------------------------------------------------------
# Programmatic Perturbation Tests: Sharp Tolerance Boundaries
# ---------------------------------------------------------------------------
def test_attachment_gap_sharp_tolerance_boundary():
    """Verify that the attachment gap gate has a sharp deterministic threshold.
    
    For a 50mm thick part, relative tolerance is max(0.5mm, 1% of 50mm) = 0.5mm.
    Perturbations <= 0.5mm must pass.
    Perturbations > 0.5mm must fail with ATTACHMENT_GAP_EXCEEDED.
    """
    box_a = {"max": [0.5, 0.4, 0.50], "min": [-0.5, -0.4, 0.00]}
    min_dim = 0.050  # 50mm

    # Perturbations in mm: (offset_mm, should_pass)
    test_cases = [
        (0.0, True),
        (0.1, True),
        (0.3, True),
        (0.49, True),
        (0.50, True),
        (0.51, False),
        (0.70, False),
        (1.0, False),
        (5.0, False),
    ]

    for offset_mm, should_pass in test_cases:
        offset_m = offset_mm / 1000.0
        box_b = {"max": [0.45, 0.35, 0.70 + offset_m], "min": [0.35, 0.25, 0.50 + offset_m]}
        if should_pass:
            assert check_attachment_gap(box_a, box_b, min_dim) is True, f"Failed on valid offset {offset_mm}mm"
        else:
            with pytest.raises(AssertionError, match="ATTACHMENT_GAP_EXCEEDED"):
                check_attachment_gap(box_a, box_b, min_dim)


def test_assembly_four_leg_symmetry_and_contact():
    """Assert a four-leg table assembly is symmetric about the center and grounded."""
    # 4 legs placed at (+/- 0.4, +/- 0.3)
    legs = [
        {"name": "leg_fl", "pos": [0.4, 0.3, 0.35], "span_z": 0.70, "min_z": 0.0},
        {"name": "leg_fr", "pos": [0.4, -0.3, 0.35], "span_z": 0.70, "min_z": 0.0},
        {"name": "leg_bl", "pos": [-0.4, 0.3, 0.35], "span_z": 0.70, "min_z": 0.0},
        {"name": "leg_br", "pos": [-0.4, -0.3, 0.35], "span_z": 0.70, "min_z": 0.0},
    ]

    # Centroid check
    centroid_x = sum(leg["pos"][0] for leg in legs) / 4.0
    centroid_y = sum(leg["pos"][1] for leg in legs) / 4.0
    assert abs(centroid_x) < 1e-6
    assert abs(centroid_y) < 1e-6

    # Ground contact check (all legs reach Z=0 within 1mm)
    assert all(abs(leg["min_z"]) < 0.001 for leg in legs)

    # Now perturb one leg horizontally by 20mm
    perturbed_legs = [dict(l) for l in legs]
    perturbed_legs[0]["pos"] = [0.42, 0.3, 0.35]
    pert_cx = sum(leg["pos"][0] for leg in perturbed_legs) / 4.0
    # Asymmetry detected: centroid shifted by 5mm
    assert abs(pert_cx) > 0.004

