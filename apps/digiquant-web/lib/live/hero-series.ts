/**
 * Hero chart series for `section#top`.
 *
 * The symbol order is `TAPE_SYMBOLS` — the same baseline list as the price
 * banner. This module does not keep a second list. A symbol is drawn only
 * when a feed returns real candles: Coinbase one-minute OHLC when that
 * product exists, otherwise daily OHLC from `/v1/market/closes`. A close
 * with no open/high/low is skipped. Nothing here resamples or fills a bar.
 */
import type { HeroBar } from "@/lib/hero-build";
import { fetchMarketCandleRows } from "./market-data";
import { displaySymbol } from "./market-bar";
import { TAPE_SYMBOLS } from "./tape-universe";

export const HERO_MINUTE = "1m";
export const HERO_DAY = "1D";
export const HERO_HOLD_MS = 20_000;
const MIN_BARS = 2;
const COINBASE_CANDLES = "https://api.exchange.coinbase.com/products";
const MARKET_LOOKBACK_MS = 200 * 86_400_000;

export type HeroSeries = {
  symbol: string;
  /** Label painted on the chart. Matches the bars, not a wished-for interval. */
  timeframe: typeof HERO_MINUTE | typeof HERO_DAY;
  /** Vela timeframe token for those bars. */
  velaTimeframe: "1" | "D";
  source: "coinbase" | "market";
  bars: HeroBar[];
};

export function heroWatermark(symbol: string, timeframe: string): string {
  return `${displaySymbol(symbol)} · ${timeframe}`;
}

/** ISO day far enough back to hold a short daily window, not the full archive. */
export function marketLookback(now: Date = new Date()): string {
  return new Date(now.getTime() - MARKET_LOOKBACK_MS).toISOString().slice(0, 10);
}

function finite(value: unknown): number | null {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

function isAbort(err: unknown): boolean {
  return err instanceof DOMException && err.name === "AbortError";
}

/** Coinbase `[time, low, high, open, close, volume]`, time in unix seconds. */
export function barsFromCoinbase(rows: unknown): HeroBar[] {
  if (!Array.isArray(rows)) return [];
  const out: HeroBar[] = [];
  for (const row of rows) {
    if (!Array.isArray(row) || row.length < 5) continue;
    const time = finite(row[0]);
    const low = finite(row[1]);
    const high = finite(row[2]);
    const open = finite(row[3]);
    const close = finite(row[4]);
    if (time === null || open === null || high === null || low === null || close === null) continue;
    if (high < low || high < open || high < close || low > open || low > close) continue;
    const volume = row.length > 5 ? finite(row[5]) : null;
    const bar: HeroBar = {
      time: time > 1e12 ? time : time * 1000,
      open,
      high,
      low,
      close,
    };
    if (volume !== null && volume >= 0) bar.volume = volume;
    out.push(bar);
  }
  out.sort((a, b) => a.time - b.time);
  return out.length >= MIN_BARS ? out : [];
}

/** Daily rows. Close-only rows are dropped — they are not candles. */
export function barsFromMarketRows(rows: readonly unknown[]): HeroBar[] {
  const out: HeroBar[] = [];
  for (const row of rows) {
    if (!row || typeof row !== "object") continue;
    const rec = row as Record<string, unknown>;
    const date = typeof rec.date === "string" ? rec.date : "";
    const time = Date.parse(`${date}T00:00:00.000Z`);
    const open = finite(rec.open);
    const high = finite(rec.high);
    const low = finite(rec.low);
    const close = finite(rec.close);
    if (!Number.isFinite(time)) continue;
    if (open === null || high === null || low === null || close === null) continue;
    if (open <= 0 || high <= 0 || low <= 0 || close <= 0) continue;
    if (high < low || high < open || high < close || low > open || low > close) continue;
    const volume = finite(rec.volume);
    const bar: HeroBar = { time, open, high, low, close };
    if (volume !== null && volume >= 0) bar.volume = volume;
    out.push(bar);
  }
  out.sort((a, b) => a.time - b.time);
  return out.length >= MIN_BARS ? out : [];
}

async function fetchCoinbaseMinuteBars(symbol: string, signal?: AbortSignal): Promise<HeroBar[]> {
  if (!symbol.endsWith("-USD")) return [];
  try {
    const url = `${COINBASE_CANDLES}/${encodeURIComponent(symbol)}/candles?granularity=60`;
    const res = await fetch(url, { signal });
    if (!res.ok) return [];
    return barsFromCoinbase(await res.json());
  } catch (err) {
    if (isAbort(err)) throw err;
    return [];
  }
}

/** Real candles for one baseline symbol, or null when neither feed has them. */
export async function loadHeroSeries(symbol: string, signal?: AbortSignal): Promise<HeroSeries | null> {
  const minute = await fetchCoinbaseMinuteBars(symbol, signal);
  if (minute.length >= MIN_BARS) {
    return { symbol, timeframe: HERO_MINUTE, velaTimeframe: "1", source: "coinbase", bars: minute };
  }
  const rows = await fetchMarketCandleRows(symbol, marketLookback(), signal);
  const daily = barsFromMarketRows(rows);
  if (daily.length < MIN_BARS) return null;
  return { symbol, timeframe: HERO_DAY, velaTimeframe: "D", source: "market", bars: daily };
}

/**
 * Next drawable symbol at or after `start`, walking `symbols` once.
 * Default order is the tape universe. A loader that returns null is skipped.
 */
export async function nextHero(
  start: number,
  load: (symbol: string, signal?: AbortSignal) => Promise<HeroSeries | null> = loadHeroSeries,
  signal?: AbortSignal,
  symbols: readonly string[] = TAPE_SYMBOLS,
): Promise<{ index: number; series: HeroSeries } | null> {
  const count = symbols.length;
  if (count === 0) return null;
  const origin = Number.isFinite(start) ? start : 0;
  for (let step = 0; step < count; step++) {
    if (signal?.aborted) return null;
    const index = (((origin + step) % count) + count) % count;
    const series = await load(symbols[index], signal);
    if (series && series.bars.length >= MIN_BARS) return { index, series };
  }
  return null;
}
