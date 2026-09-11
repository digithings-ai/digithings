-- 123_olympus_accounting_credible_tip_seam.sql
--
-- #3767 (CRITICAL): live portfolio NAV showed a false ~10% Sep-8 jump.
--
-- Root causes (verified live in core):
--   1. Tombstoned Sep 2-4 finals. Restated clean finals exist (recorded Sep 7),
--      but each is superseded by a Sep 8 zero-equity `incomplete` tombstone
--      (quality_reasons={superseded_by_restatement_3695}). The 074/084/085 tip
--      gate (`NOT EXISTS ... s.supersedes_id = p.id`) treats ANY superseder as
--      voiding, so public_finalized_nav returned only Sep 8 for the window.
--   2. public_accounting_nav_history stitches legacy + finalized with no seam
--      marker, so charts draw one continuous line across two series.
--
-- Fix (view/display only — no base-row rewrites, no new grants on
-- olympus_accounting_* tables):
--   * Credible-tip gate: a superseder voids a prior tip only when the
--     superseder is itself credible — NOT when it is an incomplete/failed
--     zero-equity tombstone (opening_equity = 0 AND closing_equity = 0)
--     and/or carries a superseded_by_restatement_* quality reason. Restated
--     clean finals therefore surface again; the tombstones stay stored
--     (append-only) but stop voiding them.
--   * series_seam marker on public_accounting_nav_history: additive boolean
--     column, true on the first row after a source flip (legacy -> finalized
--     or finalized -> legacy). Existing readers selecting explicit columns
--     keep working; chart/SSOT code must break the line at a seam instead of
--     drawing a continuous return across two series.
--
-- #3747 does NOT fix this (carries the restatement, no re-finalization or
-- seam labeling). Opening-equity chaining of Sep 8 (unchained opening) is
-- NOT fixed here: the engine (compute_period) is a pure function of caller
-- assembled inputs and no caller in this repo assembles PeriodAccountingInput
-- from a prior close, so chaining belongs to the finalize writer path —
-- see #3803 / #3804 overlap noted in the PR body. The seam marker + credible
-- gate remove the *silent false* display in the meantime.
--
-- Replay-safe: CREATE OR REPLACE VIEW only. Incorporates the 084 equity-delta
-- day_return formula and the 085 children-complete predicate verbatim.

-- 1) Period status tips — credible-tip gate + children complete (unchanged).
CREATE OR REPLACE VIEW public.public_accounting_period_status
WITH (security_invoker = false) AS
SELECT
    p.period_date AS date,
    p.status,
    p.quality_reasons,
    p.opening_equity,
    p.closing_equity,
    CASE
        WHEN p.opening_equity = 0 THEN NULL
        ELSE round(
            ((p.closing_equity - p.opening_equity) / p.opening_equity) * 100.0,
            6
        )
    END AS day_return_pct,
    p.benchmark_symbol,
    CASE
        WHEN p.benchmark_return IS NULL THEN NULL
        ELSE round(p.benchmark_return * 100.0, 6)
    END AS benchmark_return_pct,
    'accounting_period_status'::text AS contract
FROM public.olympus_accounting_periods p
WHERE NOT EXISTS (
    SELECT 1
    FROM public.olympus_accounting_periods s
    WHERE s.supersedes_id = p.id
      AND NOT (
          -- #3767: zero-equity incomplete/failed tombstones do not void a tip.
          (
              s.status IN ('incomplete', 'failed')
              AND s.opening_equity = 0
              AND s.closing_equity = 0
          )
          OR EXISTS (
              SELECT 1
              FROM unnest(s.quality_reasons) AS qr
              WHERE qr LIKE 'superseded_by_restatement%'
          )
      )
)
  AND (
      -- Idle / zero-activity periods may have empty children.
      NOT (
          (p.opening_equity - p.opening_cash) <> 0
          OR (p.closing_equity - p.closing_cash) <> 0
          OR p.net_pnl_total <> 0
          OR p.gross_pnl_total <> 0
      )
      OR EXISTS (
          SELECT 1
          FROM public.olympus_accounting_contributions c
          WHERE c.period_id = p.id
      )
  )
  AND NOT EXISTS (
      SELECT 1
      FROM public.olympus_accounting_contributions c
      WHERE c.period_id = p.id
        AND c.closing_quantity > 0
        AND NOT EXISTS (
            SELECT 1
            FROM public.olympus_accounting_holdings h
            WHERE h.period_id = p.id
              AND upper(h.symbol) = upper(c.symbol)
        )
  );

