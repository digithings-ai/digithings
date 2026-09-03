/**
 * Data-driven DCA / schema-1.3 helpers for the library card and tearsheet
 * (#3172). Drive off null KPIs and the `dca` / `vs_lump_pct` extras — never a
 * slug allowlist — so a future ETH book lights up without a frontend edit.
 */

import { inferKind } from "./strategy-kinds";
import type {
  StrategyIndexEntry,
  TearsheetData,
  TearsheetFillMarker,
  TearsheetIndicatorCurve,
  TearsheetSeriesPoint,
} from "./types";

const UNUSED_EXTRAS: { name: string; display_name: string }[] = [
  { name: "m2", display_name: "M2 liquidity" },
  { name: "rs_eth", display_name: "BTC/ETH relative strength" },
  { name: "dxy", display_name: "DXY" },
  { name: "weekly_rsi", display_name: "weekly RSI" },
  { name: "weekly_macd", display_name: "weekly log-MACD" },
  { name: "sma_band", display_name: "SMA band" },
];

/** Published btc_optimized knees when the payload omits curve_knees. */
export const DEFAULT_SDCA_KNEES = { buy_knee_risk: 25, sell_knee_risk: 70, preset: "btc_optimized" };

/** Trade-based tiles apply only when the schema reports them as numbers. */
export function hasTradeKpis(
  winRatePct: number | null | undefined,
  profitFactor: number | null | undefined,
): boolean {
  return winRatePct != null && profitFactor != null;
}

export function isDcaTearsheet(data: Pick<TearsheetData, "dca" | "kind" | "strategy" | "win_rate_pct">): boolean {
  if (data.dca != null) return true;
  if (data.kind === "dca") return true;
  if (data.win_rate_pct == null && inferKind(data.strategy, data.kind) === "dca") return true;
  return inferKind(data.strategy, data.kind) === "dca";
}

export function isDcaIndexEntry(
  e: Pick<StrategyIndexEntry, "strategy" | "kind" | "vs_lump_pct" | "win_rate_pct">,
): boolean {
  if (e.vs_lump_pct != null) return true;
  return inferKind(e.strategy, e.kind) === "dca";
}

/** Percent of MTM equity in the asset. Never uses capital_deployed (goes negative after sells). */
export function allocatedPctCurve(data: TearsheetData): TearsheetSeriesPoint[] {
  if (data.allocated_pct_curve && data.allocated_pct_curve.length > 0) return data.allocated_pct_curve;
  const eq = data.equity_curve ?? [];
  const dep = data.capital_deployed_curve ?? [];
  if (eq.length === 0 || dep.length === 0) return [];
  const depMap = new Map(dep.map((p) => [p.t, p.v]));
  const initial = data.initial_capital;
  return eq.map((p) => {
    const deployed = depMap.get(p.t) ?? 0;
    const cash = initial * (1 - deployed / 100);
    const port = p.v;
    const asset = port - cash;
    return { t: p.t, v: port > 0 ? Math.max(0, (100 * asset) / port) : 0 };
  });
}

export function fillMarkersForChart(data: TearsheetData): TearsheetFillMarker[] {
  if (data.fill_markers && data.fill_markers.length > 0) return data.fill_markers;
  const eq = data.equity_curve ?? [];
  const dep = data.capital_deployed_curve ?? [];
  const ohlc = data.ohlc_bars ?? [];
  if (eq.length === 0 || dep.length === 0 || ohlc.length === 0) return [];
  const depMap = new Map(dep.map((p) => [p.t, p.v]));
  const pxMap = new Map(ohlc.map((b) => [b.t, b.c]));
  const initial = data.initial_capital;
  const units: number[] = [];
  for (const p of eq) {
    const cash = initial * (1 - (depMap.get(p.t) ?? 0) / 100);
    const px = pxMap.get(p.t) ?? 0;
    units.push(px > 0 ? (p.v - cash) / px : 0);
  }
  const out: TearsheetFillMarker[] = [];
  for (let i = 0; i < eq.length; i++) {
    const prev = i === 0 ? 0 : units[i - 1];
    const delta = units[i] - prev;
    if (Math.abs(delta) < 1e-8) continue;
    const px = pxMap.get(eq[i].t) ?? 0;
    const trade = delta * px;
    const port = eq[i].v;
    out.push({
      t: eq[i].t,
      side: trade > 0 ? "buy" : "sell",
      book_frac: port > 0 ? Math.abs(trade) / port : 0,
      price: px,
      trade_usd: trade,
    });
  }
  return out;
}

