"""Unit tests for the extracted ProjectEnvironmentService."""

import os
import sys
import tempfile
import pytest

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from core.project_environment_service import ProjectEnvironmentService


@pytest.fixture
def env_service():
    return ProjectEnvironmentService()


@pytest.fixture
def temp_project():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


def test_scan_python_ast_imports(env_service, temp_project):
    """AST scanner extracts third-party dependencies while filtering built-ins."""
    py_file = os.path.join(temp_project, "sample.py")
    with open(py_file, "w", encoding="utf-8") as f:
        f.write("""
import os
import sys
import requests
from PIL import Image
import yaml
""")

    imports = env_service.scan_python_imports(temp_project)
    assert "requests" in imports
    assert "Pillow" in imports  # Translated PIL -> Pillow
    assert "PyYAML" in imports  # Translated yaml -> PyYAML
    assert "os" not in imports  # Built-in filtered
    assert "sys" not in imports  # Built-in filtered


def test_scan_js_ts_imports(env_service, temp_project):
    """Scanner extracts npm packages from TypeScript / JavaScript files."""
    ts_file = os.path.join(temp_project, "App.tsx")
    with open(ts_file, "w", encoding="utf-8") as f:
        f.write("""
import React from 'react';
import { useState } from 'react';
import axios from 'axios';
import { LucideIcon } from 'lucide-react';
import './theme.css';
""")

    imports = env_service.scan_js_ts_imports(temp_project)
    assert "axios" in imports
    assert "lucide-react" in imports
    assert "react" not in imports  # Built-in excluded


def test_ensure_env_defaults(env_service, temp_project):
    """Generates baseline .env file when absent."""
    env_file = os.path.join(temp_project, ".env")
    assert not os.path.exists(env_file)

    env_service.ensure_env_defaults(temp_project)
    assert os.path.exists(env_file)
    with open(env_file, "r", encoding="utf-8") as f:
        content = f.read()
    assert "VITE_API_URL" in content


def test_parse_missing_package_from_error(env_service):
    """Parses various compiler/runtime error formats into ecosystem and package names."""
    py_err = "ModuleNotFoundError: No module named 'psycopg2'"
    parsed = env_service.parse_missing_package_from_error(py_err)
    assert parsed["missing"] is True
    assert parsed["ecosystem"] == "pip"
    assert parsed["package"] == "psycopg2-binary"

    node_err = 'Failed to resolve import "zustand" from "src/store/index.ts"'
    parsed_node = env_service.parse_missing_package_from_error(node_err)
    assert parsed_node["missing"] is True
    assert parsed_node["ecosystem"] == "npm"
    assert parsed_node["package"] == "zustand"
