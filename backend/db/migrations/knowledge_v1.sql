PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
INSERT OR IGNORE INTO schema_migrations (version) VALUES (1);

-- Canonical documents - SQLite is source of truth, ChromaDB is disposable index
CREATE TABLE IF NOT EXISTS canonical_documents (
    document_id TEXT PRIMARY KEY,
    source_uri TEXT NOT NULL,
    domain TEXT NOT NULL CHECK(domain IN ('UI_UX', 'AI', 'FINANCE', 'CODE', 'PERSONAL', 'OTHER')),
    authority_level TEXT NOT NULL CHECK(authority_level IN (
        'OFFICIAL_SPEC', 'OFFICIAL_DOCS', 'MAINTAINER_REPO',
        'PEER_REVIEWED', 'COMMUNITY', 'UNVERIFIED'
    )),
    title TEXT,
    raw_content TEXT NOT NULL,
    document_hash TEXT NOT NULL,
    embedding_config_hash TEXT NOT NULL,
    valid_from TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    valid_until TEXT,
    supersedes_document_id TEXT,
    index_status TEXT NOT NULL DEFAULT 'PENDING' CHECK(index_status IN (
        'PENDING', 'INDEXING', 'INDEXED', 'FAILED', 'SUPERSEDED'
    )),
    index_error TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    CHECK(valid_until IS NULL OR valid_until >= valid_from),
    FOREIGN KEY(supersedes_document_id) REFERENCES canonical_documents(document_id)
);

CREATE INDEX IF NOT EXISTS idx_docs_domain ON canonical_documents(domain);
CREATE INDEX IF NOT EXISTS idx_docs_status ON canonical_documents(index_status);

-- Active ChromaDB collection pointer - for disaster rebuild
CREATE TABLE IF NOT EXISTS active_index_pointer (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    collection_name TEXT NOT NULL,
    activated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

INSERT OR IGNORE INTO active_index_pointer (id, collection_name, activated_at)
    VALUES (1, 'sentinel_knowledge_v1', strftime('%Y-%m-%dT%H:%M:%SZ', 'now'));

-- Research claims - structured output from researcher agent
CREATE TABLE IF NOT EXISTS research_claims (
    claim_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    claim_text TEXT NOT NULL,
    source_document_id TEXT,
    source_uri TEXT,
    source_authority TEXT NOT NULL CHECK(source_authority IN (
        'OFFICIAL_SPEC', 'OFFICIAL_DOCS', 'MAINTAINER_REPO',
        'PEER_REVIEWED', 'COMMUNITY', 'UNVERIFIED'
    )),
    retrieval_timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    confidence_score REAL NOT NULL CHECK(confidence_score BETWEEN 0.0 AND 1.0),
    confidence_basis TEXT NOT NULL,
    evidence_count INTEGER NOT NULL DEFAULT 1,
    contradiction_status TEXT NOT NULL DEFAULT 'NONE' CHECK(contradiction_status IN (
        'NONE', 'CONFLICT_DETECTED', 'RESOLVED_BY_AUTHORITY', 'RESOLVED_BY_RECENCY', 'UNRESOLVED'
    )),
    contradicts_claim_id TEXT,
    domain TEXT NOT NULL,
    FOREIGN KEY(source_document_id) REFERENCES canonical_documents(document_id),
    FOREIGN KEY(contradicts_claim_id) REFERENCES research_claims(claim_id)
);

-- Episodic memory - compressed summaries agents pass between steps
CREATE TABLE IF NOT EXISTS episodic_memory (
    memory_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    step_id TEXT,
    agent_type TEXT NOT NULL,
    summary_json TEXT NOT NULL CHECK(json_valid(summary_json)),
    retention_tier TEXT NOT NULL DEFAULT 'HOT' CHECK(retention_tier IN ('HOT', 'WARM', 'COLD')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    expires_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_episodic_task ON episodic_memory(task_id);
CREATE INDEX IF NOT EXISTS idx_episodic_tier ON episodic_memory(retention_tier);

-- Durable artifacts - large outputs stay on disk, metadata stays in SQLite.
CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    step_id TEXT,
    artifact_type TEXT NOT NULL CHECK(artifact_type IN (
        'PLAN', 'REPO_MAP', 'MODULE_SUMMARY', 'OBSERVATION',
        'RAW_OUTPUT', 'TEST_RESULT', 'CODE_DIFF', 'CONTEXT_PACK', 'FINAL_REPORT'
    )),
    storage_path TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    size_bytes INTEGER NOT NULL CHECK(size_bytes >= 0),
    metadata_json TEXT NOT NULL CHECK(json_valid(metadata_json)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_artifacts_task ON artifacts(task_id, created_at);
CREATE INDEX IF NOT EXISTS idx_artifacts_step ON artifacts(step_id);

-- Hierarchical task graph projection for semantic planning.
CREATE TABLE IF NOT EXISTS task_graph_nodes (
    node_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    parent_node_id TEXT,
    node_type TEXT NOT NULL CHECK(node_type IN (
        'GOAL', 'DOMAIN', 'MODULE', 'FILE', 'TOOL', 'PAGE', 'STEP'
    )),
    title TEXT NOT NULL,
    objective TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN (
        'PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'BLOCKED', 'SKIPPED'
    )),
    context_requirements TEXT CHECK(context_requirements IS NULL OR json_valid(context_requirements)),
    verification_criteria TEXT CHECK(verification_criteria IS NULL OR json_valid(verification_criteria)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY(parent_node_id) REFERENCES task_graph_nodes(node_id)
);

CREATE INDEX IF NOT EXISTS idx_graph_task ON task_graph_nodes(task_id, parent_node_id);

-- Procedural memory - hardcoded rules and templates (never modified by agents)
CREATE TABLE IF NOT EXISTS procedural_memory (
    rule_id TEXT PRIMARY KEY,
    rule_type TEXT NOT NULL CHECK(rule_type IN (
        'FILE_STRUCTURE', 'CODING_STYLE', 'TOOL_CONSTRAINT',
        'AGENT_INSTRUCTION', 'SAFETY_RULE'
    )),
    rule_name TEXT NOT NULL UNIQUE,
    rule_content TEXT NOT NULL CHECK(json_valid(rule_content)),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Digest history - outputs from the synthesizer
CREATE TABLE IF NOT EXISTS digests (
    digest_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    domain TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    sources TEXT CHECK(sources IS NULL OR json_valid(sources)),
    generated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    is_read INTEGER NOT NULL DEFAULT 0 CHECK(is_read IN (0, 1))
);

-- User preferences - what Sentinel knows about you
CREATE TABLE IF NOT EXISTS user_preferences (
    pref_key TEXT PRIMARY KEY,
    pref_value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

INSERT OR IGNORE INTO user_preferences (pref_key, pref_value) VALUES
    ('monitored_topics', '["UI_UX", "AI", "FINANCE"]'),
    ('coding_style', '{"theme": "dark", "style": "glassmorphic", "framework": "React", "css": "Tailwind"}'),
    ('digest_schedule', '{"time": "07:00", "timezone": "Asia/Kolkata"}'),
    ('notification_enabled', 'true');
