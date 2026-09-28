"""Hierarchical Assembly Graph Specification for recursive 3D model decomposition.

Enables multi-part models (e.g. vehicles, articulated figures, architectural complexes)
to be decomposed into a tree of manageable nodes, each authored independently in a local
coordinate frame, verified, and joined through declared spatial sockets.
"""

from __future__ import annotations
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple
from pydantic import BaseModel, Field


class PartParadigm(str, Enum):
    QUADRUPED = "quadruped_spec"
    VESSEL = "vessel_spec"
    HARD_SURFACE = "hard_surface_spec"
    PRIMITIVE = "typed_primitive"
    EXTERNAL_GENERATIVE = "external_generative"  # Hyper3D / Hunyuan3D fallback leaf


class JoinMode(str, Enum):
    FUSE = "fuse"                # boolean union, becomes one continuous mesh
    PARENT_ONLY = "parent_only"  # stays separate object, parented (rig/pose ready)
    PARENT_ATTACH = "parent_only" # canonical alias
    BOOLEAN_UNION = "fuse"       # canonical alias
    BOOLEAN_DIFFERENCE = "boolean_difference"


class InteractionType(str, Enum):
    """Defines how two objects relate spatially for verification."""
    TOUCH = "touch"              # Objects contact at surface, no overlap
    ATTACH = "attach"            # Intentionally connected, minimal overlap OK
    INSERT = "insert"            # One inside another (shaft/hole), overlap expected
    THROUGH = "through"          # Passes completely through, overlap expected
    OVERLAP_ALLOWED = "overlap"  # Explicit overlap permission
    CLEARANCE = "clearance"      # Must maintain gap
    FLOAT = "float"              # No contact required
    BOOLEAN = "boolean"          # Boolean operation target, will be deleted


class AttachmentSpec(BaseModel):
    parent_node_id: Optional[str] = None      # null only for root node
    socket_name: str = "root"                 # e.g. "chassis.wheel_front_left"
    socket_type: Optional[str] = None         # e.g. "through_axis", "top_center", "strut"
    through_axis: Optional[str] = None        # for pierce types: "x", "y", or "z"
    local_offset: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    local_rotation_euler: Tuple[float, float, float] = (0.0, 0.0, 0.0)  # in radians
    offset_space: str = "PARENT_LOCAL"        # WORLD, PARENT_LOCAL, OBJECT_LOCAL
    mating_tolerance_mm: float = 2.0          # max acceptable gap/overlap at joint in mm
    join_mode: JoinMode = JoinMode.PARENT_ONLY
    interaction_type: InteractionType = InteractionType.TOUCH  # for verification


class AssemblyNode(BaseModel):
    node_id: str                              # stable UUID or key, used as checkpoint key
    label: str                                # human-readable label, e.g. "front_left_wheel"
    paradigm: PartParadigm = PartParadigm.HARD_SURFACE
    sub_spec: Dict[str, Any] = Field(default_factory=dict)  # payload for paradigm compiler
    attachment: AttachmentSpec = Field(default_factory=AttachmentSpec)
    confidence_threshold: float = 0.4         # below this, this node re-splits or retries
    max_split_depth_remaining: int = 3        # decremented on each further decomposition
    retry_count: int = 0
    status: str = "PENDING"                   # PENDING | BUILDING | VERIFIED | FAILED | SPLIT
    children: List[AssemblyNode] = Field(default_factory=list)

    def find_node(self, target_id: str) -> Optional[AssemblyNode]:
        if self.node_id == target_id:
            return self
        for child in self.children:
            found = child.find_node(target_id)
            if found:
                return found
        return None

    def all_nodes(self) -> List[AssemblyNode]:
        nodes = [self]
        for child in self.children:
            nodes.extend(child.all_nodes())
        return nodes


AssemblyNode.model_rebuild()


