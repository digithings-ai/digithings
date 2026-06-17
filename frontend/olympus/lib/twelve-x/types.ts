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
 * `fx_consensus_snapshot` — one row per G10 currency per run_date, for the
 * weighted (relevance-weighted live) view AND the unweighted (frozen) view.
 * PRIMARY KEY (run_date, currency, weighted).
 */
export interface FxConsensusSnapshotRow {
  run_date: string; // date (ISO YYYY-MM-DD)
  currency: string;
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
  headline: string;
  summary: string;
  key_themes: string[] | string | null; // jsonb / text[]
  doc_count: number;
  broker_count: number;
}
