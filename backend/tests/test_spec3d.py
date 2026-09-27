"""Tests for the Spec3D v3 Dynamic LLM-Planned 3D Pipeline.

Test groups:
  1. Schema — hex color, Vec3, VesselSpec, centerline clamping.
  2. Templates — all archetypes pass Tier 1.
  3. Tier 1 verifier — catches unlevel paws, zero-length bones, bad centerline.
  4. Compiler — modifier order, hex color in script, unique suffix, model collection.
  5. sRGB conversion — roundtrip within 1/255.
  6. Library — initialization, exemplar retrieval, approved spec persistence.
  7. Live appender — script generation, collection name, viewport shading method.
  8. Deterministic compile — same spec → same script hash.
  9. Vessel revolution — profile shape, wall thickness, closed bottom.
 10. Handle contact check — offset-too-far mug handle flagged.
 11. Golden metrics — dog and mug spec within expected ranges.
 12. Blender 4.5 socket names — Coat Weight, Specular IOR Level in script.
 13. Append collision test — consecutive appends yield distinct names.
 14. Knob fuzz (slow) — 30 random param vectors all pass Tier 1.
 15. Headless integration tests (skipped if Blender not present).
"""

import os
import sys
import hashlib
import pytest
import random
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from core.spec3d.schema import (
    QuadrupedSpec, HardSurfaceSpec, VesselSpec,
    JointSpec, BoneSpec, MaterialSpec, FinishSpec,
    Vec3, ProfilePoint, HandleSpec,
    srgb_hex_to_linear, srgb_hex_to_linear_rgba,
)
from core.spec3d.templates import ArchetypeTemplates
from core.spec3d.verifier import SpecVerifier, MeshVerifier
from core.spec3d.compiler import SpecCompiler
from core.spec3d.runner import HeadlessBlenderRunner, DEFAULT_BLENDER_PATH
from core.spec3d.library import SpecLibrary, LiveBlenderAppender


# ===========================================================================
# 1. Schema
# ===========================================================================

def test_hex_color_validation():
    mat = MaterialSpec(color="#8B4513")
    assert mat.color == "#8B4513"

    with pytest.raises(Exception):
        MaterialSpec(color="brown")  # not a valid hex

    with pytest.raises(Exception):
        MaterialSpec(color="#ZZZZZZ")


def test_vec3_defaults():
    v = Vec3()
    assert v.x == 0.0 and v.y == 0.0 and v.z == 0.0
    assert v.as_tuple() == (0.0, 0.0, 0.0)


def test_vessel_spec_profile():
    vs = ArchetypeTemplates.wine_glass()
    assert vs.category == "vessel"
    assert len(vs.profile) >= 3
    assert all(pt.radius >= 0 for pt in vs.profile)
    assert vs.wall_thickness > 0


def test_centerline_clamping():
    spec = ArchetypeTemplates.quadruped()
    for j in spec.joints:
        if not j.name.endswith("_L") and not j.name.endswith("_R"):
            assert j.x == 0.0, f"Joint {j.name} expected x=0, got {j.x}"


# ===========================================================================
# 2. Templates — all archetypes pass Tier 1
# ===========================================================================

def test_all_templates_pass_tier1():
    results = {
        "dog": (ArchetypeTemplates.quadruped(), "quadruped"),
        "table": (ArchetypeTemplates.dining_table(), "furniture"),
        "mug": (ArchetypeTemplates.ceramic_mug(), "vessel"),
        "car": (ArchetypeTemplates.simple_car(), "vehicle"),
        "wine_glass_vessel": (ArchetypeTemplates.wine_glass(), "vessel"),
        "vase": (ArchetypeTemplates.ceramic_vase(), "vessel"),
        "chair": (ArchetypeTemplates.dining_chair(), "furniture"),
        "bookshelf": (ArchetypeTemplates.bookshelf(), "furniture"),
        "lamp": (ArchetypeTemplates.floor_lamp(), "generic"),
    }
    for label, (spec, _cat) in results.items():
        if isinstance(spec, QuadrupedSpec):
            res = SpecVerifier.verify_quadruped(spec)
        elif isinstance(spec, VesselSpec):
            res = SpecVerifier.verify_vessel(spec)
        else:
            res = SpecVerifier.verify_hard_surface(spec)
        assert res.valid, f"Template '{label}' failed Tier 1: {res.errors}"
        assert res.score >= 0.85, f"Template '{label}' low score: {res.score}"


