/**
 * TypeScript row types for the twelve-x FX research tables that Olympus reads.
 *
 * These MUST match the shared data contract (twelve-x migration 005) exactly —
 * Olympus only reads these tables, twelve-x owns the writes.
 */

/** Canonical G10 currency universe (display + ordering for consensus views). */
export const G10_CURRENCIES = [
  'USD',
  'EUR',
  'JPY',
  'GBP',
  'CHF',
  'CAD',
  'AUD',
  'NZD',
  'SEK',
  'NOK',
] as const;

export type G10Currency = (typeof G10_CURRENCIES)[number];

/**
 * The Research Matrix columns — the 8 board currencies, in the SAME order the
 * twelve-x Notion matrix uses (`nodes/publish.py` `_board_column`). A broker
 * currency_view is filed under its base currency only (pairs land under the
 * numerator, e.g. EUR/USD → EUR); views whose legs fall outside the extended
 * set (these 8 + NOK/SEK) are dropped. Kept deliberately separate from the
 * 10-entry `G10_CURRENCIES` (which the consensus uses) so the grid matches Notion.
 */
export const MATRIX_COLUMNS = ['USD', 'EUR', 'GBP', 'AUD', 'CAD', 'CHF', 'JPY', 'NZD'] as const;
export type MatrixColumn = (typeof MATRIX_COLUMNS)[number];

/** Consensus horizon bucket — the medium- vs long-term view of a currency. */
export type Timeframe = 'medium' | 'long';

/**
 * `fx_consensus_snapshot` — one row per G10 currency per run_date, for the
 * weighted (relevance-weighted live) view AND the unweighted (frozen) view.
 * PRIMARY KEY (run_date, currency, timeframe, weighted) — MULTIPLE rows per
 * currency per run (one per timeframe); callers MUST pin a timeframe.
 */
export interface FxConsensusSnapshotRow {
  run_date: string; // date (ISO YYYY-MM-DD)
  currency: string;
  timeframe: Timeframe;
  horizon_weeks: number | null;
  weighted: boolean;
  score: number; // float8, expected range [-2, +2]
  confidence: number; // float8
  agreement: number; // float8
  tilt: number; // float8
  n_eff: number; // float8 (effective sample size)
  n_brokers: number; // int
  n_views: number; // int
  bullish_pct: number; // float8
  bearish_pct: number; // float8
  neutral_pct: number; // float8
  watch_pct: number; // float8
  as_of: string; // timestamptz (ISO)
}

/**
 * `fx_confluence_snapshot` — top trade ideas per run_date, ranked.
 * PRIMARY KEY (run_date, rank).
 */
export interface FxConfluenceSnapshotRow {
  run_date: string; // date (ISO YYYY-MM-DD)
  rank: number; // int (1 = strongest)
  title: string;
  currency: string;
  direction: string; // e.g. "bullish" | "bearish" | "neutral" | "watch"
  score: number; // float8
  components: unknown; // jsonb — structured supporting components
  brief_keys: unknown; // jsonb — array of source brief identifiers
  as_of: string; // timestamptz (ISO)
}

/**
 * `fx_daily_digest` — the per-run FX digest (existing table, read as-is).
 * `key_themes` may arrive as a jsonb array or a Postgres text[]; treat as
 * `string[]` after normalization (see `fetch.ts`).
 */
export interface FxDailyDigestRow {
  run_date: string; // date (ISO YYYY-MM-DD)
  summary: string;
  key_themes: string[] | string | null; // jsonb / text[]
  doc_count: number;
  broker_count: number;
}

/**
 * One broker citation inside an `fx_events_snapshot` row's `citations` jsonb array.
 * Mirrors twelve-x `BrokerEventCitation` as projected into the snapshot.
 */
export interface FxEventCitation {
  broker: string;
  expected_outcome: string;
  fx_impact: string;
  source_file: string;
  brief_key: string;
}

/**
 * `fx_events_snapshot` (twelve-x migration 006) — one row per aggregated risk
 * event per run_date, sourced from `aggregate_risk_events(...)`. The aggregated
 * broker opinions/expectations per catalyst (P2 Events tab).
 * PRIMARY KEY (run_date, event_key).
 */
export interface FxEventSnapshotRow {
  run_date: string; // date (ISO YYYY-MM-DD)
  event_key: string;
  event_name: string;
  event_date: string | null; // date (ISO) or null
  calendar_external_id: string;
  release_at: string | null; // timestamptz (ISO) or null
  category: string;
  currencies: unknown; // jsonb — array of currency codes
  mentions: number; // int
  brokers: unknown; // jsonb — array of broker names
  citations: unknown; // jsonb — array of FxEventCitation
  as_of: string; // timestamptz (ISO)
}

