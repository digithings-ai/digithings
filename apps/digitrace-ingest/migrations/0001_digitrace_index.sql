-- digitrace index on Cloudflare D1 `digitrace` (DIG-2887 S1, replaces the
-- never-applied Supabase migration 144_digitrace_index.sql from DIG-2658).
--
-- Apply (human step, Chris's go):
--   wrangler d1 create digitrace                      # put the id in wrangler.toml
--   wrangler d1 migrations apply digitrace --remote   # from apps/digitrace-ingest
--
-- Same columns as the Postgres schema, in SQLite types:
--   uuid / text          -> TEXT
--   timestamptz          -> TEXT, ISO-8601 UTC from Date.toISOString(), so text
--                           order is time order
--   double / numeric     -> REAL
--   jsonb                -> TEXT holding JSON
-- `workspace_id` holds the verified tenant slug. D1 has no `workspaces` table,
-- and the receiver already decided the tenant from the ingest token, so the
-- slug is the tenancy key (same role as the Postgres workspace uuid). Every
-- reader must filter on it.
--
-- No RLS: D1 is reachable only through Worker bindings, so the tenant boundary
-- is the `workspace_id` filter in Worker code (ADR-0036 §5), as it already was
-- for the service-role PostgREST path.

CREATE TABLE IF NOT EXISTS digitrace_traces (
    workspace_id    TEXT NOT NULL,
    trace_id        TEXT NOT NULL,
    source          TEXT NOT NULL,
    name            TEXT,
    service_name    TEXT,
    started_at      TEXT NOT NULL,
    ended_at        TEXT,
    duration_ms     REAL,
    status          TEXT,
    status_message  TEXT,
    session_id      TEXT,
    run_id          TEXT,
    attributes      TEXT NOT NULL DEFAULT '{}',
    resource        TEXT NOT NULL DEFAULT '{}',
    span_count      INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (workspace_id, trace_id)
);

CREATE TABLE IF NOT EXISTS digitrace_spans_index (
    workspace_id    TEXT NOT NULL,
    trace_id        TEXT NOT NULL,
    span_id         TEXT NOT NULL,
    parent_span_id  TEXT,
    name            TEXT,
    kind            TEXT,
    started_at      TEXT NOT NULL,
    ended_at        TEXT,
    duration_ms     REAL,
    status          TEXT,
    status_message  TEXT,
    session_id      TEXT,
    run_id          TEXT,
    model           TEXT,
    provider        TEXT,
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    total_tokens    INTEGER,
    cost_usd        REAL,
    input_hash      TEXT,
    input_length    INTEGER,
    output_hash     TEXT,
    output_length   INTEGER,
    attributes      TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (workspace_id, trace_id, span_id)
);

-- Written by MLflow write-back / a later reader, not by this consumer.
CREATE TABLE IF NOT EXISTS digitrace_scores (
    workspace_id    TEXT NOT NULL,
    trace_id        TEXT NOT NULL,
    span_id         TEXT NOT NULL DEFAULT '',
    name            TEXT NOT NULL,
    value           REAL,
    value_text      TEXT,
    mlflow_run_id   TEXT,
    experiment_id   TEXT,
    source          TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (workspace_id, trace_id, span_id, name)
);

-- Materialised by a reader from digitrace_spans_index, not by this consumer.
CREATE TABLE IF NOT EXISTS digitrace_sessions (
    workspace_id      TEXT NOT NULL,
    session_id        TEXT NOT NULL,
    started_at        TEXT,
    last_activity_at  TEXT,
    ended_at          TEXT,
    trace_count       INTEGER NOT NULL DEFAULT 0,
    span_count        INTEGER NOT NULL DEFAULT 0,
    total_tokens      INTEGER NOT NULL DEFAULT 0,
    total_cost_usd    REAL NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (workspace_id, session_id)
);

CREATE INDEX IF NOT EXISTS digitrace_traces_workspace_started_at_idx
    ON digitrace_traces (workspace_id, started_at DESC);
CREATE INDEX IF NOT EXISTS digitrace_spans_index_workspace_started_at_idx
    ON digitrace_spans_index (workspace_id, started_at DESC);
CREATE INDEX IF NOT EXISTS digitrace_spans_index_workspace_session_idx
    ON digitrace_spans_index (workspace_id, session_id);
CREATE INDEX IF NOT EXISTS digitrace_scores_workspace_created_at_idx
    ON digitrace_scores (workspace_id, created_at);
CREATE INDEX IF NOT EXISTS digitrace_sessions_workspace_activity_idx
    ON digitrace_sessions (workspace_id, last_activity_at DESC);
