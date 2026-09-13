"use client";

/**
 * useLivePrices (#1461) — merges the two browser price lanes into one map.
 *
 *   (a) Coinbase public keyless WS  → crypto product_ids (reconnect w/ backoff,
 *       %chg from `open_24h`, ticks coalesced ~400ms, socket closed on unmount).
 *   (b) Supabase Realtime `postgres_changes` on `public.prices_live` → equities
 *       (subscribe with the anon client, unsubscribe on unmount). A TABLE, not a
 *       broadcast channel, and that is the security boundary — see lane 2 and
 *       #1807 before touching it.
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
import { useEffect, useId, useState } from "react";
import { supabase } from "./supabaseClient";
import type { LivePriceMap, LiveQuote, UseLivePricesOptions } from "./types";
import {
  applyQuotes,
  coinbaseTickerToLive,
  normalizeSymbols,
  priceRowToLive,
  seedRowToLive,
  type CoinbaseTicker,
} from "./quote-transforms";

const COINBASE_WS_URL = "wss://ws-feed.exchange.coinbase.com";
/**
 * Topic PREFIX for the equity lane — a per-hook-instance suffix is appended below.
 *
 * Purely a client-side label; it names no database object (the table below is what is
 * actually subscribed). Deliberately NOT the retired `prices:live`, so the two designs
 * cannot collide on one topic while old bundles are still cached in the wild.
 *
 * The per-instance suffix is load-bearing — do NOT collapse this back to a bare constant.
 * Two `useLivePrices` instances mount on the landing page (`LiveTickerRow` directly, and
 * `LivePortfolioPanel` via `useLivePortfolio`) against the same singleton client, and
 * `RealtimeClient.channel()` DEDUPES BY TOPIC (realtime-js 2.104.0, RealtimeClient.js:305-316)
 * — it returns the existing channel rather than creating a second one. Both instances would
 * then `.on()` the same channel, but only the first `.subscribe()` does anything
 * (RealtimeChannel.js:120 gates on `isClosed()`), so the join payload carries ONE
 * postgres_changes filter while the client holds TWO bindings. The server's `ok` reply is
 * then index-matched against those bindings, the second finds no counterpart, and
 * `_updatePostgresBindings` (RealtimeChannel.js:181-185) calls `unsubscribe()` and marks the
 * channel `errored` — killing the equity lane for BOTH consumers, silently: no exception,
 * no console error, just a tape frozen on lane 1's daily closes.
 *
 * This trap is specific to postgres_changes. The retired broadcast path had no id-matching,
 * so a shared topic was harmless there — which is exactly why it survived review as a
 * module constant until now.
 */
const PRICES_CHANNEL_PREFIX = "prices-live-db";
const PRICES_TABLE = "prices_live";
/** Coalesce inbound ticks into at most one state update per window (lanes 2+3). */
const FLUSH_MS = 400;
const BACKOFF_BASE_MS = 1_000;
const BACKOFF_MAX_MS = 30_000;

export function useLivePrices(options: UseLivePricesOptions = {}): LivePriceMap {
  const symbols = normalizeSymbols(options.symbols);
  const cryptoProductIds = normalizeSymbols(options.cryptoProductIds);
  const symbolsKey = symbols.join(",");
  const cryptoKey = cryptoProductIds.join(",");
  const client = "client" in options ? options.client ?? null : supabase;
  // Stable per-instance Realtime topic — see PRICES_CHANNEL_PREFIX for why sharing one
  // topic between hook instances silently kills the lane. `useId` is hydration-safe under
  // `output: "export"` and constant across re-renders and effect re-runs.
  const instanceId = useId();

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

  // Lane 2 — equity quotes as `postgres_changes` on `public.prices_live` (#1807).
  //
  // THIS IS A SECURITY BOUNDARY, NOT A TRANSPORT PREFERENCE. Do not "simplify" it back
  // onto a Realtime broadcast channel. It used to be one — `prices:live` — and that was
  // forgeable: broadcast messages are client-authored, delivery is a bare INSERT into
  // `realtime.messages`, `anon` holds INSERT on that table, and the anon key ships in
  // plaintext in this very bundle. Anyone could publish quotes that arrived here
  // indistinguishable from Finnhub's. The intended patch was RLS on `realtime.messages`;
  // it is UNIMPLEMENTABLE — that table is owned by `supabase_realtime_admin`, a role with
  // no members that we cannot join, so `CREATE POLICY` returns 42501 for us forever.
  //
  // Moving the feed onto a table we DO own closes it structurally instead:
  //   - `public.prices_live` has RLS enabled and exactly one policy, `FOR SELECT`. The
  //     ABSENCE of any insert/update/delete policy is the fix — with RLS on, no policy
  //     means no write is permitted, so `anon` cannot author a row at all. Adding a write
  //     policy "for convenience" would reopen the hole this lane exists to close.
  //   - postgres_changes events are replayed from the WAL, i.e. they are a consequence of
  //     a committed write. There is no client-side path to inject one, forged or otherwise.
  //     Only `service_role` (rolbypassrls, held by the edge function) can write the table.
  //
  // NO `private: true` here, deliberately. That flag routes authorization back through RLS
  // on `realtime.messages` — the table we just established we can never police. Re-adding
  // it does not fail loudly; it makes every join refused and the tape silently decays to
  // lane-1 daily closes. Every failure mode on this lane is silent, which is exactly why
  // it is written out at this length.
  //
  // Cadence note: broadcast delivered ONE message carrying every symbol, so one state
  // update per publisher run. postgres_changes delivers ONE EVENT PER ROW — up to ~40 per
  // pg_cron minute — so this lane needs lane 3's coalescing buffer or it would re-render
  // the whole landing page 40 times a minute (React does not batch across WS frames).
  useEffect(() => {
    if (!client) return;
    const allowed = new Set<string>([...symbols, ...cryptoProductIds]);

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

    const channel = client
      .channel(`${PRICES_CHANNEL_PREFIX}-${instanceId}`)
      .on<Record<string, unknown>>(
        "postgres_changes",
        { event: "*", schema: "public", table: PRICES_TABLE },
        (payload) => {
          // The publisher upserts, so this is INSERT on first sight of a ticker and
          // UPDATE thereafter; `*` covers both without caring which. DELETE carries an
          // empty `new` and priceRowToLive rejects it (no ticker) — filtering stays in
          // the transform rather than on an eventType check here.
          const q = priceRowToLive(payload.new);
          if (!q) return;
          // Same bound as before: the union of both symbol lists, empty = accept all.
          if (allowed.size > 0 && !allowed.has(q.symbol)) return;
          buffer[q.symbol] = q; // last-write-wins per symbol = free dedupe
          scheduleFlush();
        },
      )
      .subscribe();

    return () => {
      // Dropping a pending flush discards whatever is buffered. This effect re-runs when
      // the symbol list resolves (`symbolsKey` "" → "SPY,QQQ,…"), so a batch landing in
      // that window is lost — 400ms of data under lane 3, but up to a full minute here,
      // since the next pg_cron run is the next chance. Acceptable: lane 1's seed already
      // holds a value for every symbol, so the tape shows a close, not a blank.
      if (flushTimer) clearTimeout(flushTimer);
      void client.removeChannel(channel);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- keys track array content
  }, [client, symbolsKey, cryptoKey, instanceId]);

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
