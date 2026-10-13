import type { BriefApiData, PortfolioApiData } from '@/lib/api-types';
import type {
  AllocationsData,
  DigiquantRead,
  RunHealthRow,
  ThesisTableRow,
} from '@/lib/desk/digiquant';
import { deriveBookMovers, type MoverClose } from '@/lib/desk/movers';
import type { VelaSpikeBar } from '@/components/research/VelaSpikeChart';
import { isCashTicker } from '@/lib/book-reconciliation';
import { BRIEF_PANES, type DeskPaneModel, type PaneState } from './catalog';
import {
  EM_DASH,
  formatMark,
  formatSignedPct,
  formatWeight,
  provenanceBadge,
  textOrDash,
} from './format';

export interface RouteHit<T> {
  status: 'ok' | 'empty' | 'error';
  data?: T;
  message?: string;
}

export interface ChartSnap {
  status: 'ok' | 'empty' | 'error';
  symbol: string | null;
  bars: VelaSpikeBar[];
  message?: string;
  delayNote: string | null;
}

export interface BriefSnapshot {
  brief: RouteHit<DigiquantRead<BriefApiData>>;
  portfolio: RouteHit<DigiquantRead<PortfolioApiData>>;
  allocations: RouteHit<DigiquantRead<AllocationsData>>;
  /** True when theses were not read because the brief date is missing. */
  thesesSkipped: boolean;
  theses: RouteHit<ThesisTableRow[]>;
  runHealth: RouteHit<RunHealthRow[]>;
  trace: 'present' | 'none' | 'unknown';
  closes: MoverClose[];
  chart: ChartSnap;
}

export interface DecisionBody {
  kind: 'decision';
  badge: string;
  bookAsOf: string;
  day: string;
  since: string;
  sinceStart: string;
  invested: string;
  events: { ticker: string; event: string; detail: string }[];
}

export interface SignalRow {
  key: string;
  id: string;
  name: string;
  state: string;
  note: string;
}

export interface BriefPaneView extends DeskPaneModel {
  emptyLabel?: string;
  body:
    | DecisionBody
    | { kind: 'signals'; rows: SignalRow[] }
    | { kind: 'allocation'; nameCount: number; cash: string; invested: string; rows: { ticker: string; weight: string }[] }
    | { kind: 'movers'; rows: { ticker: string; mark: string; day: string; tone: 'up' | 'down' | 'flat' }[] }
    | { kind: 'breaks'; lines: string[] }
    | { kind: 'gloomberg-quotes'; marks: { ticker: string; mark: string }[] }
    | { kind: 'gloomberg-tape' }
    | { kind: 'luxalgo'; symbol: string | null; barCount: number; delayNote: string | null; bars: VelaSpikeBar[]; timeframe: string }
    | { kind: 'run'; date: string; runType: string; status: string; segments: string; trace: string };
}

type Position = PortfolioApiData['positions'][number];

/** Largest non-cash weight. Null weights are skipped — no default symbol. */
export function focusSymbol(positions: Position[]): string | null {
  let best: { ticker: string; weight: number } | null = null;
  for (const position of positions) {
    if (position.is_cash || isCashTicker(position.ticker)) continue;
    const weight = position.scaled_weight_pct ?? position.weight_pct;
    if (weight == null || !Number.isFinite(weight)) continue;
    const ticker = position.ticker.trim().toUpperCase();
    if (!ticker) continue;
    if (
      !best ||
      weight > best.weight ||
      (weight === best.weight && ticker.localeCompare(best.ticker) < 0)
    ) {
      best = { ticker, weight };
    }
  }
  return best?.ticker ?? null;
}

function criteria(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => String(item).trim()).filter((item) => item.length > 0);
}

function readEvents(raw: unknown): DecisionBody['events'] {
  if (!Array.isArray(raw)) return [];
  const events: DecisionBody['events'] = [];
  for (const item of raw) {
    if (item == null || typeof item !== 'object') continue;
    const rec = item as Record<string, unknown>;
    const ticker = typeof rec.ticker === 'string' ? rec.ticker.trim() : '';
    const event = typeof rec.event === 'string' ? rec.event.trim() : '';
    const reason = typeof rec.reason === 'string' ? rec.reason.trim() : '';
    if (!ticker && !event && !reason) continue;
    events.push({
      ticker: ticker || EM_DASH,
      event: event || EM_DASH,
      detail: reason || EM_DASH,
    });
  }
  return events;
}

function phaseFromHit(hit: RouteHit<unknown>, isEmpty: boolean): PaneState {
  if (hit.status === 'error') return 'error';
  if (hit.status === 'empty' || isEmpty) return 'empty';
  return 'ready';
}

function catalog(id: string): DeskPaneModel {
  const pane = BRIEF_PANES.find((item) => item.id === id);
  if (!pane) throw new Error(`unknown brief pane ${id}`);
  return pane;
}

function withState(
  id: string,
  state: PaneState,
  errorMessage: string | undefined,
  extra?: Partial<DeskPaneModel>,
): DeskPaneModel {
  return { ...catalog(id), ...extra, state, errorMessage: state === 'error' ? errorMessage : undefined };
}

