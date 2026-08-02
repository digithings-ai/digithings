// prices-live — server-side lane of the digiquant.io live price feed (#1461).
//
// Polls Finnhub's free REST tier (60 calls/min) for equity/ETF quotes and UPSERTS them
// into `public.prices_live`, one row per ticker. Browsers receive those rows over
// Supabase Realtime "postgres_changes" on that table. Crypto is NOT handled here —
// browsers stream crypto directly from Coinbase's public keyless WebSocket (frontend lane).
//
// WHY A TABLE AND NOT A REALTIME CHANNEL (#1807). Until 2026-08-01 each run was fanned out
// as one message on the Realtime *broadcast* topic "prices:live". Supabase grants `anon`
// INSERT on `realtime.messages`, and the anon key ships in plaintext in every digiquant.io
// bundle — so anyone could publish forged quotes onto that topic without ever touching this
// function or holding any private credential. The intended fix was migration 062: RLS
// policies on `realtime.messages` letting only `service_role` write. That migration CANNOT
// BE APPLIED — not "is awkward to apply", cannot — and this was proven read-only against
// the live project on 2026-08-01: `realtime.messages` is owned by `supabase_realtime_admin`;
// that role has zero members and no role holds admin option on it; our connection is
// `postgres` (rolsuper = false, not a member); and PostgreSQL 17.6 no longer lets CREATEROLE
// imply admin over arbitrary roles. `CREATE POLICY` therefore raises `42501 must be owner of
// table messages`, and only Supabase platform staff could clear that.
//
// So the transport moved onto objects we DO own. `public.prices_live` and the
// `supabase_realtime` publication are both owned by `postgres`. The table has RLS enabled
// with one SELECT policy for anon/authenticated and — deliberately — no INSERT/UPDATE/DELETE
// policy at all: that omission IS the security fix. `service_role` (rolbypassrls, i.e. this
// function) is the only writer, and postgres_changes payloads are replayed from the WAL
// rather than accepted from clients, so a forged quote has no path in.
//
// DO NOT "restore" the broadcast. It is not a simplicity tradeoff — it reopens the forgery,
// and there is no migration we are permitted to apply that would close it again. See
// migration 063 and digiquant/supabase/README.md.
//
// LIVE since 2026-07-13: FINNHUB_API_KEY is set and both pg_cron jobs are active.
// The function fetches on every scheduled invocation; it is NOT dormant.
//
// INVOCATION GATE (#1756): the caller must present the shared secret in the
// `x-prices-live-secret` header, matched against the PRICES_LIVE_INVOKE_SECRET
// secret. This gate runs FIRST, ahead of every other gate and any outbound fetch.
// `verify_jwt` alone is not authorization — it proves the caller holds *a* project
// key, and the anon key ships in every browser bundle.
//
// Outside extended US market hours (13:00–01:00 UTC, Mon–Fri) an authorized caller
// skips fetching and gets 200 {"market": "closed"}.
//
// See digiquant/supabase/README.md for scheduling (pg_cron + pg_net), the secret
// rollout order, and frontend consumption, and migration
// 050_public_portfolio_views.sql for the paired views.

import { createClient } from "@supabase/supabase-js";

/** Curated majors quoted alongside portfolio tickers (indices, rates, FX, credit). */
const MAJORS = ["SPY", "QQQ", "DIA", "IWM", "GLD", "TLT", "UUP", "EFA", "EEM", "HYG"];

/** Hard cap on symbols per run — well under Finnhub's 60 calls/min free tier. */
const MAX_SYMBOLS = 40;

/** Pause between sequential Finnhub calls so a run never bursts the rate limit. */
const STAGGER_MS = 150;

/** Shared secret the scheduler must present. Never the anon key — that one is public. */
const INVOKE_SECRET_ENV = "PRICES_LIVE_INVOKE_SECRET";
const INVOKE_SECRET_HEADER = "x-prices-live-secret";

/** Finnhub /quote response (https://finnhub.io/docs/api/quote). */
interface FinnhubQuote {
  c: number; // current price
  d: number | null; // change
  dp: number | null; // percent change
  h: number;
  l: number;
  o: number;
  pc: number; // previous close
  t: number; // unix seconds
}

