/**
 * Strategy tear sheet model shared by the marketing band, the strategy page,
 * and the quant TUI. Figures come only from the payload. A missing number
 * stays null (the renderer draws an em dash). A chart series is omitted
 * until it holds two finite values.
 */

export type StrategySheetMetric = {
  label: string;
  /** Preformatted figure. Null is unpublished. */
  value: string | null;
  tone?: "pos" | "neg";
};

export type StrategySheetPoint = { t: string; v: number };

export type StrategySheetBar = { t: string; o: number; h: number; l: number; c: number };

export type StrategySheetModel = {
  title: string;
  symbol: string;
  metrics: StrategySheetMetric[];
  position: StrategySheetMetric[];
  equity: StrategySheetPoint[] | null;
  drawdown: StrategySheetPoint[] | null;
  price: StrategySheetBar[] | null;
  trades: { columns: string[]; rows: string[][] } | null;
};

const TRADE_COLUMNS = ["Direction", "Entry date", "Entry", "Exit date", "Exit", "Return"];
const BARS = "▁▂▃▄▅▆▇█";

function rec(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function finite(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function toneOf(value: number | null): "pos" | "neg" | undefined {
  if (value === null || value === 0) return undefined;
  return value > 0 ? "pos" : "neg";
}

function pct(value: number | null): string | null {
  if (value === null) return null;
  return `${value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
}

function num(value: number | null, digits: number): string | null {
  if (value === null) return null;
  return value.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function metric(label: string, value: number | null, format: "pct" | "num" | "count"): StrategySheetMetric {
  if (format === "pct") return { label, value: pct(value), tone: toneOf(value) };
  if (format === "count") return { label, value: value === null ? null : String(Math.trunc(value)) };
  return { label, value: num(value, 2), tone: toneOf(value) };
}

function yearsBetween(start: string, end: string): number | null {
  const a = Date.parse(start);
  const b = Date.parse(end);
  if (!Number.isFinite(a) || !Number.isFinite(b) || b <= a) return null;
  return (b - a) / (365.25 * 24 * 3600 * 1000);
}

/** CAGR from real capital and dates. Missing inputs stay unpublished. */
export function sheetCagr(initial: number | null, final: number | null, start: string | null, end: string | null): number | null {
  if (initial === null || final === null || initial <= 0 || final <= 0 || !start || !end) return null;
  const years = yearsBetween(start, end);
  if (years === null) return null;
  return (Math.pow(final / initial, 1 / years) - 1) * 100;
}

/** Dated numeric series. Fewer than two finite points is not a chart. */
export function seriesOrNull(value: unknown): StrategySheetPoint[] | null {
  if (!Array.isArray(value)) return null;
  const points: StrategySheetPoint[] = [];
  for (const item of value) {
    const row = rec(item);
    const t = text(row?.t);
    const v = finite(row?.v);
    if (!t || v === null) continue;
    points.push({ t, v });
  }
  return points.length >= 2 ? points : null;
}

function priceOrNull(value: unknown): StrategySheetBar[] | null {
  if (!Array.isArray(value)) return null;
  const bars: StrategySheetBar[] = [];
  for (const item of value) {
    const row = rec(item);
    const t = text(row?.t);
    const o = finite(row?.o);
    const h = finite(row?.h);
    const l = finite(row?.l);
    const c = finite(row?.c);
    if (!t || o === null || h === null || l === null || c === null) continue;
    bars.push({ t, o, h, l, c });
  }
  return bars.length >= 2 ? bars : null;
}

function isDca(row: Record<string, unknown> | null): boolean {
  if (!row) return false;
  if (rec(row.dca)) return true;
  if (row.kind === "dca") return true;
  const strategy = text(row.strategy);
  return strategy !== null && strategy.includes("sdca");
}

function dashCell(value: string | null): string {
  return value ?? "—";
}

function tradeRows(value: unknown): string[][] | null {
  if (!Array.isArray(value)) return null;
  const rows: string[][] = [];
  for (const item of value) {
    const row = rec(item);
    if (!row) continue;
    const entryDate = text(row.entry_date);
    const entry = finite(row.entry_price);
    const exitDate = text(row.exit_date);
    const exit = finite(row.exit_price);
    const ret = finite(row.pnl_pct);
    const direction = text(row.direction);
    if (!entryDate && entry === null && !exitDate && exit === null) continue;
    rows.push([
      dashCell(direction),
      dashCell(entryDate),
      dashCell(num(entry, 2)),
      dashCell(exitDate),
      dashCell(num(exit, 2)),
      dashCell(pct(ret)),
    ]);
  }
  return rows.length > 0 ? rows : null;
}

function positionOf(row: Record<string, unknown> | null): StrategySheetMetric[] {
  const signal = rec(row?.current_signal);
  const place = text(signal?.position);
  const entry = text(signal?.entry_label);
  const mark = finite(signal?.last_price);
  const asOf = text(signal?.last_signal_date);
  return [
    { label: "Position", value: place },
    { label: "Entry", value: entry },
    { label: "Mark", value: num(mark, 2) },
    { label: "As of", value: asOf },
  ];
}

function metricsOf(row: Record<string, unknown> | null): StrategySheetMetric[] {
  const dca = rec(row?.dca);
  if (isDca(row)) {
    const total = finite(row?.net_profit_pct);
    const dd = finite(row?.max_drawdown_pct);
    const vs = finite(dca?.vs_lump_pct) ?? finite(row?.vs_lump_pct);
    const allocated = finite(dca?.allocated_pct) ?? finite(row?.allocated_pct);
    return [
      metric("Total return", total, "pct"),
      metric("Max DD", dd, "pct"),
      metric("Vs lump", vs, "pct"),
      metric("Allocated", allocated, "pct"),
    ];
  }
  const cagr = sheetCagr(
    finite(row?.initial_capital),
    finite(row?.final_equity),
    text(row?.period_start),
    text(row?.period_end),
  );
  return [
    metric("CAGR", cagr, "pct"),
    metric("Max DD", finite(row?.max_drawdown_pct), "pct"),
    metric("Profit factor", finite(row?.profit_factor), "num"),
    metric("Win rate", finite(row?.win_rate_pct), "pct"),
    metric("Avg trade", finite(row?.avg_trade_pct), "pct"),
    metric("Trades", finite(row?.total_trades), "count"),
  ];
}

/** One strategy sheet. `data` null, or a payload that is not a tearsheet, publishes nothing. */
export function buildStrategyTearsheet(
  data: unknown,
  fallback: { title: string; symbol: string },
): StrategySheetModel {
  const row = rec(data);
  const trades = tradeRows(row?.trades);
  return {
    title: text(row?.label) ?? fallback.title,
    symbol: text(row?.symbol) ?? fallback.symbol,
    metrics: metricsOf(row),
    position: positionOf(row),
    equity: seriesOrNull(row?.equity_curve),
    drawdown: seriesOrNull(row?.drawdown_curve),
    price: priceOrNull(row?.ohlc_bars),
    trades: trades ? { columns: TRADE_COLUMNS, rows: trades } : null,
  };
}

/** Block-character chart. One value, or a non-finite value, is not a chart. */
export function seriesSparkline(values: readonly number[], width = 24): string | null {
  const finiteValues = values.filter((value) => Number.isFinite(value));
  if (finiteValues.length < 2) return null;
  const sampled = finiteValues.length <= width ? finiteValues : sample(finiteValues, width);
  const lo = Math.min(...sampled);
  const hi = Math.max(...sampled);
  const span = hi - lo;
  return sampled
    .map((n) => {
      if (span === 0) return BARS[3] ?? BARS[0];
      const index = Math.round(((n - lo) / span) * (BARS.length - 1));
      return BARS[Math.min(BARS.length - 1, Math.max(0, index))] ?? BARS[0];
    })
    .join("");
}

function sample(values: number[], width: number): number[] {
  const last = values.length - 1;
  const out: number[] = [];
  for (let i = 0; i < width; i += 1) {
    const value = values[Math.round((i * last) / (width - 1))];
    if (value !== undefined) out.push(value);
  }
  return out;
}
