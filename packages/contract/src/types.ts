/**
 * Shared desk/API shapes. Pure types only — no Supabase client and no generated
 * database map. `Json` matches the desk `database.types` alias so instrument
 * metadata stays assignable across the package boundary.
 */

export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[];

/** A single holding as returned to components. */
export interface InstrumentDetails {
  ticker: string;
  official_name: string;
  instrument_type: string | null;
  asset_class: string | null;
  category: string | null;
  sector: string | null;
  industry: string | null;
  exchange: string | null;
  currency: string | null;
  country: string | null;
  provider: string;
  provider_metadata: Json;
  source_updated_at: string;
}

export interface Position {
  ticker: string;
  name: string;
  /** Canonical provider-sourced identity and classification, when migration 055 is present. */
  instrument?: InstrumentDetails | null;
  type: "LONG" | "SHORT";
  weight_actual: number;
  /** Snapshot target weight from digest `proposed_positions` when present (for target vs actual). */
  weight_target?: number | null;
  /** Change vs previous positions date (percentage points). */
  weight_delta?: number | null;
  current_price: number | null;
  entry_price: number | null;
  entry_date: string | null;
  rationale: string;
  thesis_ids: string[];
  category: string;
  pm_notes: string;
  stats: Record<string, unknown>;
  /** Filled by refresh_performance_metrics.py after close (optional). */
  unrealized_pnl_pct?: number | null;
  day_change_pct?: number | null;
  since_entry_return_pct?: number | null;
  contribution_pct?: number | null;
  metrics_as_of?: string | null;
  /** Unsigned per-position conviction 1–3 (cyan pip meter). */
  conviction?: number | null;
  /** Advisory risk envelope (migration 039); null on ungraded rows. */
  stop_loss_pct?: number | null;
  target_pct_gain?: number | null;
  horizon_days?: number | null;
  /** Grouping bucket for the Holdings sector grouping. */
  sector_bucket?: string | null;
}

/** Execution / change ledger row (position_events). */
export interface DashboardPositionEvent {
  date: string;
  ticker: string;
  event: "OPEN" | "EXIT" | "TRIM" | "ADD" | "HOLD";
  weight_pct: number | null;
  prev_weight_pct: number | null;
  weight_change_pct: number | null;
  price: number | null;
  thesis_id: string | null;
  reason: string | null;
  /** Stable row id when present in the public event stream. */
  id?: string | null;
  /**
   * Sell economics (TRIM/EXIT) or fill-as-entry (OPEN/ADD). Enriched once from
   * positions.entry_price — never invent fills or cost basis.
   */
  avg_entry_price?: number | null;
  sold_weight_pct?: number | null;
  realized_return_pct?: number | null;
}
