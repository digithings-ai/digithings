"use client";

/**
 * useLivePrices (#1833) — the browser's read side of `public.prices_live`.
 *
 * A one-shot SEED (so a value exists before the first realtime event) plus a Realtime
 * `postgres_changes` subscription, merged into a {@link LiveQuoteMap} keyed by UPPERCASE
 * ticker. STRICTLY READ-ONLY: `select` and `channel` only — no insert, upsert, update,
 * delete or rpc anywhere in this file, by design. A live price must never reach the
 * close-keyed record; see lib/live-valuation.ts for the invariant this feature protects.
 *
 * Static-export safe (`output: "export"`): nothing touches `window` during render and the
 * subscription lives entirely in a client effect. Null-client safe: lib/supabase.ts returns
 * null when the env is unconfigured, and both lanes then simply stay dark.
 *
 * A row's mere PRESENCE is not "live enough" on its own — `quoted_at` stops advancing when
 * the market closes, so anything rendering a freshness badge must read that timestamp
 * ({@link LiveQuote.quotedAt}) rather than infer recency from the key existing. That gate is
 * not in this file, by design: the hook reports the table honestly, and `valuePosition`
 * (lib/live-valuation.ts) turns `quoted_at` into `Valuation.isFresh` by testing its age
 * against `LIVE_QUOTE_FRESH_MS`. Presence still decides `source: 'live'`, which is PROVENANCE;
 * `isFresh` is the separate claim, and it is the only thing that may license the word "live".
 */

import { useEffect, useId, useState } from "react";
import type { SupabaseClient } from "@supabase/supabase-js";
import { supabase } from "@/lib/supabase";
import type { Database } from "@/lib/database.types";
import {
  liveQuoteFromRow,
  mergeQuotes,
  type LiveQuote,
  type LiveQuoteMap,
} from "@/lib/live-valuation";

/**
 * Topic PREFIX — a per-hook-instance suffix is appended below, and that is load-bearing.
 *
 * `RealtimeClient.channel()` DEDUPES BY TOPIC: given a topic it already holds, it returns
 * the existing channel instead of creating a second one. Two hook instances sharing a module
 * constant would therefore `.on()` the SAME channel, while only the first `.subscribe()`
 * sends a join — so the join payload carries ONE postgres_changes filter while the client
 * holds TWO bindings. The server's `ok` reply is index-matched against those bindings, the
 * second finds no counterpart, and `_updatePostgresBindings` calls `unsubscribe()` and marks
 * the channel errored — killing the lane for BOTH consumers with no exception and no console
 * error, just quotes that never arrive. Deriving the topic per instance is what prevents it.
 * (Same trap as frontend/digiquant-web/lib/live/useLivePrices.ts, which documents the
 * realtime-js line numbers.)
 *
 * {@link channelSeq} appends a per-SUBSCRIPTION counter after the instance id. Read the next
 * paragraph before deciding it is load-bearing, because an earlier revision of this comment
 * claimed it was and that claim was FALSE.
 *
 * NOT REQUIRED BY realtime-js 2.104.0 / @supabase/phoenix 0.4.0 — kept as cheap insurance.
 * The reasoning it was added for was that two successive subscriptions of one instance could
 * overlap, on the theory that `removeChannel()` is async and leaves the dying channel in
 * `client.channels` until a server leave-reply or a 10s timeout. That does not happen here, and
 * it was MEASURED rather than argued: phoenix `channel.js:242` sets `state = leaving` BEFORE
 * `:251` consults `canPush()`, and `canPush()` (`:188`) requires `isJoined()` — which `leaving`
 * fails. So `leavePush.trigger("ok", {})` fires SYNCHRONOUSLY, `onClose` runs, and both
 * `socket.remove()` and realtime-js's `_onClose` → `socket._remove()` complete inside
 * `unsubscribe()`'s promise executor, i.e. before `removeChannel()` reaches its first `await`.
 * Probed in the production steady state (socket connected, channel `joined`, leave ack withheld):
 * `client.channels` went 1 → 0 and `state` joined → closed synchronously. A control run reusing
 * one per-instance topic re-subscribed onto a FRESH channel with exactly one postgres_changes
 * binding — the lane was alive without this counter.
 *
 * It stays because synchronous leave is a library implementation detail, not a documented
 * contract: one upstream change to that `canPush()` ordering reintroduces the overlap, and the
 * failure mode is silent (no exception, no console error, no subscribe-status callback — only the
 * seed resolves, so the table keeps showing a quote that never advances). A counter is one
 * integer against that. What is genuinely load-bearing is the per-INSTANCE half above, which was
 * measured to fail: two consumers on a shared constant topic hit `channel()`'s dedupe and lose
 * the lane for both. Do not remove that.
 */
