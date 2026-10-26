-- 144_digitrace_index.sql
--
-- DIG-2658 "[tracing 4/9] Supabase core: digitrace schema (traces, spans_index,
-- scores, sessions) + tenant RLS + 90-day retention".
-- ADR-0036 (Cloudflare-native tracing with an MLflow backend store).
--
-- ============================================================================
-- What this file creates
-- ============================================================================
-- Four queryable index tables in the `public` schema of the Supabase `core`
-- project (the `digiquant` project), each prefixed `digitrace_`:
--
--   public.digitrace_traces       one row per trace
--   public.digitrace_spans_index  one row per span (index only - no bodies)
--   public.digitrace_scores       MLflow scores written back per trace/span
--   public.digitrace_sessions     one row per session, an aggregate over the spans
--
-- Plus the sessions rollup writer
-- `public.refresh_digitrace_session(uuid, text)`, the retention job
-- `public.prune_digitrace_index(integer, integer)` and its pg_cron schedule
-- (daily prune + daily plain VACUUM ANALYZE).
--
-- ============================================================================
-- ADR-0021 conformance (the M2 must-fix of DIG-2664)
-- ============================================================================
-- ADR-0021 is the house pattern: our own tables live in `public`, carry a
-- feature prefix, and carry per-table RLS. There is no `digitrace` schema for
-- our own tables - that deviation is rejected here, deliberately.
-- The one machine-owned exception in the whole design (the MLflow backend
-- store in a dedicated `mlflow` schema) is NOT in this file: it needs role
-- passwords, so it is a CHRIS STEP (see the checklist on DIG-2658), and this
-- file stays strictly `public`.
--
-- That exception is a TWO-role shape, per ADR-0036 section 4 as amended by
-- PR #6277 (the earlier "one role with USAGE and nothing else" text is
-- withdrawn): `digitrace_mlflow_owner` owns the `mlflow` schema and runs the
-- Alembic DDL; `digitrace_mlflow` is the runtime role with DML only, granted
-- through ALTER DEFAULT PRIVILEGES because the tables do not exist until the
-- upgrade creates them. `search_path=mlflow` is a ROLE default on both, not a
-- `?options=` startup parameter. Neither role is referenced here, and neither
-- touches `public`.
--
-- Additive only, like the house precedent (migration 046, the strategy store):
-- `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, `CREATE POLICY`,
-- `CREATE OR REPLACE FUNCTION`. No DROP TABLE, no ALTER TABLE, no TRUNCATE,
-- no column changes to anything that already exists. The only DROP here is
-- `DROP POLICY IF EXISTS` immediately before the matching `CREATE POLICY`,
-- which is the house replay-safe idiom from migration 098 (every policy in
-- that file is written that way, on purpose: it makes a re-apply a no-op
-- instead of an error).
--
-- ============================================================================
-- Tenancy and the tenant boundary (the M6 must-fix of DIG-2664)
-- ============================================================================
-- The tenancy column is `workspace_id uuid NOT NULL REFERENCES
-- public.workspaces(id)` - the house column, and the same one the ingest path
-- resolves server-side: the consumer maps the claimed tenant slug to a
-- `public.workspaces` row by slug and stamps that id. A slug is never stored
-- as the key, and it is NOT stored on the index row at all.
--
-- ADR-0036 section 5, read literally: `tenant_slug` and `tenant_slug_verified`
-- are EDGE VALUES AND "ARE NOT COLUMNS ON THE INDEX ROWS". The ingest Worker
-- decides the verdict and passes it on the payload; the consumer stamps both
-- into the archived batch object next to the raw spans, and the R2 key
-- `tenant=<slug>/...` carries the slug. The index has exactly one tenancy
-- column, `workspace_id`, and DIG-2661's tenant-filter test therefore has
-- exactly one target.
--
-- Why that is the right shape and not just the literal one: a column the
-- writer never populates reads `NULL` / `false` on every row, so it would
-- report "unverified" even for a claim that resolved - a wrong value wearing a
-- diagnostic's label. The evidence for a claim lives where the claim was made
-- (the archive), and the index stores only what it can keep true.
--
-- RLS IS NOT THE TENANT BOUNDARY on the paths that matter.
--   - `service_role` bypasses RLS entirely (it holds BYPASSRLS), and both the
--     digitrace consumer Worker and dashboard-api talk to Supabase with the
--     service-role key over PostgREST/REST. On those paths the tenant boundary
--     is the APPLICATION-LAYER TENANT FILTER, i.e. the `workspace_id = :resolved`
--     predicate the consumer Worker and dashboard-api put on every read and
--     write. DIG-2661 owns the test for that filter.
--   - The `authenticated` policies below are the defence for direct client
--     access (the dashboard's own session), where a row is visible only to a
--     member of its workspace via `public.workspace_members`.
--   - `anon` gets nothing. These are tenant rows.
--
-- ============================================================================
-- Retention: 90 days in the index, 180 days in the scores table
-- ============================================================================
-- R2 (`digitrace-archive`) is the system of record and keeps 180 days (R2
-- lifecycle). This Supabase index is NOT the record, it is the queryable
-- window: 90 days.
--   - Days 0-90:   indexed, dashboard-searchable.
--   - Days 91-180: the index row is gone, the R2 object is not. This is an
--                  intentional "cold, slow, rare" replay tier: `digitrace
--                  replay` enumerates R2 by prefix
--                  `tenant=<slug>/date=<YYYY-MM-DD>/` with no index to help
--                  it. It is still replayable; it is just not searchable from
--                  the dashboard.
--   - `digitrace_scores` keeps 180 days, so a replay of an old window has
--                  somewhere to write the scores it computes.
--
-- ============================================================================
-- No prompt or completion text (ADR-0036 section 7)
-- ============================================================================
-- A span carries a HASH and a LENGTH of its input/output, never the text.
-- `input_hash`, `input_length`, `output_hash`, `output_length` only. The
-- attribute keys that reach `attributes jsonb` come from an explicit
-- allowlist in the ingest Worker (DIG-2656), not from a blanket copy of the
-- OTLP payload.
--
-- ============================================================================
-- "Up to 5 connections" (the M3 must-fix of DIG-2664)
-- ============================================================================
-- This file does not open a connection. Nothing in the digitrace pipeline
-- opens a Postgres client connection at all: the consumer Worker reaches
-- Supabase over PostgREST/REST (the only precedented Worker-to-Supabase path
-- in this repository), so the connection pool is Supabase's own PostgREST
-- pool, server-side, and the Workers hold zero client connections.
-- The bound is therefore: no direct Postgres driver from any digitrace
-- Worker. If a driver is ever adopted it requires Hyperdrive as the pooler,
-- sized to 5 connections for the whole pipeline - a raw driver from an edge
-- Worker is out of scope, because Workers scale per isolate and the aggregate
-- is unbounded.
--
-- ============================================================================
-- Apply
-- ============================================================================
-- Target: the Supabase `core` project. Apply as the table owner.
-- Applying this file is a CHRIS STEP (production schema change) - see the
-- checklist on DIG-2658. There is no auto-apply workflow: `.github/workflows/
-- db-migrate.yml` was removed in #4919, so the apply is manual and followed by
-- the ledger insert into `public.digithings_schema_migrations`.
--
-- Like every migration in this directory, this file is UNWRAPPED (no
-- BEGIN/COMMIT): the apply pipeline runs it in a single transaction together
-- with the ledger insert. The VACUUM statement therefore cannot live here -
-- VACUUM is illegal inside a transaction block - it lives in the cron job,
-- exactly like migration 061 does it.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. The four index tables
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.digitrace_traces (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id          uuid NOT NULL REFERENCES public.workspaces(id),
    trace_id              text NOT NULL,
    source                text NOT NULL,
    name                  text,
    service_name          text,
    started_at            timestamptz NOT NULL,
    ended_at              timestamptz,
    duration_ms           double precision,
    status                text,
    status_message        text,
    session_id            text,
    run_id                text,
    attributes            jsonb NOT NULL DEFAULT '{}'::jsonb,
    resource              jsonb NOT NULL DEFAULT '{}'::jsonb,
    span_count            integer NOT NULL DEFAULT 0,
    created_at            timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT digitrace_traces_workspace_trace_key UNIQUE (workspace_id, trace_id)
);

CREATE TABLE IF NOT EXISTS public.digitrace_spans_index (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id          uuid NOT NULL REFERENCES public.workspaces(id),
    trace_id              text NOT NULL,
    span_id               text NOT NULL,
    parent_span_id        text,
    name                  text,
    kind                  text,
    started_at            timestamptz NOT NULL,
    ended_at              timestamptz,
    duration_ms           double precision,
    status                text,
    status_message        text,
    session_id            text,
    run_id                text,
    model                 text,
    provider              text,
    input_tokens          integer,
    output_tokens         integer,
    total_tokens          integer,
    cost_usd              numeric(18, 8),
    -- hash + length only, never the text (ADR-0036 section 7)
    input_hash            text,
    input_length          integer,
    output_hash           text,
    output_length         integer,
    attributes            jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at            timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT digitrace_spans_index_workspace_trace_span_key
        UNIQUE (workspace_id, trace_id, span_id)
);

CREATE TABLE IF NOT EXISTS public.digitrace_scores (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id   uuid NOT NULL REFERENCES public.workspaces(id),
    trace_id       text NOT NULL,
    -- '' means a trace-level score (not attached to a single span)
    span_id        text NOT NULL DEFAULT '',
    name           text NOT NULL,
    value          numeric,
    value_text     text,
    mlflow_run_id  text,
    experiment_id  text,
    source         text,
    created_at     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT digitrace_scores_workspace_trace_span_name_key
        UNIQUE (workspace_id, trace_id, span_id, name)
);

CREATE TABLE IF NOT EXISTS public.digitrace_sessions (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id          uuid NOT NULL REFERENCES public.workspaces(id),
    session_id            text NOT NULL,
    started_at            timestamptz,
    last_activity_at      timestamptz,
    ended_at              timestamptz,
    trace_count           integer NOT NULL DEFAULT 0,
    span_count            integer NOT NULL DEFAULT 0,
    total_tokens          integer NOT NULL DEFAULT 0,
    total_cost_usd        numeric(18, 8) NOT NULL DEFAULT 0,
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT digitrace_sessions_workspace_session_key UNIQUE (workspace_id, session_id)
);

-- ---------------------------------------------------------------------------
-- 2. Indexes for the query shapes the dashboard and the replay use
-- ---------------------------------------------------------------------------
-- Only shapes the UNIQUE constraints above cannot already serve. Any index on
-- (workspace_id, trace_id) would be dead weight: the spans and scores unique
-- keys already lead with those two columns, and a btree serves them as a
-- prefix scan.
--
-- The nightly prune is deliberately NOT indexed. Its predicate
-- (`started_at < cutoff`, `created_at < cutoff`) has no workspace_id, so none
-- of these workspace-leading indexes can serve it and each DELETE scans its
-- table. That is accepted rather than fixed: the same migration schedules a
-- nightly `VACUUM (ANALYZE)` over all four tables, which reads every page
-- anyway, so a dedicated (started_at) or (created_at) btree would add
-- write amplification on every span insert to save a second read of pages
-- already being read. If the volume ever makes one scan materially slower
-- than the vacuum beside it, add the bare-timestamp btree then - and price the
-- insert cost with it.

CREATE INDEX IF NOT EXISTS digitrace_traces_workspace_started_at_idx
    ON public.digitrace_traces (workspace_id, started_at DESC);

CREATE INDEX IF NOT EXISTS digitrace_spans_index_workspace_started_at_idx
    ON public.digitrace_spans_index (workspace_id, started_at DESC);

CREATE INDEX IF NOT EXISTS digitrace_spans_index_workspace_session_idx
    ON public.digitrace_spans_index (workspace_id, session_id);

CREATE INDEX IF NOT EXISTS digitrace_scores_workspace_created_at_idx
    ON public.digitrace_scores (workspace_id, created_at);

CREATE INDEX IF NOT EXISTS digitrace_sessions_workspace_activity_idx
    ON public.digitrace_sessions (workspace_id, last_activity_at DESC);

-- ---------------------------------------------------------------------------
-- 3. Grants and RLS
-- ---------------------------------------------------------------------------
-- service_role: read + write (it bypasses RLS - see the tenant-boundary note
--   in the header; the application-layer filter is the boundary on that path).
-- authenticated: SELECT only, own workspace only.
-- anon / PUBLIC: nothing. These are tenant rows.
--
-- Every privilege is revoked from PUBLIC, anon AND authenticated first, then
-- the two SELECT/DML grants are added back. Revoking authenticated explicitly
-- (rather than leaning on migration 060's default-ACL narrowing) is what makes
-- the claim in this file true on its own: a default ACL is a property of the
-- creating role and the schema, and a reader should not have to go and check
-- 060 to know that `authenticated` cannot write here.

ALTER TABLE public.digitrace_traces ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.digitrace_traces FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.digitrace_traces TO service_role;
GRANT SELECT ON public.digitrace_traces TO authenticated;
DROP POLICY IF EXISTS "authenticated_select_own_workspace" ON public.digitrace_traces;
CREATE POLICY "authenticated_select_own_workspace" ON public.digitrace_traces
    FOR SELECT TO authenticated
    USING (
        workspace_id IN (SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid())
    );

ALTER TABLE public.digitrace_spans_index ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.digitrace_spans_index FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.digitrace_spans_index TO service_role;
GRANT SELECT ON public.digitrace_spans_index TO authenticated;
DROP POLICY IF EXISTS "authenticated_select_own_workspace" ON public.digitrace_spans_index;
CREATE POLICY "authenticated_select_own_workspace" ON public.digitrace_spans_index
    FOR SELECT TO authenticated
    USING (
        workspace_id IN (SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid())
    );

ALTER TABLE public.digitrace_scores ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.digitrace_scores FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.digitrace_scores TO service_role;
GRANT SELECT ON public.digitrace_scores TO authenticated;
DROP POLICY IF EXISTS "authenticated_select_own_workspace" ON public.digitrace_scores;
CREATE POLICY "authenticated_select_own_workspace" ON public.digitrace_scores
    FOR SELECT TO authenticated
    USING (
        workspace_id IN (SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid())
    );

ALTER TABLE public.digitrace_sessions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.digitrace_sessions FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.digitrace_sessions TO service_role;
GRANT SELECT ON public.digitrace_sessions TO authenticated;
DROP POLICY IF EXISTS "authenticated_select_own_workspace" ON public.digitrace_sessions;
CREATE POLICY "authenticated_select_own_workspace" ON public.digitrace_sessions
    FOR SELECT TO authenticated
    USING (
        workspace_id IN (SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid())
    );

-- ---------------------------------------------------------------------------
-- 4. The sessions rollup writer
-- ---------------------------------------------------------------------------
-- `digitrace_sessions` is an aggregate row, and PostgREST cannot aggregate:
-- `resolution=merge-duplicates` REPLACES a row, so a second batch of the same
-- session would overwrite a larger count with a smaller one and the row would
-- silently shrink. ADR-0036 section 3 still names the consumer as this table's
-- writer, so the writer is a function, and this is it.
--
-- RECOMPUTE, not accumulate. The consumer's path is a Cloudflare Queue, which
-- is at-least-once: a redelivered batch runs this twice. Adding a batch's
-- deltas (`trace_count + excluded.trace_count`) would double-count on the
-- retry; recomputing from `digitrace_spans_index` twice lands on the same
-- numbers, so a redelivery is a no-op rather than an inflation. It is also why
-- the function needs no batch id, no dedupe table and no ordering assumption.
--
-- The cost is one aggregate over one session's spans per call, served by
-- `digitrace_spans_index_workspace_session_idx`. The consumer calls it once per
-- (workspace, session) after writing that batch's spans.
--
-- Two limits, stated rather than hidden:
--   - a trace with no spans is not counted in `trace_count` (the session id
--     lives on the spans, so there is nothing else to count them from);
--   - a session that spans the 90-day cutoff loses its older spans with the
--     index, so its totals shrink with them. The session row itself is pruned
--     on `last_activity_at` (section 5), so a live session is never cut.
--
-- SECURITY INVOKER on purpose: the only grantee is `service_role`, which
-- already holds INSERT/UPDATE on this table and SELECT on the spans, so
-- DEFINER rights would add an escalation surface and buy no capability. The
-- `search_path` is pinned anyway and every name is schema-qualified.
CREATE OR REPLACE FUNCTION public.refresh_digitrace_session(
    p_workspace_id uuid,
    p_session_id text
)
RETURNS void
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
DECLARE
    v_started timestamptz;
    v_last    timestamptz;
    v_ended   timestamptz;
    v_traces  integer;
    v_spans   integer;
    v_tokens  bigint;
    v_cost    numeric(18, 8);
BEGIN
    IF p_workspace_id IS NULL OR p_session_id IS NULL OR p_session_id = '' THEN
        RAISE EXCEPTION
            'refresh_digitrace_session: a workspace_id and a non-empty session_id are required';
    END IF;

    SELECT min(s.started_at),
           max(COALESCE(s.ended_at, s.started_at)),
           max(s.ended_at),
           count(DISTINCT s.trace_id)::integer,
           count(*)::integer,
           COALESCE(sum(s.total_tokens), 0),
           COALESCE(sum(s.cost_usd), 0)
      INTO v_started, v_last, v_ended, v_traces, v_spans, v_tokens, v_cost
      FROM public.digitrace_spans_index s
     WHERE s.workspace_id = p_workspace_id
       AND s.session_id = p_session_id;

    -- Nothing written for this session yet, or its spans are already pruned.
    -- Do not invent an empty rollup row for it.
    IF v_spans = 0 THEN
        RETURN;
    END IF;

    INSERT INTO public.digitrace_sessions
        (workspace_id, session_id, started_at, last_activity_at, ended_at,
         trace_count, span_count, total_tokens, total_cost_usd, updated_at)
    VALUES
        (p_workspace_id, p_session_id, v_started, v_last, v_ended,
         v_traces, v_spans, v_tokens, v_cost, now())
    ON CONFLICT (workspace_id, session_id) DO UPDATE
       SET started_at      = EXCLUDED.started_at,
           last_activity_at = EXCLUDED.last_activity_at,
           ended_at        = EXCLUDED.ended_at,
           trace_count     = EXCLUDED.trace_count,
           span_count      = EXCLUDED.span_count,
           total_tokens    = EXCLUDED.total_tokens,
           total_cost_usd  = EXCLUDED.total_cost_usd,
           updated_at      = EXCLUDED.updated_at;
END
$$;

REVOKE ALL ON FUNCTION public.refresh_digitrace_session(uuid, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.refresh_digitrace_session(uuid, text) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.refresh_digitrace_session(uuid, text) TO service_role;

COMMENT ON FUNCTION public.refresh_digitrace_session(uuid, text) IS
    'Recomputes one digitrace_sessions row from public.digitrace_spans_index: trace and '
    'span counts, token and cost totals, the activity window. Idempotent, so an '
    'at-least-once Queue redelivery refreshes rather than double-counts. Called by the '
    'ingest consumer (DIG-2657) over PostgREST rpc; service_role only.';

-- ---------------------------------------------------------------------------
-- 5. The retention job
-- ---------------------------------------------------------------------------
-- SECURITY DEFINER so the DELETEs are correct whatever role the cron job ends
-- up owned by (a wrong-role install would otherwise be a silent 0-row prune).
-- `search_path` is pinned empty and every name is schema-qualified. The
-- injection surface is two integers, both range-validated before use. EXECUTE
-- is revoked from PUBLIC, anon and authenticated below, so this is not
-- reachable as a PostgREST RPC with the bundled keys.
--
-- The owner assertion below mirrors migration 061: applying as a role that
-- does not own the tables would install a prune that deletes 0 rows, silently.

DO $mig$
DECLARE
    bad_owner text;
BEGIN
    SELECT string_agg(c.relname || ' (owner ' || pg_get_userbyid(c.relowner) || ')', ', ')
      INTO bad_owner
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public'
       AND c.relname IN ('digitrace_traces', 'digitrace_spans_index',
                         'digitrace_scores', 'digitrace_sessions')
       AND NOT pg_has_role(current_user, c.relowner, 'USAGE');

    IF bad_owner IS NOT NULL THEN
        RAISE EXCEPTION
            'migration 144: % is not an owner of %; the retention prune would delete 0 rows, '
            'silently. Apply as the table owner.',
            current_user, bad_owner;
    END IF;
END
$mig$;

CREATE OR REPLACE FUNCTION public.prune_digitrace_index(
    index_retain_days integer DEFAULT 90,
    scores_retain_days integer DEFAULT 180
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    index_cutoff    timestamptz;
    scores_cutoff   timestamptz;
    deleted_traces  bigint;
    deleted_spans   bigint;
    deleted_scores  bigint;
    deleted_sessions bigint;
BEGIN
    IF index_retain_days IS NULL OR index_retain_days < 1 THEN
        RAISE EXCEPTION
            'prune_digitrace_index: index_retain_days must be >= 1, got %', index_retain_days;
    END IF;
    IF scores_retain_days IS NULL OR scores_retain_days < 1 THEN
        RAISE EXCEPTION
            'prune_digitrace_index: scores_retain_days must be >= 1, got %', scores_retain_days;
    END IF;

    index_cutoff  := clock_timestamp() - make_interval(days => index_retain_days);
    scores_cutoff := clock_timestamp() - make_interval(days => scores_retain_days);

    DELETE FROM public.digitrace_spans_index WHERE started_at < index_cutoff;
    GET DIAGNOSTICS deleted_spans = ROW_COUNT;

    DELETE FROM public.digitrace_traces WHERE started_at < index_cutoff;
    GET DIAGNOSTICS deleted_traces = ROW_COUNT;

    -- a session is pruned on its last activity, so a session that is still in
    -- flight is never pruned under the consumer's feet
    DELETE FROM public.digitrace_sessions
     WHERE COALESCE(last_activity_at, started_at, created_at) < index_cutoff;
    GET DIAGNOSTICS deleted_sessions = ROW_COUNT;

    DELETE FROM public.digitrace_scores WHERE created_at < scores_cutoff;
    GET DIAGNOSTICS deleted_scores = ROW_COUNT;

    RAISE NOTICE
        'prune_digitrace_index: index_retain_days=% scores_retain_days=% deleted traces=% spans=% sessions=% scores=%',
        index_retain_days, scores_retain_days,
        deleted_traces, deleted_spans, deleted_sessions, deleted_scores;
END
$$;

REVOKE ALL ON FUNCTION public.prune_digitrace_index(integer, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.prune_digitrace_index(integer, integer) FROM anon, authenticated;

COMMENT ON FUNCTION public.prune_digitrace_index(integer, integer) IS
    'Retention for the digitrace index tables: index rows (traces, spans_index, sessions) older than '
    'index_retain_days (default 90) and scores older than scores_retain_days (default 180) are deleted. '
    'The R2 archive is the system of record and keeps 180 days; the Supabase index is the queryable '
    'window. Days 91-180 are replayable from R2 by prefix enumeration (cold, slow, rare tier).';

COMMENT ON TABLE public.digitrace_traces IS
    'One row per trace (ADR-0036). Index only - span bodies live in R2 digitrace-archive, never here. '
    'Retention 90 days by started_at, pg_cron job digitrace-index-prune (migration 144, DIG-2658). '
    'Tenant column workspace_id; RLS is the direct-client defence, the service-role boundary is the '
    'application-layer workspace_id filter.';

COMMENT ON TABLE public.digitrace_spans_index IS
    'One row per span, index only (ADR-0036 section 7). No prompt or completion text is stored: '
    'input_hash/input_length/output_hash/output_length only. Retention 90 days by started_at, '
    'pg_cron job digitrace-index-prune (migration 144, DIG-2658).';

COMMENT ON TABLE public.digitrace_scores IS
    'MLflow scores written back per trace or span (ADR-0036). span_id = '''' is a trace-level score. '
    'Retention 180 days by created_at, so a replay of a 91-180 day window still has somewhere to '
    'write its scores; pg_cron job digitrace-index-prune (migration 144, DIG-2658).';

COMMENT ON TABLE public.digitrace_sessions IS
    'One row per session (ADR-0036), an aggregate over public.digitrace_spans_index. Written only by '
    'public.refresh_digitrace_session(workspace_id, session_id); a PostgREST upsert would replace '
    'the counters instead of adding to them, so it is not the writer. Retention 90 days, pruned on '
    'last_activity_at so a session in flight is never pruned under the consumer; pg_cron job '
    'digitrace-index-prune (migration 144, DIG-2658).';

-- ---------------------------------------------------------------------------
-- 6. The schedule
-- ---------------------------------------------------------------------------
-- pg_cron absent would otherwise error and roll back the whole migration;
-- prod has pg_cron. Dynamic EXECUTE so the cron.schedule reference is never
-- planned when the extension is absent. cron.schedule upserts by
-- (username, jobname), so re-applying this migration re-points the existing
-- jobs instead of duplicating them.
--
-- Plain VACUUM (ANALYZE), never VACUUM FULL (ACCESS EXCLUSIVE lock). It lives
-- in the cron job, not in this file: VACUUM is illegal inside a transaction
-- block, and this file is applied inside one.

DO $mig$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
        RAISE NOTICE
            'migration 144: pg_cron absent, skipping schedule. The prune function is installed; '
            'schedule it manually once pg_cron is enabled.';
        RETURN;
    END IF;

    EXECUTE $q$
        SELECT cron.schedule(
            'digitrace-index-prune',
            '40 5 * * *',
            'SELECT public.prune_digitrace_index(90, 180);'
        )
    $q$;

    EXECUTE $q$
        SELECT cron.schedule(
            'digitrace-index-vacuum',
            '10 6 * * *',
            'VACUUM (ANALYZE) public.digitrace_traces, public.digitrace_spans_index, '
            'public.digitrace_scores, public.digitrace_sessions;'
        )
    $q$;
END
$mig$;
