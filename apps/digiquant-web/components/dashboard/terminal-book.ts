import type { LivePortfolioResult, LivePosition, NavPoint } from "@/lib/live/types";

/** Missing figure. Never a zero standing in for an unknown number. */
export const EM = "—";

const pctBody = (v: number) =>
  Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export function figPlainPct(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return EM;
  return `${v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
}

export function figSignedPct(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return EM;
  if (v > 0) return `+${pctBody(v)}%`;
  if (v < 0) return `-${pctBody(v)}%`;
  return "0.00%";
}

export function figPx(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return EM;
  return v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function figCount(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return EM;
  return String(Math.trunc(v));
}

export function isCash(p: LivePosition): boolean {
  return p.ticker.trim().toUpperCase() === "CASH";
}

export function sleeveOf(p: LivePosition): string {
  const name = p.category?.trim() || p.sectorBucket?.trim();
  return name && name.length > 0 ? name : "Unassigned";
}

export interface DrawdownRead {
  maxPct: number | null;
  currentPct: number | null;
  peakDate: string | null;
  troughDate: string | null;
}

const EMPTY_DRAWDOWN: DrawdownRead = {
  maxPct: null,
  currentPct: null,
  peakDate: null,
  troughDate: null,
};

/** Max and current drawdown from a real NAV index. Fewer than two positive points → all null. */
export function drawdownFromNav(points: readonly { date: string; nav: number }[]): DrawdownRead {
  const rows = points.filter((p) => Number.isFinite(p.nav) && p.nav > 0);
  if (rows.length < 2) return EMPTY_DRAWDOWN;
  let peak = rows[0].nav;
  let peakDate = rows[0].date;
  let maxPct = 0;
  let troughDate = rows[0].date;
  for (const row of rows) {
    if (row.nav >= peak) {
      peak = row.nav;
      peakDate = row.date;
    }
    const dd = (row.nav / peak - 1) * 100;
    if (dd < maxPct) {
      maxPct = dd;
      troughDate = row.date;
    }
  }
  const last = rows[rows.length - 1];
  let runPeak = rows[0].nav;
  for (const row of rows) if (row.nav > runPeak) runPeak = row.nav;
  const currentPct = (last.nav / runPeak - 1) * 100;
  return {
    maxPct,
    currentPct: Number.isFinite(currentPct) ? currentPct : null,
    peakDate,
    troughDate,
  };
}

export interface DeskKpi {
  label: string;
  value: string;
  sub: string;
}

export interface DeskHolding {
  ticker: string;
  name: string;
  weight: string;
  shares: string;
  mark: string;
  day: string;
  dayN: number | null;
  cash: boolean;
}

export interface DeskSleeve {
  sleeve: string;
  names: string;
  weight: string;
}

export interface DeskMover {
  ticker: string;
  mark: string;
  day: string;
  dayN: number | null;
}

export interface DeskModel {
  connected: boolean;
  reading: boolean;
  reason: string | null;
  asOf: string | null;
  kpis: DeskKpi[];
  sleeves: DeskSleeve[];
  movers: DeskMover[];
  holdings: DeskHolding[];
  navPoints: NavPoint[];
  navStart: string;
  navEnd: string;
  drawdown: DrawdownRead;
}

type BookInput = Pick<
  LivePortfolioResult,
  "loading" | "configured" | "error" | "navContractError" | "positions" | "nav" | "metricsAsOf" | "kpis"
>;

function kpi(label: string, value: string, sub: string): DeskKpi {
  return { label, value, sub };
}

/** Map a house-book read onto the portfolio windows. Unset, loading, and failed reads withhold figures. */
export function bookModel(live: BookInput): DeskModel {
  const reading = live.configured && live.loading;
  const failed = Boolean(live.error);
  const figures = live.configured && !reading && !failed;
  const navOk = figures && !live.navContractError;
  const positions = figures ? live.positions : [];
  const names = positions.filter((p) => !isCash(p));
  const asOf = figures ? live.metricsAsOf ?? live.nav.at(-1)?.date ?? null : null;
  const paper = asOf ? `paper · ${asOf}` : "paper";

  const reason = !live.configured
    ? "House book read is not connected in this build."
    : reading
      ? "Reading the official API."
      : live.error
        ? live.error
        : live.navContractError
          ? live.navContractError
          : null;

  const k = figures ? live.kpis : null;
  const navPoints = navOk ? live.nav.filter((n) => Number.isFinite(n.nav)) : [];

  const sleeves = new Map<string, LivePosition[]>();
  for (const p of names) {
    const key = sleeveOf(p);
    sleeves.set(key, [...(sleeves.get(key) ?? []), p]);
  }

  const movers = names
    .filter((p) => p.dayChangePct != null && Number.isFinite(p.dayChangePct))
    .slice()
    .sort((a, b) => (b.dayChangePct as number) - (a.dayChangePct as number))
    .map((p) => ({
      ticker: p.ticker,
      mark: figPx(p.currentPrice),
      day: figSignedPct(p.dayChangePct),
      dayN: p.dayChangePct,
    }));

  return {
    connected: figures,
    reading,
    reason,
    asOf,
    kpis: [
      kpi("Since inception", figSignedPct(k?.sinceInceptionPct ?? k?.portfolioReturnPct ?? null), k ? paper : "paper · no window"),
      kpi("Day", figSignedPct(k?.dayReturnPct ?? null), k?.priceAsOfDate ? `as of ${k.priceAsOfDate}` : "as of —"),
      kpi(
        "Excess",
        figSignedPct(k?.excessReturnPct ?? null),
        k?.benchmarkTicker ? `vs ${k.benchmarkTicker}` : "benchmark —",
      ),
      kpi("Names", figures ? figCount(names.length) : EM, "ex cash"),
    ],
    sleeves: [...sleeves].map(([sleeve, rows]) => {
      const weights = rows.map((r) => r.weightPct);
      const sum = weights.every((w) => Number.isFinite(w)) ? weights.reduce((a, b) => a + b, 0) : null;
      return { sleeve, names: figCount(rows.length), weight: figPlainPct(sum) };
    }),
    movers,
    holdings: positions.map((p) => ({
      ticker: p.ticker,
      name: isCash(p) ? "Cash" : p.name?.trim() || EM,
      weight: figPlainPct(p.weightPct),
      shares: EM,
      mark: isCash(p) ? EM : figPx(p.currentPrice),
      day: figSignedPct(p.dayChangePct),
      dayN: p.dayChangePct != null && Number.isFinite(p.dayChangePct) ? p.dayChangePct : null,
      cash: isCash(p),
    })),
    navPoints,
    navStart: navPoints[0]?.date ?? EM,
    navEnd: navPoints.at(-1)?.date ?? EM,
    drawdown: navOk ? drawdownFromNav(navPoints) : EMPTY_DRAWDOWN,
  };
}
