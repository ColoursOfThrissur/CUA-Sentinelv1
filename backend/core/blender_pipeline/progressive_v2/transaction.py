"""Frozen scene-plan compiler for transactional Blender model creation.

The progressive controller may use LLM stages while *planning*, but Blender is
not mutated until a complete manifest has been validated.  The compiler then
buffers all model operations and submits one construction transaction.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from .node_types import NodeKind, SocketType
from .capabilities import SCENE_PLAN_SCHEMA_VERSION, capability_manifest, validate_transaction_capabilities
from .scene_ir import ExecutableScenePlan


class ScenePlanError(RuntimeError):
    """Raised when a manifest is not safe to submit to Blender."""


@dataclass(frozen=True)
class FrozenScenePlan:
    """Small immutable identity for the plan which Blender is allowed to build."""

    fingerprint: str
    node_ids: Tuple[str, ...]
    contract_fingerprint: str

    @classmethod
    def from_manifest(cls, manifest: Any) -> "FrozenScenePlan":
        executable = ExecutableScenePlan.from_manifest(manifest)
        node_ids = tuple(sorted(manifest.nodes))
        contract = executable.contract
        contract_encoded = json.dumps(contract, sort_keys=True, default=str, separators=(",", ":"))
        return cls(
            fingerprint=executable.fingerprint,
            node_ids=node_ids,
            contract_fingerprint=hashlib.sha256(contract_encoded.encode("utf-8")).hexdigest(),
        )


@dataclass(frozen=True)
class SceneTransactionReceipt:
    part_count: int
    assembly_count: int
    boolean_count: int
    blender_objects: List[str]


class SceneTransactionCompiler:
    """Compile a resolved manifest into one Blender construction request."""

    def __init__(self, executor: Any, manifest: Any) -> None:
        self.executor = executor
        self.manifest = manifest

    def validate(self) -> None:
        errors = []
        # Constraint validation happens before executor buffering.  A failed
        # structural plan therefore cannot create a partial Blender scene.
        from .constraint_planner import StructuralConstraintPlanner
        errors.extend(StructuralConstraintPlanner.validate(self.manifest))
        # Validate explicitly requested component cardinality and physically
        # unambiguous component forms before buffering any Blender operation.
        from .design_fidelity import DesignFidelityValidator
        errors.extend(DesignFidelityValidator.validate(self.manifest))
        for node in self.manifest.nodes.values():
            if node.kind in (NodeKind.PART, NodeKind.DEFINITION) and node.geometry is None:
                errors.append(f"part '{node.label}' has no geometry")
            elif node.kind in (NodeKind.PART, NodeKind.DEFINITION):
                errors.extend(self._geometry_errors(node))
                errors.extend(validate_transaction_capabilities(node))
            if node.kind in (NodeKind.PART, NodeKind.DEFINITION, NodeKind.INSTANCE) and (
                node.transform_state is None or node.transform_state.world_matrix is None
            ):
                errors.append(f"part '{node.label}' has no world transform")
            if node.kind == NodeKind.INSTANCE and (
                not node.instance_of or node.instance_of not in self.manifest.nodes
                or self.manifest.nodes[node.instance_of].kind != NodeKind.DEFINITION
            ):
                errors.append(f"instance '{node.label}' has invalid definition reference")
            if node.kind in (NodeKind.ASSEMBLY, NodeKind.MODEL):
                if node.expected_child_count and not node.children_ids:
                    errors.append(f"assembly '{node.label}' has no committed children")
        errors.extend(self._repeated_slot_errors())
        if errors:
            raise ScenePlanError("; ".join(errors[:8]))

    async def execute(self) -> SceneTransactionReceipt:
        from .materials import ensure_manifest_materials
        from .modifiers import ensure_manifest_modifiers
        from .repair import ScenePlanRepairer
        material_report = ensure_manifest_materials(self.manifest)
        modifier_report = ensure_manifest_modifiers(
            self.manifest, enabled=bool(getattr(self.executor, "use_llm_modifiers", True)),
        )
        if hasattr(self.manifest, "stats"):
            self.manifest.stats["material_resolution"] = material_report
            self.manifest.stats["modifier_resolution"] = modifier_report
            self.manifest.stats["scene_plan_repairs"] = ScenePlanRepairer.apply(self.manifest)
        else:
            ScenePlanRepairer.apply(self.manifest)
        self.validate()
        executable_plan = ExecutableScenePlan.from_manifest(self.manifest)
        if hasattr(self.manifest, "stats"):
            self.manifest.stats["scene_plan"] = {
                "schema_version": executable_plan.schema_version,
                "scene_ir": "scene_ir.json",
                "boolean_operations": executable_plan.boolean_operations,
            }
        frozen_plan = FrozenScenePlan.from_manifest(self.manifest)
        if hasattr(self.manifest, "_build_dir"):
            executable_plan.save(self.manifest._build_dir() / "scene_ir.json")
        self.manifest.record_event(
            "scene_plan_frozen",
            details={
                "node_count": len(self.manifest.nodes), "mode": "transaction",
                "fingerprint": frozen_plan.fingerprint,
                "contract_fingerprint": frozen_plan.contract_fingerprint,
                "capabilities": capability_manifest(),
                "scene_ir": "scene_ir.json",
                "normalization_events": executable_plan.normalization_events,
            },
        )

        definitions = [node for node in self.manifest.nodes.values() if node.kind == NodeKind.DEFINITION]
        parts = [node for node in self.manifest.nodes.values() if node.kind == NodeKind.PART]
        instances = [node for node in self.manifest.nodes.values() if node.kind == NodeKind.INSTANCE]
        cutters = [
            node for node in parts
            if node.attachment and node.attachment.socket_type in (
                SocketType.BOOLEAN_CUT,
                SocketType.BOOLEAN_UNION,
                SocketType.BOOLEAN_INTERSECT,
            )
        ]

        # All operands are created before booleans; all hierarchy work is
        # appended afterwards.  No MCP call happens in this loop.
        for node in [*definitions, *parts]:
            # Preserve each part's material/modifier specification in the
            # transaction.  Boolean ordering is handled below after operands
            # exist; destructive modifier policy remains owned by the spec.
            result = await self.executor.build_node(node, self.manifest, defer_modifiers=False)
            if not result.ok:
                raise ScenePlanError(f"cannot compile '{node.label}': {result.error}")
            node.blender_objects = result.blender_objects
            node.bounding_box = result.bounding_box

        for definition in definitions:
            if definition.blender_objects:
                self.executor._script_buffer.append(
                    f"_definition=bpy.data.objects.get({definition.blender_objects[0]!r})\n"
                    f"if _definition: _definition.hide_render=True; _definition.hide_viewport=True\n"
                )

        for node in instances:
            definition = self.manifest.nodes[node.instance_of]
            result = await self.executor.build_instance(node, definition, self.manifest)
            if not result.ok:
                raise ScenePlanError(f"cannot compile instance '{node.label}': {result.error}")
            node.blender_objects = result.blender_objects
            node.bounding_box = result.bounding_box

        for b_op in executable_plan.boolean_operations:
            target = self.manifest.nodes.get(b_op.get("target_node_id"))
            cutter = self.manifest.nodes.get(b_op.get("cutter_node_id"))
            if not target or not target.blender_objects or not cutter or not cutter.blender_objects:
                raise ScenePlanError(f"boolean cutter '{cutter.label if cutter else '?'}' has no ROOT target")
            op = b_op.get("operation", "difference").upper()
            self.executor._script_buffer.append(
                self._boolean_fragment(target.blender_objects[0], cutter.blender_objects[0], operation=op)
            )

        assemblies = sorted(
            (node for node in self.manifest.nodes.values()
             if node.kind in (NodeKind.ASSEMBLY, NodeKind.MODEL) and node.children_ids),
            key=lambda node: node.hierarchy_depth,
            reverse=True,
        )
        merged = 0
        for node in assemblies:
            result = await self.executor.merge_assembly(node, self.manifest)
            if not result.ok:
                raise ScenePlanError(f"cannot compile assembly '{node.label}': {result.error}")
            node.blender_objects = result.blender_objects
            node.bounding_box = result.bounding_box
            merged += 1

        # Compilation must not change the tree that was approved.  Geometry
        # result fields are deliberately excluded from FrozenScenePlan.
        if tuple(sorted(self.manifest.nodes)) != frozen_plan.node_ids:
            raise ScenePlanError("scene plan changed while compiling; refusing partial submission")

        if not await self.executor.flush(self.manifest):
            raise ScenePlanError("Blender rejected the scene transaction")

        objects = [name for node in self.manifest.nodes.values() for name in node.blender_objects]
        self.manifest.record_event(
            "scene_transaction_committed",
            details={"parts": len(parts), "definitions": len(definitions), "instances": len(instances), "assemblies": merged, "booleans": len(cutters)},
        )
        return SceneTransactionReceipt(len(parts), merged, len(cutters), objects)

    def _geometry_errors(self, node: Any) -> List[str]:
        geo = node.geometry
        primitive = getattr(getattr(geo, "primitive", None), "value", None)
        # Test doubles and future non-mesh assets may not expose a primitive.
        if not primitive:
            return []
        positive = lambda value: isinstance(value, (int, float)) and value > 0
        if primitive == "box" and not (isinstance(geo.size, list) and len(geo.size) == 3 and all(positive(v) for v in geo.size)):
            return [f"part '{node.label}' has invalid box size"]
        if primitive == "plane" and not (isinstance(geo.size, list) and len(geo.size) == 3 and all(positive(v) for v in geo.size)):
            return [f"part '{node.label}' requires thin-panel size [x, y, thickness]"]
        if primitive in {"cylinder", "cone", "capsule", "pyramid", "prism"} and not (positive(geo.radius) and positive(geo.depth)):
            return [f"part '{node.label}' requires positive radius and depth"]
        if primitive == "capsule" and geo.depth < 2 * geo.radius:
            return [f"part '{node.label}' capsule depth must be at least twice its radius"]
        if primitive in {"sphere", "hemisphere"} and not positive(geo.radius):
            return [f"part '{node.label}' requires a positive radius"]
        if primitive == "torus" and not (positive(geo.major_radius) and positive(geo.minor_radius)):
            return [f"part '{node.label}' requires positive torus radii"]
        return []

    def _repeated_slot_errors(self) -> List[str]:
        errors: List[str] = []
        repeated = {SocketType.RADIAL, SocketType.RADIAL_BRIDGE, SocketType.ARRAY_MEMBER}
        for parent in self.manifest.nodes.values():
            groups: Dict[SocketType, List[Any]] = {}
            for child_id in parent.children_ids:
                child = self.manifest.nodes.get(child_id)
                if child and child.attachment and child.attachment.socket_type in repeated:
                    groups.setdefault(child.attachment.socket_type, []).append(child)
            for socket, children in groups.items():
                indexes = [getattr(child.attachment, "array_index" if socket == SocketType.ARRAY_MEMBER else "radial_index", None) for child in children]
                counts = [getattr(child.attachment, "array_count" if socket == SocketType.ARRAY_MEMBER else "radial_count", None) for child in children]
                if set(indexes) != set(range(len(children))) or set(counts) != {len(children)}:
                    errors.append(f"{socket.value} children of '{parent.label}' have invalid placement slots")
        return errors

    def _boolean_target(self, cutter: Any) -> Any:
        """Resolve a cutter's explicit root sibling inside its assembly."""
        parent = self.manifest.nodes.get(cutter.parent_id) if cutter.parent_id else None
        if not parent:
            return None
        for child_id in parent.children_ids:
            child = self.manifest.nodes.get(child_id)
            if child and child.attachment and child.attachment.socket_type == SocketType.ROOT:
                return child
        return None

    @staticmethod
    def _boolean_fragment(target: str, cutter: str, operation: str = "DIFFERENCE") -> str:
        return f'''\n# Non-destructive Boolean operation
_target = bpy.data.objects.get({target!r})
_cutter = bpy.data.objects.get({cutter!r})
if not _target or not _cutter:
    raise RuntimeError("Boolean operand missing")
_boolean = _target.modifiers.new(name="SentinelBoolean", type='BOOLEAN')
_boolean.operation = {operation!r}
_boolean.object = _cutter
_cutter.hide_viewport = True
_cutter.hide_render = True
'''


def _node_snapshot(node: Any) -> Dict[str, Any]:
    """Snapshot only declared plan inputs, never executor result fields."""
    return {
        "kind": getattr(getattr(node, "kind", None), "value", str(getattr(node, "kind", ""))),
        "label": getattr(node, "label", ""),
        "parent_id": getattr(node, "parent_id", None),
        "children_ids": list(getattr(node, "children_ids", [])),
        "geometry": getattr(getattr(node, "geometry", None), "to_dict", lambda: str(getattr(node, "geometry", None)))(),
        "attachment": getattr(getattr(node, "attachment", None), "to_dict", lambda: str(getattr(node, "attachment", None)))(),
        "transform": getattr(getattr(node, "transform_state", None), "to_dict", lambda: str(getattr(node, "transform_state", None)))(),
    }

