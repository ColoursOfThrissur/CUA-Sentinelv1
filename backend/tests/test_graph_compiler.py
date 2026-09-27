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


def test_defensive_rotation_stripping_in_decomp():
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
    graph = GraphCompiler._build_graph_from_decomp(decomp_data, "desc", "tid_defensive")

    base = graph.root
    head = base.children[0]

    assert "rotation" not in base.sub_spec, "Rotation must be stripped from root sub_spec"
    assert "rotation" not in head.sub_spec, "Rotation must be stripped from child sub_spec"
    assert head.attachment.local_rotation_euler[1] != 0.0
