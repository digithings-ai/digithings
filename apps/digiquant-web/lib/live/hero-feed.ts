import { COINBASE_WS_URL, CRYPTO_PRODUCTS } from "./market-bar";

/** Live data for the hero chart: real one-minute candles from Coinbase's public
 *  Exchange REST endpoint (keyless, CORS-open) for backfill, then the public
 *  WebSocket `ticker` channel (the same keyless feed the price strip reads) to move
 *  the forming candle. Nothing here needs a secret. Any failure resolves to the
 *  caller's simulated fallback; prices are never invented. */

export const HERO_PRODUCTS = CRYPTO_PRODUCTS;
export type HeroProduct = (typeof HERO_PRODUCTS)[number];
export const HERO_GRANULARITY_S = 60;

export interface FeedCandle {
  /** Bucket start, unix seconds. */
  t: number;
  o: number;
  h: number;
  l: number;
  c: number;
}

const REST_BASE = "https://api.exchange.coinbase.com";
const RECONNECT_BASE_MS = 2_000;
const RECONNECT_MAX_MS = 30_000;

/** Coinbase returns `[time, low, high, open, close, volume]`, newest first. */
export async function fetchHeroCandles(product: HeroProduct, signal: AbortSignal): Promise<FeedCandle[]> {
  const res = await fetch(`${REST_BASE}/products/${product}/candles?granularity=${HERO_GRANULARITY_S}`, { signal });
  if (!res.ok) throw new Error(`candles ${res.status}`);
  const rows: unknown = await res.json();
  if (!Array.isArray(rows)) throw new Error("candles: unexpected payload");
  const out: FeedCandle[] = [];
  for (const row of rows) {
    if (!Array.isArray(row) || row.length < 5) continue;
    const [t, l, h, o, c] = row.map(Number);
    if ([t, l, h, o, c].every(Number.isFinite)) out.push({ t, o, h, l, c });
  }
  return out.sort((a, b) => a.t - b.t);
}

/** Folds one trade price into the candle series: updates the forming candle or opens
 *  the next minute, opening at the previous close so the series stays continuous. */
export function applyTick(candles: FeedCandle[], price: number, unixSec: number): void {
  const bucket = Math.floor(unixSec / HERO_GRANULARITY_S) * HERO_GRANULARITY_S;
  const last = candles[candles.length - 1];
  if (last && bucket <= last.t) {
    last.c = price;
    last.h = Math.max(last.h, price);
    last.l = Math.min(last.l, price);
    return;
  }
  const open = last ? last.c : price;
  candles.push({ t: bucket, o: open, h: Math.max(open, price), l: Math.min(open, price), c: price });
}

/** Opens the public ticker socket for one product and reconnects with backoff until
 *  the returned function is called. `onTick` gets the trade price and its unix time. */
export function openHeroTicker(
  product: HeroProduct,
  onTick: (price: number, unixSec: number) => void,
  onState: (open: boolean) => void,
): () => void {
  let ws: WebSocket | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let attempt = 0;
  let closed = false;

  const connect = () => {
    if (closed) return;
    ws = new WebSocket(COINBASE_WS_URL);
    ws.onopen = () => {
      ws?.send(JSON.stringify({ type: "subscribe", product_ids: [product], channels: ["ticker"] }));
    };
    ws.onmessage = (ev: MessageEvent) => {
      try {
        const msg = JSON.parse(String(ev.data)) as { type?: string; price?: string; time?: string };
        if (msg.type !== "ticker" || msg.price === undefined) return;
        const price = Number(msg.price);
        const at = msg.time ? Date.parse(msg.time) : Date.now();
        if (!Number.isFinite(price)) return;
        attempt = 0;
        onState(true);
        onTick(price, (Number.isFinite(at) ? at : Date.now()) / 1000);
      } catch {
        /* a malformed frame is skipped, the socket stays up */
      }
    };
    ws.onclose = () => {
      onState(false);
      if (closed) return;
      const delay = Math.min(RECONNECT_MAX_MS, RECONNECT_BASE_MS * 2 ** attempt++);
      timer = setTimeout(connect, delay);
    };
    ws.onerror = () => ws?.close();
  };

  connect();
  return () => {
    closed = true;
    if (timer) clearTimeout(timer);
    ws?.close();
  };
}
