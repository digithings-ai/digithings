-- Migration 089: research-state pin temporal CHECKs (#2867).
--
-- Mirrors ResearchStatePin model invariants from WP12.1 (#2858):
--   requested_as_of <= knowledge_cutoff_at <= pinned_at
-- (and pinned_at >= requested_as_of, which follows from the above).
--
-- Idempotent: DROP CONSTRAINT IF EXISTS before ADD.

ALTER TABLE public.olympus_research_state_pins
    DROP CONSTRAINT IF EXISTS chk_olympus_research_state_pins_temporal;

ALTER TABLE public.olympus_research_state_pins
    ADD CONSTRAINT chk_olympus_research_state_pins_temporal
    CHECK (
        requested_as_of <= knowledge_cutoff_at
        AND knowledge_cutoff_at <= pinned_at
    );

COMMENT ON CONSTRAINT chk_olympus_research_state_pins_temporal
    ON public.olympus_research_state_pins IS
    'Pin temporal order (#2867): requested_as_of <= knowledge_cutoff_at <= pinned_at.';
