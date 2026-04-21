-- 024_thesis_deliberation_first_class.sql — First-class tables for the
-- thesis-first pipeline (Atlas Wave 1, UNIT W1-B).
--
-- Context:
--   Track B doc_types (`market_thesis_exploration`, `thesis_vehicle_map`,
--   `deliberation_transcript`, `deliberation_session_index`, `pm_allocation_memo`,
--   `asset_recommendation`) have so far been persisted only as `documents` rows
--   with JSONB payloads. That keeps the publish path cheap but makes analytics,
--   dashboards, and historical thesis-tracking queries expensive.
--
--   This migration introduces dual persistence: a structured, indexable row per
--   high-query subset (vehicles per thesis, deliberation rounds, recess triggers)
--   while the full document bodies continue to land in `documents` for the
--   frontend and for blob retrieval. See docs/adr/0010-atlas-first-class-thesis-deliberation.md.
--
-- Scope of this migration:
--   • thesis_vehicles         — per-vehicle mapping of each thesis
--   • deliberation_sessions   — one row per (date, kind, pipeline_run_id)
--   • deliberation_rounds     — one row per ticker × round within a session
--   • analyst_coverage        — daily analyst↔ticker cross-reference
--   • deep_dive_triggers      — audit trail of recess-forced deep dives
--
-- RLS convention (matches migrations 005/007/015/023): per-table `anon` SELECT
-- policy; writes require the service_role key (bypass is grant-based, not a
-- policy, so we do not declare an explicit service_role policy).
--
-- Rollback: commented-out DROP block at the end of this file.

BEGIN;

-- ─── thesis_vehicles ────────────────────────────────────────────────────────
-- Captures the vehicles (ETFs, stocks, futures) attached to each thesis on
-- each day. FKs to the existing `theses` (date, thesis_id) unique key so that
-- backfilling or evolving thesis rows preserves referential integrity.