/** The per-symbol quote we keep from Finnhub — current price, change, % change, quote time. */
interface QuoteOut {
  c: number;
  d: number | null;
  dp: number | null;
  t: number;
}

/**
 * One row of `public.prices_live` (migration 063).
 *
 * These column names are the wire contract with the browser: postgres_changes ships the row
 * verbatim, so renaming a column here does not break a build anywhere — it silently blanks a
 * field in the UI. Nullability mirrors the table: Finnhub omits `d`/`dp` for some instruments,
 * `price` and `quoted_at` are NOT NULL.
 */
interface PriceRow {
  ticker: string;
  price: number;
  change: number | null;
  change_pct: number | null;
  quoted_at: string;
  updated_at: string;
}

function json(body: Record<string, unknown>, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Constant-time secret comparison, via fixed-width SHA-256 digests.
 *
 * Digesting first means the byte loop always runs over 32 bytes regardless of input
 * length, so neither the secret's length nor its first differing byte is observable in
 * the response time. A bare `===` short-circuits on the first mismatched character and
 * leaks length outright; do not "simplify" this back to one.
 */
export async function secretMatches(presented: string, expected: string): Promise<boolean> {
  const enc = new TextEncoder();
  const [a, b] = await Promise.all([
    crypto.subtle.digest("SHA-256", enc.encode(presented)),
    crypto.subtle.digest("SHA-256", enc.encode(expected)),
  ]);
  const x = new Uint8Array(a);
  const y = new Uint8Array(b);
  let diff = 0;
  for (let i = 0; i < x.length; i++) diff |= x[i] ^ y[i];
  return diff === 0;
}

/**
 * Extended US market hours: 13:00–01:00 UTC, Mon–Fri (pre-market open through
 * after-hours close, DST-tolerant). The window wraps midnight UTC, so an 00:xx
 * timestamp belongs to the PREVIOUS day's session — 00:30 UTC Saturday is still
 * Friday evening in New York and counts as open.
 */
export function isExtendedUsMarketHours(now: Date): boolean {
  const hour = now.getUTCHours();
  const inWindow = hour >= 13 || hour < 1;
  if (!inWindow) return false;
  // 0=Sun … 6=Sat; before 01:00 UTC the session day is the previous UTC day.
  const sessionDay = hour < 1 ? (now.getUTCDay() + 6) % 7 : now.getUTCDay();
  return sessionDay >= 1 && sessionDay <= 5;
}

/**
 * Finnhub's `t` is unix **SECONDS**; `prices_live.quoted_at` is a `timestamptz`.
 *
 * Hence the `* 1000`. Getting this factor wrong does not throw and does not fail a type
 * check — it silently files every quote in January 1970 (or, dividing instead, somewhere
 * past the year 50000), and the browser renders whatever it is handed. There is no Deno lane
 * in CI, so `tests/dq/test_prices_live_publish.py` asserts the multiply on the source text.
 *
 * A missing, non-finite, or OUT-OF-RANGE `t` falls back to the run clock rather than
 * throwing. Under the old broadcast path `t` was serialized as-is, so a malformed one was
 * inert; here `toISOString()` raises `RangeError: Invalid time value`, which would abort the
 * whole handler — every minute, for as long as Finnhub returned that shape — and throw away
 * 40 good prices over one bad timestamp. `quoted_at` is NOT NULL, so *some* value is
 * required; the run clock is at worst a few seconds early and is never wrong by decades.
 *
 * The range test has to be on the constructed Date, not on `t`. Screening `t` for
 * finite-and-positive is NOT sufficient: JS dates top out at ±8.64e15 ms, so any
 * `t > 8.64e12` is finite, positive, and still throws. Guarding via `getTime()` covers that
 * without hard-coding the epoch bound.
 */
export function quotedAtIso(t: number | null | undefined, fallback: Date): string {
  if (typeof t !== "number" || !Number.isFinite(t) || t <= 0) return fallback.toISOString();
  const quoted = new Date(t * 1000);
  return Number.isNaN(quoted.getTime()) ? fallback.toISOString() : quoted.toISOString();
}

async function fetchQuote(symbol: string, apiKey: string): Promise<QuoteOut> {
  const url = `https://finnhub.io/api/v1/quote?symbol=${encodeURIComponent(symbol)}&token=${apiKey}`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Finnhub HTTP ${res.status}`);
  }
  const q = (await res.json()) as FinnhubQuote;
  // Finnhub returns c=0 (not an error) for unknown symbols — treat as a miss.
  if (typeof q?.c !== "number" || q.c <= 0) {
    throw new Error("empty quote (c<=0) — unknown symbol or no data");
  }
  return { c: q.c, d: q.d ?? null, dp: q.dp ?? null, t: q.t };
}

Deno.serve(async (req: Request): Promise<Response> => {
  const at = new Date();

  // 0) INVOCATION GATE (#1756). Must stay first — ahead of the key gate, ahead of the
  //    body parse, ahead of any outbound fetch. Two reasons, both load-bearing:
  //
  //    a) `verify_jwt` is not authorization. It proves the caller holds *a* project key,
  //       and the anon key is published in every browser bundle. Before this gate, any
  //       anon-key holder could POST `{}` during the ~60h/week market window and drive a
  //       full Finnhub fetch plus a service-role-authored publish onto the live feed —
  //       exhausting the 60-calls/min free tier out from under the legitimate 60s cron.
  //       `{"force": true}` merely widened that to 24/7; it was never the vulnerability,
  //       so gating only `force` would have fixed nothing. Moving the feed onto a table
  //       (#1807) does not retire any of this: `service_role` carries rolbypassrls, so this
  //       gate is still the only thing between the internet and a write to
  //       `public.prices_live`. The table's missing write policy stops forged quotes from
  //       *clients*; it says nothing about a caller who makes this function write for them.
  //    b) Ordering is the point. An unauthorized caller must not learn whether the
  //       Finnhub key is set or whether the market window is open. Moving this below the
  //       cheaper gates to "save work" reintroduces both an oracle and the fetch path.
  //
  //    Fail closed: with the secret unset every invocation is refused (503), never
  //    allowed through. See README "Rolling out the invocation secret" for the ordering
  //    that keeps the live feed up during rollout.
  const expectedSecret = Deno.env.get(INVOKE_SECRET_ENV);
  if (!expectedSecret) {
    console.error(`prices-live: ${INVOKE_SECRET_ENV} unset — refusing all invocations`);
    return json({ error: "invocation secret not configured" }, 503);
  }
  if (!(await secretMatches(req.headers.get(INVOKE_SECRET_HEADER) ?? "", expectedSecret))) {
    console.warn("prices-live: rejected invocation — missing or incorrect invoke secret");
    return json({ error: "unauthorized" }, 401);
  }

  // 1) Finnhub key gate. The key has been set since 2026-07-13, so this is now a
  //    misconfiguration guard (a dropped secret), not the pre-launch idle state it
  //    was originally written as.
  const finnhubKey = Deno.env.get("FINNHUB_API_KEY");
  if (!finnhubKey) {
    console.error("prices-live: FINNHUB_API_KEY not set — nothing fetched");
    return json({ dormant: true, at: at.toISOString() });
  }

  // 2) Market-hours gate — no point burning quota when US markets are shut.
  //    `{"force": true}` overrides THIS gate only (ops smoke tests, see README); it can
  //    never bypass the key, and it is now reachable only past the invocation gate.
  const force = await req
    .json()
    .then((body: unknown) => (body as { force?: unknown } | null)?.force === true)
    .catch(() => false);
  if (!force && !isExtendedUsMarketHours(at)) {
    return json({ market: "closed", at: at.toISOString() });
  }

  // These are auto-injected into every Supabase edge function.
  const supabaseUrl = Deno.env.get("SUPABASE_URL");
  const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!supabaseUrl || !serviceRoleKey) {
    console.error("prices-live: SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY missing");
    return json({ error: "supabase environment not configured" }, 500);
  }

  const supabase = createClient(supabaseUrl, serviceRoleKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });

  // 3) Symbol set = distinct portfolio tickers (public view, #1462) + curated majors.
  const symbols = new Set<string>(MAJORS);
  const { data: rows, error: tickersError } = await supabase
    .from("public_portfolio_positions")
    .select("ticker");
  if (tickersError) {
    // Majors still go out — a view hiccup should not blank the whole feed.
    console.error(`prices-live: ticker query failed: ${tickersError.message}`);
  }
  for (const row of rows ?? []) {
    const ticker = (row as { ticker: string | null }).ticker?.trim().toUpperCase();
    // "CASH" is the portfolio's cash-sleeve pseudo-ticker, not a security — and
    // Finnhub happily quotes it as Pathward Financial (NASDAQ: CASH), which the
    // 2026-07-12 smoke test proved would put a fake mover in the feed.
    if (ticker && ticker !== "CASH") symbols.add(ticker);
  }
  const symbolList = [...symbols].sort().slice(0, MAX_SYMBOLS);
  if (symbols.size > MAX_SYMBOLS) {
    console.warn(
      `prices-live: ${symbols.size} symbols exceeds cap ${MAX_SYMBOLS}; truncated`,
    );
  }

  // 4) Sequential fetch with a small stagger; per-symbol errors never abort the run.
  const quotes: Record<string, QuoteOut> = {};
  const errors: Record<string, string> = {};
  for (const [i, symbol] of symbolList.entries()) {
    if (i > 0) await sleep(STAGGER_MS);
    try {
      quotes[symbol] = await fetchQuote(symbol, finnhubKey);
    } catch (err) {
      errors[symbol] = err instanceof Error ? err.message : String(err);
    }
  }

  // 5) Publish: ONE upsert into `public.prices_live`, keyed on ticker (migration 063).
  //    Browsers pick the rows up over Realtime postgres_changes. This replaced a broadcast
  //    on "prices:live"; see the file header for why that channel is forgeable by any anon
  //    key holder and why migration 062 could never fix it. Do not put it back.
  //
  //    Three distinct clocks, none interchangeable: `quoted_at` is Finnhub's tick time (what
  //    staleness should be judged on), `updated_at` is `at` — this run's START, which at 40
  //    symbols × 150 ms stagger is up to ~6 s before the write — and the row's own `now()`
  //    default is the database write time.
  //
  //    `published` keeps the old `broadcast` field's "ok" | <error string> shape so the cron
  //    log stays greppable, and it carries the error VERBATIM on purpose: a scheduled run has
  //    no other diagnostic surface. Deploy this function before migration 063 lands and the
  //    string is `PGRST205 Could not find the table 'public.prices_live' in the schema
  //    cache`, which is the entire diagnosis.
  let published: string = "skipped (no quotes)";
  const quoted = Object.keys(quotes).length;
  if (quoted > 0) {
    const rows: PriceRow[] = Object.entries(quotes).map(([ticker, q]) => ({
      ticker,
      price: q.c,
      change: q.d,
      change_pct: q.dp,
      quoted_at: quotedAtIso(q.t, at),
      updated_at: at.toISOString(),
    }));
    try {
      // `ignoreDuplicates` stays at its supabase-js v2 default of false — this MUST resolve
      // to DO UPDATE. Set it true and every ticker freezes forever at the first price ever
      // inserted for it, with no error and a perfectly healthy-looking "ok" in the log.
      const { error } = await supabase.from("prices_live").upsert(rows, { onConflict: "ticker" });
      published = error ? error.message : "ok";
    } catch (err) {
      // postgrest-js normally returns transport failures in `error`, but an unexpected throw
      // here would 500 the whole run and lose the per-symbol error report below with it.
      published = err instanceof Error ? err.message : String(err);
    }
  }
  if (published !== "ok" && quoted > 0) {
    console.error(`prices-live: prices_live upsert failed: ${published}`);
  }

  return json({
    market: "open",
    forced: force,
    at: at.toISOString(),
    symbols: symbolList.length,
    quoted,
    failed: Object.keys(errors).length,
    errors,
    published,
  });
});
