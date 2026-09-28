"""Geometry Input Validation for Blender MCP operations.

Validates all numeric inputs before Blender execution to prevent:
- NaN/Infinity values
- Negative dimensions
- Out-of-range values
- Invalid array counts
"""

import math
from typing import Dict, List, Any, Optional
from dataclasses import dataclass


@dataclass
class ValidationError:
    field: str
    value: Any
    message: str
    severity: str = "ERROR"  # ERROR, WARNING


# Validation constraints (all in meters)
VALIDATION_RULES = {
    'radius': {'min': 0.0001, 'max': 1000.0, 'type': 'positive_float'},
    'radius1': {'min': 0.0001, 'max': 1000.0, 'type': 'positive_float'},
    'depth': {'min': 0.0001, 'max': 1000.0, 'type': 'positive_float'},
    'size': {'min': 0.0001, 'max': 1000.0, 'type': 'positive_float_list'},
    'vertices': {'min': 3, 'max': 256, 'type': 'positive_int'},
    'location': {'min': -10000.0, 'max': 10000.0, 'type': 'float_list'},
    'rotation': {'min': -3600.0, 'max': 3600.0, 'type': 'float_list'},  # degrees
    'local_offset': {'min': -10000.0, 'max': 10000.0, 'type': 'float_list'},
    'local_rotation_euler': {'min': -6.3, 'max': 6.3, 'type': 'float_list'},  # radians
    'energy': {'min': 0.0, 'max': 100000.0, 'type': 'positive_float'},
    'metallic': {'min': 0.0, 'max': 1.0, 'type': 'float'},
    'roughness': {'min': 0.0, 'max': 1.0, 'type': 'float'},
    'color': {'min': 0.0, 'max': 1.0, 'type': 'float_list'},
}

# Scene-level dimension limits (configurable)
SCENE_LIMITS = {
    'min_dimension': 0.0001,  # 0.1mm minimum
    'max_dimension': 1000.0,  # 1km maximum
    'max_object_count': 10000,
}


def validate_finite(value: Any, field: str) -> Optional[ValidationError]:
    """Check that a numeric value is finite (not NaN or Inf)."""
    if isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                return ValidationError(
                    field=f"{field}[{i}]",
                    value=v,
                    message=f"{field}[{i}] is NaN or Infinity"
                )
    elif isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return ValidationError(
                field=field,
                value=value,
                message=f"{field} is NaN or Infinity"
            )
    return None


def validate_range(value: Any, field: str, min_val: float, max_val: float) -> Optional[ValidationError]:
    """Check that a value is within allowed range."""
    if isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            if isinstance(v, (int, float)) and (v < min_val or v > max_val):
                return ValidationError(
                    field=f"{field}[{i}]",
                    value=v,
                    message=f"{field}[{i}]={v} outside allowed range [{min_val}, {max_val}]"
                )
    elif isinstance(value, (int, float)):
        if value < min_val or value > max_val:
            return ValidationError(
                field=field,
                value=value,
                message=f"{field}={value} outside allowed range [{min_val}, {max_val}]"
            )
    return None


def validate_positive(value: Any, field: str) -> Optional[ValidationError]:
    """Check that a value is positive."""
    if isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            if isinstance(v, (int, float)) and v <= 0:
                return ValidationError(
                    field=f"{field}[{i}]",
                    value=v,
                    message=f"{field}[{i}]={v} must be positive"
                )
    elif isinstance(value, (int, float)):
        if value <= 0:
            return ValidationError(
                field=field,
                value=value,
                message=f"{field}={value} must be positive"
            )
    return None


def validate_type(value: Any, field: str, expected_type: str) -> Optional[ValidationError]:
    """Check that a value has the expected type."""
    if expected_type == 'positive_float':
        if not isinstance(value, (int, float)):
            return ValidationError(field=field, value=value, message=f"{field} must be numeric")
    elif expected_type == 'positive_int':
        if not isinstance(value, int):
            return ValidationError(field=field, value=value, message=f"{field} must be integer")
    elif expected_type in ('float_list', 'positive_float_list'):
        if not isinstance(value, (list, tuple)):
            return ValidationError(field=field, value=value, message=f"{field} must be a list")
        for i, v in enumerate(value):
            if not isinstance(v, (int, float)):
                return ValidationError(field=f"{field}[{i}]", value=v, message=f"{field}[{i}] must be numeric")
    return None


