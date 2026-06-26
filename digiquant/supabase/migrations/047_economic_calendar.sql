-- 047_economic_calendar.sql
--
-- Run with:  supabase db push   (or apply via MCP against this project).
--
-- Shared economic calendar for the DigiQuant suite (#1066). The twelve-x FX research
-- project (separate Supabase project) owns the calendar ingest today, writing its own
-- `fx_economic_calendar`. The calendar is a repurposable dataset (relevant to any
-- DigiQuant project), so it belongs in the unified `core` shared data layer. This creates
-- the shared `economic_calendar` here; twelve-x's ingest is repointed to write it and the
-- twelve-x frontend is repointed to read it (sibling changes — see ADR 0021 + #1066).
--
-- Schema mirrors twelve-x `fx_economic_calendar` EXACTLY (migrations 001 + 002 there) so
-- the cutover is a table rename, not a reshape: same columns, the impact CHECK, the
-- UNIQUE(external_id) that `fx_events_snapshot.calendar_external_id` joins to app-side,
-- and the absolute-instant `event_datetime_utc` the frontend orders by.
--
-- ADDITIVE ONLY: one new table, no FKs to existing objects, no DROP/ALTER/TRUNCATE.
-- NOTE: this project carries a vestigial, unused `fx_economic_calendar` (migration 031,
-- 0 rows) — a different table; not touched here, flagged for a later drop.
--
-- RLS: enabled with anon SELECT (public, non-sensitive macro events); the ingest writes
-- via the service role (RLS bypass). Idempotent.

create table if not exists public.economic_calendar (
    id                 bigint generated always as identity primary key,
    event_date         date not null,
    event_time         text,
    country            text not null,
    event_name         text not null,
    category           text not null default 'other',
    impact             text not null default 'medium',
    actual             text,
    forecast           text,
    prior              text,
    source             text not null default 'trading_economics',
    external_id        text not null,
    scraped_at         timestamptz not null default now(),
    created_at         timestamptz not null default now(),
    updated_at         timestamptz not null default now(),
    event_datetime_utc timestamptz,
    constraint economic_calendar_external_id_key unique (external_id),
    constraint economic_calendar_impact_check check (impact in ('high', 'medium', 'low'))
);

create index if not exists idx_economic_calendar_event_date
    on public.economic_calendar (event_date);
create index if not exists idx_economic_calendar_country_date
    on public.economic_calendar (country, event_date);

alter table public.economic_calendar enable row level security;

-- drop-if-exists/create so the migration is safely re-runnable (CREATE POLICY has no
-- IF NOT EXISTS; the policy may already exist where the schema was applied before).
drop policy if exists economic_calendar_anon_select on public.economic_calendar;
create policy economic_calendar_anon_select on public.economic_calendar
    for select to anon using (true);