COMMENT ON VIEW public.public_accounting_period_status IS
  'Curated tip-period status (#2599; day_return #2779; children-complete #2780; '
  'credible-tip gate #3767). A superseder voids a tip only when credible — '
  'zero-equity incomplete/failed tombstones and superseded_by_restatement_* rows '
  'do not void restated finals. Incomplete child sets are withheld. '
  'Never substitutes lookback.';

-- 2) Finalized NAV — final + clean quality + credible tip + children complete.
CREATE OR REPLACE VIEW public.public_finalized_nav
WITH (security_invoker = false) AS
SELECT
    p.period_date AS date,
    p.closing_equity AS nav,
    CASE
        WHEN p.closing_equity = 0 THEN NULL
        ELSE round((p.closing_cash / p.closing_equity) * 100.0, 4)
    END AS cash_pct,
    CASE
        WHEN p.closing_equity = 0 THEN NULL
        ELSE round((1.0 - (p.closing_cash / p.closing_equity)) * 100.0, 4)
    END AS invested_pct,
    CASE
        WHEN p.opening_equity = 0 THEN NULL
        ELSE round(
            ((p.closing_equity - p.opening_equity) / p.opening_equity) * 100.0,
            6
        )
    END AS day_return_pct,
    'finalized_accounting'::text AS source,
    'finalized_accounting'::text AS contract
FROM public.olympus_accounting_periods p
WHERE p.status = 'final'
  AND cardinality(p.quality_reasons) = 0
  AND NOT EXISTS (
      SELECT 1
      FROM public.olympus_accounting_periods s
      WHERE s.supersedes_id = p.id
        AND NOT (
            -- #3767: zero-equity incomplete/failed tombstones do not void a tip.
            (
                s.status IN ('incomplete', 'failed')
                AND s.opening_equity = 0
                AND s.closing_equity = 0
            )
            OR EXISTS (
                SELECT 1
                FROM unnest(s.quality_reasons) AS qr
                WHERE qr LIKE 'superseded_by_restatement%'
            )
        )
  )
  AND (
      NOT (
          (p.opening_equity - p.opening_cash) <> 0
          OR (p.closing_equity - p.closing_cash) <> 0
          OR p.net_pnl_total <> 0
          OR p.gross_pnl_total <> 0
      )
      OR EXISTS (
          SELECT 1
          FROM public.olympus_accounting_contributions c
          WHERE c.period_id = p.id
      )
  )
  AND NOT EXISTS (
      SELECT 1
      FROM public.olympus_accounting_contributions c
      WHERE c.period_id = p.id
        AND c.closing_quantity > 0
        AND NOT EXISTS (
            SELECT 1
            FROM public.olympus_accounting_holdings h
            WHERE h.period_id = p.id
              AND upper(h.symbol) = upper(c.symbol)
        )
  );

COMMENT ON VIEW public.public_finalized_nav IS
  'Authoritative public NAV from finalized accounting tips with complete children '
  '(#2599 / #2780) under the credible-tip gate (#3767): restated clean finals '
  'surface even when a zero-equity tombstone names them via supersedes_id. '
  'day_return_pct is equity delta (#2779). Empty when no complete final tip — '
  'never invents values from lookback or provisional H9.';