export function indicatorPanels(data: TearsheetData): TearsheetIndicatorCurve[] {
  if (data.indicator_curves && data.indicator_curves.length > 0) return data.indicator_curves;
  const risk = data.risk_curve ?? [];
  const extras: TearsheetIndicatorCurve[] = UNUSED_EXTRAS.map((e) => ({
    name: e.name,
    display_name: e.display_name,
    weight: 0,
    in_index: false,
    points: [],
  }));
  if (risk.length === 0) return extras;
  return [
    {
      name: "valuation",
      display_name: "power law",
      weight: data.indicator_weights?.valuation ?? 1,
      in_index: true,
      points: risk,
    },
    ...extras,
  ];
}

export function curveKnees(data: TearsheetData): { buy_knee_risk: number; sell_knee_risk: number } {
  return data.curve_knees ?? DEFAULT_SDCA_KNEES;
}

export const ALLOCATED_KPI_LABEL = "Allocated";
export const VS_FLAT_KPI_LABEL = "Vs flat DCA (full sample)";
export const VS_LUMP_KPI_LABEL = "Vs buy & hold";
export const TOTAL_RETURN_KPI_LABEL = "Total return";

/** Final MTM allocated %. Never capital_deployed (goes negative after sells). */
export function lastAllocatedPct(
  data: Pick<TearsheetData, "dca" | "allocated_pct_curve" | "equity_curve" | "capital_deployed_curve" | "initial_capital">,
): number | null {
  if (data.dca?.allocated_pct != null && Number.isFinite(data.dca.allocated_pct)) {
    return Math.max(0, data.dca.allocated_pct);
  }
  const curve = allocatedPctCurve(data as TearsheetData);
  if (curve.length === 0) return null;
  return Math.max(0, curve[curve.length - 1].v);
}

export function lastAllocatedPctFromIndex(
  e: Pick<StrategyIndexEntry, "allocated_pct" | "capital_deployed_pct">,
): number | null {
  if (e.allocated_pct != null && Number.isFinite(e.allocated_pct)) {
    return Math.max(0, e.allocated_pct);
  }
  return null;
}

/** Absent / false = do not claim an OOS win over flat DCA. */
export function beatsFlatDcaOos(
  value: boolean | null | undefined,
): boolean {
  return value === true;
}

export function isValuationOnlyIndex(weights?: Record<string, number> | null): boolean {
  if (!weights) return true;
  const extras = Object.entries(weights).filter(([name]) => name !== "valuation");
  const extrasOff = extras.length === 0 || extras.every(([, w]) => w === 0);
  return extrasOff && (weights.valuation ?? 1) > 0;
}

/** Fill-day counts from actual fills — never curve-sign buy_days / sell_days. */
export function fillDayCounts(data: TearsheetData): { buys: number; sells: number } | null {
  if (data.dca?.fill_buy_days != null && data.dca.fill_sell_days != null) {
    return { buys: data.dca.fill_buy_days, sells: data.dca.fill_sell_days };
  }
  const markers = fillMarkersForChart(data);
  if (markers.length === 0) return null;
  return {
    buys: markers.filter((m) => m.side === "buy").length,
    sells: markers.filter((m) => m.side === "sell").length,
  };
}
