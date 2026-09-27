PRAGMA journal_mode = WAL;
PRAGMA synchronous = FULL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
INSERT OR IGNORE INTO schema_migrations (version) VALUES (1);

-- Worker nodes (Bazzite primary, Windows secondary)
CREATE TABLE IF NOT EXISTS worker_nodes (
    worker_id TEXT PRIMARY KEY,
    os_type TEXT NOT NULL CHECK(os_type IN ('windows', 'linux')),
    last_seen_boot_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('OFFLINE', 'BOOTING', 'ONLINE', 'UNHEALTHY')) DEFAULT 'OFFLINE',
    heartbeat_timeout_sec INTEGER NOT NULL DEFAULT 30 CHECK(heartbeat_timeout_sec >= 5),
    last_heartbeat TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Task queue - single source of truth for all work
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    parent_task_id TEXT,
    workflow_type TEXT NOT NULL CHECK(workflow_type IN (
        'RESEARCHER', 'SYNTHESIZER', 'ENDPOINT',
        'SCAFFOLDER', 'TESTER', 'REVIEWER',
        'REFACTOR', 'SECOND_BRAIN', 'SYNTHETIC_DATA'
    )),
    title TEXT NOT NULL,
    description TEXT,
    priority INTEGER NOT NULL DEFAULT 2 CHECK(priority BETWEEN 0 AND 2),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    deadline TEXT,
    requested_capabilities TEXT CHECK(requested_capabilities IS NULL OR json_valid(requested_capabilities)),
    granted_capabilities TEXT CHECK(granted_capabilities IS NULL OR json_valid(granted_capabilities)),
    status TEXT NOT NULL DEFAULT 'QUEUED' CHECK(status IN (
        'QUEUED', 'BLOCKED', 'RUNNING', 'PREEMPTED',
        'CANCEL_REQUESTED', 'CANCELLED', 'COMPLETED', 'FAILED', 'ARCHIVED'
    )),
    blocked_reason TEXT,
    cancel_requested_at TEXT,
    cancel_requested_by TEXT,
    context_budget INTEGER DEFAULT 8192 CHECK(context_budget BETWEEN 1 AND 16384),
    input_payload TEXT CHECK(input_payload IS NULL OR json_valid(input_payload)),
    result_payload TEXT CHECK(result_payload IS NULL OR json_valid(result_payload)),
    error_message TEXT,
    FOREIGN KEY(parent_task_id) REFERENCES tasks(task_id)
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_priority_created ON tasks(priority, created_at);

-- Task steps - hierarchical decomposition of a task
CREATE TABLE IF NOT EXISTS task_steps (
    step_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    step_order INTEGER NOT NULL CHECK(step_order >= 0),
    step_type TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN (
        'PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED', 'SKIPPED'
    )),
    input_context TEXT CHECK(input_context IS NULL OR json_valid(input_context)),
    output_summary TEXT CHECK(output_summary IS NULL OR json_valid(output_summary)),
    model_id TEXT,
    prompt_hash TEXT,
    config_version TEXT,
    gateway_version TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    started_at TEXT,
    finished_at TEXT,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE(task_id, step_order),
    UNIQUE(task_id, step_id),
    FOREIGN KEY(task_id) REFERENCES tasks(task_id)
);

-- Operations - individual tool calls within a step
CREATE TABLE IF NOT EXISTS operations (
    operation_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    target_resource_canonical TEXT NOT NULL,
    recovery_strategy TEXT NOT NULL CHECK(recovery_strategy IN (
        'QUERY_STATE', 'IDEMPOTENT_RETRY', 'COMPENSATE', 'HITL', 'NON_RETRYABLE'
    )),
    current_state TEXT NOT NULL DEFAULT 'PREPARED' CHECK(current_state IN (
        'PREPARED', 'EXECUTING', 'SUCCEEDED', 'FAILED', 'COMPENSATED'
    )),
    assigned_worker_id TEXT,
    assigned_boot_id TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY(task_id, step_id) REFERENCES task_steps(task_id, step_id)
);