-- 3) Reader series with explicit seam marker (#3767).
--    Same contract as before (finalized preferred, labeled legacy fallback, one
--    row per date) plus an additive `series_seam` boolean: true on the first row
--    after a source flip so charts break the line instead of drawing a phantom
--    return across two series. Existing readers selecting explicit columns are
--    unaffected; readers using SELECT * gain one trailing column.
CREATE OR REPLACE VIEW public.public_accounting_nav_history
WITH (security_invoker = false) AS
SELECT
    stitched.date,
    stitched.nav,
    stitched.cash_pct,
    stitched.invested_pct,
    stitched.day_return_pct,
    stitched.source,
    stitched.contract,
    (
        stitched.prev_source IS NOT NULL
        AND stitched.prev_source IS DISTINCT FROM stitched.source
    ) AS series_seam
FROM (
    SELECT
        u.date,
        u.nav,
        u.cash_pct,
        u.invested_pct,
        u.day_return_pct,
        u.source,
        u.contract,
        lag(u.source) OVER (ORDER BY u.date) AS prev_source
    FROM (
        SELECT
            f.date,
            f.nav,
            f.cash_pct,
            f.invested_pct,
            f.day_return_pct,
            f.source,
            f.contract
        FROM public.public_finalized_nav f
        UNION ALL
        SELECT
            legacy.date,
            legacy.nav,
            legacy.cash_pct,
            legacy.invested_pct,
            legacy.day_return_pct,
            'legacy_nav_history'::text AS source,
            'legacy_estimate'::text AS contract
        FROM (
            -- Lag over the full legacy series first so excluding finalized dates
            -- does not invent a cross-gap day return from non-adjacent rows.
            SELECT
                n.date,
                n.nav,
                n.cash_pct,
                n.invested_pct,
                round(
                    (n.nav / NULLIF(lag(n.nav) OVER (ORDER BY n.date), 0) - 1) * 100,
                    4
                ) AS day_return_pct
            FROM public.nav_history n
        ) legacy
        WHERE NOT EXISTS (
            SELECT 1
            FROM public.public_finalized_nav f
            WHERE f.date = legacy.date
        )
    ) u
) stitched;

COMMENT ON VIEW public.public_accounting_nav_history IS
  'Public NAV cutover surface (#2599; seam marker #3767): finalized accounting tips '
  'preferred; dates without a final tip use labeled legacy nav_history '
  '(source=legacy_nav_history, contract=legacy_estimate). series_seam is true on '
  'the first row after a source flip — charts must break the line there, never '
  'draw a continuous return across two series. Never combines sources for one date. '
  'Rollback: repoint readers to public_nav_history (050) without deleting '
  'accounting rows.';

-- 4) Public realized daily attribution (final credible tips with complete children).
CREATE OR REPLACE VIEW public.public_daily_realized_attribution
WITH (security_invoker = false) AS
SELECT
    c.period_date AS date,
    c.symbol AS ticker,
    CASE
        WHEN c.contribution IS NULL THEN NULL
        ELSE round(c.contribution * 100.0, 6)
    END AS contribution_pct,
    CASE
        WHEN p.benchmark_return IS NULL THEN NULL
        ELSE round(p.benchmark_return * 100.0, 6)
    END AS benchmark_return_pct,
    p.opening_equity,
    p.closing_equity,
    'daily_realized_attribution'::text AS contract,
    'final'::text AS period_status
FROM public.olympus_accounting_contributions c
JOIN public.olympus_accounting_periods p
  ON p.id = c.period_id
 AND p.period_date = c.period_date
WHERE p.status = 'final'
  AND cardinality(p.quality_reasons) = 0
  AND NOT EXISTS (
      SELECT 1
      FROM public.olympus_accounting_periods s
      WHERE s.supersedes_id = p.id
        AND NOT (
            -- #3767: zero-equity incomplete/failed tombstones do not void a tip.
            (
                s.status IN ('incomplete', 'failed')
                AND s.opening_equity = 0
                AND s.closing_equity = 0
            )
            OR EXISTS (
                SELECT 1
                FROM unnest(s.quality_reasons) AS qr
                WHERE qr LIKE 'superseded_by_restatement%'
            )
        )
  )
  AND (
      NOT (
          (p.opening_equity - p.opening_cash) <> 0
          OR (p.closing_equity - p.closing_cash) <> 0
          OR p.net_pnl_total <> 0
          OR p.gross_pnl_total <> 0
      )
      OR EXISTS (
          SELECT 1
          FROM public.olympus_accounting_contributions c2
          WHERE c2.period_id = p.id
      )
  )
  AND NOT EXISTS (
      SELECT 1
      FROM public.olympus_accounting_contributions c3
      WHERE c3.period_id = p.id
        AND c3.closing_quantity > 0
        AND NOT EXISTS (
            SELECT 1
            FROM public.olympus_accounting_holdings h
            WHERE h.period_id = p.id
              AND upper(h.symbol) = upper(c3.symbol)
        )
  );

COMMENT ON VIEW public.public_daily_realized_attribution IS
  'Public curated realized per-ticker daily contribution (#2599 / #2780) from '
  'finalized accounting tips with complete children (period_children_complete) '
  'under the credible-tip gate (#3767). Does not include current_book_lookback / '
  'position_attribution. Empty when no complete final tip — never mix lookback '
  'into this series.';

-- Grants: views only — never GRANT base olympus_accounting_* to anon/authenticated.
REVOKE ALL ON public.public_accounting_period_status FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.public_finalized_nav FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.public_accounting_nav_history FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.public_daily_realized_attribution FROM PUBLIC, anon, authenticated;

GRANT SELECT ON public.public_accounting_period_status TO anon, authenticated;
GRANT SELECT ON public.public_finalized_nav TO anon, authenticated;
GRANT SELECT ON public.public_accounting_nav_history TO anon, authenticated;
GRANT SELECT ON public.public_daily_realized_attribution TO anon, authenticated;

GRANT SELECT ON public.public_accounting_period_status TO service_role;
GRANT SELECT ON public.public_finalized_nav TO service_role;
GRANT SELECT ON public.public_accounting_nav_history TO service_role;
GRANT SELECT ON public.public_daily_realized_attribution TO service_role;
