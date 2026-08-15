-- 026_decision_log.sql — Closed-loop reflection log for Atlas Phase 9 (#432)
--
-- Records every per-ticker analyst decision the Atlas pipeline produces and
-- resolves them against actual price outcomes on the next-due run. The
-- resolved row carries an alpha-vs-benchmark figure plus a 2-4 sentence LLM
-- reflection that the next run's Portfolio Manager pulls into context via
-- ``PriorContext.decision_lessons``.
--
-- See ``apps/digiquant-atlas/src/digiquant_atlas/decision_log.py`` for the
-- write/resolve helpers and ``apps/digiquant-atlas/src/digiquant_atlas/phases/
-- phase9_evolution.py`` for the Phase A persistence step.
--
-- Idempotency: the unique key on ``(run_id, ticker)`` plus the resolver's
-- ``WHERE status='pending'`` guard means re-running Phase 9 against an
-- already-resolved decision is a no-op (matches AC #8 of the issue body).
--
-- Requires: pgcrypto (for gen_random_uuid()). Supabase ships this enabled.

BEGIN;

CREATE TABLE IF NOT EXISTS decision_log (
  id              uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id          uuid          NOT NULL,
  run_date        date          NOT NULL,
  ticker          text          NOT NULL,
  stance          text          NOT NULL,
  conviction      integer,
  thesis          text,                                          -- truncated to 800 chars at write time
  benchmark       text          NOT NULL DEFAULT 'SPY',
  holding_days    integer       NOT NULL DEFAULT 5,
  status          text          NOT NULL DEFAULT 'pending',     -- 'pending' | 'resolved'
  actual_return   numeric,                                       -- ticker total return over the window
  alpha           numeric,                                       -- actual_return - benchmark_return
  reflection      text,                                          -- LLM-generated 2-4 sentence lesson
  resolved_at     timestamptz,
  created_at      timestamptz   NOT NULL DEFAULT now(),

  CONSTRAINT decision_log_status_check CHECK (status IN ('pending', 'resolved')),
  -- One row per (run_id, ticker). Phase A relies on this for idempotent
  -- re-runs: a replay of the same Phase 9 invocation upserts the same row
  -- instead of creating a duplicate. The resolver's status guard then
  -- prevents Phase B from clobbering an already-resolved reflection.
  CONSTRAINT decision_log_run_ticker_unique UNIQUE (run_id, ticker)
);

-- (ticker, run_date desc) — supports "last 5 same-ticker lessons" lookup that
-- preflight uses to populate PriorContext.decision_lessons.
CREATE INDEX IF NOT EXISTS idx_decision_log_ticker_date
  ON decision_log (ticker, run_date DESC);

-- (status, run_date) — supports the resolver query that fans out over every
-- pending row whose holding window has elapsed.
CREATE INDEX IF NOT EXISTS idx_decision_log_status_date
  ON decision_log (status, run_date);

ALTER TABLE decision_log ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "decision_log_anon_select" ON decision_log;
CREATE POLICY "decision_log_anon_select"
  ON decision_log FOR SELECT
  TO anon USING (true);

COMMENT ON TABLE decision_log IS
  'Per-ticker analyst decisions persisted by Atlas Phase 9 (write_pending) and '
  'resolved by the Phase 0 reflection node on the next run after the holding '
  'window elapses. Resolved rows feed PriorContext.decision_lessons so the PM '
  'can reference past calls. See migration 026 + decision_log.py.';

COMMENT ON COLUMN decision_log.holding_days IS
  'Holding window in trading days. Default 5 (one week). Override via '
  'preferences["holding_days"] in AtlasConfigBundle.';

COMMENT ON COLUMN decision_log.alpha IS
  'Excess return over benchmark (default SPY) computed at resolution time. '
  'NULL while status=pending. NULL also when price_history rows are missing '
  'for either ticker or benchmark over the window (resolution skips those).';

COMMENT ON COLUMN decision_log.reflection IS
  'LLM-generated 2-4 sentence post-mortem from skills/decision-reflector. '
  'Phrased as actionable feedback the PM can apply to subsequent decisions.';

-- ── Rollback (commented; uncomment to drop) ─────────────────────────────────
-- DROP TABLE IF EXISTS decision_log;

COMMIT;
