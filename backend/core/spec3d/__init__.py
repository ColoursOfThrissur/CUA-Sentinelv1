"""Spec3D v3 — Dynamic LLM-Planned 3D Pipeline."""

from .schema import (
    QuadrupedSpec, HardSurfaceSpec, VesselSpec,
    JointSpec, BoneSpec, AttachmentSpec,
    MaterialSpec, FinishSpec, PartSpec, RelationSpec, ModifierSpec,
    Vec3, ProfilePoint, HandleSpec,
    srgb_hex_to_linear, srgb_hex_to_linear_rgba,
)
from .verifier import SpecVerifier, MeshVerifier, VerificationResult
from .compiler import SpecCompiler
from .runner import HeadlessBlenderRunner
from .library import SpecLibrary, LiveBlenderAppender
from .templates import ArchetypeTemplates
from .planner import SpecPlanner, infer_category
from .pipeline import Spec3DPipeline

__all__ = [
    "QuadrupedSpec", "HardSurfaceSpec", "VesselSpec",
    "JointSpec", "BoneSpec", "AttachmentSpec",
    "MaterialSpec", "FinishSpec", "PartSpec", "RelationSpec", "ModifierSpec",
    "Vec3", "ProfilePoint", "HandleSpec",
    "srgb_hex_to_linear", "srgb_hex_to_linear_rgba",
    "SpecVerifier", "MeshVerifier", "VerificationResult",
    "SpecCompiler",
    "HeadlessBlenderRunner",
    "SpecLibrary", "LiveBlenderAppender",
    "ArchetypeTemplates",
    "SpecPlanner", "infer_category",
    "Spec3DPipeline",
]