-- Operation attempts - tracks retries with fingerprinting
CREATE TABLE IF NOT EXISTS operation_attempts (
    attempt_id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    attempt_no INTEGER NOT NULL,
    strategy_version TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'RUNNING' CHECK(state IN (
        'RUNNING', 'SUCCEEDED', 'FAILED', 'TIMEOUT'
    )),
    started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    finished_at TEXT,
    error_fingerprint TEXT,
    error_class TEXT CHECK(error_class IN (
        'SYNTAX', 'MISSING_DEPENDENCY', 'NETWORK', 'AUTH',
        'PERMISSION', 'DETERMINISTIC_LOOP', 'DESTRUCTIVE_RISK', NULL
    )),
    UNIQUE(operation_id, attempt_no),
    FOREIGN KEY(operation_id) REFERENCES operations(operation_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_one_running_attempt
    ON operation_attempts(operation_id) WHERE state = 'RUNNING';

-- Task leases - crash-safe ownership
CREATE TABLE IF NOT EXISTS task_leases (
    lease_id TEXT PRIMARY KEY,
    task_id TEXT UNIQUE NOT NULL,
    owner_worker_id TEXT NOT NULL,
    lease_generation INTEGER NOT NULL DEFAULT 1,
    granted_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    expires_at TEXT NOT NULL,
    heartbeat TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY(task_id) REFERENCES tasks(task_id),
    FOREIGN KEY(owner_worker_id) REFERENCES worker_nodes(worker_id)
);

-- Model registry - all Ollama models with tensor geometry for exact VRAM math
CREATE TABLE IF NOT EXISTS models_registry (
    model_id TEXT PRIMARY KEY,
    model_name TEXT NOT NULL,
    ollama_tag TEXT NOT NULL UNIQUE,
    version TEXT NOT NULL,
    quantization TEXT NOT NULL,
    context_limit_max INTEGER NOT NULL CHECK(context_limit_max > 0),
    vram_mb_estimate INTEGER NOT NULL CHECK(vram_mb_estimate > 0),
    ram_mb_estimate INTEGER NOT NULL CHECK(ram_mb_estimate > 0),
    num_layers INTEGER NOT NULL CHECK(num_layers > 0),
    num_kv_heads INTEGER NOT NULL CHECK(num_kv_heads > 0),
    head_dim INTEGER NOT NULL CHECK(head_dim > 0),
    capabilities TEXT NOT NULL CHECK(json_valid(capabilities)),
    current_state TEXT NOT NULL DEFAULT 'UNLOADED' CHECK(current_state IN (
        'UNLOADED', 'LOADING', 'READY', 'BUSY', 'IDLE',
        'EVICTING', 'FAILED', 'LOAD_TIMEOUT', 'UNHEALTHY', 'RECOVERING'
    )),
    busy_task_id TEXT,
    model_lease_generation INTEGER NOT NULL DEFAULT 0,
    last_loaded_at TEXT,
    last_health_check_at TEXT,
    last_failure_at TEXT,
    failure_count INTEGER NOT NULL DEFAULT 0,
    is_enabled INTEGER NOT NULL DEFAULT 1 CHECK(is_enabled IN (0, 1)),
    FOREIGN KEY(busy_task_id) REFERENCES tasks(task_id)
);

-- HITL pending approvals
CREATE TABLE IF NOT EXISTS hitl_pending (
    approval_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    risk_level INTEGER NOT NULL CHECK(risk_level BETWEEN 0 AND 3),
    action_description TEXT NOT NULL,
    action_payload TEXT NOT NULL CHECK(json_valid(action_payload)),
    action_hash TEXT NOT NULL,
    tool_version TEXT NOT NULL,
    resource_version_hash TEXT NOT NULL,
    nonce TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN (
        'PENDING', 'APPROVED', 'REJECTED', 'EXPIRED', 'USED'
    )),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    expires_at TEXT NOT NULL,
    resolved_at TEXT,
    resolved_by TEXT,
    FOREIGN KEY(task_id) REFERENCES tasks(task_id),
    FOREIGN KEY(operation_id) REFERENCES operations(operation_id)
);

-- Scheduled jobs - for synthesizer, refactor engine etc
CREATE TABLE IF NOT EXISTS scheduled_jobs (
    job_id TEXT PRIMARY KEY,
    workflow_type TEXT NOT NULL,
    cron_expression TEXT NOT NULL,
    is_enabled INTEGER NOT NULL DEFAULT 1 CHECK(is_enabled IN (0, 1)),
    last_run_at TEXT,
    next_run_at TEXT,
    last_status TEXT CHECK(last_status IN ('SUCCESS', 'FAILED', 'RUNNING', NULL)),
    input_payload TEXT CHECK(input_payload IS NULL OR json_valid(input_payload)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Safe mode state
CREATE TABLE IF NOT EXISTS system_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

INSERT OR IGNORE INTO system_state (key, value) VALUES ('safe_mode', 'false');
INSERT OR IGNORE INTO system_state (key, value) VALUES ('emergency_stop', 'false');
INSERT OR IGNORE INTO system_state (key, value) VALUES ('current_boot_id', '');
