const ETF_CATEGORY_BY_TICKER: Record<string, string> = {
  AGG: 'fixed_income_core',
  BIL: 'fixed_income_cash',
  BND: 'fixed_income_core',
  GLD: 'commodity_gold',
  GOVT: 'fixed_income_core',
  IEF: 'fixed_income_intermediate',
  IWM: 'equity_broad',
  QQQ: 'equity_broad',
  SGOV: 'fixed_income_cash',
  SHV: 'fixed_income_cash',
  SHY: 'fixed_income_short',
  SPY: 'equity_broad',
  TLT: 'fixed_income_long',
  VTI: 'equity_broad',
  XLB: 'equity_sector',
  XLC: 'equity_sector',
  XLE: 'equity_sector',
  XLF: 'equity_sector',
  XLI: 'equity_sector',
  XLK: 'equity_sector',
  XLP: 'equity_sector',
  XLRE: 'equity_sector',
  XLU: 'equity_sector',
  XLV: 'equity_sector',
  XLY: 'equity_sector',
};

const UNKNOWN_CATEGORY_VALUES = new Set(['', '-', '—', 'unknown', 'uncategorized', 'null']);

export function normalizePortfolioCategory(raw: string | null | undefined): string | null {
  const value = String(raw ?? '').trim();
  if (!value || UNKNOWN_CATEGORY_VALUES.has(value.toLowerCase())) return null;
  return value;
}

export function inferPortfolioCategory(ticker: string | null | undefined, raw: string | null | undefined): string {
  const explicit = normalizePortfolioCategory(raw);
  if (explicit) return explicit;

  const t = String(ticker ?? '').trim().toUpperCase();
  if (t === 'CASH') return 'cash';
  return ETF_CATEGORY_BY_TICKER[t] ?? 'uncategorized';
}

export function categoryStackLabel(key: string): string {
  if (key === 'cash') return 'Cash';
  if (key === 'uncategorized') return 'Uncategorized';
  if (key === 'fixed_income_cash') return 'Cash';
  if (key === 'fixed_income_short') return 'Short Duration';
  if (key === 'fixed_income_intermediate') return 'Intermediate Duration';
  if (key === 'fixed_income_core') return 'Core Bonds';
  if (key === 'fixed_income_long') return 'Long Duration';
  if (key === 'equity_broad') return 'Broad Equity';
  if (key === 'equity_sector') return 'Equity Sector';
  return key.replace(/_/g, ' ');
}
