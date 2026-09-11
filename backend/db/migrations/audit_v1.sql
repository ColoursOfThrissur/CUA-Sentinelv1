PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
INSERT OR IGNORE INTO schema_migrations (version) VALUES (1);

-- System lifecycle events (boot, crash, safe mode transitions)
CREATE TABLE IF NOT EXISTS system_events (
    event_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT UNIQUE NOT NULL,
    worker_id TEXT NOT NULL,
    boot_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK(event_type IN (
        'BOOT', 'SHUTDOWN_CLEAN', 'CRASH_DETECTED',
        'SAFE_MODE_ENTERED', 'SAFE_MODE_EXITED',
        'WATCHDOG_RESTART', 'EMERGENCY_STOP'
    )),
    component TEXT NOT NULL,
    description TEXT,
    run_id TEXT,
    task_id TEXT,
    operation_id TEXT,
    attempt_id TEXT,
    timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Run manifests - reproducibility record for every task execution
CREATE TABLE IF NOT EXISTS run_manifests (
    manifest_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT UNIQUE NOT NULL,
    task_id TEXT NOT NULL,
    config_version TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    model_versions TEXT NOT NULL CHECK(json_valid(model_versions)),
    tool_versions TEXT NOT NULL CHECK(json_valid(tool_versions)),
    environment_hash TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Append-only audit log - every governance decision recorded
CREATE TABLE IF NOT EXISTS audit_logs (
    log_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    log_id TEXT UNIQUE NOT NULL,
    run_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    step_id TEXT,
    operation_id TEXT,
    attempt_id TEXT,
    who_actor TEXT NOT NULL,
    action_type TEXT NOT NULL,
    tool_name TEXT,
    pre_state_hash TEXT,
    arguments_hash TEXT,
    result_hash TEXT,
    approval_id TEXT,
    decision_summary TEXT NOT NULL CHECK(json_valid(decision_summary)),
    decision_factors TEXT CHECK(decision_factors IS NULL OR json_valid(decision_factors)),
    policy_rule_ids TEXT CHECK(policy_rule_ids IS NULL OR json_valid(policy_rule_ids)),
    reconciliation_status TEXT NOT NULL DEFAULT 'VALIDATED' CHECK(reconciliation_status IN (
        'VALIDATED', 'PENDING', 'ORPHANED'
    )),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- HITL approval events - full lifecycle of every human approval
CREATE TABLE IF NOT EXISTS hitl_approval_events (
    event_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT UNIQUE NOT NULL,
    approval_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK(event_type IN (
        'REQUESTED', 'GRANTED', 'REJECTED', 'REVOKED', 'USED', 'EXPIRED'
    )),
    target_action_hash TEXT NOT NULL,
    tool_version TEXT NOT NULL,
    resource_version_hash TEXT NOT NULL,
    nonce TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    cryptographic_signature TEXT,
    actor TEXT,
    timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- High frequency telemetry events (GPU, VRAM, RAM, tokens)
CREATE TABLE IF NOT EXISTS telemetry_events (
    event_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT UNIQUE NOT NULL,
    worker_id TEXT NOT NULL,
    boot_id TEXT NOT NULL,
    run_id TEXT,
    task_id TEXT,
    event_type TEXT NOT NULL CHECK(event_type IN (
        'INFERENCE_BATCH', 'TOOL_EXECUTION', 'MODEL_LOAD',
        'MODEL_UNLOAD', 'HARDWARE_SAMPLE', 'TASK_COMPLETE'
    )),
    gpu_temp_c REAL,
    vram_used_mb INTEGER,
    ram_used_mb INTEGER,
    tokens_in INTEGER DEFAULT 0,
    tokens_out INTEGER DEFAULT 0,
    duration_ms INTEGER,
    model_id TEXT,
    tool_name TEXT,
    exit_code INTEGER,
    metadata TEXT CHECK(metadata IS NULL OR json_valid(metadata)),
    timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Aggregated telemetry - hourly and daily rollups to keep DB size manageable
CREATE TABLE IF NOT EXISTS telemetry_hourly (
    bucket_hour TEXT PRIMARY KEY,
    processed_until_sequence INTEGER NOT NULL,
    gpu_temp_avg REAL,
    gpu_temp_max REAL,
    vram_avg_mb INTEGER,
    vram_max_mb INTEGER,
    ram_avg_mb INTEGER,
    ram_max_mb INTEGER,
    tokens_in_total INTEGER DEFAULT 0,
    tokens_out_total INTEGER DEFAULT 0,
    inference_count INTEGER DEFAULT 0,
    tool_execution_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS telemetry_daily (
    bucket_date TEXT PRIMARY KEY,
    processed_until_sequence INTEGER NOT NULL,
    gpu_temp_avg REAL,
    gpu_temp_max REAL,
    vram_avg_mb INTEGER,
    vram_max_mb INTEGER,
    ram_avg_mb INTEGER,
    ram_max_mb INTEGER,
    tokens_in_total INTEGER DEFAULT 0,
    tokens_out_total INTEGER DEFAULT 0,
    inference_count INTEGER DEFAULT 0,
    tool_execution_count INTEGER DEFAULT 0
);

-- Append-only enforcement triggers
CREATE TRIGGER IF NOT EXISTS prevent_system_events_update
    BEFORE UPDATE ON system_events
    BEGIN SELECT RAISE(ABORT, 'system_events is append-only'); END;

CREATE TRIGGER IF NOT EXISTS prevent_system_events_delete
    BEFORE DELETE ON system_events
    BEGIN SELECT RAISE(ABORT, 'system_events is append-only'); END;

CREATE TRIGGER IF NOT EXISTS prevent_run_manifests_update
    BEFORE UPDATE ON run_manifests
    BEGIN SELECT RAISE(ABORT, 'run_manifests is append-only'); END;

CREATE TRIGGER IF NOT EXISTS prevent_run_manifests_delete
    BEFORE DELETE ON run_manifests
    BEGIN SELECT RAISE(ABORT, 'run_manifests is append-only'); END;

CREATE TRIGGER IF NOT EXISTS prevent_audit_logs_delete
    BEFORE DELETE ON audit_logs
    BEGIN SELECT RAISE(ABORT, 'audit_logs is append-only'); END;

CREATE TRIGGER IF NOT EXISTS prevent_audit_logs_update
    BEFORE UPDATE OF log_sequence, log_id, run_id, task_id, step_id, operation_id,
                     attempt_id, who_actor, action_type, tool_name, pre_state_hash,
                     arguments_hash, result_hash, approval_id, decision_summary,
                     decision_factors, policy_rule_ids, created_at
    ON audit_logs
    BEGIN SELECT RAISE(ABORT, 'audit_logs is append-only except reconciliation_status'); END;

CREATE TRIGGER IF NOT EXISTS prevent_hitl_events_update
    BEFORE UPDATE ON hitl_approval_events
    BEGIN SELECT RAISE(ABORT, 'hitl_approval_events is append-only'); END;

CREATE TRIGGER IF NOT EXISTS prevent_hitl_events_delete
    BEFORE DELETE ON hitl_approval_events
    BEGIN SELECT RAISE(ABORT, 'hitl_approval_events is append-only'); END;

CREATE TRIGGER IF NOT EXISTS prevent_telemetry_events_update
    BEFORE UPDATE ON telemetry_events
    BEGIN SELECT RAISE(ABORT, 'telemetry_events is append-only'); END;

CREATE TRIGGER IF NOT EXISTS prevent_telemetry_events_delete
    BEFORE DELETE ON telemetry_events
    BEGIN SELECT RAISE(ABORT, 'telemetry_events is append-only'); END;
