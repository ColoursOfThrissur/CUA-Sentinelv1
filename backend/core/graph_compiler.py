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
)

logger = logging.getLogger(__name__)


# Structured decomposition system prompt for the LLM
DECOMPOSITION_SYSTEM_PROMPT = """You are a 3D CAD Assembly Decomposer.
Your task is to decompose any described physical object into a hierarchical AssemblyGraph.

Rules:
1. Identify all distinct physical components (e.g. base, stem, head, legs, tabletop, plates, grip).
2. Root part MUST be the base/ground part or primary central mass (Z=0 touching surface or central chassis).
3. For each part, specify its intrinsic shape:
   - "box": size [dx, dy, dz]
   - "cylinder": radius r, depth h, vertices n (e.g. 6 for hexagon, 32 for smooth cylinder)
   - "sphere": radius r
   Extract the EXACT dimensions specified in the user's prompt. Do not invent unrelated dimensions.
4. For every non-root part, specify:
   - parent_label: label of the part it mounts to
   - socket_name: e.g. "top_center", "left_end", "corner_fl"
   - local_offset: [dx, dy, dz] relative to parent's centroid
   - local_rotation_euler: [rx, ry, rz] in degrees
   - join_mode: "parent_only" or "fuse"
5. Do NOT include rotation inside the shape params. Put rotation ONLY in local_rotation_euler.

Output strictly valid JSON with this schema:
{
  "root": {
    "label": "<name>",
    "shape": {"primitive": "cylinder|box|sphere", ...},
    "attachment": {"local_offset": [0,0,z_centroid]}
  },
  "parts": [
    {
      "label": "<name>",
      "parent_label": "<parent_name>",
      "socket_name": "<socket>",
      "shape": {"primitive": "...", ...},
      "local_offset": [dx, dy, dz],
      "local_rotation_euler": [rx, ry, rz],
      "join_mode": "parent_only"
    }
  ]
}
"""


class GraphCompiler:
    """Compiles 3D requests into an AssemblyGraph without hardcoded dimension lookups."""

    @classmethod
    async def compile_from_prompt(
        cls,
        prompt: str,
        model_manager: Any = None,
        task_id: Optional[str] = None,
    ) -> AssemblyGraph:
        """Decompose an arbitrary natural language prompt using the LLM."""
        tid = task_id or f"graph_{uuid.uuid4().hex[:8]}"

        # If LLM is available, perform genuine zero-shot decomposition
        if model_manager is not None:
            try:
                response = await model_manager.generate(
                    system_prompt=DECOMPOSITION_SYSTEM_PROMPT,
                    prompt=prompt,
                    temperature=0.1,
                )
                decomp = cls._extract_json(response)
                if decomp and "root" in decomp:
                    return cls._build_graph_from_decomp(decomp, prompt, tid)
            except Exception as e:
                logger.warning(f"LLM decomposition failed ({e}), falling back to deterministic extractor")

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
    def _build_graph_from_decomp(cls, data: Dict[str, Any], description: str, tid: str) -> AssemblyGraph:
        """Convert LLM decomposition JSON into an AssemblyGraph v2.0."""
        root_data = data["root"]
        root_shape = dict(root_data.get("shape", {"primitive": "box", "size": [2, 2, 2]}))
        # Defensive invariant: shape sub_specs contain ONLY intrinsic dimensions, never rotation
        root_shape.pop("rotation", None)
        root_shape.pop("location", None)

        root_att = root_data.get("attachment", {})
        root_offset = tuple(root_att.get("local_offset", [0, 0, 0]))

        root_node = AssemblyNode(
            node_id=f"root_{root_data.get('label', 'base')}_{tid}",
            label=root_data.get("label", "base"),
            paradigm=PartParadigm.PRIMITIVE,
            sub_spec=root_shape,
            attachment=AttachmentSpec(local_offset=root_offset),
            children=[],
        )

        nodes_by_label = {root_node.label: root_node}

        for part in data.get("parts", []):
            label = part.get("label", f"part_{uuid.uuid4().hex[:4]}")
            p_label = part.get("parent_label", root_node.label)
            parent_node = nodes_by_label.get(p_label, root_node)

            # Defensive invariant: strip any rotation from shape dict
            shape = dict(part.get("shape", {}))
            shape.pop("rotation", None)
            shape.pop("location", None)

            rot_deg = part.get("local_rotation_euler", [0, 0, 0])
            rot_rad = tuple(math.radians(r) for r in rot_deg)
            offset = tuple(part.get("local_offset", [0, 0, 0]))
            join_str = part.get("join_mode", "parent_only")
            join_mode = JoinMode.FUSE if join_str.lower() in ("fuse", "boolean_union") else JoinMode.PARENT_ONLY

            node = AssemblyNode(
                node_id=f"node_{label}_{tid}",
                label=label,
                paradigm=PartParadigm.PRIMITIVE,
                sub_spec=shape,
                attachment=AttachmentSpec(
                    parent_node_id=parent_node.node_id,
                    socket_name=part.get("socket_name", "joint"),
                    local_offset=offset,
                    local_rotation_euler=rot_rad,
                    join_mode=join_mode,
                ),
                children=[],
            )
            parent_node.children.append(node)
            nodes_by_label[label] = node

        return AssemblyGraph(
            schema_version="2.0",
            task_id=tid,
            root=root_node,
            description=description,
            status="PENDING",
        )