def validate_geometry_params(params: Dict[str, Any]) -> List[ValidationError]:
    """Validate all geometry parameters in a dict.
    
    Returns list of validation errors (empty if all valid).
    """
    errors = []
    
    for field, value in params.items():
        if field not in VALIDATION_RULES:
            continue
        
        rules = VALIDATION_RULES[field]
        
        # Type check
        type_error = validate_type(value, field, rules['type'])
        if type_error:
            errors.append(type_error)
            continue
        
        # Finite check
        finite_error = validate_finite(value, field)
        if finite_error:
            errors.append(finite_error)
            continue
        
        # Range check
        range_error = validate_range(value, field, rules['min'], rules['max'])
        if range_error:
            errors.append(range_error)
        
        # Positive check for positive types
        if rules['type'] in ('positive_float', 'positive_int', 'positive_float_list'):
            pos_error = validate_positive(value, field)
            if pos_error:
                errors.append(pos_error)
    
    return errors


def validate_shape_spec(shape: Dict[str, Any]) -> List[ValidationError]:
    """Validate a shape specification dict."""
    errors = []
    
    prim = shape.get("primitive", "box")
    
    if prim == "cylinder":
        if "radius" in shape:
            errors.extend(validate_geometry_params({"radius": shape["radius"]}))
        if "depth" in shape:
            errors.extend(validate_geometry_params({"depth": shape["depth"]}))
        if "vertices" in shape:
            errors.extend(validate_geometry_params({"vertices": shape["vertices"]}))
    
    elif prim == "sphere" or prim == "hemisphere":
        if "radius" in shape:
            errors.extend(validate_geometry_params({"radius": shape["radius"]}))
    
    elif prim == "cone":
        if "radius1" in shape:
            errors.extend(validate_geometry_params({"radius1": shape["radius1"]}))
        if "depth" in shape:
            errors.extend(validate_geometry_params({"depth": shape["depth"]}))
    
    elif prim == "box":
        if "size" in shape:
            errors.extend(validate_geometry_params({"size": shape["size"]}))
    
    return errors


def validate_assembly_node(node_data: Dict[str, Any]) -> List[ValidationError]:
    """Validate an assembly node's geometry data."""
    errors = []
    
    # Validate shape
    if "shape" in node_data:
        errors.extend(validate_shape_spec(node_data["shape"]))
    
    # Validate offset
    if "local_offset" in node_data:
        errors.extend(validate_geometry_params({"local_offset": node_data["local_offset"]}))
    
    # Validate rotation
    if "local_rotation_euler" in node_data:
        errors.extend(validate_geometry_params({"local_rotation_euler": node_data["local_rotation_euler"]}))
    
    return errors


def normalize_units(value: float, from_unit: str) -> float:
    """Convert a dimension value to meters."""
    conversions = {
        'mm': 0.001,
        'cm': 0.01,
        'm': 1.0,
        'meters': 1.0,
        'in': 0.0254,
        'inches': 0.0254,
        'ft': 0.3048,
        'feet': 0.3048,
    }
    
    factor = conversions.get(from_unit.lower(), 1.0)
    return value * factor


def sanitize_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize parameters by clamping to valid ranges.
    
    Use this for auto-correction rather than rejection.
    """
    sanitized = dict(params)
    
    for field, value in params.items():
        if field not in VALIDATION_RULES:
            continue
        
        rules = VALIDATION_RULES[field]
        
        if isinstance(value, (list, tuple)):
            sanitized[field] = [
                max(rules['min'], min(rules['max'], v)) if isinstance(v, (int, float)) else v
                for v in value
            ]
        elif isinstance(value, (int, float)):
            sanitized[field] = max(rules['min'], min(rules['max'], value))
    
    return sanitized
