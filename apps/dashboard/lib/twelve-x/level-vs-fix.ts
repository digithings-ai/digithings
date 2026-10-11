/**
 * Level-vs-fix assembly for the track-record charts: flat published trade
 * levels against the moving FX fix, with entry/exit anchors.
 *
 * The pair→series map mirrors twelve-x `fx_rates._build_pair_specs` (direct /
 * invert / multiply / divide over the `FX/XXX` native series in
 * `macro_series_observations`). When the table has no usable series for a
 * pair, callers fall back to the anchors-only series built from the eval row's
 * `entry_fix`/`exit_fix` — the chart still renders levels + markers.
 */
import { parseTradeLevels } from './trade-levels';
import type { FxIdeaEvalRow, FxTradeIdeaRow, FxTradeLevels } from './types';

export interface FxFixPoint {
  /** Observation date (YYYY-MM-DD). */
  date: string;
  fix: number;
}

export type FixComposeOp = 'direct' | 'invert' | 'multiply' | 'divide';

export interface PairFixSpec {
  seriesIds: string[];
  op: FixComposeOp;
  /**
   * Invert the composed value (mirrors twelve-x `_compose_history`, which wraps
   * the `JPY/CAD` / `JPY/CHF` / `CHF/CAD` divide in `_invert_series`).
   */
  invert?: boolean;
}

const DIRECT: Record<string, string> = {
  'EUR/USD': 'FX/EUR',
  'GBP/USD': 'FX/GBP',
  'USD/JPY': 'FX/JPY',
  'USD/CAD': 'FX/CAD',
  'AUD/USD': 'FX/AUD',
  'USD/CHF': 'FX/CHF',
  'NZD/USD': 'FX/NZD',
};

/**
 * Explicit pair→series map, mirrored 1:1 from twelve-x `fx_rates._build_pair_specs`
 * (same universe, same op, same leg order — including the upstream
 * `JPY/CAD`/`CAD/JPY` shared divide orientation and the `_invert_series` wrap
 * applied to `JPY/CAD`/`JPY/CHF`/`CHF/CAD` at compose time, so chart values
 * stay consistent with the eval job's own entry/exit fixes).
 */
const SPECS: Record<string, PairFixSpec> = Object.fromEntries(
  Object.entries(DIRECT).map(([pair, series]) => [pair, { seriesIds: [series], op: 'direct' as const }]),
);
for (const [pair, series] of [
  ['USD/EUR', 'FX/EUR'],
  ['USD/GBP', 'FX/GBP'],
  ['JPY/USD', 'FX/JPY'],
  ['CAD/USD', 'FX/CAD'],
  ['USD/AUD', 'FX/AUD'],
  ['CHF/USD', 'FX/CHF'],
  ['USD/NZD', 'FX/NZD'],
] as const) {
  SPECS[pair] = { seriesIds: [series], op: 'invert' };
}
for (const [pair, a, b] of [
  ['EUR/JPY', 'FX/EUR', 'FX/JPY'],
  ['EUR/CAD', 'FX/EUR', 'FX/CAD'],
  ['EUR/CHF', 'FX/EUR', 'FX/CHF'],
  ['GBP/JPY', 'FX/GBP', 'FX/JPY'],
  ['GBP/CAD', 'FX/GBP', 'FX/CAD'],
  ['GBP/CHF', 'FX/GBP', 'FX/CHF'],
  ['AUD/JPY', 'FX/AUD', 'FX/JPY'],
  ['AUD/CAD', 'FX/AUD', 'FX/CAD'],
  ['AUD/CHF', 'FX/AUD', 'FX/CHF'],
  ['NZD/JPY', 'FX/NZD', 'FX/JPY'],
  ['NZD/CAD', 'FX/NZD', 'FX/CAD'],
  ['NZD/CHF', 'FX/NZD', 'FX/CHF'],
] as const) {
  SPECS[pair] = { seriesIds: [a, b], op: 'multiply' };
}
/**
 * Pairs whose divide result is inverted at compose time to mirror twelve-x
 * `_compose_history` (it wraps these legs in `_invert_series`).
 */
