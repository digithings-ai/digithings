-- 105_documents_workspace_id.sql
--
-- T4 review (privacy boundary): add workspace_id to `documents` and REPLACE the
-- legacy UNIQUE(date, document_key). Overlay + house same-key rows collide if the
-- legacy unique stays — this is the exception to T0's "keep legacy UNIQUE until
-- P6" pattern (T0 finding-1 lesson: every live writer that upserts on the old
-- arbiter must be updated in the same commit).
--
-- HUMAN GATE: tenancy / RLS. Authenticated own-workspace SELECT is added for
-- non-house/non-system rows. anon_read USING (true) is NOT touched (T1-train
-- rule). Production may set OLYMPUS_OVERLAY_PERSIST=1 only after that anon
-- drop ships; overlay private-phase writers refuse with persist_disabled until
-- then.
--
-- job_runs.status CHECK is extended with `persist_disabled`.
--
-- Documents writers updated in this same change (on_conflict + workspace stamp):
--   1. digiquant/src/digiquant/olympus/atlas/supabase_io.py::publish_document
--      (canonical; also publish_document_delta)
--   2. digiquant/src/digiquant/olympus/atlas/phases/publish_phase.py
--   3. digiquant/src/digiquant/olympus/hermes/writers/commit_io.py
--      (publish_hermes_documents, save_commit_manifest)
--   4. digiquant/src/digiquant/olympus/attention_plan_io.py
--   5. digiquant/src/digiquant/olympus/learning/beliefs_distillation.py
--   6. digiquant/scripts/atlas/publish_document.py
--   7. digiquant/scripts/atlas/publish_research.py
--   8. digiquant/scripts/atlas/materialize_snapshot.py (two upserts)
--   9. digiquant/scripts/atlas/backfill_normalize_schemas.py
--  10. digiquant/scripts/atlas/backfill_pm_rebalance_and_activity.py
--
-- House workspace id (096 seed): 6b753576-ced9-5319-9bfa-c5d0aacd9319
-- System workspace id (096 seed): 1105372f-4109-5815-be5a-21091ccfc8ad
--
-- MIGRATION NUMBER: next free after 104. Unwrapped; replay-safe.

-- --- job_runs persist_disabled ------------------------------------------------
ALTER TABLE public.job_runs DROP CONSTRAINT IF EXISTS job_runs_status_check;
ALTER TABLE public.job_runs ADD CONSTRAINT job_runs_status_check
    CHECK (status IN (
        'pending', 'running', 'succeeded', 'failed',
        'skipped', 'budget_exhausted', 'persist_disabled'
    ));

COMMENT ON COLUMN public.job_runs.status IS
    'pending|running|succeeded|failed|skipped|budget_exhausted|persist_disabled. '
    'persist_disabled is overlay private-phase refuse when OLYMPUS_OVERLAY_PERSIST is off.';

-- --- documents.workspace_id ---------------------------------------------------
ALTER TABLE public.documents ADD COLUMN IF NOT EXISTS workspace_id uuid;

UPDATE public.documents
    SET workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid
    WHERE workspace_id IS NULL;

ALTER TABLE public.documents ALTER COLUMN workspace_id SET NOT NULL;

ALTER TABLE public.documents DROP CONSTRAINT IF EXISTS documents_workspace_id_fkey;
ALTER TABLE public.documents
    ADD CONSTRAINT documents_workspace_id_fkey
    FOREIGN KEY (workspace_id) REFERENCES public.workspaces (id);

-- REPLACE legacy UNIQUE(date, document_key) — both historical names.
ALTER TABLE public.documents DROP CONSTRAINT IF EXISTS documents_date_document_key_key;
ALTER TABLE public.documents DROP CONSTRAINT IF EXISTS documents_new_date_document_key;
ALTER TABLE public.documents DROP CONSTRAINT IF EXISTS documents_workspace_date_document_key_key;
ALTER TABLE public.documents
    ADD CONSTRAINT documents_workspace_date_document_key_key
    UNIQUE (workspace_id, date, document_key);

CREATE INDEX IF NOT EXISTS idx_documents_workspace_date
    ON public.documents (workspace_id, date DESC);

-- Authenticated: house + system stay readable; other workspaces are own-member only.
-- Do NOT DROP or rewrite anon_read.
DROP POLICY IF EXISTS "authenticated_select_documents" ON public.documents;
CREATE POLICY "authenticated_select_documents" ON public.documents
    FOR SELECT TO authenticated
    USING (
        workspace_id = '6b753576-ced9-5319-9bfa-c5d0aacd9319'::uuid
        OR workspace_id = '1105372f-4109-5815-be5a-21091ccfc8ad'::uuid
        OR workspace_id IN (
            SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid()
        )
    );

GRANT SELECT ON TABLE public.documents TO authenticated;

COMMENT ON COLUMN public.documents.workspace_id IS
    'Owning workspace. House/system rows remain the shared research library; '
    'overlay private-phase rows require OLYMPUS_OVERLAY_PERSIST=1 after the '
    'T1-train anon-policy drop. UNIQUE is (workspace_id, date, document_key).';
