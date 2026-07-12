"use client";

/**
 * useLivePrices (#1461) — merges the two browser price lanes into one map.
 *
 *   (a) Coinbase public keyless WS  → crypto product_ids (reconnect w/ backoff,
 *       %chg from `open_24h`, ticks coalesced ~400ms, socket closed on unmount).
 *   (b) Supabase Realtime broadcast "prices:live" → equities (subscribe with the
 *       anon client, unsubscribe on unmount).
 *   + a one-shot SEED from `public_price_latest` so values exist before the
 *     first tick and when a lane is dark (marked `stale`).
 *
 * SSR/static-export safe: no `window`/`WebSocket` access during render; every
 * connection lives in a client effect. Null-client safe: the equity+seed lanes
 * simply stay dark (no crash). Crypto streams regardless of Supabase config —
 * Coinbase is keyless and never touches the Supabase client.
 *
 * Returns a {@link LivePriceMap} keyed by uppercase symbol. Live ticks flip
 * `stale` to `false`; seeds keep it `true`. Consumers that value or badge
 * "live" must gate on `!stale`, not on mere presence.
 */
import { useEffect, useState } from "react";
import { supabase } from "./supabaseClient";
import type { LivePriceMap, LiveQuote, UseLivePricesOptions } from "./types";
import {
  applyQuotes,
  broadcastQuoteToLive,
  coinbaseTickerToLive,
  normalizeSymbols,
  parseBroadcastPayload,
  seedRowToLive,
  type CoinbaseTicker,
} from "./quote-transforms";

const COINBASE_WS_URL = "wss://ws-feed.exchange.coinbase.com";
const BROADCAST_CHANNEL = "prices:live";
const BROADCAST_EVENT = "quotes";
/** Coalesce Coinbase ticks into at most one state update per window. */
const FLUSH_MS = 400;
const BACKOFF_BASE_MS = 1_000;
const BACKOFF_MAX_MS = 30_000;

export function useLivePrices(options: UseLivePricesOptions = {}): LivePriceMap {
  const symbols = normalizeSymbols(options.symbols);
  const cryptoProductIds = normalizeSymbols(options.cryptoProductIds);
  const symbolsKey = symbols.join(",");
  const cryptoKey = cryptoProductIds.join(",");
  const client = "client" in options ? options.client ?? null : supabase;

  const [quotes, setQuotes] = useState<LivePriceMap>({});

  // Lane 1 — one-shot daily-close seed from public_price_latest. Seeds the UNION
  // of equities + crypto product_ids: `public_price_latest` carries the `-USD`
  // closes too, so crypto still shows a (stale) value before Coinbase connects
  // and when that lane is dark — consumers keep the two lists disjoint.
  useEffect(() => {
    const seedSymbols = [...new Set<string>([...symbols, ...cryptoProductIds])];
    if (!client || seedSymbols.length === 0) return;
    let cancelled = false;
    void (async () => {
      const { data, error } = await client
        .from("public_price_latest")
        .select("ticker, close, change_pct")
        .in("ticker", seedSymbols);
      if (cancelled || error || !Array.isArray(data)) return;
      const seeds = data
        .map((r) => seedRowToLive(r as { ticker?: unknown; close?: unknown; change_pct?: unknown }))
        .filter((q): q is LiveQuote => q !== null);
      if (seeds.length) setQuotes((prev) => applyQuotes(prev, seeds));
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- keys track array content
  }, [client, symbolsKey, cryptoKey]);

  // Lane 2 — equity quotes over the Supabase Realtime broadcast.
  useEffect(() => {
    if (!client) return;
    const allowed = new Set<string>([...symbols, ...cryptoProductIds]);
    const channel = client.channel(BROADCAST_CHANNEL);
    channel
      .on("broadcast", { event: BROADCAST_EVENT }, (message: { payload?: unknown }) => {
        const incoming = parseBroadcastPayload(message.payload);
        const now = Date.now();
        const batch: LiveQuote[] = [];
        for (const [sym, q] of Object.entries(incoming)) {
          const upper = sym.toUpperCase();
          if (allowed.size > 0 && !allowed.has(upper)) continue;
          batch.push(broadcastQuoteToLive(upper, q, now));
        }
        if (batch.length) setQuotes((prev) => applyQuotes(prev, batch));
      })
      .subscribe();
    return () => {
      void client.removeChannel(channel);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- keys track array content
  }, [client, symbolsKey, cryptoKey]);

  // Lane 3 — crypto over Coinbase's public WS (keyless, backoff, coalesced).
  useEffect(() => {
    if (cryptoProductIds.length === 0) return;
    if (typeof WebSocket === "undefined") return; // SSR / non-browser guard

    let ws: WebSocket | null = null;
    let closed = false;
    let attempt = 0;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let flushTimer: ReturnType<typeof setTimeout> | null = null;
    const buffer: Record<string, LiveQuote> = {};

    const flush = () => {
      flushTimer = null;
      const batch = Object.values(buffer);
      for (const k of Object.keys(buffer)) delete buffer[k];
      if (batch.length) setQuotes((prev) => applyQuotes(prev, batch));
    };
    const scheduleFlush = () => {
      if (flushTimer === null) flushTimer = setTimeout(flush, FLUSH_MS);
    };

    const scheduleReconnect = () => {
      if (closed) return;
      const delay = Math.min(BACKOFF_BASE_MS * 2 ** attempt, BACKOFF_MAX_MS);
      attempt += 1;
      reconnectTimer = setTimeout(connect, delay);
    };

    function connect() {
      if (closed) return;
      ws = new WebSocket(COINBASE_WS_URL);
      ws.onopen = () => {
        attempt = 0;
        ws?.send(
          JSON.stringify({ type: "subscribe", product_ids: cryptoProductIds, channels: ["ticker"] }),
        );
      };
      ws.onmessage = (ev: MessageEvent) => {
        let msg: CoinbaseTicker;
        try {
          msg = JSON.parse(typeof ev.data === "string" ? ev.data : "") as CoinbaseTicker;
        } catch {
          return;
        }
        const q = coinbaseTickerToLive(msg);
        if (q) {
          buffer[q.symbol] = q;
          scheduleFlush();
        }
      };
      ws.onclose = () => scheduleReconnect();
      ws.onerror = () => {
        try {
          ws?.close();
        } catch {
          /* close() during connecting can throw — reconnect handles it */
        }
      };
    }

    connect();
    return () => {
      closed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (flushTimer) clearTimeout(flushTimer);
      if (ws) {
        ws.onclose = null; // the close we trigger must not schedule a reconnect
        try {
          ws.close();
        } catch {
          /* ignore */
        }
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- cryptoKey tracks array content
  }, [cryptoKey]);

  return quotes;
}