const INVERT_ON_DIVIDE = new Set(['JPY/CAD', 'JPY/CHF', 'CHF/CAD']);

for (const [pair, a, b] of [
  ['EUR/GBP', 'FX/EUR', 'FX/GBP'],
  ['GBP/EUR', 'FX/GBP', 'FX/EUR'],
  ['EUR/AUD', 'FX/EUR', 'FX/AUD'],
  ['EUR/NZD', 'FX/EUR', 'FX/NZD'],
  ['GBP/AUD', 'FX/GBP', 'FX/AUD'],
  ['GBP/NZD', 'FX/GBP', 'FX/NZD'],
  ['AUD/NZD', 'FX/AUD', 'FX/NZD'],
  ['NZD/AUD', 'FX/NZD', 'FX/AUD'],
  ['CAD/JPY', 'FX/JPY', 'FX/CAD'],
  ['JPY/CAD', 'FX/JPY', 'FX/CAD'],
  ['CHF/JPY', 'FX/JPY', 'FX/CHF'],
  ['JPY/CHF', 'FX/JPY', 'FX/CHF'],
  ['CAD/CHF', 'FX/CHF', 'FX/CAD'],
  ['CHF/CAD', 'FX/CHF', 'FX/CAD'],
] as const) {
  SPECS[pair] = {
    seriesIds: [a, b],
    op: 'divide',
    ...(INVERT_ON_DIVIDE.has(pair) ? { invert: true } : {}),
  };
}

/** Normalize `EURUSD` / `eur-usd` to `EUR/USD`; unparseable input passes through uppercased. */
export function normalizeFixPair(pair: string | null | undefined): string {
  const raw = (pair ?? '').toUpperCase().replace(/[\s_-]+/g, '');
  if (raw.includes('/')) {
    const [base, quote] = raw.split('/');
    if (base && quote) return `${base}/${quote}`;
    return raw;
  }
  if (/^[A-Z]{6}$/.test(raw)) return `${raw.slice(0, 3)}/${raw.slice(3)}`;
  return raw;
}

/**
 * PURE — fix-history window covering the idea's life plus a 30d margin
 * (LOW4: the bare 90d fetch default truncates older idea windows). Floor 90;
 * unparseable run dates clamp to the floor.
 */
export function fixWindowDays(runDate: string, today = new Date().toISOString().slice(0, 10)): number {
  const age = Math.round((Date.parse(today) - Date.parse(runDate)) / 86_400_000);
  if (!Number.isFinite(age) || age <= 0) return 90;
  return Math.max(90, age + 30);
}

/**
 * PURE — the native-series spec composing a pair's fix history, or `null`
 * when the pair is outside the covered universe (same coverage as the
 * twelve-x eval job's pair specs).
 */
export function pairFixSpec(pair: string | null | undefined): PairFixSpec | null {
  return SPECS[normalizeFixPair(pair)] ?? null;
}

/**
 * PURE — compose a pair fix history from native series histories (inner join
 * on date, ascending). Non-finite legs and zero divisors drop the date.
 */
export function composeFixSeries(
  spec: PairFixSpec,
  bySeriesId: Record<string, FxFixPoint[]>,
): FxFixPoint[] {
  const legs = spec.seriesIds.map((id) => bySeriesId[id] ?? []);
  if (legs.some((l) => l.length === 0)) return [];
  const byDate = new Map<string, number[]>();
  legs.forEach((points, leg) => {
    for (const p of points) {
      if (!Number.isFinite(p.fix)) continue;
      const entry = byDate.get(p.date);
      if (entry) entry[leg] = p.fix;
      else {
        const arr: number[] = [];
        arr[leg] = p.fix;
        byDate.set(p.date, arr);
      }
    }
  });
  const out: FxFixPoint[] = [];
  for (const [date, values] of byDate) {
    if (values.length !== legs.length || values.some((v) => !Number.isFinite(v))) continue;
    let fix: number;
    switch (spec.op) {
      case 'direct':
        fix = values[0];
        break;
      case 'invert':
        if (values[0] === 0) continue;
        fix = 1 / values[0];
        break;
      case 'multiply':
        fix = values[0] * values[1];
        break;
      case 'divide':
        if (values[1] === 0) continue;
        fix = values[0] / values[1];
        break;
    }
    if (spec.invert) {
      if (fix === 0) continue;
      fix = 1 / fix;
    }
    if (Number.isFinite(fix)) out.push({ date, fix });
  }
  return out.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
}