function latestRun(rows: RunHealthRow[]): RunHealthRow | null {
  if (rows.length === 0) return null;
  return [...rows].sort((a, b) => (b.created_at ?? '').localeCompare(a.created_at ?? ''))[0] ?? null;
}

function countOrDash(value: number | null | undefined): string {
  return value != null && Number.isFinite(value) ? String(value) : EM_DASH;
}

/** Loading frames — one per catalog pane. No figures. */
export function loadingBriefPanes(timeframe: string): BriefPaneView[] {
  return BRIEF_PANES.map((pane) => ({
    ...pane,
    state: 'loading' as const,
    body: emptyBody(pane.id, timeframe),
  }));
}

function emptyBody(id: string, timeframe: string): BriefPaneView['body'] {
  switch (id) {
    case 'decision':
      return {
        kind: 'decision',
        badge: EM_DASH,
        bookAsOf: EM_DASH,
        day: EM_DASH,
        since: EM_DASH,
        sinceStart: EM_DASH,
        invested: EM_DASH,
        events: [],
      };
    case 'signals':
      return { kind: 'signals', rows: [] };
    case 'allocation':
      return { kind: 'allocation', nameCount: 0, cash: EM_DASH, invested: EM_DASH, rows: [] };
    case 'movers':
      return { kind: 'movers', rows: [] };
    case 'breaks':
      return { kind: 'breaks', lines: [] };
    case 'gloomberg-quotes':
      return { kind: 'gloomberg-quotes', marks: [] };
    case 'gloomberg-tape':
      return { kind: 'gloomberg-tape' };
    case 'luxalgo':
      return { kind: 'luxalgo', symbol: null, barCount: 0, delayNote: null, bars: [], timeframe };
    case 'run':
      return { kind: 'run', date: EM_DASH, runType: EM_DASH, status: EM_DASH, segments: EM_DASH, trace: EM_DASH };
    default:
      throw new Error(`unknown brief pane ${id}`);
  }
}

function thesesForDate(rows: ThesisTableRow[], date: string): ThesisTableRow[] {
  return rows.filter((row) => (row.date ?? '').trim() === date);
}

function killLines(rows: ThesisTableRow[]): string[] {
  const lines: string[] = [];
  for (const row of rows) {
    const label = textOrDash(row.thesis_id ?? row.name);
    const invalidation = row.invalidation?.trim() ?? '';
    if (invalidation) lines.push(`${label}: ${invalidation}`);
    for (const item of criteria(row.invalidation_criteria)) {
      lines.push(`${label}: ${item}`);
    }
  }
  return lines;
}

/**
 * Map a loaded snapshot onto pane models. Null percents stay em dashes.
 * Gloomberg never receives headline copy.
 */
