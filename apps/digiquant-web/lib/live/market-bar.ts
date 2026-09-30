"use client";

/**
 * useMarketBar — data for the MarketBar chrome strip (design plan 3.1 / 7).
 *
 * Crypto (BTC/ETH/SOL-USD): Coinbase Exchange public WebSocket `ticker`
 * channel. Keyless (the "Coinbase Market Data" endpoint is public; only
 * ws-direct needs auth), browsers do not apply CORS to WebSockets, and a
 * subscribe frame must be sent within 5s of connect. Rate limits: 8 connects/s
 * per IP, 100 client msgs/s per IP: we open one socket and send one subscribe.
 *
 * Equities/ETFs (SPY, QQQ): daily closes from the R2 market Worker
 * (`/v1/market/closes`, via `fetchBenchmarkHistory`; CORS allowlist covers
 * https://digiquant.io). Each cell carries its own "as of YYYY-MM-DD close"
 * stamp. When `NEXT_PUBLIC_MARKET_DATA_URL` is unset or the call fails, those
 * cells are OMITTED. Prices are never invented and never rendered at SSR:
 * the first render is `{cells: [], status: "connecting"}`.
 */
import { useEffect, useState } from "react";
import { fetchBenchmarkHistory, seedWindowStart } from "./market-data";
import { num } from "./quote-transforms";

export const COINBASE_WS_URL = "wss://ws-feed.exchange.coinbase.com";
export const CRYPTO_PRODUCTS = ["BTC-USD", "ETH-USD", "SOL-USD"] as const;
export const EQUITY_SYMBOLS = ["SPY", "QQQ"] as const;

/** Socket open + tick within this window = "live". */
export const LIVE_WINDOW_MS = 15_000;
/** No tick for this long (or never reconnected) = "offline". */
export const OFFLINE_AFTER_MS = 60_000;
export const BACKOFF_BASE_MS = 1_000;
export const BACKOFF_MAX_MS = 30_000;
const STATUS_TICK_MS = 1_000;
const FLUSH_MS = 400;
/** Failed attempts with no tick ever before the bar reads "offline". */
const OFFLINE_AFTER_FAILURES = 3;

export type MarketBarStatus = "connecting" | "live" | "stale" | "offline";

export interface MarketCell {
  symbol: string;
  kind: "crypto" | "equity";
  price: number;
  /** Percent points; null when the source gave no baseline. */
  changePct: number | null;
  /** Crypto: ISO time of last tick. Equity: YYYY-MM-DD of the close. */
  asOf: string;
  /** Pre-formatted strings for rendering. */
  value: string;
  change: string;
  stamp: string;
  /** Signed direction for --up/--down; null when unknown. */
  up: boolean | null;
}

export interface MarketBarState {
  cells: MarketCell[];
  status: MarketBarStatus;
  /** ISO time of the most recent crypto tick, else null. */
  asOf: string | null;
}

/* ------------------------------ formatters ------------------------------ */

/** Display symbol: "BTC-USD" -> "BTC". */
export function displaySymbol(symbol: string): string {
  return symbol.replace(/-USD$/, "");
}