function numOrNull(v: string | null | undefined): number | null {
  if (v === null || v === undefined) return null;
  const n = Number(String(v).trim());
  return Number.isFinite(n) ? n : null;
}

export interface LevelFixSeries {
  pair: string;
  entryLow: number | null;
  entryHigh: number | null;
  stop: number | null;
  targets: number[];
  entryDate: string | null;
  exitDate: string | null;
  entryFix: number | null;
  exitFix: number | null;
  /** Table fix history, or the anchors-only fallback (entry→exit), or []. */
  points: FxFixPoint[];
  /** True when `points` is just the eval anchors (no table history). */
  anchorsOnly: boolean;
}

/**
 * A bracket publishes complete or not at all (DIG-260 L5). `partial`,
 * `incomplete`, and any status `parseTradeLevels` did not recognise (it
 * coerces those to `incomplete`) all mean the ladder is not publishable.
 *
 * This mirrors `isPublishableBracket` in `./trade-levels` rather than
 * importing it: that predicate is module-private and that file is a frozen
 * contract. The two must be kept in step — `level-vs-fix.test.ts` asserts
 * this gate and `trade-levels.pending-levels.test.ts` asserts the model gate,
 * and neither alone pins the pair. That is why the test file cross-checks the
 * two gates against each other.
 */
function isPublishableBracket(tradeLevels: FxTradeLevels | null): tradeLevels is FxTradeLevels {
  return tradeLevels !== null && tradeLevels.status === 'complete';
}

/**
 * PURE — flat published levels + moving fix for one idea. `fixes` is the
 * table history for the idea's pair (possibly empty); `evalRow` supplies the
 * entry/exit anchors. Anchors-only fallback keeps levels + markers rendering
 * when the rates table has nothing for the pair.
 *
 * The bracket is gated on publishability, not on shape: a half bracket drawn
 * against an axis and a legend reads as actionable, which is the same defect
 * the panel's component gate prevents in the text column. The fix history and
 * the eval anchors are the chart's other subject and are not gated — they come
 * from the eval row, not from the bracket.
 */
export function buildLevelFixSeries(
  idea: FxTradeIdeaRow,
  evalRow: FxIdeaEvalRow | null | undefined,
  fixes: FxFixPoint[],
): LevelFixSeries {
  const tl = parseTradeLevels(idea.trade_levels);
  const published = isPublishableBracket(tl) ? tl : null;
  const entryFix = evalRow?.entry_fix ?? null;
  const exitFix = evalRow?.exit_fix ?? null;
  const entryDate = evalRow?.entry_date ?? null;
  const exitDate = evalRow?.exit_date ?? null;

  const tablePoints = (fixes ?? []).filter((p) => Number.isFinite(p.fix));
  let points = tablePoints;
  let anchorsOnly = false;
  if (points.length === 0 && entryFix !== null && exitFix !== null && entryDate && exitDate) {
    points = [
      { date: entryDate, fix: entryFix },
      { date: exitDate, fix: exitFix },
    ];
    anchorsOnly = true;
  }

  return {
    pair: idea.pair,
    entryLow: published ? numOrNull(published.entry_low?.value) : null,
    entryHigh: published ? numOrNull(published.entry_high?.value) : null,
    stop: published ? numOrNull(published.stop?.value) : null,
    targets: published
      ? published.targets
          .map((t) => numOrNull(t.value))
          .filter((n): n is number => n !== null)
      : [],
    entryDate,
    exitDate,
    entryFix,
    exitFix,
    points,
    anchorsOnly,
  };
}
