PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

-- Dynamic MCP Tool Catalog & Drift Tracking
-- Located in knowledge.sqlite to avoid lock contention on operational.sqlite checkpoints.
CREATE TABLE IF NOT EXISTS mcp_tool_catalog (
    tool_key TEXT PRIMARY KEY,               -- 'mcp:filesystem:read_file'
    app_id TEXT NOT NULL,                    -- 'filesystem'
    tool_name TEXT NOT NULL,                 -- 'read_file'
    description TEXT,
    input_schema TEXT NOT NULL,              -- Sanitized JSON schema string
    spec_sha256 TEXT NOT NULL,               -- Combined hash of {"description": ..., "schema": ...}
    is_active INTEGER NOT NULL DEFAULT 1,    -- 1 if connected, 0 on disconnect
    total_calls INTEGER NOT NULL DEFAULT 0,  -- Reserved for future reranking
    success_rate REAL DEFAULT NULL,          -- Reserved for future reranking
    last_called_at TEXT DEFAULT NULL,        -- Reserved for future reranking
    last_discovered_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_mcp_tool_app ON mcp_tool_catalog(app_id);
CREATE INDEX IF NOT EXISTS idx_mcp_tool_active ON mcp_tool_catalog(is_active);
