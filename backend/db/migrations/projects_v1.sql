PRAGMA journal_mode = WAL;
PRAGMA synchronous = FULL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS created_projects (
    project_id TEXT PRIMARY KEY,
    project_name TEXT NOT NULL,
    target_path TEXT NOT NULL UNIQUE,
    tech_stack TEXT NOT NULL,
    ui_style TEXT NOT NULL,
    blueprint_filename TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    health_score INTEGER NOT NULL DEFAULT 100 CHECK(health_score BETWEEN 0 AND 100),
    security_score INTEGER NOT NULL DEFAULT 100 CHECK(security_score BETWEEN 0 AND 100),
    status TEXT NOT NULL DEFAULT 'STOPPED' CHECK(status IN ('REGISTERED', 'RUNNING', 'STOPPED', 'ERROR')),
    active_port INTEGER,
    active_pid INTEGER
);

CREATE INDEX IF NOT EXISTS idx_created_projects_status ON created_projects(status);
