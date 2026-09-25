/**
 * Wire shapes for the Workers dashboard API (`apps/dashboard-api`, contract
 * `apps/dashboard-api/CONTRACT.md`). All specific routes return the §1
 * envelope `{ ok: true, data, provenance }`; this module types the `data`
 * payloads the dashboard consumes. Generic table reads (`GET
 * /v1/tables/:table`) return bare row arrays and are typed at each call site.
 */
import type { PerformanceSsotMeta } from './performance-ssot';

export interface ApiEnvelope<T> {
  ok: boolean;
  data: T;
  provenance: {
    source: string;
    tip_date: string | null;
    contract: string | null;
    seam: boolean;
    marks: string;
  } | null;
}

export interface PortfolioApiData {
  book_as_of: string | null;
  nav_tip: {
    date: string;
    nav: number;
    contract: string;
    invested_pct: number | null;
    cash_pct: number | null;
    day_return_pct: number | null;
  } | null;
  seam: {
    crosses_nav_seam: boolean;
    lag_days: number | null;
    lag_direction: string | null;
  };
  invested: {
    kpi_pct: number | null;
    envelope_pct: number | null;
    cash_pct: number | null;
    definition: string;
  };
  positions: {
    ticker: string;
    weight_pct: number | null;
    scaled_weight_pct: number | null;
    is_cash: boolean;
  }[];
}

export interface BriefApiData {
  book_as_of: string | null;
  nav_tip: { date: string | null; nav: number | null; contract: string };
  day_return_pct: number | null;
  since_inception_pct: number | null;
  since_inception_start_date: string | null;
  overlay: { active: boolean; live_vs_mark_pct: number; badge: string };
  invested_pct: number | null;
  session_events: unknown[];
}

export interface PerformanceApiData {
  nav: {
    tip_date: string | null;
    base100_tip: number | null;
    points: { date: string; index: number; day_return_pct: number | null }[];
  };
  metrics: {
    day_return_pct: number | null;
    since_inception_pct: number | null;
    excess_return_pct: number | null;
    alpha_pct: number | null;
    information_ratio: number | null;
    beta: number | null;
    overlap_days: number;
  };
  benchmark: { ticker: string; aligned_start: string | null };
  stale: {
    lag_days: number | null;
    lag_direction: 'metrics lag' | 'nav lag' | null;
    metrics_as_of: string | null;
  };
  /** Full SSOT chrome — identical to the client's `PerformanceSsotMeta`. */
  ssot: PerformanceSsotMeta;
}

/** The three specific-route payloads the dashboard consumes, keyed by route. */
export interface DashboardApiData {
  portfolio: PortfolioApiData;
  brief: BriefApiData;
  performance: PerformanceApiData;
}