const CHANNEL_PREFIX = "olympus-prices-live";
/**
 * Monotonic per-SUBSCRIPTION discriminator. Incremented in the effect BODY, never during
 * render: a render-phase mutation is not idempotent, and React would double-fire it under
 * StrictMode. Module scope (not a ref) is deliberate — uniqueness must hold across every
 * consumer sharing the one `RealtimeClient`, which is what dedupes by topic.
 */
let channelSeq = 0;

/**
 * The topic for ONE subscription: prefix + hook instance + counter. CALL IT FROM AN EFFECT,
 * never from render — it mutates {@link channelSeq}.
 *
 * Exported so the contract that matters ("no two subscriptions ever share a topic, not even
 * two subscriptions of the same hook instance") is testable in a node environment, without a
 * DOM or a renderer to drive the effect. It is the whole fix for a silent dead lane; see
 * {@link CHANNEL_PREFIX} for the mechanism and why nothing surfaces when it regresses.
 */
export function nextChannelTopic(instanceId: string): string {
  return `${CHANNEL_PREFIX}-${instanceId}-${channelSeq++}`;
}

const TABLE = "prices_live" as const;
/**
 * `postgres_changes` fires ONE EVENT PER ROW — up to ~25 per publisher minute, not one per
 * batch — and React does not batch across WebSocket frames. Without coalescing, every
 * consumer re-renders 25 times a minute.
 */
const FLUSH_MS = 400;

const EMPTY_MAP: LiveQuoteMap = {};

/** Uppercase, de-duped, blanks dropped — the map's key contract. */
function normalizeTickers(input: readonly string[] | undefined): string[] {
  if (!input) return [];
  const seen = new Set<string>();
  for (const t of input) {
    const s = t?.trim().toUpperCase();
    if (s) seen.add(s);
  }
  return [...seen];
}

export interface UseLivePricesOptions {
  /**
   * Client override, for tests and for callers holding their own client. Pass `null` to
   * disable both lanes explicitly; omit to use the shared browser client.
   */
  client?: SupabaseClient<Database> | null;
}

/**
 * Live quotes for `tickers`, keyed by uppercase ticker. Missing keys are normal — the
 * publisher caps at 25 symbols, so a held ticker may have no live coverage at all and the
 * consumer must fall back to the close (that is `valuePosition`'s job in lib/live-valuation.ts).
 *
 * An empty `tickers` list is a no-op: no query, no channel, empty map.
 */
