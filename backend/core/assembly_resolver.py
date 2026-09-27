"""AssemblyResolver — Top-down spatial placement and bottom-up assembly execution.

Walks a verified AssemblyGraph, computes world-space transforms for every node
from parent-relative AttachmentSpecs, applies placement in Blender via MCP, and joins
or parents children according to declared JoinModes.
"""

from typing import Dict, List, Any, Tuple, Optional
import math
import logging
from core.assembly_spec import AssemblyGraph, AssemblyNode, JoinMode

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure Python 4x4 Affine Matrix Helper (fallback when mathutils not in backend)
# ---------------------------------------------------------------------------

class Mat4:
    """Lightweight 4x4 matrix for affine transforms [row][col]."""
    __slots__ = ("m",)

    def __init__(self, rows: Optional[List[List[float]]] = None):
        if rows:
            self.m = [list(r) for r in rows]
        else:
            self.m = [
                [1.0, 0.0, 0.0, 0.0],
                [0.0, 1.0, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ]

    @classmethod
    def identity(cls) -> "Mat4":
        return cls()

    @classmethod
    def translation(cls, x: float, y: float, z: float) -> "Mat4":
        res = cls()
        res.m[0][3] = float(x)
        res.m[1][3] = float(y)
        res.m[2][3] = float(z)
        return res

    @classmethod
    def euler_xyz(cls, rx: float, ry: float, rz: float) -> "Mat4":
        """Euler rotation in radians (XYZ order)."""
        cx, sx = math.cos(rx), math.sin(rx)
        cy, sy = math.cos(ry), math.sin(ry)
        cz, sz = math.cos(rz), math.sin(rz)

        # R = Rz * Ry * Rx
        m = [
            [cy * cz, sx * sy * cz - cx * sz, cx * sy * cz + sx * sz, 0.0],
            [cy * sz, sx * sy * sz + cx * cz, cx * sy * sz - sx * cz, 0.0],
            [-sy,     sx * cy,                cx * cy,                0.0],
            [0.0,     0.0,                    0.0,                    1.0],
        ]
        return cls(m)

    def __matmul__(self, other: "Mat4") -> "Mat4":
        res = [[0.0] * 4 for _ in range(4)]
        for r in range(4):
            for c in range(4):
                res[r][c] = (
                    self.m[r][0] * other.m[0][c]
                    + self.m[r][1] * other.m[1][c]
                    + self.m[r][2] * other.m[2][c]
                    + self.m[r][3] * other.m[3][c]
                )
        return Mat4(res)

    def decompose(self) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
        """Extract translation (x, y, z) and euler rotations in degrees (rx, ry, rz)."""
        tx = self.m[0][3]
        ty = self.m[1][3]
        tz = self.m[2][3]

        # Extract Euler XYZ
        sy = -self.m[2][0]
        cy = math.sqrt(max(0.0, 1.0 - sy * sy))
        if cy > 1e-6:
            rx = math.atan2(self.m[2][1], self.m[2][2])
            ry = math.atan2(sy, cy)
            rz = math.atan2(self.m[1][0], self.m[0][0])
        else:
            rx = math.atan2(-self.m[1][2], self.m[1][1])
            ry = math.atan2(sy, cy)
            rz = 0.0

        return (
            (round(tx, 4), round(ty, 4), round(tz, 4)),
            (round(math.degrees(rx), 2), round(math.degrees(ry), 2), round(math.degrees(rz), 2)),
        )


class AssemblyResolutionError(Exception):
    def __init__(self, node_id: str, reason: str):
        self.node_id = node_id
        self.reason = reason
        super().__init__(f"[{node_id}] {reason}")


class AssemblyResolver:
    """Walks a verified AssemblyGraph, computes world coordinates, and applies assembly."""

    def __init__(self, tool_gateway_or_bridge: Any):
        self.bridge = tool_gateway_or_bridge

    async def resolve(self, graph: AssemblyGraph, transaction: Optional[Any] = None) -> Dict[str, Any]:
        """Resolve placement top-down, then apply joins bottom-up within a SceneTransaction."""
        from core.scene_transaction import SceneTransaction

        world_transforms: Dict[str, Mat4] = {}
        errors: List[AssemblyResolutionError] = []

        # 1. Top-Down spatial calculation
        self._resolve_node(
            node=graph.root,
            parent_world=Mat4.identity(),
            world_transforms=world_transforms,
            errors=errors,
        )

        if errors:
            logger.error(f"Assembly resolution failed with {len(errors)} errors")
            return {
                "ok": False,
                "error": f"{len(errors)} node(s) failed spatial placement",
                "failed_nodes": [e.node_id for e in errors],
                "reasons": [e.reason for e in errors],
            }

        # 2. Top-down execution in Blender (wrapped in SceneTransaction)
        txn = transaction or SceneTransaction(tool_executor=self.bridge)
        try:
            async with txn:
                await self._apply_node(graph.root, world_transforms, txn)

                # 3. Mandatory AssemblyVerification across all nodes and edges
                from core.assembly_verification import AssemblyVerificationGate
                verifier = AssemblyVerificationGate(blender_bridge=self.bridge)
                v_res = await verifier.verify(graph)

                if not v_res.get("ok"):
                    logger.warning(f"Assembly verification failed: {v_res.get('error')}. Initiating rollback.")
                    await txn.rollback()
                    graph.status = "FAILED"
                    return {
                        "ok": False,
                        "error": f"Spatial verification failed: {v_res.get('error')}",
                        "verification": v_res,
                        "rolled_back": True,
                    }

                await txn.commit()
        except Exception as e:
            logger.error(f"SceneTransaction failed during assembly execution: {e}")
            graph.status = "FAILED"
            return {
                "ok": False,
                "error": f"Assembly execution failed with rollback: {e}",
                "rolled_back": True,
            }

        graph.status = "VERIFIED_AND_LOADED"
        return {
            "ok": True,
            "status": "VERIFIED_AND_LOADED",
            "all_joints_verified": True,
            "nodes_placed": len(world_transforms),
            "root_node": graph.root.node_id,
        }

    def _resolve_node(
        self,
        node: AssemblyNode,
        parent_world: Mat4,
        world_transforms: Dict[str, Mat4],
        errors: List[AssemblyResolutionError],
    ) -> None:
        try:
            att = node.attachment
            trans = Mat4.translation(*att.local_offset)
            rot = Mat4.euler_xyz(*att.local_rotation_euler)
            local = trans @ rot
            node_world = parent_world @ local
            world_transforms[node.node_id] = node_world
        except Exception as e:
            errors.append(AssemblyResolutionError(node.node_id, f"Transform calculation error: {e}"))
            return

        for child in node.children:
            self._resolve_node(child, node_world, world_transforms, errors)

    async def _apply_node(self, node: AssemblyNode, world_transforms: Dict[str, Mat4], txn: Any) -> None:
        wt = world_transforms[node.node_id]
        loc, rot_deg = wt.decompose()

        # 1. Create geometry for this node first (parent before children)
        if node.sub_spec:
            prim = node.sub_spec.get("primitive") or ("box" if "size" in node.sub_spec else "cylinder" if "radius" in node.sub_spec else None)
            tool = node.sub_spec.get("tool")
            if tool:
                args = {k: v for k, v in node.sub_spec.items() if k != "tool"}
                args["name"] = node.label
                args["location"] = list(loc)
                args["rotation"] = [float(r) for r in rot_deg]
                await self._call_tool(tool, args)
                txn.record(node.label)
            elif prim == "box":
                await self._call_tool("blender:create_box", {
                    "name": node.label,
                    "size": node.sub_spec.get("size", [2.0, 2.0, 2.0]),
                    "location": list(loc),
                    "rotation": [float(r) for r in rot_deg],
                })
                txn.record(node.label)
            elif prim == "cylinder":
                await self._call_tool("blender:create_cylinder", {
                    "name": node.label,
                    "radius": float(node.sub_spec.get("radius", 1.0)),
                    "depth": float(node.sub_spec.get("depth", 2.0)),
                    "vertices": int(node.sub_spec.get("vertices", 32)),
                    "location": list(loc),
                    "rotation": [float(r) for r in rot_deg],
                })
                txn.record(node.label)
            elif prim == "sphere":
                await self._call_tool("blender:create_sphere", {
                    "name": node.label,
                    "radius": float(node.sub_spec.get("radius", 1.0)),
                    "location": list(loc),
                })
                txn.record(node.label)
            else:
                await self._call_tool("blender:set_transform", {
                    "name": node.label,
                    "location": list(loc),
                    "rotation_euler": list(rot_deg),
                })
        else:
            await self._call_tool("blender:set_transform", {
                "name": node.label,
                "location": list(loc),
                "rotation_euler": list(rot_deg),
            })

        # 2. Recurse into children
        for child in node.children:
            await self._apply_node(child, world_transforms, txn)

            # 3. Parent or fuse child to this node
            if child.attachment.join_mode in (JoinMode.PARENT_ONLY, JoinMode.PARENT_ATTACH):
                await self._call_tool("blender:parent_object", {
                    "name": child.label,
                    "parent_name": node.label,
                    "keep_transform": True,
                })
            elif child.attachment.join_mode in (JoinMode.FUSE, JoinMode.BOOLEAN_UNION):
                await self._call_tool("blender:apply_boolean", {
                    "name": node.label,
                    "target_name": child.label,
                    "operation": "UNION",
                    "delete_target": True,
                })

    async def _call_tool(self, tool_name: str, args: Dict[str, Any]) -> Any:
        if hasattr(self.bridge, "execute_tool"):
            return await self.bridge.execute_tool(tool_name, args)
        elif hasattr(self.bridge, "call"):
            res = self.bridge.call(tool_name, args)
            if hasattr(res, "__await__"):
                return await res
            return res
        elif callable(self.bridge):
            res = self.bridge(tool_name, args)
            if hasattr(res, "__await__"):
                return await res
            return res
        raise RuntimeError("No callable tool executor provided to AssemblyResolver")
