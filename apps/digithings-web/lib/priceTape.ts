"use client";

import { useEffect, useState } from "react";
import type { TickerItem } from "@digithings/ui";

/**
 * The digithings.ai price tape (round 3, #4429).
 *
 * The digiquant band used to show eight hard-coded quotes. The owner's note:
 * "make the live price banner true". This hook is that banner's data layer: the
 * real latest close and the real prior-session change for the majors, read from
 * the same public market-data Worker `digiquant.io` already uses
 * (`GET {NEXT_PUBLIC_MARKET_DATA_URL}/v1/market/closes`).
 *
 * WHAT "LIVE" MEANS HERE. This is not a WebSocket tick stream. It is the latest
 * daily close the R2 archive holds, so the figure is a real price and the change
 * is a real prior-session move — and the band labels it `markets · latest close`
 * rather than a word that would overstate it. A seed is deliberately not a live
 * tick, which is why nothing in this module claims streaming.
 *
 * WHY IT DEGRADES QUIETLY. A tape is decoration on a marketing page. If the
 * Worker is unset, slow or down, the band keeps a muted "connecting" line rather
 * than an error, a spinner or a blank strip — and because the fetch lives in an
 * effect, the static export prerenders that connecting line and never opens a
 * socket during render.
 *
 * NO SUPABASE. `digiquant.io` layers the Worker seed with a Realtime subscription
 * for intraday equity moves; this app takes only the keyless, public, R2-backed
 * read, so the landing page gains one GET and no second service.
 */

/** The Worker 400s above this rather than truncating. Our universe is one batch. */
const MAX_TICKERS_PER_REQUEST = 25;

/** A window wide enough to hold two sessions, so a real change is computable. */
const SEED_LOOKBACK_DAYS = 14;

/** Past this, the band settles on its connecting line instead of hanging. */
const REQUEST_TIMEOUT_MS = 8_000;

/**
 * Crypto first, then the equity/ETF majors — the order the digiquant tape reads
 * in. These are the stored-universe symbols that the Worker actually serves; the
 * archive also holds a few the venue has no product for, which are left out on
 * purpose rather than shown as blanks.
 */
export const TAPE_SYMBOLS: readonly string[] = [
  "BTC-USD",
  "ETH-USD",
  "SOL-USD",
  "XRP-USD",
  "DOGE-USD",
  "ADA-USD",
  "AVAX-USD",
  "LINK-USD",
  "DOT-USD",
  "BCH-USD",
  "LTC-USD",
  "ATOM-USD",
  "NEAR-USD",
  "SPY",
  "QQQ",
  "DIA",
  "IWM",
  "GLD",
  "TLT",
  "UUP",
  "EFA",
  "EEM",
  "HYG",
];

/** One row of the Worker's `/v1/market/closes` payload. */
export interface MarketCloseRow {
  date: string;
  ticker: string;
  close: number;
}

/**
 * The market-data origin, read per call rather than at module scope: the
 * `NEXT_PUBLIC_*` export is inlined at build time, and tests stub the env
 * between imports.
 */
function marketDataBaseUrl(): string {
  const raw = process.env.NEXT_PUBLIC_MARKET_DATA_URL ?? "";
  return raw.trim().replace(/\/+$/, "");
}

/** Today minus the lookback, as an ISO date — always in the past by construction. */
export function seedWindowStart(now: Date = new Date()): string {
  return new Date(now.getTime() - SEED_LOOKBACK_DAYS * 86_400_000)
    .toISOString()
    .slice(0, 10);
}

/**
 * Price formatting for the tape. A four-figure index and a sub-dollar token both
 * have to sit on the same strip legibly, so the decimal count follows magnitude:
 * nothing below $1 should print as `0.00`.
 */
