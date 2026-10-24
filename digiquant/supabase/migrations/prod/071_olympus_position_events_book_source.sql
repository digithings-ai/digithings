-- 071_olympus_position_events_book_source.sql
-- Task 2.5 / #2422 — label compatibility projections so legacy reconstructed
-- position_events rows cannot be mistaken for authoritative ledger fills.
--
-- Additive only: one column + two curated views. Does not rewrite historical
-- row content; existing rows keep book_source = 'legacy' via DEFAULT.
-- Does not expose private portfolio_ledger_* tables.
--
-- Cutover/retirement: legacy prose writers may stay until holding_lots are
-- seeded and --no-ledger is removed from the morning job (#2508 follow-up).
-- Authoritative consumers should read olympus_position_events_authoritative
-- (or filter book_source = 'authoritative'). Existing Activity readers may keep
-- reading public.position_events unmodified.

ALTER TABLE public.position_events
    ADD COLUMN IF NOT EXISTS book_source text NOT NULL DEFAULT 'legacy';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_position_events_book_source'
    ) THEN
        ALTER TABLE public.position_events
            ADD CONSTRAINT chk_position_events_book_source
            CHECK (book_source IN ('legacy', 'authoritative'));
    END IF;
END $$;

COMMENT ON COLUMN public.position_events.book_source IS
  'Source quality for the compatibility projection (#2422 / Task 2.5). '
  '''legacy'' = prose/document reconstruction or pre-ledger history (permanent label). '
  '''authoritative'' = projected from the portfolio lineage ledger paper fill chain. '
  'Never silently promote legacy → authoritative; consumers that require lineage must '
  'filter or use olympus_position_events_authoritative.';

CREATE INDEX IF NOT EXISTS idx_position_events_book_source_date
    ON public.position_events (book_source, date DESC);

-- Compatibility mirror: same rows as the base table, with book_source explicit.
-- security_invoker = true so base-table RLS remains the gate (no definer bypass).
CREATE OR REPLACE VIEW public.olympus_position_events
WITH (security_invoker = true) AS
SELECT
    id,
    date,
    ticker,
    event,
    weight_pct,
    prev_weight_pct,
    cumulative_return_since_event_pct,
    price,
    thesis_id,
    reason,
    created_at,
    book_source
FROM public.position_events;

COMMENT ON VIEW public.olympus_position_events IS
  'Labeled compatibility projection of position_events (#2422). Includes legacy and '
  'authoritative rows with book_source. Existing Activity readers may keep using the '
  'base table; new consumers that need an explicit label should prefer this view.';

-- Authoritative-only: excludes legacy permanently. Ambiguous / unlabeled rows cannot
-- appear here because book_source is NOT NULL with a closed check.
CREATE OR REPLACE VIEW public.olympus_position_events_authoritative
WITH (security_invoker = true) AS
SELECT
    id,
    date,
    ticker,
    event,
    weight_pct,
    prev_weight_pct,
    cumulative_return_since_event_pct,
    price,
    thesis_id,
    reason,
    created_at,
    book_source
FROM public.position_events
WHERE book_source = 'authoritative';

COMMENT ON VIEW public.olympus_position_events_authoritative IS
  'Authoritative-only activity projection (#2422). Only book_source = ''authoritative'' '
  'rows (ledger paper-fill projections). Legacy reconstructed history never appears here. '
  'Does not SELECT from private portfolio_ledger_* tables.';

REVOKE ALL ON public.olympus_position_events FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.olympus_position_events_authoritative FROM PUBLIC, anon, authenticated;

-- Match base position_events read posture for cutover continuity; private ledger stays locked.
GRANT SELECT ON public.olympus_position_events TO anon, authenticated, service_role;
GRANT SELECT ON public.olympus_position_events_authoritative TO anon, authenticated, service_role;
