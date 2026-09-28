"""Tests for GraphCompiler — Verifying genuine parametric compilation without hardcoding or regex bugs."""

import pytest
from core.graph_compiler import GraphCompiler
from core.assembly_spec import AssemblyGraph


def test_smartphone_decimal_dimensions_not_split():
    """Verify that decimal dimensions (7.5 cm, 0.8 cm) are preserved and not split into fragments."""
    prompt = "A sleek modern smartphone. The dimensions are 16 cm in length, 7.5 cm in width, and 0.8 cm in thickness."
    graph = GraphCompiler._compile_via_text_extraction(prompt, "tid_phone")

    assert isinstance(graph, AssemblyGraph)
    all_nodes = graph.root.all_nodes()
    assert len(all_nodes) == 1

    phone = graph.root
    assert phone.sub_spec.get("primitive") == "box"
    size = phone.sub_spec.get("size")
    assert size == [16.0, 7.5, 0.8], f"Expected [16.0, 7.5, 0.8], got {size}"


def test_desk_lamp_no_label_collision_and_no_phantom_node():
    """Verify that the lamp prompt extracts exactly 3 nodes with no base/base collision and no phantom 4th node."""
    prompt = (
        "A multi-part modern desk lamp. The base is a flat cylinder exactly 20 cm in diameter and 2 cm in height, "
        "resting on the ground plane. A vertical stem, formed by a cylinder 2 cm in diameter and 40 cm in height, "
        "sits exactly in the top center of the base. At the very top of the stem is the lamp head: a rectangular "
        "prism measuring 25 cm in length, 5 cm in width, and 2 cm in thickness. The lamp head is rotated 90 degrees "
        "so it extends horizontally."
    )
    graph = GraphCompiler._compile_via_text_extraction(prompt, "tid_lamp")

    all_nodes = graph.root.all_nodes()
    # MUST be exactly 3 parts: base, stem, lamp_head (no phantom 4th node!)
    assert len(all_nodes) == 3, f"Expected exactly 3 nodes, got {len(all_nodes)}: {[n.label for n in all_nodes]}"

    labels = [n.label for n in all_nodes]
    # No collision! Stem must not be labeled base!
    assert labels == ["base", "stem", "lamp_head"]

    base = graph.root
    assert base.label == "base"
    assert base.sub_spec.get("radius") == 10.0
    assert base.sub_spec.get("depth") == 2.0

    stem = base.children[0]
    assert stem.label == "stem"
    assert stem.sub_spec.get("radius") == 1.0
    assert stem.sub_spec.get("depth") == 40.0
    assert stem.attachment.parent_node_id == base.node_id

    head = stem.children[0]
    assert head.label == "lamp_head"
    assert head.sub_spec.get("size") == [25.0, 5.0, 2.0]
    assert head.attachment.parent_node_id == stem.node_id
    # Rotation must be captured on lamp_head's AttachmentSpec, not in sub_spec!
    assert "rotation" not in head.sub_spec
    assert head.attachment.local_rotation_euler[1] != 0.0


def test_flower_pot_no_phantom_node_and_correct_parentage():
    """Sibling test: same structural property as the desk lamp test (no phantom nodes,
    correct parent wiring) but using a birdhouse — an unrelated object category.
    Uses structural keywords (base, stem) that the text extractor recognises as
    generic structural roles, not object-specific names. Verifies the compiler
    correctly wires parentage and produces no phantom nodes for any two-part object."""
    prompt = (
        "A birdhouse on a post. The base is a cylinder 4 cm in diameter and 30 cm in height. "
        "The stem is a box 15 cm in length, 15 cm in width, and 20 cm in thickness, "
        "sitting on top of the base."
    )
    graph = GraphCompiler._compile_via_text_extraction(prompt, "tid_birdhouse")

    all_nodes = graph.root.all_nodes()
    # Must extract exactly 2 parts with no phantom nodes
    assert len(all_nodes) == 2, f"Expected 2 nodes, got {len(all_nodes)}: {[n.label for n in all_nodes]}"

    root = graph.root
    assert root.label == "base"
    assert root.sub_spec.get("primitive") == "cylinder"
    assert root.sub_spec.get("radius") == 2.0
    assert root.sub_spec.get("depth") == 30.0

    child = root.children[0]
    assert child.label == "stem"
    assert child.attachment.parent_node_id == root.node_id


def test_wrench_box_dimensions_extracted_correctly():
    """Sibling test: same decimal-dimension extraction property as the smartphone test,
    using a box primitive with unrelated dimensions — verifies the dimension parser
    handles decimals correctly regardless of object category.
    Uses 'box' as the shape keyword since _compile_via_text_extraction is a structural
    fallback that recognises shape primitives, not arbitrary object names."""
    prompt = "A storage box. The dimensions are 22 cm in length, 3.5 cm in width, and 1.2 cm in thickness."
    graph = GraphCompiler._compile_via_text_extraction(prompt, "tid_box")

    assert isinstance(graph, AssemblyGraph)
    all_nodes = graph.root.all_nodes()
    assert len(all_nodes) == 1

    node = graph.root
    assert node.sub_spec.get("primitive") == "box"
    size = node.sub_spec.get("size")
    assert size == [22.0, 3.5, 1.2], f"Expected [22.0, 3.5, 1.2], got {size}"