class AssemblyGraph(BaseModel):
    schema_version: str = "2.0"               # Schema version for contract stability
    task_id: str
    root: AssemblyNode
    description: str = ""                     # original user prompt, for context
    max_retries_per_node: int = 3
    created_at: str = ""
    status: str = "PENDING"                   # PENDING | RESOLVING | ASSEMBLED | FAILED
    rests_on_surface: bool = True             # False for free-floating symmetric objects (dumbbells, axles)

    def get_node(self, node_id: str) -> Optional[AssemblyNode]:
        return self.root.find_node(node_id)


def graph_to_blender_steps(
    graph: "AssemblyGraph",
    style_tag: str = "hard_surface_industrial",
    modifier_intents: "Optional[Dict[str, Any]]" = None,
) -> "List[Tuple[str, dict]]":
    """Convert an AssemblyGraph into a flat list of (tool_name, args) Blender steps.

    Uses proper matrix composition for transforms (not Euler addition).
    Walks the node tree depth-first, accumulating world transforms.

    rests_on_surface=True  -> root world Z = root_bottom_face_offset
    rests_on_surface=False -> root world Z = 0 (centered at origin)

    hemisphere primitive -> create_sphere + apply_boolean(DIFFERENCE, box cutter)
    
    Post-processing applies modifiers based on:
    1. modifier_intents from Stage 4.5 (if provided)
    2. Fallback: infer from style_tag heuristics
    
    CRITICAL: Modifiers (bevel, subsurf) are applied AFTER all boolean operations
    complete, so bevels apply to the final joined mesh, not pre-boolean operands.
    
    Args:
        graph: The AssemblyGraph to convert
        style_tag: Style hint from Stage 0 (affects modifier application)
        modifier_intents: Optional dict from Stage 4.5 mapping label -> ModifierIntent
    """
    import math as _math

    # Phase 1: Geometry creation steps
    # NOTE: No clear_scene - executor uses collection-based isolation
    geometry_steps: List[Tuple[str, dict]] = []
    
    # Phase 2: Boolean/join operations (collected during tree walk)
    boolean_steps: List[Tuple[str, dict]] = []
    
    # Phase 3: Post-processing modifiers (applied after all booleans)
    modifier_steps: List[Tuple[str, dict]] = []
    
    # Track created mesh info: (name, prim_type, sub_spec, received_boolean)
    created_meshes: List[Tuple[str, str, dict, bool]] = []
    
    # Track which meshes are boolean targets (they receive cuts/unions)
    boolean_targets: set = set()

    # Track world transforms as 4x4 matrices (conceptually)
    # For simplicity we track position + rotation separately but compose properly
    world_transforms: Dict[str, Tuple[Tuple[float, float, float], Tuple[float, float, float]]] = {}

    def _bottom_face_offset(sub_spec: dict) -> float:
        """Distance from shape local origin to its lowest point."""
        prim = sub_spec.get("primitive", "box")
        if prim == "cylinder":
            return float(sub_spec.get("depth", 2.0)) / 2.0
        elif prim in ("sphere", "hemisphere"):
            return float(sub_spec.get("radius", 1.0))
        elif prim == "cone":
            return float(sub_spec.get("depth", 2.0)) / 2.0
        else:  # box
            size = sub_spec.get("size", [2.0, 2.0, 2.0])
            return float(size[2]) / 2.0 if isinstance(size, list) and len(size) >= 3 else 1.0

    def _euler_to_matrix(rot_rad: Tuple[float, float, float]) -> List[List[float]]:
        """Convert Euler XYZ rotation (radians) to 3x3 rotation matrix.
        
        Blender uses XYZ Euler order: Rz @ Ry @ Rx
        """
        rx, ry, rz = rot_rad
        cx, sx = _math.cos(rx), _math.sin(rx)
        cy, sy = _math.cos(ry), _math.sin(ry)
        cz, sz = _math.cos(rz), _math.sin(rz)
        
        # Combined rotation matrix for XYZ order
        # M = Rz @ Ry @ Rx
        return [
            [cy*cz, sx*sy*cz - cx*sz, cx*sy*cz + sx*sz],
            [cy*sz, sx*sy*sz + cx*cz, cx*sy*sz - sx*cz],
            [-sy,   sx*cy,            cx*cy           ],
        ]
    
    def _matrix_to_euler(m: List[List[float]]) -> Tuple[float, float, float]:
        """Convert 3x3 rotation matrix back to Euler XYZ (radians).
        
        Handles gimbal lock cases.
        """
        # Extract Euler angles from rotation matrix (XYZ order)
        if abs(m[2][0]) < 0.9999:
            ry = _math.asin(-m[2][0])
            rx = _math.atan2(m[2][1], m[2][2])
            rz = _math.atan2(m[1][0], m[0][0])
        else:
            # Gimbal lock: ry = ±90°
            rz = 0.0
            if m[2][0] < 0:  # ry = 90°
                ry = _math.pi / 2
                rx = _math.atan2(m[0][1], m[0][2])
            else:  # ry = -90°
                ry = -_math.pi / 2
                rx = _math.atan2(-m[0][1], -m[0][2])
        return (rx, ry, rz)
    
    def _matrix_multiply_3x3(a: List[List[float]], b: List[List[float]]) -> List[List[float]]:
        """Multiply two 3x3 matrices."""
        return [
            [
                a[i][0]*b[0][j] + a[i][1]*b[1][j] + a[i][2]*b[2][j]
                for j in range(3)
            ]
            for i in range(3)
        ]
    
    def _matrix_vector_multiply(m: List[List[float]], v: Tuple[float, float, float]) -> Tuple[float, float, float]:
        """Multiply 3x3 matrix by 3D vector."""
        return (
            m[0][0]*v[0] + m[0][1]*v[1] + m[0][2]*v[2],
            m[1][0]*v[0] + m[1][1]*v[1] + m[1][2]*v[2],
            m[2][0]*v[0] + m[2][1]*v[1] + m[2][2]*v[2],
        )

    def _rotate_vector(v: Tuple[float, float, float], rot_rad: Tuple[float, float, float]) -> Tuple[float, float, float]:
        """Rotate vector by Euler XYZ rotation using proper matrix math."""
        rx, ry, rz = rot_rad
        if abs(rx) < 0.0001 and abs(ry) < 0.0001 and abs(rz) < 0.0001:
            return v  # No rotation
        
        m = _euler_to_matrix(rot_rad)
        result = _matrix_vector_multiply(m, v)
        return (round(result[0], 6), round(result[1], 6), round(result[2], 6))

    def _compose_rotations(parent_rot: Tuple[float, float, float], child_rot: Tuple[float, float, float]) -> Tuple[float, float, float]:
        """Compose two Euler XYZ rotations via matrix multiplication.
        
        CRITICAL: Euler angles do NOT compose by addition!
        We must convert to matrices, multiply, then convert back.
        
        Result = Parent @ Child (child rotation applied first in local space,
        then parent rotation applied in world space).
        """
        prx, pry, prz = parent_rot
        crx, cry, crz = child_rot
        
        # Fast path: if either is identity, return the other
        if abs(prx) < 0.0001 and abs(pry) < 0.0001 and abs(prz) < 0.0001:
            return child_rot
        if abs(crx) < 0.0001 and abs(cry) < 0.0001 and abs(crz) < 0.0001:
            return parent_rot
        
        # Convert to matrices
        parent_m = _euler_to_matrix(parent_rot)
        child_m = _euler_to_matrix(child_rot)
        
        # Compose: world = parent @ child
        composed_m = _matrix_multiply_3x3(parent_m, child_m)
        
        # Convert back to Euler
        result = _matrix_to_euler(composed_m)
        return (round(result[0], 6), round(result[1], 6), round(result[2], 6))

    def _emit_node(node: AssemblyNode, parent_world_pos: Tuple[float, float, float], parent_world_rot: Tuple[float, float, float]) -> None:
        offset = node.attachment.local_offset
        local_rot = node.attachment.local_rotation_euler
        
        # Transform local offset by parent's world rotation
        rotated_offset = _rotate_vector(offset, parent_world_rot)
        
        # World position = parent world pos + rotated offset
        world_pos = (
            round(parent_world_pos[0] + rotated_offset[0], 6),
            round(parent_world_pos[1] + rotated_offset[1], 6),
            round(parent_world_pos[2] + rotated_offset[2], 6),
        )
        
        # World rotation = composed rotations
        world_rot = _compose_rotations(parent_world_rot, local_rot)
        
        world_transforms[node.node_id] = (world_pos, world_rot)
        
        rot_deg = [round(_math.degrees(r), 4) for r in world_rot]
        sub = node.sub_spec
        prim = sub.get("primitive", "box")
        name = node.label

        if prim == "cylinder":
            geometry_steps.append(("blender:create_cylinder", {
                "name": name,
                "radius": float(sub.get("radius", 1.0)),
                "depth": float(sub.get("depth", 2.0)),
                "vertices": int(sub.get("vertices", 32)),
                "location": list(world_pos),
                "rotation": rot_deg,
            }))
            created_meshes.append((name, prim, sub, False))
        elif prim == "sphere":
            geometry_steps.append(("blender:create_sphere", {
                "name": name,
                "radius": float(sub.get("radius", 1.0)),
                "location": list(world_pos),
            }))
            created_meshes.append((name, prim, sub, False))
        elif prim == "hemisphere":
            r = float(sub.get("radius", 1.0))
            # Use native hemisphere template (bisect_plane) - no boolean needed
            geometry_steps.append(("blender:create_hemisphere", {
                "name": name,
                "radius": r,
                "location": list(world_pos),
                "rotation": rot_deg,
            }))
            created_meshes.append((name, prim, sub, False))
        elif prim == "cone":
            geometry_steps.append(("blender:create_cone", {
                "name": name,
                "radius1": float(sub.get("radius1", 1.0)),
                "depth": float(sub.get("depth", 2.0)),
                "location": list(world_pos),
                "rotation": rot_deg,
            }))
            created_meshes.append((name, prim, sub, False))
        else:  # box
            size = sub.get("size", [2.0, 2.0, 2.0])
            geometry_steps.append(("blender:create_box", {
                "name": name,
                "size": size,
                "location": list(world_pos),
                "rotation": rot_deg,
            }))
            created_meshes.append((name, prim, sub, False))
        
        # Apply material after creating the primitive (still in geometry phase)
        mat = sub.get("material")
        if mat:
            mat_args = {"name": name}
            if mat.get("color"):
                mat_args["color"] = list(mat["color"])
            if mat.get("metallic") is not None:
                mat_args["metallic"] = float(mat["metallic"])
            if mat.get("roughness") is not None:
                mat_args["roughness"] = float(mat["roughness"])
            if mat.get("emission_color"):
                mat_args["emission_color"] = list(mat["emission_color"])
                mat_args["emission_strength"] = float(mat.get("emission_strength", 1.0))
            geometry_steps.append(("blender:set_material", mat_args))

        # Handle join modes for children after they're created
        for child in node.children:
            _emit_node(child, world_pos, world_rot)
            
            # Apply join mode operations - these go to boolean_steps phase
            join_mode = child.attachment.join_mode
            if join_mode == JoinMode.BOOLEAN_DIFFERENCE:
                boolean_steps.append(("blender:apply_boolean", {
                    "name": name,
                    "target_name": child.label,
                    "operation": "DIFFERENCE",
                    "delete_target": True,
                }))
                boolean_targets.add(name)  # Parent receives the boolean
            elif join_mode in (JoinMode.FUSE, JoinMode.BOOLEAN_UNION):
                boolean_steps.append(("blender:apply_boolean", {
                    "name": name,
                    "target_name": child.label,
                    "operation": "UNION",
                    "delete_target": True,
                }))
                boolean_targets.add(name)
            elif join_mode == JoinMode.PARENT_ONLY:
                # Parenting goes after booleans but before modifiers
                boolean_steps.append(("blender:parent_object", {
                    "name": child.label,
                    "parent_name": name,
                }))

    # Compute root world position
    # For rests_on_surface=True: root centroid Z = half-height (bottom face at Z=0)
    # For rests_on_surface=False: root centroid Z = 0 (centered at origin)
    if graph.rests_on_surface:
        root_z = _bottom_face_offset(graph.root.sub_spec)
    else:
        root_z = 0.0

    # CRITICAL: The root's local_offset from LLM is ignored for world positioning.
    # Root always sits at (0, 0, root_z). Children compute relative to this.
    root_world_pos = (0.0, 0.0, root_z)
    root_world_rot = graph.root.attachment.local_rotation_euler
    
    # Store root transform for children to reference
    world_transforms[graph.root.node_id] = (root_world_pos, root_world_rot)
    
    # Emit root geometry
    sub = graph.root.sub_spec
    prim = sub.get("primitive", "box")
    name = graph.root.label
    rot_deg = [round(_math.degrees(r), 4) for r in root_world_rot]
    
    if prim == "cylinder":
        geometry_steps.append(("blender:create_cylinder", {
            "name": name,
            "radius": float(sub.get("radius", 1.0)),
            "depth": float(sub.get("depth", 2.0)),
            "vertices": int(sub.get("vertices", 32)),
            "location": list(root_world_pos),
            "rotation": rot_deg,
        }))
        created_meshes.append((name, prim, sub, False))
    elif prim == "sphere":
        geometry_steps.append(("blender:create_sphere", {
            "name": name,
            "radius": float(sub.get("radius", 1.0)),
            "location": list(root_world_pos),
        }))
        created_meshes.append((name, prim, sub, False))
    elif prim == "hemisphere":
        r = float(sub.get("radius", 1.0))
        # Use native hemisphere template (bisect_plane) - no boolean needed
        geometry_steps.append(("blender:create_hemisphere", {
            "name": name,
            "radius": r,
            "location": list(root_world_pos),
            "rotation": rot_deg,
        }))
        created_meshes.append((name, prim, sub, False))
    elif prim == "cone":
        geometry_steps.append(("blender:create_cone", {
            "name": name,
            "radius1": float(sub.get("radius1", 1.0)),
            "depth": float(sub.get("depth", 2.0)),
            "location": list(root_world_pos),
            "rotation": rot_deg,
        }))
        created_meshes.append((name, prim, sub, False))
    else:  # box
        size = sub.get("size", [2.0, 2.0, 2.0])
        geometry_steps.append(("blender:create_box", {
            "name": name,
            "size": size,
            "location": list(root_world_pos),
            "rotation": rot_deg,
        }))
        created_meshes.append((name, prim, sub, False))
    
    # Apply material to root
    mat = sub.get("material")
    if mat:
        mat_args = {"name": name}
        if mat.get("color"):
            mat_args["color"] = list(mat["color"])
        if mat.get("metallic") is not None:
            mat_args["metallic"] = float(mat["metallic"])
        if mat.get("roughness") is not None:
            mat_args["roughness"] = float(mat["roughness"])
        if mat.get("emission_color"):
            mat_args["emission_color"] = list(mat["emission_color"])
            mat_args["emission_strength"] = float(mat.get("emission_strength", 1.0))
        geometry_steps.append(("blender:set_material", mat_args))
    
    # Emit children with correct parent world position
    for child in graph.root.children:
        _emit_node(child, root_world_pos, root_world_rot)
        
        # Apply join mode operations for root's direct children
        join_mode = child.attachment.join_mode
        if join_mode == JoinMode.BOOLEAN_DIFFERENCE:
            boolean_steps.append(("blender:apply_boolean", {
                "name": name,
                "target_name": child.label,
                "operation": "DIFFERENCE",
                "delete_target": True,
            }))
            boolean_targets.add(name)
        elif join_mode in (JoinMode.FUSE, JoinMode.BOOLEAN_UNION):
            boolean_steps.append(("blender:apply_boolean", {
                "name": name,
                "target_name": child.label,
                "operation": "UNION",
                "delete_target": True,
            }))
            boolean_targets.add(name)
        elif join_mode == JoinMode.PARENT_ONLY:
            boolean_steps.append(("blender:parent_object", {
                "name": child.label,
                "parent_name": name,
            }))

    # ===== POST-PROCESSING: Apply modifiers AFTER all booleans complete =====
    # This ensures bevels apply to the final joined mesh, not pre-boolean operands.
    # 
    # Modifier order per mesh:
    # 1. Smooth shading (always)
    # 2. Subdivision (if needed) - before bevel for smoother base
    # 3. Bevel (if needed) - after subsurf, on final edges
    # 4. Surface detail arrays (if needed)
    
    def _get_part_extents(sub_spec: dict) -> Tuple[float, float]:
        """Get (smallest_extent, surface_length) for modifier sizing."""
        prim = sub_spec.get("primitive", "box")
        if prim == "cylinder":
            radius = float(sub_spec.get("radius", 0.5))
            depth = float(sub_spec.get("depth", 1.0))
            return (radius, depth)
        elif prim in ("sphere", "hemisphere"):
            radius = float(sub_spec.get("radius", 0.5))
            return (radius, radius * 2)
        elif prim == "cone":
            radius = float(sub_spec.get("radius1", 0.5))
            depth = float(sub_spec.get("depth", 1.0))
            return (min(radius, depth / 2), depth)
        else:  # box
            size = sub_spec.get("size", [1.0, 1.0, 1.0])
            if isinstance(size, list) and len(size) >= 3:
                half_sizes = [s / 2.0 for s in size]
                return (min(half_sizes), max(size))
            return (0.5, 1.0)
    
    def _emit_surface_detail_array(
        mesh_name: str,
        detail: Any,  # ArrayDetailParams
        world_pos: Tuple[float, float, float],
    ) -> None:
        """Emit steps for surface detail array (rivets, panel lines, etc.)."""
        # Create base detail mesh
        base_name = f"{mesh_name}_detail_base"
        
        if detail.base_mesh_type == "rivets":
            # Small cylinder for rivet
            modifier_steps.append(("blender:create_cylinder", {
                "name": base_name,
                "radius": detail.base_radius,
                "depth": detail.base_radius * 0.6,
                "vertices": 12,
                "location": [world_pos[0], world_pos[1], world_pos[2]],
            }))
        elif detail.base_mesh_type == "studs":
            # Small sphere for stud
            modifier_steps.append(("blender:create_sphere", {
                "name": base_name,
                "radius": detail.base_radius,
                "location": [world_pos[0], world_pos[1], world_pos[2]],
            }))
        elif detail.base_mesh_type in ("panel_lines", "ribbing"):
            # Thin box for groove/ridge
            modifier_steps.append(("blender:create_box", {
                "name": base_name,
                "size": [detail.base_radius * 2, detail.base_radius * 0.5, detail.base_radius * 0.3],
                "location": [world_pos[0], world_pos[1], world_pos[2]],
            }))
        else:
            return  # Unknown type
        
        # Apply array modifier
        modifier_steps.append(("blender:apply_array", {
            "name": base_name,
            "count": detail.count,
            "offset": [detail.spacing / (detail.base_radius * 2 + 0.001), 0.0, 0.0],
            "use_relative_offset": True,
        }))
        
        # For panel_lines, apply as boolean difference to parent
        if detail.base_mesh_type == "panel_lines":
            modifier_steps.append(("blender:apply_boolean", {
                "name": mesh_name,
                "target_name": base_name,
                "operation": "DIFFERENCE",
                "delete_target": True,
            }))
        else:
            # Parent detail array to mesh
            modifier_steps.append(("blender:parent_object", {
                "name": base_name,
                "parent_name": mesh_name,
            }))
    
    # Build set of meshes that still exist (not consumed by booleans)
    consumed_by_boolean = set()
    for step_name, step_args in boolean_steps:
        if step_name == "blender:apply_boolean" and step_args.get("delete_target"):
            consumed_by_boolean.add(step_args.get("target_name"))
    
    if modifier_intents:
        # Stage 4.5 path: use resolved modifier intents
        for mesh_name, prim_type, sub_spec, had_internal_boolean in created_meshes:
            # Skip meshes consumed by boolean operations
            if mesh_name in consumed_by_boolean:
                continue
            
            intent = modifier_intents.get(mesh_name)
            if not intent:
                continue
            
            # Check if this mesh received additional booleans from children
            received_boolean = had_internal_boolean or mesh_name in boolean_targets
            
            # 1. Smooth shading always
            modifier_steps.append(("blender:set_smooth_shading", {
                "name": mesh_name,
                "smooth": True,
            }))
            
            # 2. Subdivision (before bevel)
            if hasattr(intent, 'subsurf') and intent.subsurf:
                modifier_steps.append(("blender:apply_subdivision", {
                    "name": mesh_name,
                    "levels": intent.subsurf.levels,
                }))
            
            # 3. Bevel (after subsurf, applies to final edges including boolean cuts)
            if hasattr(intent, 'bevel') and intent.bevel:
                modifier_steps.append(("blender:apply_bevel", {
                    "name": mesh_name,
                    "width": round(intent.bevel.width, 5),
                    "segments": intent.bevel.segments,
                }))
            
            # 4. Surface detail arrays
            if hasattr(intent, 'surface_detail') and intent.surface_detail:
                # Get world position for this mesh
                mesh_world_pos = (0.0, 0.0, 0.0)
                for node in graph.root.all_nodes():
                    if node.label == mesh_name and node.node_id in world_transforms:
                        mesh_world_pos = world_transforms[node.node_id][0]
                        break
                _emit_surface_detail_array(mesh_name, intent.surface_detail, mesh_world_pos)
    else:
        # Fallback: infer from style_tag (original heuristic path)
        is_organic = style_tag in ("organic_worn", "soft_domestic")
        is_hard_surface = style_tag in ("hard_surface_industrial", "stylized_clean")
        
        for mesh_name, prim_type, sub_spec, had_internal_boolean in created_meshes:
            # Skip meshes consumed by boolean operations
            if mesh_name in consumed_by_boolean:
                continue
            
            # 1. Smooth shading for all meshes
            modifier_steps.append(("blender:set_smooth_shading", {
                "name": mesh_name,
                "smooth": True,
            }))
            
            # 2. Subdivision for organic spheres/hemispheres
            if prim_type in ("sphere", "hemisphere") and is_organic:
                modifier_steps.append(("blender:apply_subdivision", {
                    "name": mesh_name,
                    "levels": 1,
                }))
            
            # 3. Bevel (after any subdivision)
            if prim_type == "box":
                size = sub_spec.get("size", [1.0, 1.0, 1.0])
                min_dim = min(size) if isinstance(size, list) else 1.0
                bevel_pct = 0.05 if is_organic else 0.03
                bevel_width = max(0.005, min_dim * bevel_pct)
                modifier_steps.append(("blender:apply_bevel", {
                    "name": mesh_name,
                    "width": round(bevel_width, 4),
                    "segments": 3 if is_organic else 2,
                }))
            elif prim_type == "cylinder" and is_hard_surface:
                radius = sub_spec.get("radius", 0.5)
                bevel_width = max(0.002, radius * 0.02)
                modifier_steps.append(("blender:apply_bevel", {
                    "name": mesh_name,
                    "width": round(bevel_width, 4),
                    "segments": 2,
                }))

    # ===== COMBINE ALL PHASES =====
    # Order: geometry creation -> boolean/join operations -> modifiers
    # This ensures bevels apply AFTER boolean cuts are made
    return geometry_steps + boolean_steps + modifier_steps