export function formatPrice(price: number): string {
  if (!Number.isFinite(price)) return "—";
  const digits = Math.abs(price) >= 1 ? 2 : 4;
  return price.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function formatChange(changePct: number | null): string {
  if (changePct === null || !Number.isFinite(changePct)) return "—";
  const arrow = changePct >= 0 ? "▲" : "▼";
  return `${arrow}${Math.abs(changePct).toFixed(2)}%`;
}

export function formatCloseStamp(date: string): string {
  return `as of ${date} close`;
}

export function formatLiveStamp(iso: string): string {
  return `live ${iso.slice(11, 19)}Z`;
}

/* ------------------------------ tick parsing ----------------------------- */

export interface ParsedTick {
  productId: string;
  price: number;
  changePct: number | null;
  /** ISO timestamp. */
  time: string;
}

/**
 * Parse one raw ws frame. Returns null for anything that is not a usable
 * ticker for a product we asked for (subscriptions acks, errors, heartbeats).
 */
export function parseTick(
  raw: unknown,
  now: number = Date.now(),
  products: readonly string[] = CRYPTO_PRODUCTS,
): ParsedTick | null {
  let msg: unknown = raw;
  if (typeof raw === "string") {
    try {
      msg = JSON.parse(raw);
    } catch {
      return null;
    }
  }
  if (!msg || typeof msg !== "object") return null;
  const m = msg as Record<string, unknown>;
  if (m.type !== "ticker" || typeof m.product_id !== "string") return null;
  const productId = m.product_id.toUpperCase();
  if (!products.includes(productId)) return null;
  const price = num(m.price);
  if (price === null || price <= 0) return null;
  const open = num(m.open_24h);
  const changePct = open !== null && open > 0 ? ((price - open) / open) * 100 : null;
  const parsed = typeof m.time === "string" ? Date.parse(m.time) : NaN;
  const time = new Date(Number.isFinite(parsed) ? parsed : now).toISOString();
  return { productId, price, changePct, time };
}

export function cryptoCell(t: ParsedTick): MarketCell {
  return {
    symbol: t.productId,
    kind: "crypto",
    price: t.price,
    changePct: t.changePct,
    asOf: t.time,
    value: formatPrice(t.price),
    change: formatChange(t.changePct),
    stamp: formatLiveStamp(t.time),
    up: t.changePct === null ? null : t.changePct >= 0,
  };
}

/** Latest close + prior-session move from an ascending close series; null if empty. */
export function equityCell(symbol: string, series: { date: string; price: number }[]): MarketCell | null {
  if (series.length === 0) return null;
  const sorted = [...series].sort((a, b) => a.date.localeCompare(b.date));
  const last = sorted[sorted.length - 1];
  const prev = sorted.length > 1 ? sorted[sorted.length - 2].price : null;
  const changePct = prev !== null && prev > 0 ? ((last.price - prev) / prev) * 100 : null;
  return {
    symbol,
    kind: "equity",
    price: last.price,
    changePct,
    asOf: last.date,
    value: formatPrice(last.price),
    change: formatChange(changePct),
    stamp: formatCloseStamp(last.date),
    up: changePct === null ? null : changePct >= 0,
  };
}

/* ------------------------- status + feed controller ---------------------- */

/**
 * Pure status rule. `openedOnce`/`failures` cover the never-ticked case:
 * "connecting" until the first tick, unless repeated failures say otherwise.
 */
export function computeStatus(input: {
  now: number;
  open: boolean;
  lastTickAt: number | null;
  failures: number;
}): MarketBarStatus {
  const { now, open, lastTickAt, failures } = input;
  if (lastTickAt === null) {
    return failures >= OFFLINE_AFTER_FAILURES ? "offline" : "connecting";
  }
  const age = now - lastTickAt;
  if (open && age <= LIVE_WINDOW_MS) return "live";
  return age > OFFLINE_AFTER_MS ? "offline" : "stale";
}

/** Minimal WebSocket surface, so tests can inject a fake. */
export interface SocketLike {
  onopen: ((ev?: unknown) => void) | null;
  onmessage: ((ev: { data: unknown }) => void) | null;
  onclose: ((ev?: unknown) => void) | null;
  onerror: ((ev?: unknown) => void) | null;
  send(data: string): void;
  close(): void;
}

export interface CryptoFeedOptions {
  url?: string;
  products?: readonly string[];
  createSocket: (url: string) => SocketLike;
  onUpdate: (state: { cells: MarketCell[]; status: MarketBarStatus; asOf: string | null }) => void;
  now?: () => number;
}

export interface CryptoFeed {
  /** Begin connecting (idempotent). */
  start(): void;
  /** Close the socket and stop reconnecting (tab hidden). */
  pause(): void;
  /** Permanent teardown (unmount). */
  stop(): void;
}

export function createCryptoFeed(opts: CryptoFeedOptions): CryptoFeed {
  const url = opts.url ?? COINBASE_WS_URL;
  const products = opts.products ?? CRYPTO_PRODUCTS;
  const now = opts.now ?? Date.now;

  let ws: SocketLike | null = null;
  let open = false;
  let destroyed = false;
  let paused = true;
  let attempt = 0;
  let failures = 0;
  let lastTickAt: number | null = null;
  let lastTime: string | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let statusTimer: ReturnType<typeof setInterval> | null = null;
  let flushTimer: ReturnType<typeof setTimeout> | null = null;
  let lastStatus: MarketBarStatus | null = null;
  const cells = new Map<string, MarketCell>();

  const emit = () => {
    flushTimer = null;
    const status = computeStatus({ now: now(), open, lastTickAt, failures });
    lastStatus = status;
    opts.onUpdate({
      cells: products.map((p) => cells.get(p)).filter((c): c is MarketCell => Boolean(c)),
      status,
      asOf: lastTime,
    });
  };
  const scheduleFlush = () => {
    if (flushTimer === null) flushTimer = setTimeout(emit, FLUSH_MS);
  };
  const checkStatus = () => {
    const status = computeStatus({ now: now(), open, lastTickAt, failures });
    if (status !== lastStatus) emit();
  };

  const detach = () => {
    if (!ws) return;
    ws.onopen = ws.onmessage = ws.onclose = ws.onerror = null;
    try {
      ws.close();
    } catch {
      /* close() while connecting can throw */
    }
    ws = null;
    open = false;
  };

  const scheduleReconnect = () => {
    if (destroyed || paused || reconnectTimer) return;
    const delay = Math.min(BACKOFF_BASE_MS * 2 ** attempt, BACKOFF_MAX_MS);
    attempt += 1;
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      connect();
    }, delay);
  };

  const onDown = () => {
    open = false;
    ws = null;
    if (lastTickAt === null) failures += 1;
    checkStatus();
    scheduleReconnect();
  };

  function connect() {
    if (destroyed || paused || ws) return;
    let sock: SocketLike;
    try {
      sock = opts.createSocket(url);
    } catch {
      failures += 1;
      scheduleReconnect();
      return;
    }
    ws = sock;
    sock.onopen = () => {
      open = true;
      attempt = 0;
      sock.send(JSON.stringify({ type: "subscribe", product_ids: [...products], channels: ["ticker"] }));
      checkStatus();
    };
    sock.onmessage = (ev) => {
      const tick = parseTick(ev.data, now(), products);
      if (!tick) return;
      lastTickAt = now();
      lastTime = tick.time;
      failures = 0;
      cells.set(tick.productId, cryptoCell(tick));
      scheduleFlush();
    };
    sock.onclose = onDown;
    sock.onerror = () => {
      try {
        sock.close();
      } catch {
        /* onclose handles reconnect */
      }
    };
  }

  return {
    start() {
      if (destroyed) return;
      paused = false;
      if (!statusTimer) statusTimer = setInterval(checkStatus, STATUS_TICK_MS);
      connect();
    },
    pause() {
      paused = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      reconnectTimer = null;
      detach();
    },
    stop() {
      destroyed = true;
      paused = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (statusTimer) clearInterval(statusTimer);
      if (flushTimer) clearTimeout(flushTimer);
      reconnectTimer = statusTimer = flushTimer = null;
      detach();
    },
  };
}

