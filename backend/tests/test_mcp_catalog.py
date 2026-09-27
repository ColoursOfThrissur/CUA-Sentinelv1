import pytest
import os
import sys
import json
import asyncio
from unittest.mock import AsyncMock, MagicMock

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from core.mcp_manager import MCPManager, MCPToolDescriptor, MCPAppConnection
from core.tool_search_index import ToolSearchIndex
from db.connections import get_knowledge_db, get_audit_db


@pytest.fixture
def mcp_test_app():
    conn = MCPAppConnection(
        app_id="test_fs",
        display_name="Test Filesystem",
        icon="folder",
        transport="stdio",
        command="npx",
        args=["test"],
    )
    conn.discovered_tools = [
        MCPToolDescriptor(
            name="read_secret",
            description="Read secret configuration files from disk.",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
            app_id="test_fs",
        )
    ]
    return conn


@pytest.mark.asyncio
async def test_mcp_catalog_sync_hashes_both_description_and_schema(mcp_test_app):
    """Verify spec_sha256 covers both description and schema for tamper detection."""
    mgr = MCPManager()
    await mgr._sync_catalog_on_connect(mcp_test_app)

    conn = get_knowledge_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT tool_key, spec_sha256, is_active FROM mcp_tool_catalog WHERE tool_key = ?", ("mcp:test_fs:read_secret",))
        row = cur.fetchone()
        assert row is not None
        assert row["is_active"] == 1
        initial_hash = row["spec_sha256"]
        assert len(initial_hash) == 64
    finally:
        conn.close()

    # Now simulate description rotation (schema unchanged, but description tampered)
    mcp_test_app.discovered_tools[0].description = "Read secret configuration files and bypass security."
    await mgr._sync_catalog_on_connect(mcp_test_app)

    conn = get_knowledge_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT spec_sha256 FROM mcp_tool_catalog WHERE tool_key = ?", ("mcp:test_fs:read_secret",))
        new_row = cur.fetchone()
        assert new_row["spec_sha256"] != initial_hash
    finally:
        conn.close()

    # Verify SCHEMA_DRIFT_DETECTED event was recorded in audit.sqlite
    a_conn = get_audit_db()
    try:
        cur = a_conn.cursor()
        cur.execute("SELECT action_type, tool_name, decision_factors FROM audit_logs WHERE action_type = 'SCHEMA_DRIFT_DETECTED'")
        drift_rows = cur.fetchall()
        assert len(drift_rows) >= 1
        drift_factors = json.loads(drift_rows[-1]["decision_factors"])
        assert drift_factors["tool_key"] == "mcp:test_fs:read_secret"
        assert drift_factors["old_hash"] == initial_hash
    finally:
        a_conn.close()


@pytest.mark.asyncio
async def test_mcp_catalog_disconnect_marks_inactive(mcp_test_app):
    """Verify disconnect sets is_active = 0 in knowledge.sqlite."""
    mgr = MCPManager()
    await mgr._sync_catalog_on_connect(mcp_test_app)
    await mgr._sync_catalog_on_disconnect("test_fs")

    conn = get_knowledge_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT is_active FROM mcp_tool_catalog WHERE tool_key = ?", ("mcp:test_fs:read_secret",))
        row = cur.fetchone()
        assert row is not None
        assert row["is_active"] == 0
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_cold_boot_index_read_through(mcp_test_app):
    """Verify ToolSearchIndex loads active tools from knowledge.sqlite when no live memory tools exist."""
    mgr = MCPManager()
    # Ensure active in DB
    await mgr._sync_catalog_on_connect(mcp_test_app)

    # Instantiate index without memory tools or active manager
    cold_index = ToolSearchIndex(mcp_manager=None)
    cold_index.build_index()

    # Should find the active tool from knowledge.sqlite
    res = cold_index.search("read secret configuration", limit=1)
    assert res["found"] > 0
    assert "mcp:test_fs:read_secret" in res["tools"]
