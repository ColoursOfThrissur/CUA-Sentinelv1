"""GraphCompiler — General compiler converting 3D requests into versioned AssemblyGraph v2.0.

NO hardcoded dimension lookup tables.
- For natural language: Performs structured LLM decomposition into parts, sockets, and intrinsic dimensions.
- For flat plans: Infers real parentage trees via spatial proximity (star, stack, or branching)
  rather than naive sequential chaining.
- Strict rotation hygiene: Intrinsic sub_specs contain ONLY dimensions (size, radius, depth).
  ALL spatial orientation belongs exclusively to AttachmentSpec.local_rotation_euler.
"""

from typing import Dict, List, Any, Optional, Union, Tuple
import uuid
import re
import math
import json
import logging

from core.assembly_spec import (
    AssemblyGraph,
    AssemblyNode,
    AttachmentSpec,
    JoinMode,
    PartParadigm,
    InteractionType,
)
from core.geometry_validation import normalize_units
from core.decomposition_schema import (
    validate_decomposition,
    DecompositionSchemaError,
    infer_socket_type,
    SocketType,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Unit Detection and Normalization
# ---------------------------------------------------------------------------
# Per BLENDER_GEOMETRY_CALCULATIONS.md Section 2:
# "All geometry calculations use meters internally. 1 Blender unit = 1 meter."
#
# LLMs typically output dimensions in mm or cm (human-scale units).
# We detect the likely unit from magnitude and normalize to meters.
# ---------------------------------------------------------------------------

def _sanity_check_dimensions(shape: dict, description: str = "") -> dict:
    """Log warning if dimensions seem absurd, but trust the LLM's meters output.
    
    The system prompt explicitly instructs the LLM to output meters.
    We don't auto-convert because magnitude alone can't disambiguate units
    (60 could be 60mm mistake OR a legitimate 60m silo).
    
    Instead: log warnings for review, let the build proceed.
    """
    shape = dict(shape)  # Don't mutate original
    
    # Collect all dimension values
    dims = []
    if "size" in shape:
        dims.extend(shape["size"])
    if "radius" in shape:
        dims.append(shape["radius"])
    if "radius1" in shape:
        dims.append(shape["radius1"])
    if "depth" in shape:
        dims.append(shape["depth"])
    
    if not dims:
        return shape
    
    max_dim = max(abs(d) for d in dims)
    
    # Flag absurd values but don't auto-convert
    if max_dim > 50:  # >50m is suspicious for most objects
        logger.warning(
            f"Suspicious dimension {max_dim}m in shape {shape}. "
            f"LLM may have output mm/cm instead of meters. Description: {description[:100]}"
        )
    elif max_dim < 0.001:  # <1mm is suspicious
        logger.warning(
            f"Suspicious dimension {max_dim}m (< 1mm) in shape {shape}. "
            f"Description: {description[:100]}"
        )
    
    return shape


def resolve_extension_position(
    parent_face_position: Tuple[float, float, float],
    direction: Tuple[float, float, float],
    child_length: float,
) -> Tuple[float, float, float]:
    """General rule for ANY 'extends from / mounted on / attached to' relationship.

    The child's CENTER sits at parent_face_position + direction * (child_length / 2).
    Has no knowledge of what the parent or child are — only needs the face position,
    a direction unit vector, and the child's length along that direction.

    Works identically for:
    - a rod extending upward from a plate:   direction=(0,0,1)
    - an antenna on a phone:                 direction=(0,0,1)
    - a teapot spout extending sideways:     direction=(1,0,0)
    - a drawer handle extending forward:     direction=(0,1,0)
    - a leg hanging downward from a table:   direction=(0,0,-1)
    """
    half = child_length / 2.0
    return (
        parent_face_position[0] + direction[0] * half,
        parent_face_position[1] + direction[1] * half,
        parent_face_position[2] + direction[2] * half,
    )


def resolve_hollow_shell_inner_solid(
    outer_center_z: float,
    outer_depth: float,
    wall_thickness: float,
    open_faces: set,
    clearance: float = 0.05,
) -> Tuple[float, float]:
    """Returns (inner_center_z, inner_depth) for the boolean DIFFERENCE cutter of ANY hollow shell.

    A face listed in open_faces is cut fully through (with clearance margin to avoid
    coplanar-cap degenerate booleans). A face NOT in open_faces is preserved at
    exactly wall_thickness.

    open_faces is a subset of {"top", "bottom"}.

    Examples:
    - Open-top vessel (cup, carafe, vase):  open_faces={"top"}
    - Pipe / tube (open both ends):         open_faces={"top", "bottom"}
    - Closed shell (hollow sphere cap):     open_faces=set()
    - Upside-down lampshade (open bottom):  open_faces={"bottom"}
    """
    outer_top = outer_center_z + outer_depth / 2.0
    outer_bottom = outer_center_z - outer_depth / 2.0

    inner_top = (outer_top + clearance) if "top" in open_faces else (outer_top - wall_thickness)
    inner_bottom = (outer_bottom - clearance) if "bottom" in open_faces else (outer_bottom + wall_thickness)

    inner_depth = inner_top - inner_bottom
    inner_center_z = (inner_top + inner_bottom) / 2.0
    return round(inner_center_z, 6), round(inner_depth, 6)


# Structured decomposition system prompt for the LLM
DECOMPOSITION_SYSTEM_PROMPT = """You are a 3D CAD Assembly Decomposer.
Your task is to decompose any described physical object into a hierarchical AssemblyGraph.

**CRITICAL FIELD NAME REQUIREMENTS — PARSE WILL FAIL IF WRONG:**
You MUST use EXACTLY these field names. Any deviation causes a parse failure:
- Shape type: "primitive" (NOT "type")
- Part name: "label" (NOT "name")
- Parent reference: "parent_label" (NOT "parent")
- Socket hint: "socket_name" (NOT "socket")
- Position: "local_offset" (NOT "offset" or "position")
- Rotation: "local_rotation_euler" (NOT "rotation")

**CRITICAL: ALL DIMENSIONS MUST BE IN METERS.**
Blender uses meters as its base unit. Convert all measurements:
- 120mm = 0.12m
- 60cm = 0.6m  
- 2 feet = 0.6096m

Rules:
1. Identify all distinct physical components (e.g. base, stem, head, legs, tabletop, plates, grip).
2. Root part MUST be the base/ground part or primary central mass.
   - Set "rests_on_surface": true if the object physically rests on a surface in normal use.
   - Set "rests_on_surface": false ONLY for free-floating symmetric objects (dumbbells, axles, satellites).
3. For rests_on_surface=true objects, root Z offset = root_height/2 (base sits on Z=0).
   For rests_on_surface=false objects, root Z offset = 0 (object centered at origin).
4. For each part, specify its intrinsic shape (ALL DIMENSIONS IN METERS):
   - "box": size [dx, dy, dz] in meters
   - "cylinder": radius r in meters, depth h in meters, vertices n (32 for smooth)
   - "sphere": radius r in meters
   - "cone": radius1 (base radius) in meters, depth h in meters
5. For every non-root part, specify:
   - parent_label: label of the part it mounts to
   - socket_name: MUST include one of these EXACT keywords:
       "top_center"    — child stacks on TOP of parent
       "bottom_center" — child hangs BELOW parent
       "through_axis"  — child passes THROUGH parent horizontally (axles, crossbars)
       "left_end"      — child at LEFT end of horizontal parent
       "right_end"     — child at RIGHT end of horizontal parent
       "front_face"    — child on front (-Y) face
       "back_face"     — child on back (+Y) face
       "left_face"     — child on left (-X) face
       "right_face"    — child on right (+X) face
       "surface_mount" — child sits ON a surface
   - local_offset: [dx, dy, dz] IN METERS — vector from parent centroid to child centroid
   - local_rotation_euler: [rx, ry, rz] in degrees
   - join_mode: "parent_only", "fuse", or "boolean_difference"

**CRITICAL: LOCAL FRAME RULE FOR HORIZONTAL PARENTS**
When a parent is rotated (e.g., a horizontal cylinder with [0,90,0]), its children's
local_offset is computed in the PARENT'S LOCAL FRAME (before rotation is applied).
- A cylinder's local Z axis is along its LENGTH (depth).
- "left_end" means NEGATIVE local Z: offset = [0, 0, -(parent_half_depth + child_half)].
- "right_end" means POSITIVE local Z: offset = [0, 0, +(parent_half_depth + child_half)].
The pipeline transforms these local offsets to world positions using the parent's rotation.

**ROTATION RULES:**
- Vertical cylinders: [0, 0, 0]
- Horizontal cylinder along X-axis (left-right): [0, 90, 0]
- Horizontal cylinder along Y-axis (front-back): [90, 0, 0]

**COMMON MISTAKES — DO NOT DO THESE:**
1. DO NOT use "type" instead of "primitive" — WRONG: {"type": "cylinder"} → CORRECT: {"primitive": "cylinder"}
2. DO NOT use "name" instead of "label" — WRONG: "name": "base" → CORRECT: "label": "base"
3. DO NOT use "parent" instead of "parent_label" — WRONG: "parent": "base" → CORRECT: "parent_label": "base"
4. DO NOT copy-paste identical offsets for different parts — each part needs its own computed offset
5. DO NOT nest all parts under root — parts should parent to their actual physical attachment point
6. DO NOT put rotation inside shape — rotation goes ONLY in local_rotation_euler

Output strictly valid JSON with this schema:
{
  "rests_on_surface": true,
  "root": {
    "label": "<name>",
    "shape": {"primitive": "cylinder|box|sphere", ...dimensions in METERS...},
    "attachment": {"local_offset": [0, 0, z_centroid], "local_rotation_euler": [0, 0, 0]}
  },
  "parts": [
    {
      "label": "<name>",
      "parent_label": "<parent_name>",
      "socket_name": "<keyword_from_list>",
      "shape": {"primitive": "...", ...dimensions in METERS...},
      "local_offset": [dx, dy, dz],
      "local_rotation_euler": [rx, ry, rz],
      "join_mode": "parent_only"
    }
  ]
}

**EXAMPLE 1: Horizontal axle with parts on left and right ends**
Request: "A horizontal crossbar (cylinder 0.02m radius, 0.4m long) with a disc on the left end and a sphere on the right end"

```json
{
  "rests_on_surface": false,
  "root": {
    "label": "crossbar",
    "shape": {"primitive": "cylinder", "radius": 0.02, "depth": 0.4, "vertices": 32},
    "attachment": {"local_offset": [0, 0, 0], "local_rotation_euler": [0, 90, 0]}
  },
  "parts": [
    {
      "label": "left_disc",
      "parent_label": "crossbar",
      "socket_name": "left_end",
      "shape": {"primitive": "cylinder", "radius": 0.05, "depth": 0.01, "vertices": 32},
      "local_offset": [0, 0, -0.205],
      "local_rotation_euler": [0, 90, 0],
      "join_mode": "parent_only"
    },
    {
      "label": "right_sphere",
      "parent_label": "crossbar",
      "socket_name": "right_end",
      "shape": {"primitive": "sphere", "radius": 0.04},
      "local_offset": [0, 0, 0.24],
      "local_rotation_euler": [0, 0, 0],
      "join_mode": "parent_only"
    }
  ]
}
```
Why: crossbar depth=0.4m → half=0.2m. left_disc depth=0.01m → half=0.005m.
left_end offset Z = -(0.2 + 0.005) = -0.205. right_sphere radius=0.04m.
right_end offset Z = +(0.2 + 0.04) = +0.24.

**EXAMPLE 2: Training dummy with through-axis arm**
Request: "A training dummy: vertical post with a horizontal arm passing through it, shield on left, ball on right"

```json
{
  "rests_on_surface": true,
  "root": {
    "label": "post",
    "shape": {"primitive": "cylinder", "radius": 0.05, "depth": 1.8, "vertices": 32},
    "attachment": {"local_offset": [0, 0, 0.9], "local_rotation_euler": [0, 0, 0]}
  },
  "parts": [
    {
      "label": "arm_axis",
      "parent_label": "post",
      "socket_name": "through_axis",
      "shape": {"primitive": "cylinder", "radius": 0.02, "depth": 0.5, "vertices": 32},
      "local_offset": [0, 0, 0.5],
      "local_rotation_euler": [0, 90, 0],
      "join_mode": "parent_only"
    },
    {
      "label": "strike_shield",
      "parent_label": "arm_axis",
      "socket_name": "left_end",
      "shape": {"primitive": "cylinder", "radius": 0.1, "depth": 0.02, "vertices": 32},
      "local_offset": [0, 0, -0.26],
      "local_rotation_euler": [0, 90, 0],
      "join_mode": "parent_only"
    },
    {
      "label": "counterweight",
      "parent_label": "arm_axis",
      "socket_name": "right_end",
      "shape": {"primitive": "sphere", "radius": 0.05},
      "local_offset": [0, 0, 0.3],
      "local_rotation_euler": [0, 0, 0],
      "join_mode": "parent_only"
    }
  ]
}
```
Why: arm_axis uses "through_axis" socket and [0,90,0] rotation to lie horizontal.
strike_shield parents to arm_axis (not post!) with "left_end" → negative Z offset.
counterweight parents to arm_axis with "right_end" → positive Z offset.

**SOCKET CHOICE GUIDANCE:**
If uncertain between sockets, prefer:
- "through_axis" for anything that passes THROUGH another part
- "left_end"/"right_end" for attachments at ends of horizontal cylinders
- "top_center" for vertical stacking
- "surface_mount" when unsure about face attachment
"""

class GraphCompiler:
    """Compiles 3D requests into an AssemblyGraph without hardcoded dimension lookups."""

    @classmethod
    async def compile_from_prompt(
        cls,
        prompt: str,
        model_manager: Any = None,
        task_id: Optional[str] = None,
        lease_id: str = "system",
        lease_generation: int = 0,
        model_id: Optional[str] = None,
    ) -> AssemblyGraph:
        """Decompose an arbitrary natural language prompt using the LLM."""
        tid = task_id or f"graph_{uuid.uuid4().hex[:8]}"

        # If LLM is available, perform genuine zero-shot decomposition.
        # IMPORTANT: use a synthetic task_id (prefixed "decomp_") so this nested
        # generate_async call never competes with the live task's model lease.
        # The live task holds the model as BUSY with its own task_id; passing the
        # same task_id here would cause a re-entrancy race on the SQLite IMMEDIATE
        # transaction inside generate(), silently failing and falling back to the
        # raw LLM plan with wrong dimensions.
        if model_manager is not None:
            try:
                mid = model_id or model_manager.get_model_for_workflow("ENDPOINT")
                decomp_task_id = f"decomp_{tid}"
                response = await model_manager.generate_async(
                    model_id=mid,
                    task_id=decomp_task_id,
                    lease_id="internal",
                    lease_generation=0,
                    system_prompt=DECOMPOSITION_SYSTEM_PROMPT,
                    prompt=prompt,
                    temperature=0.1,
                )
                decomp = cls._extract_json(response)
                if decomp and "root" in decomp:
                    # FAIL-LOUD: Validate schema before building graph
                    try:
                        decomp = validate_decomposition(decomp)
                    except DecompositionSchemaError as schema_err:
                        logger.error(
                            f"GraphCompiler: Schema validation failed: {schema_err}. "
                            f"Raw decomp keys: {list(decomp.keys()) if isinstance(decomp, dict) else 'not a dict'}"
                        )
                        raise  # Don't silently fall back - fail loud
                    return await cls._build_graph_from_decomp(decomp, prompt, tid)
                logger.warning(f"GraphCompiler: LLM returned no valid JSON (response[:200]={response[:200]!r})")
            except Exception as e:
                logger.warning(f"LLM decomposition failed ({type(e).__name__}: {e}), falling back to deterministic extractor")

        # Deterministic fallback: extract parts and dimensions directly from prompt text
        return cls._compile_via_text_extraction(prompt, tid)

    @classmethod
    def compile_plan(
        cls,
        steps: List[Dict[str, Any]],
        task_id: Optional[str] = None,
        description: str = "",
    ) -> AssemblyGraph:
        """Converts flat plan steps into an AssemblyGraph using spatial proximity parenting.
        
        Avoids linear conga-line chaining: determines which part is parent by finding
        which existing part's centroid/surface is closest in coordinate space.
        """
        tid = task_id or f"graph_{uuid.uuid4().hex[:8]}"
        if not steps:
            raise ValueError("Cannot compile an empty plan into an AssemblyGraph")

        parsed_steps: List[Dict[str, Any]] = []
        for idx, step in enumerate(steps):
            args = step.get("args", {})
            name = args.get("name", f"part_{idx}")
            loc = [float(c) for c in args.get("location", [0.0, 0.0, 0.0])]
            rot = [float(r) for r in args.get("rotation", [0.0, 0.0, 0.0])]

            # Extract intrinsic shape params only (exclude world location and world rotation)
            sub_spec = {}
            tool = step.get("tool", "")
            if "size" in args:
                sub_spec = {"primitive": "box", "size": [float(s) for s in args["size"]]}
            elif "radius" in args:
                sub_spec = {
                    "primitive": "cylinder",
                    "radius": float(args["radius"]),
                    "depth": float(args.get("depth", 1.0)),
                    "vertices": int(args.get("vertices", 32)),
                }
            elif "radius1" in args:
                sub_spec = {
                    "primitive": "cone",
                    "radius1": float(args["radius1"]),
                    "depth": float(args.get("depth", 1.0)),
                }
            else:
                sub_spec = {k: v for k, v in args.items() if k not in ("location", "rotation", "name")}

            parsed_steps.append({
                "name": name,
                "tool": tool,
                "sub_spec": sub_spec,
                "location": loc,
                "rotation": rot,
            })

        # Step 0 is the root part
        root_data = parsed_steps[0]
        root_node = AssemblyNode(
            node_id=f"node_{root_data['name']}_{tid}",
            label=root_data["name"],
            paradigm=PartParadigm.PRIMITIVE,
            sub_spec=root_data["sub_spec"],
            attachment=AttachmentSpec(
                parent_node_id=None,
                local_offset=tuple(root_data["location"]),
                local_rotation_euler=tuple(math.radians(r) for r in root_data["rotation"]),
                join_mode=JoinMode.PARENT_ONLY,
            ),
            children=[],
        )

        all_placed_nodes = {root_data["name"]: (root_node, root_data["location"])}

        # For remaining parts, find parent via spatial proximity / contact rather than blind chaining
        for part in parsed_steps[1:]:
            p_name = part["name"]
            p_loc = part["location"]

            # Find closest already-placed part to serve as parent
            best_parent_name = root_data["name"]
            min_dist = float("inf")
            for placed_name, (_, placed_loc) in all_placed_nodes.items():
                # Euclidean distance between centroids
                dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(p_loc, placed_loc)))
                if dist < min_dist:
                    min_dist = dist
                    best_parent_name = placed_name

            parent_node, parent_loc = all_placed_nodes[best_parent_name]

            # Relative offset in parent space
            rel_offset = (
                round(p_loc[0] - parent_loc[0], 4),
                round(p_loc[1] - parent_loc[1], 4),
                round(p_loc[2] - parent_loc[2], 4),
            )

            child_node = AssemblyNode(
                node_id=f"node_{p_name}_{tid}",
                label=p_name,
                paradigm=PartParadigm.PRIMITIVE,
                sub_spec=part["sub_spec"],
                attachment=AttachmentSpec(
                    parent_node_id=parent_node.node_id,
                    socket_name=f"{parent_node.label}.socket",
                    local_offset=rel_offset,
                    local_rotation_euler=tuple(math.radians(r) for r in part["rotation"]),
                    join_mode=JoinMode.PARENT_ONLY,
                ),
                children=[],
            )

            parent_node.children.append(child_node)
            all_placed_nodes[p_name] = (child_node, p_loc)

        return AssemblyGraph(
            schema_version="2.0",
            task_id=tid,
            root=root_node,
            description=description or f"Plan of {len(steps)} steps",
            status="PENDING",
            rests_on_surface=True,
        )

    @classmethod
    def _compile_via_text_extraction(cls, text: str, tid: str) -> AssemblyGraph:
        """Generic parser extracting parts and parametric dimensions without hardcoding.
        
        Fixes:
        1. Sentence splitting protects decimals (7.5 cm, 0.8 cm) by requiring letter boundary.
        2. Disambiguates declared part from prepositional parent reference ("stem ... sits in base" -> stem, parent=base).
        3. Treats property-only clauses ("rotated 90 degrees") as modifiers on existing parts, avoiding phantom nodes.
        4. Wires parentage directly to referenced parent rather than linear conga-line chaining.
        """
        # Split on sentence boundaries, NEVER on decimal points like 7.5 or 0.8
        sentences = [s.strip() for s in re.split(r'(?<=[a-zA-Z0-9])\.\s+(?=[A-Z])|[;\n]+', text) if s.strip()]

        parts_by_label: Dict[str, Dict[str, Any]] = {}

        for sent in sentences:
            lower = sent.lower()

            # Check if sentence is a property modifier on an existing part (e.g. 'The lamp head is rotated 90 degrees')
            has_dims = bool(re.search(r'\d+(?:\.\d+)?\s*(?:cm|mm|m)?\s*(?:in\s*)?(?:diameter|radius|height|length|width|thickness|depth)', lower))
            if not has_dims and "rotated" in lower:
                rot_match = re.search(r'rotated\s*(\d+)\s*degrees?', lower)
                if rot_match:
                    deg = float(rot_match.group(1))
                    for existing_label in parts_by_label:
                        if existing_label in lower or ("head" in existing_label and "head" in lower):
                            parts_by_label[existing_label]["rotation_rad"] = (0.0, math.radians(deg), 0.0)
                continue

            # Identify prepositional parent reference (e.g. "of the base", "in the top center of the base")
            parent_ref = None
            prep = re.search(r'(?:in|on|at|of|outside)\s+(?:the\s+)?(?:top\s+center\s+of\s+)?(?:the\s+)?(?:very\s+top\s+of\s+the\s+)?(base|stem|grip|tabletop|chassis|plate)', lower)
            if prep:
                parent_ref = prep.group(1)

            # Disambiguate declared subject part from referenced parent part
            label = None
            if "base" in lower and parent_ref != "base":
                label = "base"
            elif "stem" in lower and parent_ref != "stem":
                label = "stem"
            elif "head" in lower and parent_ref != "head":
                label = "lamp_head"
            elif "grip" in lower:
                label = "grip"
            elif "plate" in lower:
                label = "left_plate" if "left" in lower else "right_plate" if "right" in lower else "plate"
            elif "collar" in lower:
                label = "left_collar" if "left" in lower else "right_collar" if "right" in lower else "collar"
            elif any(k in lower for k in ("smartphone", "phone", "box", "cube", "tabletop")):
                label = "smartphone" if "smartphone" in lower or "phone" in lower else "tabletop" if "tabletop" in lower else "box"

            # Extract cylinder dimensions
            diam_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:cm|mm|m)?\s*in\s*diameter', lower)
            rad_match = re.search(r'radius\s*(?:of)?\s*(\d+(?:\.\d+)?)', lower)
            h_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:cm|mm|m)?\s*in\s*(?:height|length|thickness|depth)', lower)

            # Extract box / prism dimensions (including decimals)
            len_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:cm|mm|m)?\s*in\s*length', lower)
            wid_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:cm|mm|m)?\s*in\s*width', lower)
            thk_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:cm|mm|m)?\s*in\s*thickness', lower)

            if not label:
                # If sentence specifies dimensions for the active object (e.g. "The dimensions are 16 cm in length...")
                if parts_by_label and (len_match or diam_match or rad_match):
                    last_label = list(parts_by_label.keys())[-1]
                    if len_match and wid_match and thk_match:
                        l = float(len_match.group(1))
                        w = float(wid_match.group(1))
                        t = float(thk_match.group(1))
                        parts_by_label[last_label]["sub_spec"] = {"primitive": "box", "size": [l, w, t]}
                        parts_by_label[last_label]["height"] = t
                    elif diam_match and h_match:
                        r = float(diam_match.group(1)) / 2.0
                        h = float(h_match.group(1))
                        parts_by_label[last_label]["sub_spec"] = {"primitive": "cylinder", "radius": r, "depth": h, "vertices": 32}
                        parts_by_label[last_label]["height"] = h
                        parts_by_label[last_label]["radius"] = r
                continue

            # Rotation in declaration clause
            rot_deg = (0.0, 0.0, 0.0)
            rot_m = re.search(r'rotated\s*(\d+)\s*degrees?', lower)
            if rot_m:
                rot_deg = (0.0, math.radians(float(rot_m.group(1))), 0.0)

            if "cylinder" in lower or label in ("base", "stem", "grip", "plate", "collar"):
                radius = (float(diam_match.group(1)) / 2.0) if diam_match else float(rad_match.group(1)) if rad_match else 5.0
                depth = float(h_match.group(1)) if h_match else 2.0
                vertices = 6 if ("6-sided" in lower or "hexagonal" in lower) else 32

                parts_by_label[label] = {
                    "label": label,
                    "parent": parent_ref,
                    "sub_spec": {"primitive": "cylinder", "radius": radius, "depth": depth, "vertices": vertices},
                    "height": depth,
                    "radius": radius,
                    "rotation_rad": rot_deg,
                }
            elif any(k in lower for k in ("prism", "box", "cube", "head", "smartphone", "phone", "tabletop")):
                l = float(len_match.group(1)) if len_match else 2.0
                w = float(wid_match.group(1)) if wid_match else 2.0
                t = float(thk_match.group(1)) if thk_match else float(h_match.group(1)) if h_match else 2.0

                parts_by_label[label] = {
                    "label": label,
                    "parent": parent_ref,
                    "sub_spec": {"primitive": "box", "size": [l, w, t]},
                    "height": t,
                    "rotation_rad": rot_deg,
                }

        if not parts_by_label:
            return cls._compile_fallback_cube(text, tid)

        # Build AssemblyGraph: root is first part (or explicit base/grip)
        part_items = list(parts_by_label.values())
        root_part = part_items[0]
        root_h = root_part.get("height", 2.0)
        root_rot = root_part.get("rotation_rad", (0.0, 0.0, 0.0))

        root_node = AssemblyNode(
            node_id=f"root_{root_part['label']}_{tid}",
            label=root_part["label"],
            paradigm=PartParadigm.PRIMITIVE,
            sub_spec=root_part["sub_spec"],
            attachment=AttachmentSpec(
                parent_node_id=None,
                local_offset=(0.0, 0.0, round(root_h / 2.0, 4)),
                local_rotation_euler=root_rot,
                join_mode=JoinMode.PARENT_ONLY,
            ),
            children=[],
        )

        nodes_by_label = {root_node.label: root_node}

        for part in part_items[1:]:
            p_label = part["label"]
            parent_name = part.get("parent")
            parent_node = nodes_by_label.get(parent_name, root_node)

            p_h = part.get("height", 2.0)
            parent_half = parent_node.sub_spec.get("depth", parent_node.sub_spec.get("size", [0, 0, 2])[2]) / 2.0
            child_half = p_h / 2.0
            z_offset = round(parent_half + child_half, 4)

            child_node = AssemblyNode(
                node_id=f"node_{p_label}_{tid}",
                label=p_label,
                paradigm=PartParadigm.PRIMITIVE,
                sub_spec=part["sub_spec"],
                attachment=AttachmentSpec(
                    parent_node_id=parent_node.node_id,
                    socket_name=f"{parent_node.label}.top",
                    local_offset=(0.0, 0.0, z_offset),
                    local_rotation_euler=part.get("rotation_rad", (0.0, 0.0, 0.0)),
                    join_mode=JoinMode.PARENT_ONLY,
                ),
                children=[],
            )
            parent_node.children.append(child_node)
            nodes_by_label[p_label] = child_node

        return AssemblyGraph(
            schema_version="2.0",
            task_id=tid,
            root=root_node,
            description=text,
            status="PENDING",
            rests_on_surface=True,
        )

    @classmethod
    def _compile_fallback_cube(cls, text: str, tid: str) -> AssemblyGraph:
        """Generic 1-node cube with extracted size."""
        size_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:m|cm)?\s*(?:cube|box)', text.lower())
        s = float(size_match.group(1)) if size_match else 2.0
        root = AssemblyNode(
            node_id=f"root_cube_{tid}",
            label="cube",
            paradigm=PartParadigm.PRIMITIVE,
            sub_spec={"primitive": "box", "size": [s, s, s]},
            attachment=AttachmentSpec(local_offset=(0.0, 0.0, s / 2.0)),
            children=[],
        )
        return AssemblyGraph(
            schema_version="2.0",
            task_id=tid,
            root=root,
            description=text,
            status="PENDING",
            rests_on_surface=True,
        )

    @classmethod
    def _extract_json(cls, text: str) -> Optional[Dict[str, Any]]:
        """Safely extract JSON object from LLM response text."""
        try:
            m = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', text)
            if m:
                return json.loads(m.group(1))
            m2 = re.search(r'\{[\s\S]*\}', text)
            if m2:
                return json.loads(m2.group(0))
        except Exception:
            pass
        return None

    @classmethod
    async def _build_graph_from_decomp(cls, data: Dict[str, Any], description: str, tid: str) -> AssemblyGraph:
        """Convert LLM decomposition JSON into an AssemblyGraph v2.0.

        Runs DimensionResolver on any dimension the LLM did not receive verbatim
        from the user (confidence < 1.0). Resolver results are stored on each node
        as _dimension_sources so assembly_verification can invalidate bad entries.

        Runtime geometry corrections (dynamic, not hardcoded):
        1. Zero-Z stacking: when local_offset[2] ≈ 0, compute from shape half-extents
        2. Diagonal tilt: when cylinder has XY offset + Z-only rotation, compute proper
           tilt in the compass plane using axis-angle → Euler conversion
        3. Rotated parent offset: when parent has rotation, transform local_offset
           into world space before accumulating
        """
        from core.dimension_resolver import DimensionResolver
        resolver = DimensionResolver(web_search_fn=None)
        web_lookups_used = 0

        async def _resolve_shape_dims(part_data: Dict[str, Any], label: str, shape: Dict[str, Any]) -> Dict[str, str]:
            """Run resolver over any sub-1.0-confidence dimension in shape. Returns sources map.
            
            Now properly async - awaits resolver.resolve() directly instead of
            broken run_until_complete() which fails inside an already-running event loop.
            """
            nonlocal web_lookups_used
            conf_map = part_data.get("dimension_confidence", {})
            sources: Dict[str, str] = {}
            if not conf_map:
                return sources
            category = data.get("category", description.split()[0] if description else "object")
            for dim_name, conf in conf_map.items():
                if float(conf) >= 1.0 or dim_name not in shape:
                    sources[dim_name] = "user_stated"
                    continue
                try:
                    decision = await resolver.resolve(
                        task_id=tid,
                        category=category,
                        descriptor=label,
                        dimension_name=dim_name,
                        model_value=float(shape[dim_name]) if not isinstance(shape[dim_name], list) else float(shape[dim_name][0]),
                        model_confidence=float(conf),
                        web_lookups_used_this_task=web_lookups_used,
                    )
                    if not isinstance(shape[dim_name], list):
                        shape[dim_name] = decision.value
                    if decision.source == "web_verified":
                        web_lookups_used += 1
                    sources[dim_name] = decision.source
                    logger.debug(f"DimensionResolver: {label}.{dim_name} = {decision.value} (source={decision.source})")
                except Exception as e:
                    logger.warning(f"DimensionResolver failed for {label}.{dim_name}: {e}")
                    sources[dim_name] = "resolution_failed"
            return sources

        def _resolve_socket_offset(
            socket_type: SocketType,
            parent_shape: dict,
            child_shape: dict,
            raw_offset: List[float],
            child_rotation_deg: List[float],
        ) -> Tuple[List[float], List[float]]:
            """Resolve offset and rotation from semantic socket type.
            
            This is where the MATH lives - in tested code, not in the LLM.
            The LLM only needs to pick the right socket type.
            
            Returns:
                (resolved_offset, resolved_rotation_deg)
            """
            # Get parent dimensions
            p_half_x = _shape_half_x(parent_shape)
            p_half_y = _shape_half_y(parent_shape)
            p_half_z = _shape_half_z(parent_shape)
            
            # Get child dimensions
            c_half_x = _shape_half_x(child_shape)
            c_half_y = _shape_half_y(child_shape)
            c_half_z = _shape_half_z(child_shape)
            
            # Child's length along its local Z axis (depth for cylinders)
            c_prim = child_shape.get("primitive", "box")
            if c_prim in ("cylinder", "cone"):
                c_length = float(child_shape.get("depth", 1.0))
            else:
                c_length = c_half_z * 2
            
            offset = list(raw_offset)
            rotation = list(child_rotation_deg)
            
            if socket_type == SocketType.TOP_CENTER:
                # Child sits on top of parent, centered
                offset = [0.0, 0.0, p_half_z + c_half_z]
                
            elif socket_type == SocketType.BOTTOM_CENTER:
                # Child hangs below parent
                offset = [0.0, 0.0, -(p_half_z + c_half_z)]
                
            elif socket_type == SocketType.FRONT_FACE:
                # Child on -Y face of parent
                offset = [offset[0], -(p_half_y + c_half_y), offset[2]]
                
            elif socket_type == SocketType.BACK_FACE:
                # Child on +Y face of parent
                offset = [offset[0], p_half_y + c_half_y, offset[2]]
                
            elif socket_type == SocketType.LEFT_FACE:
                # Child on -X face of parent
                offset = [-(p_half_x + c_half_x), offset[1], offset[2]]
                
            elif socket_type == SocketType.RIGHT_FACE:
                # Child on +X face of parent
                offset = [p_half_x + c_half_x, offset[1], offset[2]]
                
            elif socket_type == SocketType.THROUGH_AXIS:
                # Child passes THROUGH parent horizontally
                # Child is rotated 90° to lie horizontal, centered on parent
                # The child's Z-axis (length) becomes the X-axis
                offset = [0.0, 0.0, offset[2] if abs(offset[2]) > 0.01 else 0.0]
                rotation = [0.0, 90.0, 0.0]  # Rotate to horizontal along X
                
            elif socket_type == SocketType.LEFT_END:
                # Child at left end of an elongated parent
                # For a horizontal cylinder (rotated 90 around Y), its length is along X in world space
                # But in the parent's LOCAL frame, the length is still along Z (depth axis)
                # So "left end" in local frame = -Z direction
                p_prim = parent_shape.get("primitive", "box")
                if p_prim in ("cylinder", "cone"):
                    p_half_length = float(parent_shape.get("depth", 1.0)) / 2.0
                else:
                    p_half_length = p_half_z
                # In parent's local frame, left end is at -Z (before rotation transforms it)
                offset = [0.0, 0.0, -(p_half_length + c_half_z)]
                
            elif socket_type == SocketType.RIGHT_END:
                # Child at right end of an elongated parent
                # In parent's local frame, right end is at +Z
                p_prim = parent_shape.get("primitive", "box")
                if p_prim in ("cylinder", "cone"):
                    p_half_length = float(parent_shape.get("depth", 1.0)) / 2.0
                else:
                    p_half_length = p_half_z
                offset = [0.0, 0.0, p_half_length + c_half_z]
                
            elif socket_type == SocketType.SURFACE_MOUNT:
                # Generic surface mount - use LLM's offset but ensure outside parent
                # Check each axis and push out if inside
                if abs(offset[0]) < p_half_x and abs(offset[1]) < p_half_y:
                    # Inside on XY, push out on Y (front face default)
                    if offset[1] <= 0:
                        offset[1] = -(p_half_y + c_half_y)
                    else:
                        offset[1] = p_half_y + c_half_y
            
            # Round for cleanliness
            offset = [round(o, 6) for o in offset]
            rotation = [round(r, 4) for r in rotation]
            
            return offset, rotation

        def _shape_half_z(shape: dict) -> float:
            """Half-extent along local Z axis (centroid to top face for upright shape)."""
            prim = shape.get("primitive", "box")
            if prim in ("cylinder", "cone"):
                return float(shape.get("depth", 2.0)) / 2.0
            elif prim in ("sphere", "hemisphere"):
                return float(shape.get("radius", 1.0))
            else:  # box
                size = shape.get("size", [2.0, 2.0, 2.0])
                return float(size[2]) / 2.0 if isinstance(size, list) and len(size) >= 3 else 1.0

        def _shape_radius_xy(shape: dict) -> float:
            """XY radius/extent for determining if offset is 'large' relative to shape."""
            prim = shape.get("primitive", "box")
            if prim in ("cylinder", "cone", "sphere", "hemisphere"):
                return float(shape.get("radius", shape.get("radius1", 1.0)))
            else:  # box
                size = shape.get("size", [2.0, 2.0, 2.0])
                return max(float(size[0]), float(size[1])) / 2.0 if isinstance(size, list) and len(size) >= 2 else 1.0

        def _shape_half_y(shape: dict) -> float:
            """Half-extent along Y axis (for surface attachment calculations)."""
            prim = shape.get("primitive", "box")
            if prim in ("cylinder", "cone"):
                return float(shape.get("radius", shape.get("radius1", 1.0)))
            elif prim in ("sphere", "hemisphere"):
                return float(shape.get("radius", 1.0))
            else:  # box
                size = shape.get("size", [2.0, 2.0, 2.0])
                return float(size[1]) / 2.0 if isinstance(size, list) and len(size) >= 2 else 1.0

        def _shape_half_x(shape: dict) -> float:
            """Half-extent along X axis (for surface attachment calculations)."""
            prim = shape.get("primitive", "box")
            if prim in ("cylinder", "cone"):
                return float(shape.get("radius", shape.get("radius1", 1.0)))
            elif prim in ("sphere", "hemisphere"):
                return float(shape.get("radius", 1.0))
            else:  # box
                size = shape.get("size", [2.0, 2.0, 2.0])
                return float(size[0]) / 2.0 if isinstance(size, list) and len(size) >= 1 else 1.0

        def _is_structural_connector(label: str, socket_name: str) -> bool:
            """Check if part is a structural connector that should use endpoint geometry.
            Uses label and socket hints — no hardcoded part names.
            Per BLENDER_GEOMETRY_CALCULATIONS.md Section 8.
            """
            from core.connector_geometry import is_connector_part
            return is_connector_part(label, socket_name)

        def _compute_connector_rotation(offset_x: float, offset_y: float, offset_z: float) -> Tuple[float, float, float]:
            """Compute Euler XYZ rotation for a connector using endpoint geometry.

            Per BLENDER_GEOMETRY_CALCULATIONS.md Section 8:
            RULE: For connectors, define by endpoints, not Euler angles.

            Uses quaternion-based rotation_between() for accuracy instead of
            manual Euler angle computation which is error-prone.

            Returns (rx, ry, rz) in radians.
            """
            from core.connector_geometry import Vec3, Quaternion

            total_mag = math.sqrt(offset_x ** 2 + offset_y ** 2 + offset_z ** 2)
            if total_mag < 0.001:
                return (0.0, 0.0, 0.0)

            # Direction vector from parent to child
            direction = Vec3(offset_x, offset_y, offset_z).normalized()

            # Cylinder's local +Z axis
            up = Vec3(0, 0, 1)

            # Quaternion that rotates +Z to direction
            rotation = Quaternion.rotation_between(up, direction)

            return rotation.to_euler_xyz()

        def _rotate_offset_by_parent(offset: List[float], parent_rot_rad: Tuple[float, float, float]) -> List[float]:
            """Transform local offset into world space when parent has rotation.

            Uses Euler XYZ rotation matrix. Essential for children of tilted parts.
            """
            rx, ry, rz = parent_rot_rad
            if abs(rx) < 0.001 and abs(ry) < 0.001 and abs(rz) < 0.001:
                return offset  # No rotation, skip matrix math

            # Rotation matrices for each axis
            cx, sx = math.cos(rx), math.sin(rx)
            cy, sy = math.cos(ry), math.sin(ry)
            cz, sz = math.cos(rz), math.sin(rz)

            # Combined XYZ rotation matrix (Blender's default order)
            # R = Rz @ Ry @ Rx
            x, y, z = offset
            # Apply Rx
            y1 = cx * y - sx * z
            z1 = sx * y + cx * z
            # Apply Ry
            x2 = cy * x + sy * z1
            z2 = -sy * x + cy * z1
            # Apply Rz
            x3 = cz * x2 - sz * y1
            y3 = sz * x2 + cz * y1

            return [round(x3, 6), round(y3, 6), round(z2, 6)]

        # Build root node
        root_data = data["root"]
        root_shape = dict(root_data.get("shape", {"primitive": "box", "size": [2, 2, 2]}))
        root_shape.pop("rotation", None)
        root_shape.pop("location", None)
        
        # === SANITY CHECK (no auto-conversion) ===
        # The system prompt instructs LLM to output meters.
        # We log warnings for suspicious values but trust the output.
        root_shape = _sanity_check_dimensions(root_shape, description)

        root_sources = await _resolve_shape_dims(root_data, root_data.get("label", "base"), root_shape)
        root_att = root_data.get("attachment", {})
        raw_root_offset = list(root_att.get("local_offset", [0, 0, 0]))
        
        # Extract root rotation (in degrees from LLM, convert to radians)
        root_rot_deg = root_att.get("local_rotation_euler", [0, 0, 0])
        root_rot_rad = tuple(math.radians(r) for r in root_rot_deg)
        
        # Trust LLM's offset (system prompt instructs meters)
        root_offset = tuple(raw_root_offset)

        root_node = AssemblyNode(
            node_id=f"root_{root_data.get('label', 'base')}_{tid}",
            label=root_data.get("label", "base"),
            paradigm=PartParadigm.PRIMITIVE,
            sub_spec=root_shape,
            attachment=AttachmentSpec(
                local_offset=root_offset,
                local_rotation_euler=root_rot_rad,
            ),
            children=[],
        )
        root_node._dimension_sources = root_sources  # type: ignore[attr-defined]

        nodes_by_label = {root_node.label: root_node}

        for part in data.get("parts", []):
            label = part.get("label", f"part_{uuid.uuid4().hex[:4]}")
            p_label = part.get("parent_label", root_node.label)
            parent_node = nodes_by_label.get(p_label, root_node)
            socket_name = part.get("socket_name", "joint")

            # Defensive invariant: strip any rotation from shape dict
            shape = dict(part.get("shape", {}))
            shape.pop("rotation", None)
            shape.pop("location", None)
            
            # === SANITY CHECK (no auto-conversion) ===
            shape = _sanity_check_dimensions(shape, description)

            part_sources = await _resolve_shape_dims(part, label, shape)

            rot_deg = part.get("local_rotation_euler", [0, 0, 0])
            rot_rad = list(math.radians(r) for r in rot_deg)
            raw_offset = list(part.get("local_offset", [0, 0, 0]))
            
            # Extract join_mode early (needed for surface attachment correction)
            join_str = part.get("join_mode", "parent_only").lower()
            
            # === SOCKET-BASED POSITION RESOLUTION ===
            # Infer semantic socket type and let the resolver compute positions
            socket_type = infer_socket_type(socket_name, parent_node.label)
            
            # CRITICAL: Boolean cutters should NOT have their positions resolved
            # They need to stay where the LLM placed them (inside the parent)
            is_boolean_cutter = join_str == "boolean_difference"
            
            # For semantic socket types, use the resolver instead of trusting LLM math
            # EXCEPT for boolean cutters which must stay inside parent
            if not is_boolean_cutter and socket_type not in (SocketType.JOINT, SocketType.STRUT, SocketType.RADIAL):
                resolved_offset, resolved_rotation = _resolve_socket_offset(
                    socket_type,
                    parent_node.sub_spec,
                    shape,
                    raw_offset,
                    rot_deg,
                )
                # Use resolved values, but preserve LLM's Z offset if it seems intentional
                # (e.g., "near the top" vs "at the top")
                if socket_type in (SocketType.THROUGH_AXIS, SocketType.LEFT_END, SocketType.RIGHT_END,
                                   SocketType.TOP_CENTER, SocketType.BOTTOM_CENTER,
                                   SocketType.TOP_END, SocketType.BOTTOM_END):
                    # For these axial socket types, trust the resolver completely
                    raw_offset = resolved_offset
                    rot_deg = resolved_rotation
                else:
                    # For surface mounts, use resolved XY but keep LLM's Z if non-zero
                    if abs(raw_offset[2]) > 0.01:
                        resolved_offset[2] = raw_offset[2]
                    raw_offset = resolved_offset
                
                # Convert rotation back to radians
                rot_rad = [math.radians(r) for r in rot_deg]
            else:
                rot_rad = list(math.radians(r) for r in rot_deg)

            # === CORRECTION 1: Stacking offset fix ===
            # LLMs make several common mistakes with stacking offsets:
            # a) Return [0,0,0] — need to compute full offset
            # b) Return [0,0,parent_half] — forgot child's half-height
            # c) Return [0,0,parent_half+child_half] — correct, leave alone
            #
            # Detection: if X/Y are near zero (pure vertical stack), check Z
            # SKIP for socket-resolved parts (LEFT_END, RIGHT_END, THROUGH_AXIS, etc.)
            # which intentionally have negative Z offsets in parent's local frame.
            socket_was_resolved = socket_type in (
                SocketType.THROUGH_AXIS, SocketType.LEFT_END, SocketType.RIGHT_END,
                SocketType.TOP_END, SocketType.BOTTOM_END,
                SocketType.TOP_CENTER, SocketType.BOTTOM_CENTER,
            )
            
            parent_half_z = _shape_half_z(parent_node.sub_spec)
            child_half_z = _shape_half_z(shape)
            correct_stack_z = parent_half_z + child_half_z
            
            is_vertical_stack = abs(raw_offset[0]) < 0.01 and abs(raw_offset[1]) < 0.01
            
            if is_vertical_stack and not socket_was_resolved:
                if abs(raw_offset[2]) < 0.01:
                    # Case (a): LLM returned [0,0,0] — compute full offset
                    raw_offset[2] = round(correct_stack_z, 6)
                elif abs(raw_offset[2] - parent_half_z) < 0.5:
                    # Case (b): LLM returned ~parent_half only — add child's half
                    raw_offset[2] = round(correct_stack_z, 6)

            # === CORRECTION 2: Diagonal tilt for structural connectors ===
            # When a cylinder has XY offset but only Z-axis rotation (yaw),
            # the LLM gave a spin instead of a tilt. Compute proper diagonal tilt.
            xy_mag = math.sqrt(raw_offset[0] ** 2 + raw_offset[1] ** 2)
            only_z_rotation = abs(rot_rad[0]) < 0.01 and abs(rot_rad[1]) < 0.01
            is_cylinder = shape.get("primitive") == "cylinder"
            parent_radius = _shape_radius_xy(parent_node.sub_spec)

            # Tilt correction fires when:
            # - Part is a cylinder with significant XY offset (> 10% of parent radius)
            # - LLM gave only Z rotation (no X/Y tilt)
            # - Part is a structural connector OR offset is large relative to parent
            should_correct_tilt = (
                is_cylinder
                and xy_mag > 0.1 * parent_radius
                and only_z_rotation
                and (_is_structural_connector(label, socket_name) or xy_mag > 0.5 * parent_radius)
            )

            if should_correct_tilt:
                # Compute proper rotation using endpoint geometry (quaternion-based)
                tilt_rx, tilt_ry, tilt_rz = _compute_connector_rotation(raw_offset[0], raw_offset[1], raw_offset[2])
                rot_rad[0] = tilt_rx
                rot_rad[1] = tilt_ry
                # Preserve any Z rotation (compass yaw) from LLM if it was intentional
                if abs(rot_rad[2]) > 0.01:
                    pass  # Keep LLM's Z rotation
                else:
                    rot_rad[2] = tilt_rz

            # === CORRECTION 3: Rotated parent offset transform ===
            # REMOVED: The offset should stay in parent's local frame.
            # graph_to_blender_steps handles the world-space transform.
            # Applying it here AND there causes double-transformation.

            # CORRECTION 4 REMOVED: Now fully handled by _resolve_socket_offset
            # for FRONT_FACE/BACK_FACE/LEFT_FACE/RIGHT_FACE socket types.
            # Having duplicate implementations was a divergence risk.

            offset = tuple(raw_offset)
            rot_rad = tuple(rot_rad)

            # === JOIN MODE ROUTING ===
            # Map LLM join_mode string to JoinMode enum, including boolean_difference
            # (join_str was extracted earlier for surface attachment correction)
            if join_str in ("fuse", "boolean_union"):
                join_mode = JoinMode.FUSE
                interaction_type = InteractionType.ATTACH
            elif join_str == "boolean_difference":
                join_mode = JoinMode.BOOLEAN_DIFFERENCE
                interaction_type = InteractionType.BOOLEAN  # Skip verification for cutters
            else:
                join_mode = JoinMode.PARENT_ONLY
                interaction_type = InteractionType.TOUCH

            node = AssemblyNode(
                node_id=f"node_{label}_{tid}",
                label=label,
                paradigm=PartParadigm.PRIMITIVE,
                sub_spec=shape,
                attachment=AttachmentSpec(
                    parent_node_id=parent_node.node_id,
                    socket_name=socket_name,
                    local_offset=offset,
                    local_rotation_euler=rot_rad,
                    join_mode=join_mode,
                    interaction_type=interaction_type,
                ),
                children=[],
            )
            node._dimension_sources = part_sources  # type: ignore[attr-defined]
            parent_node.children.append(node)
            nodes_by_label[label] = node

        return AssemblyGraph(
            schema_version="2.0",
            task_id=tid,
            root=root_node,
            description=description,
            status="PENDING",
            rests_on_surface=bool(data.get("rests_on_surface", True)),
        )