/* --------------------------------- hook ---------------------------------- */

const INITIAL: MarketBarState = { cells: [], status: "connecting", asOf: null };

async function loadEquityCells(): Promise<MarketCell[]> {
  const from = seedWindowStart();
  const out = await Promise.all(
    EQUITY_SYMBOLS.map(async (s) => equityCell(s, await fetchBenchmarkHistory(s, from))),
  );
  return out.filter((c): c is MarketCell => c !== null);
}

export function useMarketBar(): MarketBarState {
  const [crypto, setCrypto] = useState<MarketBarState>(INITIAL);
  const [equities, setEquities] = useState<MarketCell[]>([]);

  useEffect(() => {
    let cancelled = false;
    void loadEquityCells()
      .then((cells) => {
        if (!cancelled) setEquities(cells);
      })
      .catch(() => {
        /* equities stay omitted */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (typeof WebSocket === "undefined") return;
    const feed = createCryptoFeed({
      createSocket: (url) => new WebSocket(url) as unknown as SocketLike,
      onUpdate: setCrypto,
    });
    const sync = () => {
      if (document.visibilityState === "hidden") feed.pause();
      else feed.start();
    };
    sync();
    document.addEventListener("visibilitychange", sync);
    return () => {
      document.removeEventListener("visibilitychange", sync);
      feed.stop();
    };
  }, []);

  return { cells: [...crypto.cells, ...equities], status: crypto.status, asOf: crypto.asOf };
}
