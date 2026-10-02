/**
 * Brief reads against digiquant house routes (plan §4.2 path table).
 * `getFullDashboardData()` is intentionally not used.
 */
import { ApiError } from '@/lib/api-client';
import { fetchMarketCloses } from '@/lib/market-data';
import { fetchVelaBars, type VelaTimeframe } from '@/lib/vela-bars';
import { isCashTicker } from '@/lib/book-reconciliation';
import {
  getAllocations,
  getBrief,
  getPortfolio,
  getTable,
  type RunHealthRow,
  type ThesisTableRow,
} from '@/lib/desk/digiquant';
import type { MoverClose } from '@/lib/desk/movers';
import { focusSymbol, type BriefSnapshot, type RouteHit } from './model';

function isNotFound(err: unknown): boolean {
  return err instanceof ApiError && (err.status === 404 || err.code === 'not_found');
}

export function paneErrorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error && err.message.trim()) return err.message;
  return 'The read failed.';
}

async function settle<T>(
  promise: Promise<T>,
): Promise<{ ok: true; value: T } | { ok: false; error: unknown }> {
  try {
    return { ok: true, value: await promise };
  } catch (error) {
    return { ok: false, error };
  }
}

function hit<T>(
  result: { ok: true; value: T } | { ok: false; error: unknown },
): RouteHit<T> {
  if (result.ok) return { status: 'ok', data: result.value };
  if (isNotFound(result.error)) return { status: 'empty' };
  return { status: 'error', message: paneErrorMessage(result.error) };
}

function shiftUtcDate(iso: string, days: number): string | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(Date.UTC(year, month - 1, day));
  if (Number.isNaN(date.getTime())) return null;
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function latestRun(rows: RunHealthRow[]): RunHealthRow | null {
  if (rows.length === 0) return null;
  return [...rows].sort((a, b) => (b.created_at ?? '').localeCompare(a.created_at ?? ''))[0] ?? null;
}

/** Load every Brief pane. One route failing does not zero the others. */
export async function loadBriefSnapshot(timeframe: VelaTimeframe): Promise<BriefSnapshot> {
  const [briefR, portfolioR, allocationsR, runR] = await Promise.all([
    settle(getBrief({ overlay: 'auto' })),
    settle(getPortfolio()),
    settle(getAllocations({ includeMarks: true })),
    settle(getTable<RunHealthRow>('run_health', { order: 'created_at.desc', limit: 20 })),
  ]);

  const brief = hit(briefR);
  const portfolio = hit(portfolioR);
  const allocations = hit(allocationsR);
  const runHealth = hit(runR);

  const bookDate = briefR.ok ? briefR.value.data.book_as_of : null;
  let thesesSkipped = true;
  let theses: RouteHit<ThesisTableRow[]> = { status: 'ok', data: [] };
  if (bookDate) {
    thesesSkipped = false;
    theses = hit(
      await settle(getTable<ThesisTableRow>('theses', { eq: { date: bookDate }, limit: 100 })),
    );
  }

  let trace: BriefSnapshot['trace'] = 'unknown';
  if (runR.ok) {
    const run = latestRun(runR.value);
    if (!run?.run_id) {
      trace = 'none';
    } else {
      const traceR = await settle(
        getTable<{ run_id?: string }>('run_event_trace', {
          eq: { run_id: run.run_id },
          limit: 1,
        }),
      );
      if (!traceR.ok) trace = 'unknown';
      else trace = traceR.value.length > 0 ? 'present' : 'none';
    }
  }

  let closes: MoverClose[] = [];
  if (allocationsR.ok) {
    const tickers = allocationsR.value.data.rows
      .map((row) => row.ticker.trim().toUpperCase())
      .filter((ticker) => ticker.length > 0 && !isCashTicker(ticker));
    const asOf = allocationsR.value.data.book_as_of ?? bookDate;
    const from = asOf ? shiftUtcDate(asOf, -14) : null;
    if (tickers.length > 0 && asOf && from) {
      const rows = await fetchMarketCloses(tickers, from, asOf);
      closes = rows.map((row) => ({ date: row.date, ticker: row.ticker, close: row.close }));
    }
  }

  const symbol = portfolioR.ok ? focusSymbol(portfolioR.value.data.positions) : null;
  let chart: BriefSnapshot['chart'] = {
    status: 'empty',
    symbol,
    bars: [],
    delayNote: null,
    message: symbol ? undefined : 'No book symbol to chart.',
  };
  if (symbol) {
    try {
      const bars = await fetchVelaBars(symbol, timeframe);
      chart =
        bars.bars.length === 0
          ? { status: 'empty', symbol, bars: [], delayNote: bars.delayNote }
          : { status: 'ok', symbol, bars: bars.bars, delayNote: bars.delayNote };
    } catch (error) {
      chart = {
        status: 'error',
        symbol,
        bars: [],
        delayNote: null,
        message: paneErrorMessage(error),
      };
    }
  }

  return {
    brief,
    portfolio,
    allocations,
    thesesSkipped,
    theses,
    runHealth,
    trace,
    closes,
    chart,
  };
}
