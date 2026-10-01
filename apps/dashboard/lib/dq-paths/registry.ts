/**
 * DigiQuant API path registry — the UI path tree mirrors the dashboard-api
 * worker routes (apps/dashboard-api/CONTRACT.md §6). Every data block binds
 * to one entry here; top-chrome breadcrumbs are derived from `uiPath`.
 */
export type DqEnvelope<T> = {
  data: T;
  as_of: string | null;
  retrieval_pin?: string | null;
  provenance: {
    source: string;
    tip_date: string | null;
    contract: 'finalized_accounting' | 'legacy_estimate' | null;
    seam: boolean;
    marks: 'stored' | 'market_api' | 'unavailable';
  };
};

export type DqPathDef = {
  /** Slash-path shown in the top chrome (page = path). */
  uiPath: string;
  /** Worker route this path reads (CONTRACT §6). */
  apiRoute: string;
};

export const DQ_PATHS = {
  book: { uiPath: '/book', apiRoute: '/allocations' },
  portfolio: { uiPath: '/portfolio', apiRoute: '/portfolio' },
  brief: { uiPath: '/brief', apiRoute: '/brief' },
  performance: { uiPath: '/performance', apiRoute: '/performance' },
  ledger: { uiPath: '/ledger', apiRoute: '/ledger' },
} as const satisfies Record<string, DqPathDef>;

export type DqPathKey = keyof typeof DQ_PATHS;

export type BookRow = {
  ticker: string;
  weight_pct: number;
  scaled_weight_pct: number;
  entry_price: number | null;
  current_price: number | null;
  unrealized_pct: number | null;
  marks: 'stored' | 'market_api' | 'unavailable';
  marks_as_of: string | null;
};

export type BookData = {
  book_as_of: string | null;
  invested_pct: number | null;
  cash_pct: number | null;
  invested_definition: string;
  rows: BookRow[];
  marks_unstamped: boolean;
};

/** Split a ui path into breadcrumb segments (`/house/portfolio` → [house, portfolio]). */
export function pathSegments(uiPath: string): string[] {
  return uiPath.split('/').filter(Boolean);
}

/** Format a nullable percent; fail closed to an em dash (never invent P&L). */
export function fmtPct(v: number | null | undefined, digits = 2): string {
  return v === null || v === undefined || !Number.isFinite(v) ? '—' : `${v.toFixed(digits)}%`;
}

export function fmtPrice(v: number | null | undefined): string {
  return v === null || v === undefined || !Number.isFinite(v) ? '—' : v.toFixed(2);
}