export function buildBriefPanes(snapshot: BriefSnapshot, timeframe: string): BriefPaneView[] {
  const briefData = snapshot.brief.status === 'ok' ? snapshot.brief.data?.data : undefined;
  const bookDate = briefData?.book_as_of ?? null;
  const datedTheses =
    bookDate && snapshot.theses.status === 'ok'
      ? thesesForDate(snapshot.theses.data ?? [], bookDate)
      : [];

  const decisionState = phaseFromHit(snapshot.brief, briefData?.book_as_of == null);
  const decisionBody: DecisionBody = {
    kind: 'decision',
    badge: provenanceBadge(briefData?.overlay),
    bookAsOf: textOrDash(briefData?.book_as_of),
    day: formatSignedPct(briefData?.day_return_pct),
    since: formatSignedPct(briefData?.since_inception_pct),
    sinceStart: textOrDash(briefData?.since_inception_start_date),
    invested: formatWeight(briefData?.invested_pct),
    events: readEvents(briefData?.session_events),
  };

  let signalsState: PaneState;
  let signalsError: string | undefined;
  if (snapshot.brief.status === 'error') {
    signalsState = 'error';
    signalsError = 'Brief date withheld.';
  } else if (!bookDate || snapshot.thesesSkipped) {
    signalsState = 'empty';
  } else if (snapshot.theses.status === 'error') {
    signalsState = 'error';
    signalsError = snapshot.theses.message;
  } else if (datedTheses.length === 0) {
    signalsState = 'empty';
  } else {
    signalsState = 'ready';
  }

  const portfolio = snapshot.portfolio.status === 'ok' ? snapshot.portfolio.data?.data : undefined;
  const held = (portfolio?.positions ?? []).filter(
    (position) => !position.is_cash && !isCashTicker(position.ticker),
  );
  const allocationState = phaseFromHit(
    snapshot.portfolio,
    portfolio == null || (portfolio.book_as_of == null && held.length === 0),
  );

  const allocationRows = held.map((position) => ({
    ticker: position.ticker.trim().toUpperCase() || EM_DASH,
    weight: formatWeight(position.scaled_weight_pct ?? position.weight_pct),
  }));

  const allocData = snapshot.allocations.status === 'ok' ? snapshot.allocations.data?.data : undefined;
  const moverRows =
    snapshot.allocations.status === 'ok'
      ? deriveBookMovers(
          (allocData?.rows ?? []).map((row) => ({
            ticker: row.ticker,
            currentPrice: row.current_price,
          })),
          snapshot.closes,
        )
      : [];
  const moversState = phaseFromHit(snapshot.allocations, moverRows.length === 0);

  let breaksState: PaneState;
  let breaksError: string | undefined;
  const lines = killLines(datedTheses);
  if (snapshot.brief.status === 'error') {
    breaksState = 'error';
    breaksError = 'Brief date withheld.';
  } else if (!bookDate || snapshot.thesesSkipped) {
    breaksState = 'empty';
  } else if (snapshot.theses.status === 'error') {
    breaksState = 'error';
    breaksError = snapshot.theses.message;
  } else if (lines.length === 0) {
    breaksState = 'empty';
  } else {
    breaksState = 'ready';
  }

  const gloomState: PaneState =
    snapshot.allocations.status === 'error'
      ? 'error'
      : snapshot.allocations.status === 'empty'
        ? 'empty'
        : 'ready';
  const marks =
    gloomState === 'ready'
      ? (allocData?.rows ?? []).map((row) => ({
          ticker: row.ticker.trim().toUpperCase() || EM_DASH,
          mark: formatMark(row.current_price),
        }))
      : [];

  const chartState: PaneState =
    snapshot.chart.status === 'error' ? 'error' : snapshot.chart.status === 'empty' ? 'empty' : 'ready';
  const luxTitle = snapshot.chart.symbol ? `LuxAlgo · ${snapshot.chart.symbol}` : 'LuxAlgo';

  const runs = snapshot.runHealth.status === 'ok' ? (snapshot.runHealth.data ?? []) : [];
  const latest = latestRun(runs);
  const runState = phaseFromHit(snapshot.runHealth, runs.length === 0);
  const traceLabel =
    snapshot.trace === 'present' ? 'present' : snapshot.trace === 'none' ? 'none' : EM_DASH;

  const signalRows: SignalRow[] = datedTheses.map((row, index) => ({
    key: row.thesis_id?.trim() || `row-${index}`,
    id: textOrDash(row.thesis_id),
    name: textOrDash(row.name),
    state: textOrDash(row.status),
    note: textOrDash(row.notes),
  }));

  return [
    {
      ...withState('decision', decisionState, snapshot.brief.message),
      body: decisionBody,
    },
    {
      ...withState('signals', signalsState, signalsError),
      body: { kind: 'signals', rows: signalsState === 'ready' ? signalRows : [] },
    },
    {
      ...withState('allocation', allocationState, snapshot.portfolio.message),
      body: {
        kind: 'allocation',
        nameCount: held.length,
        cash: formatWeight(portfolio?.invested.cash_pct),
        invested: formatWeight(portfolio?.invested.kpi_pct),
        rows: allocationState === 'ready' ? allocationRows : [],
      },
    },
    {
      ...withState('movers', moversState, snapshot.allocations.message),
      body: {
        kind: 'movers',
        rows:
          moversState === 'ready'
            ? moverRows.map((row) => ({
                ticker: row.ticker,
                mark: formatMark(row.mark),
                day: formatSignedPct(row.dayPct),
                tone: row.dayPct == null || row.dayPct === 0 ? 'flat' : row.dayPct > 0 ? 'up' : 'down',
              }))
            : [],
      },
    },
    {
      ...withState('breaks', breaksState, breaksError),
      emptyLabel:
        bookDate && datedTheses.length > 0 && lines.length === 0
          ? 'No kill conditions on this book date.'
          : undefined,
      body: { kind: 'breaks', lines: breaksState === 'ready' ? lines : [] },
    },
    {
      ...withState('gloomberg-quotes', gloomState, snapshot.allocations.message),
      body: { kind: 'gloomberg-quotes', marks },
    },
    {
      ...withState('gloomberg-tape', gloomState, snapshot.allocations.message),
      body: { kind: 'gloomberg-tape' },
    },
    {
      ...withState('luxalgo', chartState, snapshot.chart.message, { title: luxTitle }),
      emptyLabel: snapshot.chart.symbol
        ? 'No series is drawn in this state.'
        : 'No book symbol to chart.',
      body: {
        kind: 'luxalgo',
        symbol: snapshot.chart.symbol,
        barCount: snapshot.chart.bars.length,
        delayNote: snapshot.chart.delayNote,
        bars: chartState === 'ready' ? snapshot.chart.bars : [],
        timeframe,
      },
    },
    {
      ...withState('run', runState, snapshot.runHealth.message),
      body: {
        kind: 'run',
        date: textOrDash(latest?.run_date),
        runType: textOrDash(latest?.run_type),
        status: textOrDash(latest?.status),
        segments: `ok ${countOrDash(latest?.segments_ok)} · carried ${countOrDash(latest?.segments_carried)} · failed ${countOrDash(latest?.segments_failed)}`,
        trace: traceLabel,
      },
    },
  ];
}