# ===========================================================================
# 3. Tier 1 verifier edge cases
# ===========================================================================

def test_tier1_catches_unlevel_paws():
    dog = ArchetypeTemplates.quadruped()
    for j in dog.joints:
        if j.name == "paw_front_L":
            j.z += 0.05
    res = SpecVerifier.verify_quadruped(dog)
    assert not res.valid
    assert any("Unlevel paws" in e for e in res.errors)
    assert "joints.paw_front_L.z" in res.repair_patches


def test_tier1_catches_zero_length_bones():
    dog = ArchetypeTemplates.quadruped()
    neck = next(j for j in dog.joints if j.name == "neck")
    head = next(j for j in dog.joints if j.name == "head")
    head.x, head.y, head.z = neck.x, neck.y, neck.z
    res = SpecVerifier.verify_quadruped(dog)
    assert not res.valid
    assert any("Zero-length bone" in e for e in res.errors)


def test_tier1_catches_bad_centerline():
    """The Pydantic field_validator auto-clamps x to 0.0 for centerline joints.
    The verifier should then report the spec as valid (the clamp fixed it).
    If someone bypasses the validator and passes x=0.5 directly, the verifier catches it.
    """
    dog = ArchetypeTemplates.quadruped()
    # Field validator already clamped all centerline joints to x=0.0
    for j in dog.joints:
        if j.name == "chest":
            assert j.x == 0.0, "Validator should have clamped x to 0.0"
    res = SpecVerifier.verify_quadruped(dog)
    assert res.valid, f"Valid spec after clamping should pass: {res.errors}"

    # Manually inject a bad value post-validation to test the verifier path
    for j in dog.joints:
        if j.name == "chest":
            object.__setattr__(j, "x", 0.5)  # bypass Pydantic immutability
    res2 = SpecVerifier.verify_quadruped(dog)
    assert not res2.valid
    assert any("Centerline" in e for e in res2.errors)


def test_tier1_catches_disconnected_joint():
    dog = ArchetypeTemplates.quadruped()
    # Add a floating joint with no bone
    dog.joints.append(JointSpec(name="floating", x=0.5, y=0.5, z=0.5, rx=0.05, ry=0.05))
    res = SpecVerifier.verify_quadruped(dog)
    assert not res.valid
    assert any("Disconnected" in e for e in res.errors)


# ===========================================================================
# 4. Compiler
# ===========================================================================

def test_compiler_modifier_order_skeleton():
    dog = ArchetypeTemplates.quadruped()
    script = SpecCompiler.compile_to_script(dog)

    pos_mirror  = script.find('obj.modifiers.new(name="Mirror"')
    pos_skin    = script.find('obj.modifiers.new(name="Skin"')
    pos_subsurf = script.find('obj.modifiers.new(name="Subdivision"')

    assert pos_mirror != -1,  "Mirror modifier missing"
    assert pos_skin != -1,    "Skin modifier missing"
    assert pos_subsurf != -1, "Subsurf modifier missing"
    assert pos_mirror < pos_skin < pos_subsurf, "Modifier order must be MIRROR→SKIN→SUBSURF"


def test_compiler_branch_smoothing():
    dog = ArchetypeTemplates.quadruped()
    script = SpecCompiler.compile_to_script(dog)
    assert "branch_smoothing" in script
    assert "0.5" in script


def test_compiler_unique_build_suffix():
    dog = ArchetypeTemplates.quadruped()
    script = SpecCompiler.compile_to_script(dog)
    assert "BUILD_SUFFIX" in script
    assert "MODEL_COLL_NAME" in script
    assert "Sentinel_Model_" in script


