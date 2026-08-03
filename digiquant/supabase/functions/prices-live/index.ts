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
// A RATE GUARD, NOT AN INVOCATION SECRET. `verify_jwt: true` is not authorization: it
// proves the caller holds *a* project key, and the anon key ships in plaintext in every
// digiquant.io bundle. So anyone can invoke this function, and the harm they can do is to
// burn the Finnhub free tier (60 calls/min) out from under the legitimate 60 s cron —
// a RATE problem, not an IDENTITY problem. #1756 answered it with a shared secret in an
// `x-prices-live-secret` header; that secret is now GONE, deliberately. It was an
// operational credential to store, rotate and lose, and it bounded *who* could invoke
// rather than *how often* a fetch may happen — the quantity that actually has to be
// bounded. What replaces it makes an unauthorized invocation worthless instead of
// forbidden: the caller still gets a 200, it just does not fetch anything.
//
// THE GUARD IS AN ATOMIC LEASE CLAIM (migration 064). `public.claim_prices_live_refresh(
// min_age_seconds)` is ONE conditional `UPDATE public.prices_live_lease SET claimed_at =
// clock_timestamp() WHERE id = 1 AND claimed_at < clock_timestamp() - <min_age>`, returning
// `FOUND`. Concurrent callers block on that row's lock, then re-evaluate the WHERE clause
// against the committed new `claimed_at` (READ COMMITTED) and match zero rows. Exactly one
// winner per window, whatever the arrival pattern.
//
// DO NOT REPLACE IT WITH `SELECT max(updated_at) FROM prices_live`. That reads then acts,
// and the two steps are ~6 SECONDS apart: `updated_at` is written by the upsert AFTER the
// fetch loop (40 symbols × 150 ms stagger). For those 6 s every concurrent invocation reads
// the same stale timestamp, all pass the freshness check, and all fetch — ten parallel
// requests is ~400 Finnhub calls in 6 seconds, i.e. zero protection against the only
// attacker that matters. An advisory lock is not a substitute either: PostgREST hands out a
// fresh session per RPC call, so a session-scoped lock releases long before the 6 s fetch
// this claim is meant to cover.
//
// FAIL CLOSED. An RPC `error`, a thrown exception, or a `data` that is anything other than
// `true` all mean NOT claimed, and this function then returns 200 {"skipped": "not claimed"}
// without fetching. Deploying ahead of migration 064 therefore fetches NOTHING (the missing
// function surfaces as a PostgREST error), which is the safe direction to be wrong in.
//
// The rate arithmetic is now a guarantee rather than a sequential best case, precisely
// because the claim is atomic: at most one fetch per MIN_REFRESH_SECONDS = 50 s, so
// MAX_SYMBOLS × (60/50) = 48 Finnhub calls/min, under the 60/min free tier, with pg_cron
// firing every 60 s for 10 s of jitter margin. Raising MAX_SYMBOLS or lowering
// MIN_REFRESH_SECONDS breaks that invariant; a test asserts the product.
//
// Migration 064 REVOKEs EXECUTE on the RPC from `anon`/`authenticated`, and that revoke is
// load-bearing in both directions. Without it an attacker could call the claim directly in a
// loop, win every window and leave the cron nothing to claim — a denial of *freshness*, the
// mirror image of the quota attack.
//
// NO ORDERING ORACLE ARGUMENT ANY MORE. The old secret gate had to run first so that an
// unauthorized caller could not learn whether the Finnhub key was set or the market open.
// That rationale is retired with the secret: there is nothing left to authenticate, and US
// market hours are public information. The claim (handler step 3) runs *after* the
// market-hours gate on purpose — it must not consume a lease window on a run that was going
// to skip anyway. It still runs before the portfolio-ticker query, so a loser reads nothing.
//
// Outside extended US market hours (13:00–01:00 UTC, Mon–Fri) a caller skips fetching and
// gets 200 {"market": "closed"}. `{"force": true}` overrides THAT gate only and cannot
// bypass the claim (see the handler). It follows that a forced off-hours call can consume a
// lease window — which is harmless, because whoever wins the claim fetches Finnhub and
// upserts the same correct prices. Starvation only comes from calling the RPC directly, and
// that is what 064's REVOKE closes.
//
// See digiquant/supabase/README.md for scheduling (pg_cron + pg_net) and frontend
// consumption, migration 064_prices_live_lease.sql for the lease table and claim function,
// and migration 050_public_portfolio_views.sql for the paired views.