CREATE TABLE IF NOT EXISTS thesis_vehicles (
  date                     date        NOT NULL,
  thesis_id                text        NOT NULL,
  ticker                   text        NOT NULL,

  rationale                text,
  exclusion_reasons        jsonb,       -- array of {reason, source} entries
  candidate_rank           integer,     -- 1 = top pick; NULL = not ranked
  user_mandate_notes       jsonb,       -- mandate-derived constraints / notes
  source_exploration_key   text,        -- pointer into documents (market_thesis_exploration)

  created_at               timestamptz NOT NULL DEFAULT now(),

  PRIMARY KEY (date, thesis_id, ticker),
  FOREIGN KEY (date, thesis_id) REFERENCES theses (date, thesis_id)
    ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_thesis_vehicles_ticker_date
  ON thesis_vehicles (ticker, date DESC);

CREATE INDEX IF NOT EXISTS idx_thesis_vehicles_date
  ON thesis_vehicles (date DESC);

ALTER TABLE thesis_vehicles ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "thesis_vehicles_anon_select" ON thesis_vehicles;
CREATE POLICY "thesis_vehicles_anon_select"
  ON thesis_vehicles FOR SELECT
  TO anon USING (true);

COMMENT ON TABLE thesis_vehicles IS
  'Vehicles (tickers) linked to each active thesis per day. Populated from '
  'the thesis_vehicle_map document payload during the Hermes sub-graph. '
  'Writes via service_role; anon may SELECT.';

COMMENT ON COLUMN thesis_vehicles.source_exploration_key IS
  'documents.document_key pointer to the market_thesis_exploration row that '
  'produced this vehicle mapping.';

-- ─── deliberation_sessions ──────────────────────────────────────────────────
-- One row per deliberation session. `kind` partitions baseline (weekly),
-- delta_scoped (weekday) and monthly review sessions.

CREATE TABLE IF NOT EXISTS deliberation_sessions (
  session_id        uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  date              date        NOT NULL,
  kind              text        NOT NULL,
  all_converged     boolean,
  roster            jsonb,       -- {analysts: [...], pm: "..."} roster snapshot
  started_at        timestamptz,
  finished_at       timestamptz,
  pipeline_run_id   uuid,

  created_at        timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT chk_deliberation_sessions_kind CHECK (
    kind IN ('baseline', 'delta_scoped', 'monthly')
  ),
  CONSTRAINT uq_deliberation_sessions_date_kind_run
    UNIQUE (date, kind, pipeline_run_id)
);

CREATE INDEX IF NOT EXISTS idx_deliberation_sessions_date
  ON deliberation_sessions (date DESC);

ALTER TABLE deliberation_sessions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "deliberation_sessions_anon_select" ON deliberation_sessions;
CREATE POLICY "deliberation_sessions_anon_select"
  ON deliberation_sessions FOR SELECT
  TO anon USING (true);

COMMENT ON TABLE deliberation_sessions IS
  'One row per Hermes deliberation session (baseline, delta_scoped, or monthly). '
  'Indexed subset of the deliberation_session_index document.';

-- ─── deliberation_rounds ────────────────────────────────────────────────────
-- Round-loop persistence. Each ticker within a session can loop up to
-- ATLAS_DELIBERATION_MAX_ROUNDS rounds. Sections blob holds the analyst/PM
-- section pair for that round.

CREATE TABLE IF NOT EXISTS deliberation_rounds (
  id                         bigserial   PRIMARY KEY,
  session_id                 uuid        NOT NULL
    REFERENCES deliberation_sessions (session_id) ON DELETE CASCADE,
  ticker                     text        NOT NULL,
  round_number               integer     NOT NULL,
  label                      text,
  sections                   jsonb       NOT NULL,
  converged                  boolean     NOT NULL DEFAULT false,
  recess_triggered           boolean     NOT NULL DEFAULT false,
  deep_dive_document_key     text,
  created_at                 timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT uq_deliberation_rounds UNIQUE (session_id, ticker, round_number),
  CONSTRAINT chk_deliberation_rounds_round_number CHECK (round_number >= 1)
);

CREATE INDEX IF NOT EXISTS idx_deliberation_rounds_ticker_session
  ON deliberation_rounds (ticker, session_id);

CREATE INDEX IF NOT EXISTS idx_deliberation_rounds_session
  ON deliberation_rounds (session_id, round_number);

ALTER TABLE deliberation_rounds ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "deliberation_rounds_anon_select" ON deliberation_rounds;
CREATE POLICY "deliberation_rounds_anon_select"
  ON deliberation_rounds FOR SELECT
  TO anon USING (true);

COMMENT ON TABLE deliberation_rounds IS
  'One row per (session, ticker, round). Mirrors the deliberation_transcript '
  'document at round granularity for dashboards and convergence analytics.';

COMMENT ON COLUMN deliberation_rounds.deep_dive_document_key IS
  'When recess_triggered=true and a deep-dive document has been published, '
  'documents.document_key pointer to that row.';

-- ─── analyst_coverage ───────────────────────────────────────────────────────
-- Small denormalized row for "which analyst covers AAPL today" frontend query.

CREATE TABLE IF NOT EXISTS analyst_coverage (
  date                         date        NOT NULL,
  ticker                       text        NOT NULL,
  thesis_ids                   jsonb,       -- array of linked thesis_ids
  analyst_role                 text,
  current_recommendation_key   text,        -- documents.document_key pointer
  last_updated                 timestamptz NOT NULL DEFAULT now(),

  PRIMARY KEY (date, ticker)
);

CREATE INDEX IF NOT EXISTS idx_analyst_coverage_ticker_date
  ON analyst_coverage (ticker, date DESC);

ALTER TABLE analyst_coverage ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "analyst_coverage_anon_select" ON analyst_coverage;
CREATE POLICY "analyst_coverage_anon_select"
  ON analyst_coverage FOR SELECT
  TO anon USING (true);

COMMENT ON TABLE analyst_coverage IS
  'Daily denormalized analyst↔ticker index. Supports frontend "coverage by '
  'analyst" queries without scanning every documents payload.';

-- ─── deep_dive_triggers ─────────────────────────────────────────────────────
-- Audit log for every time a deliberation round (or a manual operator action
-- or a delta-watch rule) forced a deep-dive to be generated.

CREATE TABLE IF NOT EXISTS deep_dive_triggers (
  id                       bigserial   PRIMARY KEY,
  session_id               uuid
    REFERENCES deliberation_sessions (session_id) ON DELETE SET NULL,
  ticker                   text        NOT NULL,
  triggered_by             text        NOT NULL,
  trigger_reason           text,
  deep_dive_document_key   text,
  created_at               timestamptz NOT NULL DEFAULT now(),
  resolved_at              timestamptz,

  CONSTRAINT chk_deep_dive_triggers_source CHECK (
    triggered_by IN ('pm_recess', 'delta_watch', 'manual')
  )
);

CREATE INDEX IF NOT EXISTS idx_deep_dive_triggers_ticker
  ON deep_dive_triggers (ticker, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_deep_dive_triggers_session
  ON deep_dive_triggers (session_id);

ALTER TABLE deep_dive_triggers ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "deep_dive_triggers_anon_select" ON deep_dive_triggers;
CREATE POLICY "deep_dive_triggers_anon_select"
  ON deep_dive_triggers FOR SELECT
  TO anon USING (true);

COMMENT ON TABLE deep_dive_triggers IS
  'Audit trail: every time deliberation, delta-watch, or a human operator '
  'forced a deep-dive to be generated. resolved_at stamped when the deep-dive '
  'document lands.';

COMMIT;

-- ─── Rollback (commented) ───────────────────────────────────────────────────
-- Run in reverse dependency order. DROP POLICY first so the DROP TABLE path
-- is clean even on older PostgREST revisions that error on policy leftovers.
--
-- BEGIN;
-- DROP POLICY IF EXISTS "deep_dive_triggers_anon_select"     ON deep_dive_triggers;
-- DROP POLICY IF EXISTS "analyst_coverage_anon_select"       ON analyst_coverage;
-- DROP POLICY IF EXISTS "deliberation_rounds_anon_select"    ON deliberation_rounds;
-- DROP POLICY IF EXISTS "deliberation_sessions_anon_select"  ON deliberation_sessions;
-- DROP POLICY IF EXISTS "thesis_vehicles_anon_select"        ON thesis_vehicles;
--
-- DROP TABLE IF EXISTS deep_dive_triggers;
-- DROP TABLE IF EXISTS deliberation_rounds;
-- DROP TABLE IF EXISTS deliberation_sessions;
-- DROP TABLE IF EXISTS analyst_coverage;
-- DROP TABLE IF EXISTS thesis_vehicles;
-- COMMIT;