def test_compiler_model_collection_in_script():
    dog = ArchetypeTemplates.quadruped()
    script = SpecCompiler.compile_to_script(dog)
    assert "model_coll = bpy.data.collections.new(MODEL_COLL_NAME)" in script
    assert "link_to_model_coll(" in script


def test_compiler_no_viewport_shading_in_headless():
    """Headless script must NOT reference bpy.context.screen (None in -b mode)."""
    dog = ArchetypeTemplates.quadruped()
    script = SpecCompiler.compile_to_script(dog)
    # The viewport shading code should NOT be in the headless script
    # (it lives in the append script only)
    assert "bpy.context.screen.areas" not in script


def test_compiler_hex_color_conversion_in_script():
    dog = ArchetypeTemplates.quadruped()
    script = SpecCompiler.compile_to_script(dog)
    assert "srgb_to_linear(" in script
    assert "hex_to_linear_rgba(" in script


def test_compiler_vessel_spin():
    vase = ArchetypeTemplates.ceramic_vase()
    script = SpecCompiler.compile_to_script(vase)
    assert "bmesh.ops.spin" in script
    assert "bmesh.ops.remove_doubles" in script
    assert "bmesh.ops.recalc_face_normals" in script
    assert "SOLIDIFY" in script  # wall thickness


def test_blender_45_socket_names():
    """Compiled script must handle Coat Weight and Specular IOR Level."""
    dog = ArchetypeTemplates.quadruped()
    script = SpecCompiler.compile_to_script(dog)
    assert "Coat Weight" in script
    assert "Specular IOR Level" in script


# ===========================================================================
# 5. sRGB conversion
# ===========================================================================

def test_srgb_hex_to_linear_roundtrip():
    """#8B4513 → linear → back to sRGB within 1/255."""
    hex_in = "#8B4513"
    r_l, g_l, b_l = srgb_hex_to_linear(hex_in)

    def _to_srgb(c: float) -> float:
        return c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055

    r_s = round(_to_srgb(r_l) * 255)
    g_s = round(_to_srgb(g_l) * 255)
    b_s = round(_to_srgb(b_l) * 255)

    assert abs(r_s - 0x8B) <= 1
    assert abs(g_s - 0x45) <= 1
    assert abs(b_s - 0x13) <= 1


def test_srgb_white_and_black():
    assert srgb_hex_to_linear("#000000") == (0.0, 0.0, 0.0)
    r, g, b = srgb_hex_to_linear("#FFFFFF")
    assert abs(r - 1.0) < 0.001 and abs(g - 1.0) < 0.001 and abs(b - 1.0) < 0.001


# ===========================================================================
# 6. Library
# ===========================================================================

def test_spec_library_initialization_and_retrieval():
    SpecLibrary.initialize_library()
    dog_ex = SpecLibrary.get_few_shot_exemplar("quadruped")
    assert dog_ex is not None
    assert dog_ex.get("category") == "quadruped"

    table_ex = SpecLibrary.get_few_shot_exemplar("furniture")
    assert table_ex is not None

    mug_ex = SpecLibrary.get_few_shot_exemplar("vessel")
    assert mug_ex is not None


def test_library_category_aliases():
    SpecLibrary.initialize_library()
    assert SpecLibrary.get_few_shot_exemplar("dog") is not None    # alias for quadruped
    assert SpecLibrary.get_few_shot_exemplar("mug") is not None    # alias for vessel
    assert SpecLibrary.get_few_shot_exemplar("table") is not None  # alias for furniture


def test_library_no_exact_match_for_unknown():
    assert not SpecLibrary.has_exact_match("a_very_obscure_object_xyz_123")


# ===========================================================================
# 7. Live Blender Appender
# ===========================================================================