export function fmtTapePrice(price: number): string {
  if (!Number.isFinite(price)) return "—";
  const digits = price >= 1000 ? 0 : price >= 1 ? 2 : 4;
  return price.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

/** The strip prints signed-ness as a colour, so the number itself is unsigned. */
export function fmtTapeChange(pct: number): string {
  if (!Number.isFinite(pct)) return "0.00%";
  return `${Math.abs(pct).toFixed(2)}%`;
}

/**
 * Fold the Worker's rows into tape items: group by ticker, order by date, and
 * take the latest close against the one before it. A symbol with a single
 * session in the window shows no change rather than a fabricated one, and blank
 * or non-numeric rows are dropped instead of rendered as `NaN`.
 */
export function tapeRowsToItems(rows: readonly MarketCloseRow[]): TickerItem[] {
  const byTicker = new Map<string, MarketCloseRow[]>();
  for (const row of rows) {
    const key = String(row.ticker ?? "")
      .trim()
      .toUpperCase();
    const close = Number(row.close);
    if (!key || !Number.isFinite(close)) continue;
    const list = byTicker.get(key);
    if (list) list.push({ date: row.date, ticker: key, close });
    else byTicker.set(key, [{ date: row.date, ticker: key, close }]);
  }

  const items: TickerItem[] = [];
  for (const [ticker, list] of byTicker) {
    list.sort((a, b) => a.date.localeCompare(b.date));
    const latest = list[list.length - 1];
    const prior = list.length > 1 ? list[list.length - 2] : undefined;
    const changePct =
      prior && prior.close !== 0 ? ((latest.close - prior.close) / prior.close) * 100 : 0;
    items.push({
      symbol: ticker,
      last: fmtTapePrice(latest.close),
      change: fmtTapeChange(changePct),
      up: changePct >= 0,
    });
  }
  return items;
}

async function fetchBatch(
  symbols: readonly string[],
  base: string,
  signal: AbortSignal,
): Promise<MarketCloseRow[]> {
  const query = `tickers=${encodeURIComponent(symbols.join(","))}&from=${seedWindowStart()}`;
  const response = await fetch(`${base}/v1/market/closes?${query}`, { signal });
  if (!response.ok) throw new Error(`market data responded ${response.status}`);
  const payload = (await response.json()) as { rows?: MarketCloseRow[] };
  return payload.rows ?? [];
}

/**
 * Read the whole tape. All-or-nothing: a failed batch throws so the caller keeps
 * its connecting line, because a half-filled tape would pin some symbols to
 * closes from a different window and read as a data bug.
 */
export async function fetchPriceTape(
  symbols: readonly string[] = TAPE_SYMBOLS,
  signal?: AbortSignal,
): Promise<TickerItem[]> {
  const base = marketDataBaseUrl();
  if (!base) return [];
  const controller = signal ? null : new AbortController();
  const effective = signal ?? controller!.signal;

  const batches: string[][] = [];
  for (let i = 0; i < symbols.length; i += MAX_TICKERS_PER_REQUEST) {
    batches.push(symbols.slice(i, i + MAX_TICKERS_PER_REQUEST));
  }
  const results = await Promise.all(batches.map((batch) => fetchBatch(batch, base, effective)));
  return tapeRowsToItems(results.flat());
}

/**
 * The tape's client hook. Returns `items` (empty until the read lands) and
 * `ready`, so a caller can tell "still connecting" from "there is nothing to
 * show" without inventing a third state.
 */
export function usePriceTape(): { items: TickerItem[]; ready: boolean } {
  const [items, setItems] = useState<TickerItem[]>([]);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    let cancelled = false;

    (async () => {
      try {
        const next = await fetchPriceTape(TAPE_SYMBOLS, controller.signal);
        if (!cancelled) setItems(next);
      } catch {
        // Decoration, not a dependency: keep the connecting line, say nothing.
      } finally {
        clearTimeout(timer);
        if (!cancelled) setReady(true);
      }
    })();

    return () => {
      cancelled = true;
      clearTimeout(timer);
      controller.abort();
    };
  }, []);

  return { items, ready };
}
