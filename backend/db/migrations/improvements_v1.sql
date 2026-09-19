PRAGMA journal_mode = WAL;
PRAGMA synchronous = FULL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS improvement_proposals (
    proposal_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    project_name TEXT NOT NULL,
    title TEXT NOT NULL,
    rationale TEXT NOT NULL,
    affected_files TEXT NOT NULL,
    suggested_changes TEXT,
    risk_level TEXT NOT NULL CHECK(risk_level IN ('LOW', 'MEDIUM', 'HIGH')),
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING', 'APPROVED', 'REJECTED', 'APPLIED')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    reviewed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_proposals_status ON improvement_proposals(status);
CREATE INDEX IF NOT EXISTS idx_proposals_project ON improvement_proposals(project_id);