import { createClient } from "@supabase/supabase-js";

/** Curated majors quoted alongside portfolio tickers (indices, rates, FX, credit). */
const MAJORS = ["SPY", "QQQ", "DIA", "IWM", "GLD", "TLT", "UUP", "EFA", "EEM", "HYG"];

/**
 * Hard cap on symbols per run. Coupled to MIN_REFRESH_SECONDS — see there for the arithmetic.
 *
 * 25 is not arbitrary and is NOT slack to be spent: two claims can land in one sliding
 * 60 s window (see MIN_REFRESH_SECONDS), so the ceiling is 2 × MAX_SYMBOLS = 50 Finnhub
 * calls/min against a 60/min free tier. At 40 it was 80 — over the tier, which is the
 * staleness this guard exists to prevent.
 *
 * Live demand as of 2026-08-03 is at most 20 symbols (10 MAJORS ∪ 10 distinct non-CASH
 * portfolio tickers), so nothing truncates today and there is room for ~5 more holdings.
 * Past that the run starts dropping symbols with only a console.warn — if the portfolio
 * grows, raise this *and* re-derive MIN_REFRESH_SECONDS together, or coverage silently
 * shrinks. The two constants are one decision.
 */
const MAX_SYMBOLS = 25;

/** Pause between sequential Finnhub calls so a run never bursts the rate limit. */
const STAGGER_MS = 150;

/**
 * Minimum age of the refresh lease before another fetch may be claimed (migration 064).
 *
 * Together with MAX_SYMBOLS this bounds the Finnhub burn rate. Count claims per window
 * CORRECTLY — the intuitive `60 / MIN_REFRESH_SECONDS` is wrong and understates it:
 *
 *   claims that fit in ANY sliding 60 s window = floor(60 / MIN_REFRESH_SECONDS) + 1
 *
 * At 50 s that is 2, not 1.2 — claims at t=0 and t=50 both sit inside [0,60]. So the real
 * ceiling is 2 × MAX_SYMBOLS = 50 calls/min against a 60/min free tier. The `+ 1` is the
 * whole point: an attacker invoking ~51 s after each cron beat wins a claim, the cron's next
 * beat then loses, and the attacker becomes the refresher — data stays correct, but the
 * window carries two batches. With MAX_SYMBOLS at 40 that was 80 calls/min, over the tier,
 * producing 429s and the partial staleness this guard exists to prevent.
 *
 * It is a guarantee rather than a sequential best case *because* the claim is atomic — see
 * the file header. Keep this strictly below pg_cron's 60 s period (10 s of jitter margin at
 * 50 s) so the legitimate beat is never starved by its own guard. Change either constant and
 * re-derive both; `tests/dq/test_prices_live_rate_guard.py` asserts the inequality.
 */
const MIN_REFRESH_SECONDS = 50;

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

/**
 * The awaited shape of the `claim_prices_live_refresh` RPC, narrowed to what the guard reads.
 *
 * `data` is deliberately `unknown` and not `boolean`. The client is untyped here (no generated
 * `Database` type), so its `rpc()` result would otherwise widen to `any` — and under `any` the
 * fail-closed test `data === true` still compiles if the function is renamed, dropped, or ever
 * returns a row set instead of a scalar. `unknown` forces the comparison to be the narrowing.
 */
interface ClaimResponse {
  data: unknown;
  error: { message: string } | null;
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

