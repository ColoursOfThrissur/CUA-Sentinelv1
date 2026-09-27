"""Archetype Templates — v3 role: FEW-SHOT EXEMPLAR SEEDERS ONLY.

Templates are NOT the production path.  They seed golden JSON files into
backend/data/specs/ for the LLM to study as few-shot references.
They are never called directly during a live build request.

The LLM reads the seeded exemplar JSON to learn the schema vocabulary,
then generates its own spec for whatever object the user described.

Changes from v2:
- All color fields use '#RRGGBB' hex strings (MaterialSpec.color is now str).
- All offset/scale fields use Vec3 (x/y/z keys) where AttachmentSpec expects them.
- simple_car updated: WHEEL_POSITIONS relation_type is now valid in RelationSpec.
- New seeds: lamp, vase, chair, bookshelf.
- quadruped uses 18 joints (same as before, kept stable for golden tests).
"""

from typing import List, Optional
from .schema import (
    QuadrupedSpec, HardSurfaceSpec, VesselSpec,
    JointSpec, BoneSpec,
    AttachmentSpec, MaterialSpec, FinishSpec,
    PartSpec, RelationSpec, ModifierSpec,
    Vec3, ProfilePoint, HandleSpec,
)


class ArchetypeTemplates:

    # ----------------------------------------------------------------
    # Quadruped (dog / generic)
    # ----------------------------------------------------------------

    @staticmethod
    def quadruped(
        name: str = "dog_model",
        body_length: float = 0.85,
        withers_height: float = 0.55,
        torso_thickness: float = 0.12,
        snout_length: float = 0.14,
        tail_length: float = 0.30,
        color: str = "#8B5A2B",   # warm brown
        roughness: float = 0.85,
    ) -> QuadrupedSpec:
        paw_z = 0.035
        hip_z = withers_height * 0.90
        shoulder_z = withers_height

        pelvis_y = -body_length * 0.42
        waist_y  = -body_length * 0.10
        chest_y  =  body_length * 0.38
        neck_y   = chest_y + 0.10
        neck_z   = shoulder_z + 0.10
        head_y   = neck_y + 0.10
        head_z   = neck_z + 0.08
        snout_y  = head_y + snout_length * 0.70
        snout_z  = head_z - 0.03
        nose_y   = head_y + snout_length
        nose_z   = head_z - 0.04

        leg_x = torso_thickness * 0.88

        joints = [
            JointSpec(name="pelvis",   x=0.0,  y=pelvis_y, z=hip_z,            rx=torso_thickness*0.92, ry=torso_thickness*0.90),
            JointSpec(name="waist",    x=0.0,  y=waist_y,  z=hip_z*0.96,       rx=torso_thickness*0.78, ry=torso_thickness*0.78),
            JointSpec(name="chest",    x=0.0,  y=chest_y,  z=shoulder_z,       rx=torso_thickness*1.08, ry=torso_thickness*1.25),
            JointSpec(name="neck",     x=0.0,  y=neck_y,   z=neck_z,           rx=torso_thickness*0.65, ry=torso_thickness*0.70),
            JointSpec(name="head",     x=0.0,  y=head_y,   z=head_z,           rx=torso_thickness*0.68, ry=torso_thickness*0.72),
            JointSpec(name="snout",    x=0.0,  y=snout_y,  z=snout_z,          rx=torso_thickness*0.38, ry=torso_thickness*0.35),
            JointSpec(name="nose",     x=0.0,  y=nose_y,   z=nose_z,           rx=0.022,                ry=0.022),
            JointSpec(name="tail_base",x=0.0,  y=pelvis_y-0.04,  z=hip_z+0.03,          rx=0.035, ry=0.035),
            JointSpec(name="tail_mid", x=0.0,  y=pelvis_y-tail_length*0.55, z=hip_z+tail_length*0.25,  rx=0.026, ry=0.026),
            JointSpec(name="tail_tip", x=0.0,  y=pelvis_y-tail_length*0.85, z=hip_z+tail_length*0.50,  rx=0.016, ry=0.016),
            JointSpec(name="shoulder_L",  x=leg_x, y=chest_y-0.02,  z=shoulder_z*0.85, rx=0.052, ry=0.056),
            JointSpec(name="elbow_L",     x=leg_x, y=chest_y-0.07,  z=shoulder_z*0.52, rx=0.040, ry=0.040),
            JointSpec(name="wrist_L",     x=leg_x, y=chest_y-0.04,  z=shoulder_z*0.24, rx=0.034, ry=0.034),
            JointSpec(name="paw_front_L", x=leg_x, y=chest_y-0.02,  z=paw_z,           rx=0.038, ry=0.038),
            JointSpec(name="hip_L",       x=leg_x, y=pelvis_y-0.02, z=hip_z*0.85,      rx=0.062, ry=0.065),
            JointSpec(name="knee_L",      x=leg_x, y=pelvis_y+0.08, z=hip_z*0.50,      rx=0.046, ry=0.046),
            JointSpec(name="hock_L",      x=leg_x, y=pelvis_y-0.05, z=hip_z*0.24,      rx=0.036, ry=0.036),
            JointSpec(name="paw_rear_L",  x=leg_x, y=pelvis_y-0.03, z=paw_z,           rx=0.038, ry=0.038),
        ]

        bones = [
            BoneSpec(parent="pelvis",      child="waist"),
            BoneSpec(parent="waist",       child="chest"),
            BoneSpec(parent="chest",       child="neck"),
            BoneSpec(parent="neck",        child="head"),
            BoneSpec(parent="head",        child="snout"),
            BoneSpec(parent="snout",       child="nose"),
            BoneSpec(parent="pelvis",      child="tail_base"),
            BoneSpec(parent="tail_base",   child="tail_mid"),
            BoneSpec(parent="tail_mid",    child="tail_tip"),
            BoneSpec(parent="chest",       child="shoulder_L"),
            BoneSpec(parent="shoulder_L",  child="elbow_L"),
            BoneSpec(parent="elbow_L",     child="wrist_L"),
            BoneSpec(parent="wrist_L",     child="paw_front_L"),
            BoneSpec(parent="pelvis",      child="hip_L"),
            BoneSpec(parent="hip_L",       child="knee_L"),
            BoneSpec(parent="knee_L",      child="hock_L"),
            BoneSpec(parent="hock_L",      child="paw_rear_L"),
        ]

        attachments = [
            AttachmentSpec(
                name="ear_L",
                parent_joint="head",
                shape="CONE",
                scale=Vec3(x=0.035, y=0.025, z=0.075),
                offset=Vec3(x=torso_thickness*0.52, y=0.01, z=torso_thickness*0.62),
            ),
        ]

        return QuadrupedSpec(
            category="quadruped",
            name=name,
            symmetry="x",
            body_length_m=body_length,
            withers_height_m=withers_height,
            joints=joints,
            bones=bones,
            attachments=attachments,
            material=MaterialSpec(name="Dog_Fur", color=color, roughness=roughness, metallic=0.0),
            finish=FinishSpec(subdiv_levels=2, shading="SMOOTH"),
        )

    # ----------------------------------------------------------------
    # Dining table
    # ----------------------------------------------------------------

    @staticmethod
    def dining_table(
        name: str = "dining_table",
        length: float = 1.60,
        width: float = 0.90,
        height: float = 0.75,
        top_thickness: float = 0.04,
        leg_thickness: float = 0.05,
        color: str = "#5C3317",   # walnut
        roughness: float = 0.55,
    ) -> HardSurfaceSpec:
        leg_height = height - top_thickness
        mat = MaterialSpec(name="Table_Wood", color=color, roughness=roughness)
        return HardSurfaceSpec(
            category="furniture",
            name=name,
            parts=[
                PartSpec(
                    name="tabletop",
                    primitive="BOX",
                    size=[width, length, top_thickness],
                    modifiers=[ModifierSpec(type="BEVEL", width=0.008, segments=2)],
                    material=mat,
                ),
                PartSpec(
                    name="leg",
                    primitive="CYLINDER",
                    size=[leg_thickness / 2.0, leg_height],
                    modifiers=[ModifierSpec(type="BEVEL", width=0.004, segments=2)],
                    material=mat,
                ),
            ],
            relations=[
                RelationSpec(
                    target_part="leg",
                    parent_part="tabletop",
                    relation_type="CORNER_LEGS",
                    inset=0.06,
                ),
            ],
            finish=FinishSpec(subdiv_levels=0, shading="SMOOTH"),
        )

    # ----------------------------------------------------------------
    # Ceramic mug
    # ----------------------------------------------------------------

    @staticmethod
    def ceramic_mug(
        name: str = "ceramic_mug",
        height: float = 0.10,
        radius: float = 0.042,
        wall_thickness: float = 0.005,
        handle_radius: float = 0.028,
        color: str = "#CC1A1A",   # glossy red
        roughness: float = 0.12,
    ) -> HardSurfaceSpec:
        mat = MaterialSpec(name="Ceramic", color=color, roughness=roughness, coat_weight=1.0)
        return HardSurfaceSpec(
            category="vessel",
            name=name,
            parts=[
                PartSpec(
                    name="mug_body",
                    primitive="CYLINDER",
                    size=[radius, height],
                    end_fill_type="NOTHING",
                    modifiers=[
                        ModifierSpec(type="SOLIDIFY", thickness=wall_thickness),
                        ModifierSpec(type="BEVEL", width=0.002, segments=3),
                        ModifierSpec(type="SUBSURF", levels=2),
                    ],
                    material=mat,
                ),
                PartSpec(
                    name="mug_handle",
                    primitive="TORUS",
                    size=[handle_radius, wall_thickness * 1.5],
                    modifiers=[ModifierSpec(type="SUBSURF", levels=2)],
                    material=mat,
                ),
            ],
            relations=[
                RelationSpec(
                    target_part="mug_handle",
                    parent_part="mug_body",
                    relation_type="ATTACH_SIDE",
                    offset=Vec3(x=radius * 1.05, y=0.0, z=0.0),
                ),
            ],
            finish=FinishSpec(subdiv_levels=2, shading="SMOOTH"),
        )

    # ----------------------------------------------------------------
    # Simple car  (fixed: WHEEL_POSITIONS is now valid in RelationSpec)
    # ----------------------------------------------------------------

    @staticmethod
    def simple_car(
        name: str = "simple_car",
        length: float = 2.4,
        width: float = 1.1,
        height: float = 0.85,
        wheel_radius: float = 0.22,
        color: str = "#2660C8",   # automotive blue
        roughness: float = 0.18,
    ) -> HardSurfaceSpec:
        chassis_h = height * 0.40
        cabin_h = height * 0.50
        cabin_l = length * 0.52
        cabin_w = width * 0.84
        paint = MaterialSpec(name="Car_Paint", color=color, roughness=roughness, metallic=0.7, coat_weight=0.9)
        glass = MaterialSpec(name="Car_Glass", color="#141E28", roughness=0.05, metallic=0.1)
        rubber = MaterialSpec(name="Tire", color="#0A0A0A", roughness=0.9)
        return HardSurfaceSpec(
            category="vehicle",
            name=name,
            parts=[
                PartSpec(
                    name="chassis",
                    primitive="BOX",
                    size=[width, length, chassis_h * 0.7],
                    modifiers=[
                        ModifierSpec(type="BEVEL", width=0.025, segments=3),
                        ModifierSpec(type="SUBSURF", levels=1),
                    ],
                    material=paint,
                ),
                PartSpec(
                    name="cabin",
                    primitive="BOX",
                    size=[cabin_w, cabin_l, cabin_h],
                    modifiers=[
                        ModifierSpec(type="BEVEL", width=0.035, segments=3),
                        ModifierSpec(type="SUBSURF", levels=1),
                    ],
                    material=glass,
                ),
                PartSpec(
                    name="wheel",
                    primitive="CYLINDER",
                    size=[wheel_radius, 0.12],
                    modifiers=[ModifierSpec(type="BEVEL", width=0.015, segments=2)],
                    material=rubber,
                ),
            ],
            relations=[
                RelationSpec(
                    target_part="cabin",
                    parent_part="chassis",
                    relation_type="ON_TOP_OF",
                    offset=Vec3(x=0.0, y=-length * 0.08, z=0.0),
                ),
                RelationSpec(
                    target_part="wheel",
                    parent_part="chassis",
                    relation_type="WHEEL_POSITIONS",
                    inset=0.10,
                ),
            ],
            finish=FinishSpec(subdiv_levels=1, shading="SMOOTH"),
        )

    # ----------------------------------------------------------------
    # Wine glass  (VesselSpec — bmesh spin revolution)
    # ----------------------------------------------------------------

    @staticmethod
    def wine_glass(
        name: str = "wine_glass",
        color: str = "#E8E8FF",   # pale glass
        roughness: float = 0.02,
    ) -> VesselSpec:
        """Wine glass profile revolved around Z.  Bowl → stem → base."""
        profile = [
            ProfilePoint(radius=0.000, height=0.000),   # base center
            ProfilePoint(radius=0.050, height=0.002),   # base edge
            ProfilePoint(radius=0.048, height=0.006),   # base top-inner
            ProfilePoint(radius=0.009, height=0.010),   # stem bottom
            ProfilePoint(radius=0.007, height=0.090),   # stem mid
            ProfilePoint(radius=0.009, height=0.110),   # stem top
            ProfilePoint(radius=0.018, height=0.120),   # bowl base
            ProfilePoint(radius=0.042, height=0.160),   # bowl lower
            ProfilePoint(radius=0.052, height=0.190),   # bowl equator
            ProfilePoint(radius=0.048, height=0.215),   # bowl upper
            ProfilePoint(radius=0.044, height=0.230),   # rim
        ]
        return VesselSpec(
            category="vessel",
            name=name,
            profile=profile,
            wall_thickness=0.003,
            bottom_closed=True,
            top_closed=False,
            steps=48,
            material=MaterialSpec(
                name="Glass_Mat",
                color=color,
                roughness=roughness,
                metallic=0.0,
                coat_weight=1.0,
            ),
            finish=FinishSpec(subdiv_levels=2, shading="SMOOTH"),
        )

    # ----------------------------------------------------------------
    # Vase  (VesselSpec)
    # ----------------------------------------------------------------

    @staticmethod
    def ceramic_vase(
        name: str = "ceramic_vase",
        color: str = "#1A6B8A",   # teal glaze
        roughness: float = 0.08,
    ) -> VesselSpec:
        profile = [
            ProfilePoint(radius=0.000, height=0.000),
            ProfilePoint(radius=0.060, height=0.005),
            ProfilePoint(radius=0.055, height=0.020),
            ProfilePoint(radius=0.075, height=0.100),
            ProfilePoint(radius=0.090, height=0.200),
            ProfilePoint(radius=0.080, height=0.280),
            ProfilePoint(radius=0.040, height=0.340),
            ProfilePoint(radius=0.035, height=0.360),
        ]
        return VesselSpec(
            category="vessel",
            name=name,
            profile=profile,
            wall_thickness=0.006,
            bottom_closed=True,
            top_closed=False,
            steps=32,
            material=MaterialSpec(name="Glaze", color=color, roughness=roughness, coat_weight=0.8),
            finish=FinishSpec(subdiv_levels=2, shading="SMOOTH"),
        )

    # ----------------------------------------------------------------
    # Chair
    # ----------------------------------------------------------------

    @staticmethod
    def dining_chair(
        name: str = "dining_chair",
        color: str = "#5C3317",
        roughness: float = 0.60,
    ) -> HardSurfaceSpec:
        mat = MaterialSpec(name="Chair_Wood", color=color, roughness=roughness)
        return HardSurfaceSpec(
            category="furniture",
            name=name,
            parts=[
                PartSpec(name="seat",      primitive="BOX",      size=[0.46, 0.46, 0.03],
                         modifiers=[ModifierSpec(type="BEVEL", width=0.005, segments=2)], material=mat),
                PartSpec(name="back_panel",primitive="BOX",      size=[0.44, 0.04, 0.42],
                         modifiers=[ModifierSpec(type="BEVEL", width=0.004, segments=2)], material=mat),
                PartSpec(name="leg",       primitive="CYLINDER",  size=[0.02, 0.45],
                         modifiers=[ModifierSpec(type="BEVEL", width=0.003, segments=2)], material=mat),
            ],
            relations=[
                RelationSpec(target_part="back_panel", parent_part="seat",
                             relation_type="ON_TOP_OF",
                             offset=Vec3(x=0.0, y=-0.21, z=0.0)),
                RelationSpec(target_part="leg", parent_part="seat",
                             relation_type="CORNER_LEGS", inset=0.04),
            ],
            finish=FinishSpec(subdiv_levels=0, shading="SMOOTH"),
        )

    # ----------------------------------------------------------------
    # Bookshelf
    # ----------------------------------------------------------------

    @staticmethod
    def bookshelf(
        name: str = "bookshelf",
        color: str = "#C8A86E",   # light oak
        roughness: float = 0.50,
    ) -> HardSurfaceSpec:
        mat = MaterialSpec(name="Shelf_Wood", color=color, roughness=roughness)
        return HardSurfaceSpec(
            category="furniture",
            name=name,
            parts=[
                PartSpec(name="side_panel",  primitive="BOX", size=[0.03, 0.30, 1.80],
                         modifiers=[], material=mat, pattern="CORNERS", count=2),
                PartSpec(name="shelf_board", primitive="BOX", size=[0.76, 0.28, 0.02],
                         modifiers=[], material=mat, pattern="GRID", count=5),
                PartSpec(name="back_board",  primitive="BOX", size=[0.76, 0.01, 1.78],
                         modifiers=[], material=mat),
            ],
            relations=[
                RelationSpec(target_part="shelf_board", parent_part="side_panel",
                             relation_type="ALIGN_CENTER",
                             offset=Vec3(x=0.0, y=0.0, z=0.0)),
            ],
            finish=FinishSpec(subdiv_levels=0, shading="SMOOTH"),
        )

    # ----------------------------------------------------------------
    # Floor lamp
    # ----------------------------------------------------------------

    @staticmethod
    def floor_lamp(
        name: str = "floor_lamp",
        shade_color: str = "#F5DEB3",   # warm ivory
        base_color: str = "#C0C0C0",    # silver
        roughness: float = 0.30,
    ) -> HardSurfaceSpec:
        shade_mat = MaterialSpec(name="Shade", color=shade_color, roughness=0.7)
        pole_mat  = MaterialSpec(name="Pole",  color=base_color,  roughness=roughness, metallic=0.8)
        return HardSurfaceSpec(
            category="generic",
            name=name,
            parts=[
                PartSpec(name="base",      primitive="CYLINDER", size=[0.18, 0.03],
                         modifiers=[ModifierSpec(type="BEVEL", width=0.005, segments=2)],
                         material=pole_mat),
                PartSpec(name="pole",      primitive="CYLINDER", size=[0.015, 1.40],
                         material=pole_mat),
                PartSpec(name="lampshade", primitive="CYLINDER", size=[0.20, 0.30],
                         end_fill_type="NOTHING",
                         modifiers=[ModifierSpec(type="SOLIDIFY", thickness=0.004)],
                         material=shade_mat),
            ],
            relations=[
                RelationSpec(target_part="pole", parent_part="base",
                             relation_type="ON_TOP_OF", offset=Vec3()),
                RelationSpec(target_part="lampshade", parent_part="pole",
                             relation_type="ON_TOP_OF", offset=Vec3()),
            ],
            finish=FinishSpec(subdiv_levels=1, shading="SMOOTH"),
        )