/**
 * `fx_economic_calendar` (twelve-x migration 001/002) — upcoming macro catalysts.
 * Read for the next-14-day window, ordered by `event_datetime_utc`.
 */
export interface FxEconomicCalendarRow {
  id: number; // bigserial
  external_id: string; // stable feed key; joins to FxEventSnapshotRow.calendar_external_id
  event_date: string; // date (ISO YYYY-MM-DD), wall-clock feed date
  event_time: string | null; // wall-clock feed time string
  country: string;
  event_name: string;
  category: string;
  impact: string; // 'high' | 'medium' | 'low'
  actual: string | null;
  forecast: string | null;
  prior: string | null;
  event_datetime_utc: string | null; // timestamptz (ISO), absolute release instant
}

/**
 * One element of a brief's `currency_views` jsonb array.
 */
export interface CurrencyView {
  currency: string;
  direction: string; // 'bullish' | 'bearish' | 'neutral' | 'watch' | ...
  conviction: string; // 'high' | 'medium' | 'low' | ...
  signal?: string;
  rationale?: string;
  key_facts?: string[];
  targets?: unknown[];
}

/**
 * `fx_research_history` — one row per broker document per run (P3 brief).
 * The Traceability link key across surfaces is `source_file`; a brief is the
 * pair (run_date, source_file). `currency_views` is the per-desk view array.
 * PRIMARY KEY/UPSERT on (file_id, run_date).
 */
export interface FxBriefRow {
  run_date: string; // date (ISO YYYY-MM-DD)
  source_file: string; // traceability key
  source_url: string | null;
  document_title: string | null;
  broker_name: string | null;
  analyst_names: string[] | null; // text[]
  report_date: string | null; // date (ISO) or null
  trader_relevance: string | null;
  central_thesis: string | null;
  brief_markdown: string | null;
  currency_views: unknown; // jsonb — array of CurrencyView
  risk_events: unknown; // jsonb
  macro_themes: unknown; // jsonb
  positioning_signals: unknown; // jsonb
}

/**
 * `fx_relevance_ledger` — the per-opinion deliberation log (P4 Observability).
 * One row per currency view considered, with the relevance weight decomposition
 * (w_time · w_event · w_review) and a lifecycle classification. Joins back to a
 * brief view via (source_file, view_index) and to a brief via (run_date, source_file).
 */
export interface FxLedgerRow {
  run_date: string; // date (ISO YYYY-MM-DD)
  source_file: string; // traceability key (join to brief)
  view_index: number; // index into the brief's currency_views (join key)
  broker_name: string | null;
  currency: string;
  direction: string;
  conviction: string | null;
  report_date: string | null;
  w_time: number; // double precision
  w_event: number; // double precision
  w_review: number; // double precision
  relevance: number; // double precision (product / final weight)
  classification: string; // 'active' | 'confirmed' | 'invalidated' | 'superseded' | ...
  reason: string | null;
  as_of: string; // timestamptz (ISO)
}

/**
 * One cell of the broker×G10 matrix — the LATEST currency_view a desk holds on a
 * currency over a recent window. Derived in TS from brief `currency_views`
 * (display grouping, not consensus math).
 */
export interface MatrixCell {
  broker: string;
  column: MatrixColumn; // the G10 board column this view files under (base currency)
  currency: string; // the verbatim instrument as stated (e.g. "EUR/USD"), for display
  direction: string;
  conviction: string;
  signal?: string;
  run_date: string; // the brief's run_date (as-of)
  report_date: string | null;
  source_file: string; // drill-to-brief key
  rationale?: string;
  key_facts?: string[];
  targets?: unknown[];
}

/**
 * Per-currency consensus movement between the two newest distinct runs for a
 * pinned timeframe. Computed in TS (see `computeConsensusDeltaSet`).
 */
export interface ConsensusDelta {
  currency: string;
  scoreNow: number;
  scorePrev: number | null;
  scoreDelta: number | null;
  confidenceDelta: number | null;
  flippedDirection: boolean;
  prevRunDate: string | null;
}

/** A notable consensus shift since the previous run (for the movers strip). */
export interface Mover {
  currency: string;
  scoreNow: number;
  scoreDelta: number;
  absDelta: number;
  direction: 'up' | 'down';
}

/** The full run-over-run delta picture: per-currency deltas plus top movers. */
export interface ConsensusDeltaSet {
  runDate: string | null;
  prevRunDate: string | null;
  byCurrency: Record<string, ConsensusDelta>;
  movers: Mover[];
}

/** The catalyst a confluence idea hangs on, resolved against the events feed. */
export interface ConfluenceCatalyst {
  eventKey: string | null;
  eventName: string | null;
  eventDate: string | null;
  calendarExternalId: string | null;
  daysToCatalyst: number | null;
}
