/**
 * TODO(slice-b): Slice B owns `lib/desk/movers.ts`. Brief imports
 * `deriveBookMovers` from here until that module replaces this seam.
 *
 * Client-derived book movers. There is no `GET /movers` route.
 * Day percent is mark versus the prior market close. A name with no mark
 * and no close stays an em dash — this function does not invent a percent.
 */

export interface MoverInputRow {
  ticker: string;
  currentPrice: number | null;
  isCash?: boolean;
}

export interface MoverClose {
  date: string;
  ticker: string;
  close: number;
}

export interface BookMover {
  ticker: string;
  /** Allocation mark, else the latest finite close. Null when neither exists. */
  mark: number | null;
  /** Null when the mark is missing or there is no prior close. */
  dayPct: number | null;
}

function finiteOrNull(value: number | null | undefined): number | null {
  return value != null && Number.isFinite(value) ? value : null;
}

function seriesByTicker(closes: MoverClose[]): Map<string, { date: string; close: number }[]> {
  const byTicker = new Map<string, Map<string, number>>();
  for (const row of closes) {
    const close = finiteOrNull(row.close);
    const ticker = row.ticker.trim().toUpperCase();
    const date = row.date.trim();
    if (close == null || !ticker || !date) continue;
    let byDate = byTicker.get(ticker);
    if (!byDate) {
      byDate = new Map();
      byTicker.set(ticker, byDate);
    }
    byDate.set(date, close);
  }
  const out = new Map<string, { date: string; close: number }[]>();
  for (const [ticker, byDate] of byTicker) {
    const series = [...byDate.entries()]
      .map(([date, close]) => ({ date, close }))
      .sort((a, b) => a.date.localeCompare(b.date));
    out.set(ticker, series);
  }
  return out;
}

/** Top day moves for the held book. Missing marks sort last and stay null. */
export function deriveBookMovers(rows: MoverInputRow[], closes: MoverClose[]): BookMover[] {
  const series = seriesByTicker(closes);
  const held = new Map<string, number | null>();
  for (const row of rows) {
    const ticker = row.ticker.trim().toUpperCase();
    if (!ticker || row.isCash || ticker === 'CASH') continue;
    const price = finiteOrNull(row.currentPrice);
    const prev = held.get(ticker);
    if (prev === undefined || (prev == null && price != null)) held.set(ticker, price);
  }

  const movers: BookMover[] = [];
  for (const [ticker, currentPrice] of held) {
    const points = series.get(ticker) ?? [];
    const latest = points.length > 0 ? points[points.length - 1]!.close : null;
    const prior = points.length > 1 ? points[points.length - 2]!.close : null;
    const mark = currentPrice ?? latest;
    const dayPct =
      mark == null || prior == null || prior === 0 ? null : ((mark - prior) / prior) * 100;
    movers.push({ ticker, mark, dayPct });
  }

  movers.sort((a, b) => {
    const aMissing = a.dayPct == null;
    const bMissing = b.dayPct == null;
    if (aMissing !== bMissing) return aMissing ? 1 : -1;
    if (a.dayPct != null && b.dayPct != null) {
      const byAbs = Math.abs(b.dayPct) - Math.abs(a.dayPct);
      if (byAbs !== 0) return byAbs;
    }
    return a.ticker.localeCompare(b.ticker);
  });
  return movers;
}
