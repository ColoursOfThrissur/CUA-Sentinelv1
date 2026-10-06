import pytest
from backend.core.blender_pipeline.progressive_v2.manifest import BuildManifest
from backend.core.blender_pipeline.progressive_v2.node_types import NodeKind
from backend.core.blender_pipeline.progressive_v2.stages.stage3_semantics import Stage3Semantics

def test_relevant_reference_targets_priority_and_truncation():
    manifest = BuildManifest.create("complex assembly model", model_id="m_test_targets")
    root_id = manifest.root_node_id

    # Create 2 assemblies
    asm1 = manifest.add_child_node(parent_id=root_id, label="asm1", kind=NodeKind.ASSEMBLY)
    asm2 = manifest.add_child_node(parent_id=root_id, label="asm2", kind=NodeKind.ASSEMBLY)

    # In asm1, add target part and 4 sibling parts
    target_node = manifest.add_child_node(parent_id=asm1.node_id, label="current_part", kind=NodeKind.PART)
    for i in range(4):
        manifest.add_child_node(parent_id=asm1.node_id, label=f"sibling_{i}", kind=NodeKind.PART)

    # In asm2, add 25 parts
    for i in range(25):
        manifest.add_child_node(parent_id=asm2.node_id, label=f"distant_{i}", kind=NodeKind.PART)

    # Call _relevant_reference_targets with max_shown=10
    result = Stage3Semantics._relevant_reference_targets(
        node=target_node,
        manifest=manifest,
        parent_label="asm1",
        max_shown=10,
    )

    assert result["total"] == 29 # 4 siblings + 25 distant parts
    assert result["truncated"] is True
    assert len(result["shown"]) == 10
    # Sibling parts must be at the front!
    for i in range(4):
        assert f"sibling_{i}" in result["shown"][:4]
