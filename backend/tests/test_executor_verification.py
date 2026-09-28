"""Tests for executor verification and rollback functionality."""

import pytest
from core.blender_pipeline.executor import (
    PipelineStatus,
    DEFAULT_DIMENSION_TOLERANCE_M,
    DEFAULT_CONNECTOR_REACH_TOLERANCE_M,
)


class TestPipelineStatus:
    """Test PipelineStatus enum values."""
    
    def test_status_values_exist(self):
        """All expected status values should exist."""
        assert PipelineStatus.SUCCESS == "SUCCESS"
        assert PipelineStatus.BUILD_FAILED == "BUILD_FAILED"
        assert PipelineStatus.VERIFICATION_FAILED == "VERIFICATION_FAILED"
        assert PipelineStatus.VERIFICATION_UNAVAILABLE == "VERIFICATION_UNAVAILABLE"
        assert PipelineStatus.ROLLBACK_COMPLETE == "ROLLBACK_COMPLETE"
    
    def test_status_is_string_enum(self):
        """Status should be usable as string."""
        # Value comparison works directly
        assert PipelineStatus.SUCCESS.value == "SUCCESS"
        assert PipelineStatus.BUILD_FAILED == "BUILD_FAILED"


class TestConfigurableTolerances:
    """Test that tolerances are configurable."""
    
    def test_dimension_tolerance_default(self):
        """Default dimension tolerance should be 1cm."""
        assert DEFAULT_DIMENSION_TOLERANCE_M == 0.01
    
    def test_connector_reach_tolerance_default(self):
        """Default connector reach tolerance should be 5cm."""
        assert DEFAULT_CONNECTOR_REACH_TOLERANCE_M == 0.05
    
    def test_tolerances_are_positive(self):
        """Tolerances must be positive values."""
        assert DEFAULT_DIMENSION_TOLERANCE_M > 0
        assert DEFAULT_CONNECTOR_REACH_TOLERANCE_M > 0


class TestRollbackScript:
    """Test rollback script generation (unit tests without Blender)."""
    
    def test_rollback_script_includes_orphan_cleanup(self):
        """Rollback script should include orphan mesh/material cleanup."""
        # Import the function to check its script content
        import inspect
        from core.blender_pipeline.executor import _rollback_generation
        
        source = inspect.getsource(_rollback_generation)
        
        # Should track meshes before removal
        assert "meshes_before" in source
        assert "materials_before" in source
        
        # Should clean up orphaned data
        assert "orphan_meshes" in source
        assert "orphan_materials" in source
        
        # Should NOT use global orphan purge
        assert "bpy.ops.outliner.orphans_purge" not in source


class TestConnectorVerificationScript:
    """Test connector verification logic."""
    
    def test_connector_verification_function_exists(self):
        """Connector verification function should exist."""
        from core.blender_pipeline.executor import _verify_connectors_reach_targets
        assert callable(_verify_connectors_reach_targets)
    
    def test_connector_verification_checks_strut_and_radial_bridge(self):
        """Verification should check STRUT and RADIAL_BRIDGE socket types."""
        import inspect
        from core.blender_pipeline.executor import _verify_connectors_reach_targets
        
        source = inspect.getsource(_verify_connectors_reach_targets)
        
        assert "STRUT" in source
        assert "RADIAL_BRIDGE" in source
