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
    active_pid INTEGER,
    backend_port INTEGER,
    frontend_port INTEGER
);


CREATE INDEX IF NOT EXISTS idx_created_projects_status ON created_projects(status);

CREATE TABLE IF NOT EXISTS project_health_daemon_logs (
    log_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    project_name TEXT NOT NULL,
    target_path TEXT NOT NULL,
    pre_health INTEGER,
    post_health INTEGER,
    vulnerabilities_count INTEGER,
    test_status TEXT,
    action_taken TEXT NOT NULL,
    details_json TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_daemon_logs_project ON project_health_daemon_logs(project_id);
CREATE INDEX IF NOT EXISTS idx_daemon_logs_created ON project_health_daemon_logs(created_at DESC);