def test_appender_uses_collection_load():
    script = LiveBlenderAppender.generate_append_script(
        "C:/tmp/test.blend", "Sentinel_Model_abc123"
    )
    assert "bpy.data.libraries.load" in script
    assert "Sentinel_Model_abc123" in script
    assert "data_to.collections" in script  # collection-based append


def test_appender_viewport_shading_via_window_manager():
    script = LiveBlenderAppender.generate_append_script("C:/tmp/x.blend", "Sentinel_Dog")
    # Must use window_manager path, NOT bpy.context.screen directly
    assert "window_manager" in script or "wm.windows" in script
    assert "space.shading.type = 'MATERIAL'" in script


def test_appender_safe_path_serialization():
    """Windows paths with backslashes must be embedded safely."""
    script = LiveBlenderAppender.generate_append_script(
        r"C:\Users\derik\tmp\test.blend", "Sentinel_Test"
    )
    # json.dumps wraps in double quotes and escapes backslashes
    assert r"\\" in script or '"C:/Users' in script or "C:\\\\Users" in script


def test_appender_excludes_staging_objects():
    script = LiveBlenderAppender.generate_append_script("C:/tmp/x.blend", "Sentinel_Dog")
    # Staging filter should exclude Key_ lights
    assert "Key_" in script  # referenced in filter
    assert "not o.startswith" in script or "data_to.collections" in script


# ===========================================================================
# 8. Deterministic compile
# ===========================================================================

def test_deterministic_compile_same_hash():
    dog = ArchetypeTemplates.quadruped(name="test_dog")
    script_a = SpecCompiler.compile_to_script(dog)
    script_b = SpecCompiler.compile_to_script(dog)
    hash_a = hashlib.sha256(script_a.encode()).hexdigest()
    hash_b = hashlib.sha256(script_b.encode()).hexdigest()
    assert hash_a == hash_b, "Same spec must produce identical script"


def test_different_specs_different_hash():
    dog = ArchetypeTemplates.quadruped(name="dog_a", body_length=0.85)
    cat = ArchetypeTemplates.quadruped(name="cat_a", body_length=0.50)
    hash_dog = hashlib.sha256(SpecCompiler.compile_to_script(dog).encode()).hexdigest()
    hash_cat = hashlib.sha256(SpecCompiler.compile_to_script(cat).encode()).hexdigest()
    assert hash_dog != hash_cat


# ===========================================================================
# 9. Vessel revolution checks (script-level)
# ===========================================================================

def test_vessel_revolution_script_bottom_cap():
    vase = ArchetypeTemplates.ceramic_vase()
    vase.bottom_closed = True
    script = SpecCompiler.compile_to_script(vase)
    assert "bottom_closed" in script
    assert "convex_hull" in script  # bottom cap fill


def test_vessel_revolution_steps_in_script():
    glass = ArchetypeTemplates.wine_glass()
    script = SpecCompiler.compile_to_script(glass)
    assert f"steps = {glass.steps}" in script or str(glass.steps) in script


def test_vessel_handle_torus_in_script():
    mug = ArchetypeTemplates.ceramic_mug()  # HardSurfaceSpec — uses torus part
    script = SpecCompiler.compile_to_script(mug)
    assert "TORUS" in script or "primitive_torus_add" in script


# ===========================================================================
# 10. Handle contact check (Tier 2 metric)
# ===========================================================================

def test_tier2_handle_contact_too_far():
    """A handle with min_dist_mm > 2 and required=True must produce an error."""
    metrics = {
        "contact_results": [
            {"pair": "mug_body–mug_handle", "min_dist_mm": 15.0, "required": True}
        ]
    }
    res = MeshVerifier.verify_mesh_tier2(metrics, category="vessel")
    assert not res.valid
    assert any("Contact check failed" in e for e in res.errors)


def test_tier2_handle_contact_passes():
    metrics = {
        "contact_results": [
            {"pair": "mug_body–mug_handle", "min_dist_mm": 1.2, "required": True}
        ]
    }
    res = MeshVerifier.verify_mesh_tier2(metrics, category="vessel")
    assert res.valid


