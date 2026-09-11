-- 125_drop_grounding_purposes.sql
--
-- Run with:  supabase db push   (or apply via MCP against the core project).
-- Unwrapped on purpose: db-migrate.yml applies the file + ledger in one
-- transaction. Do not write an unbackticked begin-statement in this file
-- (comments included) — that grep drops the wrapping transaction.
--
-- Tool-only grounding (#3859): the web_grounding / x_grounding synthesis
-- purposes are retired — grounding arrives via the first-party web_search
-- tool (purposes web_search / x_search). Drop the two retired values from
-- the olympus_provider_calls purpose CHECK. Migration 067 stays immutable;
-- this file rewrites the inline CHECK it created (Postgres auto-name
-- olympus_provider_calls_purpose_check) with the two values removed.
ALTER TABLE public.olympus_provider_calls
    DROP CONSTRAINT olympus_provider_calls_purpose_check;
ALTER TABLE public.olympus_provider_calls
    ADD CONSTRAINT olympus_provider_calls_purpose_check CHECK (
        purpose IN (
            'initial_generation',
            'chat_completion',
            'structured_completion',
            'structured_repair',
            'tool_selection',
            'tool_follow_up',
            'tool_loop',
            'web_search',
            'x_search',
            'embedding'
        )
    );
