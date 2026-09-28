-- LLM call traces for debugging - NOT append-only, pruned to keep only recent N tasks
-- Stored in operational.sqlite since it's mutable debug data, not audit trail

CREATE TABLE IF NOT EXISTS llm_traces (
    trace_id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    step_id TEXT,
    model_id TEXT NOT NULL,
    system_prompt TEXT,
    user_prompt TEXT NOT NULL,
    response TEXT,
    tokens_in_est INTEGER,
    tokens_out_est INTEGER,
    temperature REAL,
    context_budget INTEGER,
    duration_ms INTEGER,
    error TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_llm_traces_task ON llm_traces(task_id);
CREATE INDEX IF NOT EXISTS idx_llm_traces_created ON llm_traces(created_at DESC);
