-- 046_strategy_store.sql
--
-- Run with:  supabase db push   (or apply via MCP against this project).
--
-- DigiQuant strategy store (#1064). This project — historically the Olympus/Atlas
-- DB (config.toml project_id "digiquant-atlas") — is being repurposed as the unified
-- DigiQuant shared backend (Supabase display name "core"), beside the dedicated
-- "twelve-x" project. The shared market datasets (price_history / price_technicals /
-- trading_calendar / macro_series_observations) already live here, so #1064 reduces to
-- ADDING the strategy store. See docs/adr/0021-digiquant-supabase-project-topology.md.
--
-- ADDITIVE ONLY: this migration creates new tables whose only foreign keys point at
-- each other. It does NOT touch any existing table, policy, column, or row — no DROP,
-- no ALTER, no TRUNCATE. (#1065's cross-project price copy is obviated: prices already
-- live here.)
--
-- RLS: every new table RLS-enabled. The public reference + tearsheet tables grant anon
-- SELECT; server-side writers use the service role (which bypasses RLS). The private
-- strategy_calibrations sidecar gets NO anon policy — with RLS enabled and zero policies
-- anon reads return an empty result set (not a permission error) while the service role
-- keeps full access, mirroring the atlas_run_diagnostics idiom (migration 033). Idempotent.

create table if not exists public.strategies (
    id          text primary key,
    symbol      text not null,
    label       text,
    engine      text not null,
    config      jsonb not null default '{}'::jsonb,
    enabled     boolean not null default true,
    version     integer not null default 1,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

-- Private 1:1 sidecar for fitted calibration params (service-role-only; see RLS below).
create table if not exists public.strategy_calibrations (
    strategy_id text primary key references public.strategies (id) on delete cascade,
    calibration jsonb not null default '{}'::jsonb,
    as_of       timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

create table if not exists public.strategy_trades (
    id          bigint generated always as identity primary key,
    strategy_id text not null references public.strategies (id) on delete cascade,
    entry_ts    timestamptz,
    exit_ts     timestamptz,
    side        text,
    entry_price numeric,
    exit_price  numeric,
    qty         numeric,
    pnl         numeric,
    return_pct  numeric,
    created_at  timestamptz not null default now()
);
create index if not exists idx_strategy_trades_strategy_entry
    on public.strategy_trades (strategy_id, entry_ts desc);

-- Latest computed tearsheet payload per strategy (one row per strategy).
create table if not exists public.strategy_tearsheets (
    strategy_id  text primary key references public.strategies (id) on delete cascade,
    metrics      jsonb not null default '{}'::jsonb,
    equity_curve jsonb,
    as_of        timestamptz not null,
    updated_at   timestamptz not null default now()
);

-- Current signal/state per strategy (one row per strategy).
create table if not exists public.strategy_signals (
    strategy_id      text primary key references public.strategies (id) on delete cascade,
    position         text not null default 'flat' check (position in ('long', 'flat', 'short')),
    last_signal_date date,
    last_price       numeric,
    as_of            timestamptz not null,
    updated_at       timestamptz not null default now()
);

-- ── Row-level security ──────────────────────────────────────────────────────────

alter table public.strategies            enable row level security;
alter table public.strategy_calibrations enable row level security;
alter table public.strategy_trades       enable row level security;
alter table public.strategy_tearsheets   enable row level security;
alter table public.strategy_signals      enable row level security;

-- Public reference + tearsheet tables: anon may SELECT; service role writes (RLS bypass).
create policy strategies_anon_select on public.strategies
    for select to anon using (true);

create policy strategy_trades_anon_select on public.strategy_trades
    for select to anon using (true);

create policy strategy_tearsheets_anon_select on public.strategy_tearsheets
    for select to anon using (true);

create policy strategy_signals_anon_select on public.strategy_signals
    for select to anon using (true);

-- strategy_calibrations: PRIVATE. RLS enabled, NO anon policy → anon reads return an
-- empty result set; the service role keeps full access. Do not add an anon policy here.
