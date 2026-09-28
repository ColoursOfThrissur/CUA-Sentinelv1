-- DimensionResolver cache: self-populating, self-correcting dimension reference table.
-- Lives in knowledge.sqlite — derived/cached knowledge, not execution state.

CREATE TABLE IF NOT EXISTS object_dimension_decisions (
    decision_key  TEXT PRIMARY KEY,       -- normalized "category|descriptor|dimension_name"
    category      TEXT NOT NULL,          -- e.g. "desk_lamp"
    descriptor    TEXT NOT NULL DEFAULT '',-- e.g. "modern", "" if none given
    dimension_name TEXT NOT NULL,         -- e.g. "height_cm"
    value         REAL NOT NULL,
    confidence    REAL NOT NULL,
    source        TEXT NOT NULL,          -- 'user_stated'|'prior_knowledge'|'web_verified'|'prior_knowledge_low_confidence'
    status        TEXT NOT NULL DEFAULT 'ACTIVE', -- 'ACTIVE'|'SUSPECT'|'SUPERSEDED'
    superseded_by TEXT,                   -- decision_key of replacement, if any
    times_used    INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    last_used_at  TEXT
);

CREATE INDEX IF NOT EXISTS idx_dim_decisions_category ON object_dimension_decisions(category);
CREATE INDEX IF NOT EXISTS idx_dim_decisions_status   ON object_dimension_decisions(status);