  // 1) Finnhub key gate. The key has been set since 2026-07-13, so this is now a
  //    misconfiguration guard (a dropped secret), not the pre-launch idle state it
  //    was originally written as.
  const finnhubKey = Deno.env.get("FINNHUB_API_KEY");
  if (!finnhubKey) {
    console.error("prices-live: FINNHUB_API_KEY not set — nothing fetched");
    return json({ dormant: true, at: at.toISOString() });
  }

  // 2) Market-hours gate — no point burning quota when US markets are shut.
  //    `{"force": true}` overrides THIS gate only (ops smoke tests, see README). It can
  //    never bypass the Finnhub key gate, and — read this before "fixing" it — it cannot
  //    bypass the refresh claim in step 3 either. That makes `force` much weaker as a smoke
  //    test than it used to be: a forced call inside 50 s of any other run returns
  //    {"skipped": "not claimed"} and fetches nothing. This is the accepted trade, not an
  //    oversight. A `force` that skipped the claim would hand every anon-key holder the
  //    unbounded-fetch path back, which is the entire vulnerability this design closes.
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

  // 3) ATOMIC CLAIM — the rate guard, and the only thing bounding Finnhub spend now that the
  //    #1756 invocation secret is gone. One conditional UPDATE inside migration 064's
  //    `claim_prices_live_refresh`, so concurrent callers block on the lease row and then see
  //    a `claimed_at` too young to match: exactly one winner per MIN_REFRESH_SECONDS window,
  //    however many requests arrive together. The header explains at length why the obvious
  //    `SELECT max(updated_at) FROM prices_live` alternative protects nothing (it reads ~6 s
  //    before the write it is reading) and why an advisory lock cannot stand in for this.
  //
  //    It runs BEFORE the symbol query on purpose: a caller who loses the claim must not even
  //    read `public_portfolio_positions`, let alone reach Finnhub.
  //
  //    FAIL CLOSED — `claimed` starts false and only `data === true` sets it. Three distinct
  //    failure modes, all of which must skip:
  //      a) `error` returned — includes the pre-migration case, where PostgREST answers
  //         `PGRST202 Could not find the function public.claim_prices_live_refresh`. Deploying
  //         this function ahead of migration 064 must fetch NOTHING, never everything.
  //      b) a thrown exception — a transport failure inside postgrest-js, which must not 500
  //         the handler into a retry loop that hammers the quota.
  //      c) `data` that is not exactly `true` — `null` (function returned NULL), `false`
  //         (someone else holds the window), or any other shape. None of these are truthy
  //         here, which is why the test is `=== true` and not `if (data)`.
  let claimed = false;
  try {
    // The cast must wrap the AWAITED value: casting the builder first would break the
    // thenable, leaving `data` a PostgrestFilterBuilder that is never `true` — a guard that
    // fails closed forever and silently stops the feed.
    const { data, error } = (await supabase.rpc("claim_prices_live_refresh", {
      min_age_seconds: MIN_REFRESH_SECONDS,
    })) as ClaimResponse;
    if (error) {
      console.error(`prices-live: refresh claim failed: ${error.message}`);
    } else {
      claimed = data === true;
    }
  } catch (err) {
    console.error(
      `prices-live: refresh claim threw: ${err instanceof Error ? err.message : String(err)}`,
    );
  }
  if (!claimed) {
    // 200, not 429: the scheduled caller did nothing wrong and pg_cron has no retry to
    // suppress. The body is distinguishable so `net._http_response` shows which runs fetched.
    return json({ skipped: "not claimed", at: at.toISOString() });
  }

  // 4) Symbol set = distinct portfolio tickers (public view, #1462) + curated majors.
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

  // 5) Sequential fetch with a small stagger; per-symbol errors never abort the run.
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

  // 6) Publish: ONE upsert into `public.prices_live`, keyed on ticker (migration 063).
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