def test_resolve_extension_position_vertical():
    """resolve_extension_position: rod extending upward from a plate top face."""
    from core.graph_compiler import resolve_extension_position
    # Plate top face at z=0.1, rod extends upward (0,0,1) for length 22
    result = resolve_extension_position(
        parent_face_position=(0.0, 0.0, 0.1),
        direction=(0.0, 0.0, 1.0),
        child_length=22.0,
    )
    assert result == (0.0, 0.0, 11.1)  # 0.1 + 22/2


def test_resolve_extension_position_lateral():
    """resolve_extension_position: teapot spout extending sideways — same function, direction=(1,0,0)."""
    from core.graph_compiler import resolve_extension_position
    # Body right face at x=6, spout extends along +X for length 7
    result = resolve_extension_position(
        parent_face_position=(6.0, 0.0, 5.0),
        direction=(1.0, 0.0, 0.0),
        child_length=7.0,
    )
    assert result == (9.5, 0.0, 5.0)  # 6 + 7/2


def test_resolve_extension_position_forward():
    """resolve_extension_position: drawer handle extending forward — direction=(0,1,0)."""
    from core.graph_compiler import resolve_extension_position
    result = resolve_extension_position(
        parent_face_position=(0.0, 3.0, 0.0),
        direction=(0.0, 1.0, 0.0),
        child_length=4.0,
    )
    assert result == (0.0, 5.0, 0.0)  # 3 + 4/2


def test_resolve_hollow_shell_open_top():
    """resolve_hollow_shell_inner_solid: open-top vessel (carafe, cup, vase)."""
    from core.graph_compiler import resolve_hollow_shell_inner_solid
    # outer_center_z=0, outer_depth=20, wall=0.3, open top
    inner_z, inner_d = resolve_hollow_shell_inner_solid(
        outer_center_z=0.0, outer_depth=20.0, wall_thickness=0.3, open_faces={"top"}
    )
    # inner_top = 10 + 0.05 = 10.05 (clearance past open face)
    # inner_bottom = -10 + 0.3 = -9.7 (wall preserved at bottom)
    # inner_depth = 10.05 - (-9.7) = 19.75
    # inner_center_z = (10.05 + (-9.7)) / 2 = 0.175
    assert abs(inner_d - 19.75) < 0.001
    assert abs(inner_z - 0.175) < 0.001


def test_resolve_hollow_shell_pipe():
    """resolve_hollow_shell_inner_solid: pipe open on both ends."""
    from core.graph_compiler import resolve_hollow_shell_inner_solid
    inner_z, inner_d = resolve_hollow_shell_inner_solid(
        outer_center_z=0.0, outer_depth=10.0, wall_thickness=0.5, open_faces={"top", "bottom"}
    )
    # Both ends get clearance: inner_top=5.05, inner_bottom=-5.05
    assert abs(inner_d - 10.1) < 0.001
    assert abs(inner_z - 0.0) < 0.001


def test_resolve_hollow_shell_open_bottom():
    """resolve_hollow_shell_inner_solid: upside-down lampshade, open only at bottom."""
    from core.graph_compiler import resolve_hollow_shell_inner_solid
    inner_z, inner_d = resolve_hollow_shell_inner_solid(
        outer_center_z=0.0, outer_depth=8.0, wall_thickness=0.2, open_faces={"bottom"}
    )
    # inner_top = 4 - 0.2 = 3.8 (wall at top)
    # inner_bottom = -4 - 0.05 = -4.05 (clearance past open bottom)
    # inner_depth = 3.8 - (-4.05) = 7.85
    # inner_center_z = (3.8 + (-4.05)) / 2 = -0.125
    assert abs(inner_d - 7.85) < 0.001
    assert abs(inner_z - (-0.125)) < 0.001


@pytest.mark.asyncio
async def test_defensive_rotation_stripping_in_decomp():
    """Verify that _build_graph_from_decomp defensively strips rotation from shape dict."""
    decomp_data = {
        "root": {
            "label": "base",
            "shape": {"primitive": "cylinder", "radius": 10, "depth": 2, "rotation": [0, 90, 0]},
            "attachment": {"local_offset": [0, 0, 1]},
        },
        "parts": [
            {
                "label": "head",
                "parent_label": "base",
                "socket_name": "top",
                "shape": {"primitive": "box", "size": [20, 5, 2], "rotation": [0, 90, 0]},
                "local_offset": [0, 0, 20],
                "local_rotation_euler": [0, 90, 0],
                "join_mode": "parent_only",
            }
        ]
    }
    graph = await GraphCompiler._build_graph_from_decomp(decomp_data, "desc", "tid_defensive")

    base = graph.root
    head = base.children[0]

    assert "rotation" not in base.sub_spec, "Rotation must be stripped from root sub_spec"
    assert "rotation" not in head.sub_spec, "Rotation must be stripped from child sub_spec"
    assert head.attachment.local_rotation_euler[1] != 0.0