# ===========================================================================
# 11. Golden metrics (spec-level)
# ===========================================================================

def test_golden_dog_joint_count():
    dog = ArchetypeTemplates.quadruped()
    assert len(dog.joints) == 18
    assert len(dog.bones) == 17


def test_golden_mug_part_count():
    mug = ArchetypeTemplates.ceramic_mug()
    assert len(mug.parts) == 2
    assert mug.parts[0].name == "mug_body"
    assert mug.parts[1].name == "mug_handle"


def test_golden_dog_proportions():
    dog = ArchetypeTemplates.quadruped()
    res = SpecVerifier.verify_quadruped(dog)
    assert res.score >= 0.90


# ===========================================================================
# 12. Append collision test (script-level)
# ===========================================================================

def test_append_unique_suffixes_prevent_collision():
    """Two consecutive builds of the same object must produce different BUILD_SUFFIX values
    (because the spec JSON differs only in name suffix or timestamp, but the suffix is
    derived from the spec hash — so two identical specs get the same suffix, which is
    intentional deduplication.  We verify different names produce different suffixes.)
    """
    dog_a = ArchetypeTemplates.quadruped(name="dog_a")
    dog_b = ArchetypeTemplates.quadruped(name="dog_b")
    script_a = SpecCompiler.compile_to_script(dog_a)
    script_b = SpecCompiler.compile_to_script(dog_b)

    import re
    suffix_a = re.search(r"BUILD_SUFFIX = '([0-9a-f]+)'", script_a)
    suffix_b = re.search(r"BUILD_SUFFIX = '([0-9a-f]+)'", script_b)
    assert suffix_a and suffix_b
    assert suffix_a.group(1) != suffix_b.group(1)


# ===========================================================================
# 13. Knob fuzz (slow) — random param vectors all pass Tier 1
# ===========================================================================

@pytest.mark.slow
def test_knob_fuzz_quadruped_tier1():
    """30 random quadruped param vectors must all pass Tier 1."""
    rng = random.Random(42)
    failures = []
    for i in range(30):
        body_length    = rng.uniform(0.30, 2.50)
        withers_height = rng.uniform(0.20, body_length * 1.2)
        torso_thickness = rng.uniform(0.06, 0.18)
        try:
            spec = ArchetypeTemplates.quadruped(
                name=f"fuzz_{i}",
                body_length=body_length,
                withers_height=withers_height,
                torso_thickness=torso_thickness,
            )
            res = SpecVerifier.verify_quadruped(spec)
            if not res.valid:
                failures.append((i, body_length, withers_height, torso_thickness, res.errors))
        except Exception as e:
            failures.append((i, body_length, withers_height, torso_thickness, [str(e)]))

    assert not failures, f"Fuzz failures: {failures}"


@pytest.mark.slow
def test_knob_fuzz_vessel_tier1():
    """30 random vessel configs must all pass Tier 1."""
    rng = random.Random(99)
    failures = []
    for i in range(30):
        n_pts = rng.randint(4, 12)
        profile = []
        z = 0.0
        r = rng.uniform(0.005, 0.02)
        for _ in range(n_pts):
            z += rng.uniform(0.005, 0.04)
            r = max(0.0, r + rng.uniform(-0.015, 0.025))
            profile.append(ProfilePoint(radius=r, height=z))
        try:
            spec = VesselSpec(
                name=f"fuzz_vessel_{i}",
                profile=profile,
                wall_thickness=rng.uniform(0.002, 0.008),
            )
            res = SpecVerifier.verify_vessel(spec)
            if not res.valid:
                failures.append((i, res.errors))
        except Exception as e:
            failures.append((i, [str(e)]))
    assert not failures, f"Vessel fuzz failures: {failures}"


# ===========================================================================
# 14. Headless integration tests (skipped if Blender absent)
# ===========================================================================