export function useLivePrices(
  tickers: readonly string[],
  options: UseLivePricesOptions = {}
): LiveQuoteMap {
  const symbols = normalizeTickers(tickers);
  // Deps key on content, not identity — callers commonly pass a fresh array each render.
  const symbolsKey = symbols.join(",");
  const client = options.client === undefined ? supabase : options.client;
  // Stable per-instance topic; see CHANNEL_PREFIX for why sharing one is fatal. `useId` is
  // hydration-safe under `output: "export"` and constant across re-renders and effect re-runs.
  // Stripped to `[A-Za-z0-9_-]` because the topic is sent verbatim in the phoenix join and
  // this format is version-dependent: React 19.2.5 emits `_R_1_` (verified, already safe),
  // but React 18 emitted `:r0:` and the current dev build can emit `«r0»`. The disambiguating
  // digits survive the strip, so uniqueness holds either way.
  const instanceId = useId().replace(/[^A-Za-z0-9_-]/g, "");

  const [quotes, setQuotes] = useState<LiveQuoteMap>(EMPTY_MAP);

  // Lane 1 — one-shot seed. Without it the map is empty until the publisher's next write:
  // `postgres_changes` only fires on a change, so a freshly mounted tab would show nothing
  // for up to a minute during the session, and nothing at all overnight and all weekend
  // when the publisher is idle.
  useEffect(() => {
    if (!client || symbols.length === 0) return;
    let cancelled = false;
    void (async () => {
      // Matches on the uppercase form, the publisher's convention. Migration 063 declined a
      // ticker-casing CHECK, so casing is not enforced in the table — hence the read path
      // (liveQuoteFromRow) uppercases defensively rather than trusting the row.
      const { data, error } = await client
        .from(TABLE)
        .select("ticker, price, change_pct, quoted_at")
        .in("ticker", symbols);
      if (cancelled || error || !Array.isArray(data)) return;
      const seeded: Record<string, LiveQuote> = {};
      for (const row of data) {
        const parsed = liveQuoteFromRow(row);
        if (parsed) seeded[parsed.ticker] = parsed.quote;
      }
      if (Object.keys(seeded).length === 0) return;
      // mergeQuotes, not a spread: lane 2 may already have landed a fresher tick for a
      // ticker while this query was in flight, and the seed must not overwrite it.
      setQuotes((prev) => mergeQuotes(prev, seeded));
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- symbolsKey tracks array content
  }, [client, symbolsKey]);

  // Lane 2 — Realtime `postgres_changes` on the table itself.
  //
  // NO `private: true`, deliberately. That flag routes authorization through RLS on
  // `realtime.messages`, which this project can never police: the table is owned by
  // `supabase_realtime_admin`, a role with zero members that we cannot join, so `CREATE
  // POLICY` returns 42501 for us forever (why migration 062 was withdrawn). Adding it does
  // not fail loudly — every join is refused silently and the overlay decays to closes.
  useEffect(() => {
    if (!client || symbols.length === 0) return;
    const allowed = new Set(symbols);

    let flushTimer: ReturnType<typeof setTimeout> | null = null;
    const buffer: Record<string, LiveQuote> = {};
    const flush = () => {
      flushTimer = null;
      const batch = { ...buffer };
      for (const k of Object.keys(buffer)) delete buffer[k];
      if (Object.keys(batch).length === 0) return;
      setQuotes((prev) => mergeQuotes(prev, batch));
    };

    // Topic = prefix + instance + subscription, minted HERE in the effect body. See
    // CHANNEL_PREFIX: the instance id keeps two mounted consumers apart, and the counter keeps
    // THIS consumer's next subscription off the still-dying channel its previous one left
    // behind in `client.channels`.
    const channel = client
      .channel(nextChannelTopic(instanceId))
      .on<Record<string, unknown>>(
        "postgres_changes",
        { event: "*", schema: "public", table: TABLE },
        (payload) => {
          // The publisher upserts, so this is INSERT on first sight and UPDATE thereafter;
          // `*` covers both. A DELETE carries an empty `new` and liveQuoteFromRow rejects it
          // (no ticker), so a partial row can never enter the map.
          const parsed = liveQuoteFromRow(payload.new);
          if (!parsed || !allowed.has(parsed.ticker)) return;
          buffer[parsed.ticker] = parsed.quote; // last-write-wins per ticker = free dedupe
          if (flushTimer === null) flushTimer = setTimeout(flush, FLUSH_MS);
        }
      )
      .subscribe();

    return () => {
      // Dropping a pending flush discards at most one window of quotes. The seed already
      // holds a value for every covered ticker, so a consumer sees a mark, not a blank.
      if (flushTimer) clearTimeout(flushTimer);
      void client.removeChannel(channel);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- symbolsKey tracks array content
  }, [client, symbolsKey, instanceId]);

  // Accumulate-only: a quote for a ticker no longer requested is simply never looked up.
  return quotes;
}