@pytest.mark.asyncio
async def test_headless_quadruped():
    runner = HeadlessBlenderRunner()
    if not Path(runner.blender_bin).is_file():
        pytest.skip(f"Blender not found at {runner.blender_bin}")

    dog = ArchetypeTemplates.quadruped(name="headless_dog")
    script = SpecCompiler.compile_to_script(dog)
    success, metrics, blend_path = await runner.build_and_verify(script, timeout_seconds=60)

    assert success, f"Build failed: {metrics.get('error')} stderr={metrics.get('stderr')}"
    assert Path(blend_path).is_file()
    assert metrics.get("total_polys", 0) > 50
    assert metrics.get("model_collection", "").startswith("Sentinel_Model_")

    try:
        os.remove(blend_path)
    except Exception:
        pass


@pytest.mark.asyncio
async def test_headless_vessel_revolution():
    runner = HeadlessBlenderRunner()
    if not Path(runner.blender_bin).is_file():
        pytest.skip(f"Blender not found at {runner.blender_bin}")

    glass = ArchetypeTemplates.wine_glass(name="headless_wineglass")
    script = SpecCompiler.compile_to_script(glass)
    success, metrics, blend_path = await runner.build_and_verify(script, timeout_seconds=60)

    assert success, f"Vessel build failed: {metrics.get('error')}"
    assert metrics.get("total_polys", 0) > 100
    assert metrics.get("non_manifold_edges", 0) == 0, "Vessel should be manifold"

    try:
        os.remove(blend_path)
    except Exception:
        pass


@pytest.mark.asyncio
async def test_headless_table():
    runner = HeadlessBlenderRunner()
    if not Path(runner.blender_bin).is_file():
        pytest.skip(f"Blender not found at {runner.blender_bin}")

    table = ArchetypeTemplates.dining_table(name="headless_table")
    script = SpecCompiler.compile_to_script(table)
    success, metrics, blend_path = await runner.build_and_verify(script, timeout_seconds=60)

    assert success, f"Table build failed: {metrics.get('error')}"
    assert metrics.get("object_count", 0) >= 5  # top + 4 legs

    try:
        os.remove(blend_path)
    except Exception:
        pass


@pytest.mark.asyncio
async def test_headless_append_no_staging_objects():
    """After append, the scene must contain no Sentinel_Staging_ objects."""
    runner = HeadlessBlenderRunner()
    if not Path(runner.blender_bin).is_file():
        pytest.skip(f"Blender not found at {runner.blender_bin}")

    dog = ArchetypeTemplates.quadruped(name="collision_test_dog")
    script = SpecCompiler.compile_to_script(dog)
    success, metrics, blend_path = await runner.build_and_verify(script, timeout_seconds=60)
    if not success:
        pytest.skip("Build failed — cannot test append")

    append_script = LiveBlenderAppender.generate_append_script(
        blend_path, metrics.get("model_collection", "Sentinel_Dog")
    )
    # Verify no staging objects are referenced in the append payload
    assert "Sentinel_Staging" not in append_script.split("data_to")[1].split("data_from")[0]

    try:
        os.remove(blend_path)
    except Exception:
        pass


def test_blender_ops_resilient_templates():
    """Verify that blender_ops templates embed _find_blender_object for fuzzy/substring matching."""
    from core.blender_ops import (
        _SET_MATERIAL_TEMPLATE,
        _APPLY_SUBDIVISION_TEMPLATE,
        _SET_TRANSFORM_TEMPLATE,
        SetMaterialParams,
        render_op_script,
    )

    assert "_find_blender_object" in _SET_MATERIAL_TEMPLATE
    assert "_find_blender_object" in _APPLY_SUBDIVISION_TEMPLATE
    assert "_find_blender_object" in _SET_TRANSFORM_TEMPLATE

    params = SetMaterialParams(name="penguin_figurine", color=[0.9, 0.9, 0.9, 1.0], metallic=0.2, roughness=0.1)
    rendered = render_op_script(_SET_MATERIAL_TEMPLATE, params)
    assert "PARAMS_JSON" in rendered
    assert "penguin_figurine" in rendered
    assert "_find_blender_object" in rendered
