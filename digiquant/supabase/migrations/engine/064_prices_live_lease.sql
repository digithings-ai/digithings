-- 064_prices_live_lease.sql — Replace the `prices-live` invocation secret with an ATOMIC
-- refresh lease, so an unauthorized invocation is worthless instead of merely forbidden
-- (supersedes the #1756 shared-secret gate; the feed's transport is migration 063 / #1807).
--
-- Run with:  supabase db push   (or apply via MCP against this project).
--
-- THE ABUSE THIS GUARDS — AND WHY IT IS A RATE PROBLEM, NOT AN IDENTITY PROBLEM
-- ----------------------------------------------------------------------------
-- The `prices-live` edge function polls Finnhub's FREE tier (60 calls/min) for up to
-- MAX_SYMBOLS = 40 symbols and upserts `public.prices_live`; browsers read that table over
-- Realtime `postgres_changes`. pg_cron invokes it once every 60s during extended US market
-- hours. `verify_jwt: true` is NOT authorization — it proves the caller holds *a* project
-- key, and the anon key ships in plaintext in every digiquant.io bundle (this repo is
-- public). So anyone could POST `{}` and drive a full 40-call Finnhub fetch. Hammer it and
-- the 60-calls/min quota is exhausted out from under the legitimate cron: the feed goes
-- stale for every real visitor. Nothing is stolen and nothing is forged — the damage is
-- purely that a metered resource gets consumed faster than it refills.
--
-- #1756 answered that with a shared secret (`x-prices-live-secret` matched against the
-- `PRICES_LIVE_INVOKE_SECRET` env var). It worked, and it has been WITHDRAWN by user
-- ruling, because it answered the wrong question. A secret is an operational credential:
-- it has to be generated, stored in Supabase secrets, embedded in the pg_cron `command`
-- (i.e. written into `cron.job`, readable by anyone who can read that catalog), rotated,
-- and it is a live outage the day it is lost or mistyped. All of that carrying cost buys
-- an answer to "WHO is calling?" when the actual constraint is "HOW OFTEN may anyone
-- call?". This migration answers the second question directly. With it in place an
-- attacker who invokes the function a thousand times a minute causes exactly the same
-- Finnhub load as the cron alone — their calls return `{"skipped": "not claimed"}` — so
-- there is no longer anything for a secret to protect. Note what is deliberately NOT
-- claimed: this is not an authorization control and does not pretend to be one. Unwanted
-- callers still reach the function; they just cannot make it do any metered work.
--
-- WHY THIS IS AN ATOMIC CLAIM AND NOT A FRESHNESS `SELECT` — READ BEFORE SIMPLIFYING
-- ---------------------------------------------------------------------------------
-- The obvious implementation is a freshness check, and it is WRONG. It looks like this,
-- and a future reader will try to "simplify" this whole file down to it:
--
--     -- DO NOT DO THIS
--     SELECT max(updated_at) FROM public.prices_live;
--     -- ... if younger than N seconds, skip; else fetch
--
-- That is READ-THEN-ACT, and the gap between the read and the act is enormous.
-- `prices_live.updated_at` is written by the UPSERT that runs AFTER the whole fetch loop
-- completes — 40 symbols at a 150 ms stagger is roughly 6 SECONDS of wall clock. For those
-- ~6 seconds the newest timestamp in the table is still the PREVIOUS run's. So N callers
-- arriving inside that window all read the same stale value, all conclude "the feed is
-- old, I should refresh", and all fetch. Ten parallel requests become ~400 Finnhub calls
-- in six seconds. It is not a narrow race that a tighter threshold would shrink: it offers
-- ZERO protection against a caller issuing requests in parallel, which is the only caller
-- worth defending against. A sequential test of that design passes perfectly, which is
-- exactly why the design survives review.
--
-- Both halves of that were MEASURED, not reasoned about, against postgres 17.10 while this
-- migration was written: 20 callers released at one wall-clock instant against the
-- freshness-check shape → 20 of 20 decided to fetch. The same 20 against the claim below
-- → 1 of 20. Separately, 10 callers held blocked on the lease row and then released
-- together → 1 winner, 9 zero-row losers.
--
-- The guard therefore has to be a CLAIM: one statement that both tests the condition and
-- consumes it, and reports whether THIS caller won.
--
--     UPDATE public.prices_live_lease
--        SET claimed_at = clock_timestamp()
--      WHERE id = 1 AND claimed_at < clock_timestamp() - make_interval(...);
--
-- A single UPDATE gets this right for a reason worth spelling out. Concurrent callers all
-- target the same row. The first one to reach it takes a row-level write lock; the others
-- BLOCK on that lock rather than proceeding. When the winner commits, each blocked caller
-- re-evaluates its WHERE clause against the newly committed version of the row (this is
-- READ COMMITTED's EvalPlanQual re-check, not a fresh snapshot), sees a `claimed_at` of
-- roughly *now*, fails the age predicate, and matches ZERO rows. `FOUND` is false and it
-- skips. Exactly one winner per window, for any arrival pattern — simultaneous, staggered,
-- or adversarially timed. Test the condition and consume it in one statement or you do not
-- have a guard.
--
-- This is READ COMMITTED-SPECIFIC, which is the project default and what PostgREST uses.
-- Under REPEATABLE READ or SERIALIZABLE the loser gets `40001 could not serialize access
-- due to concurrent update` instead of a clean 0-row result. That is still SAFE — the edge
-- function treats any exception as not-claimed and skips — but do not "harden" this by
-- raising the isolation level and then wonder why the cron log fills with serialization
-- errors. The 0-row outcome is the intended one.
--
-- WHY ADVISORY LOCKS CANNOT SUBSTITUTE FOR DURABLE STATE
-- -----------------------------------------------------
-- `pg_try_advisory_lock` is the reflex answer to "only one at a time" and it cannot work
-- here, for a reason stronger than lock scoping: THE PROTECTED REGION IS NOT IN THE
-- DATABASE AT ALL. The ~6-second Finnhub fetch runs in Deno. By the time the first symbol
-- is requested the RPC has already returned and the pooled connection has been handed
-- back. A transaction-level lock died at that commit. A session-level one is worse rather
-- than better: PostgREST pools its connections, so the next invocation is not guaranteed
-- the same session and cannot re-check or release the lock it took, and a lock left held
-- either evaporates on connection reset or LEAKS onto a pooled connection that some
-- unrelated request later reuses. No lock of any duration can span a region that outlives
-- every session able to hold it. The lease is durable committed state precisely because a
-- lock cannot outlive the call that took it.
--
-- WHY `claimed_at` DEFAULTS TO '-infinity'
-- ----------------------------------------
-- The very first claim after a rebuild must WIN. Seeding with `now()` would mean the feed
-- stays dark for the first MIN_REFRESH_SECONDS after any restore or fresh apply, and
-- seeding NULL would make the age predicate NULL, i.e. not true, i.e. never claimable —
-- a permanently dead feed with no error anywhere. `-infinity` is unconditionally older
-- than any threshold, so the first caller claims immediately and the column can stay
-- NOT NULL. Re-seeding is `ON CONFLICT (id) DO NOTHING`, so re-running this migration
-- during market hours does NOT reset a live lease and cannot hand out a second claim
-- inside the current window.
--
-- WHY THE REVOKE FROM `anon` IS LOAD-BEARING IN BOTH DIRECTIONS
-- ------------------------------------------------------------
-- Without the REVOKE, PostgREST would publish this as
-- `POST /rest/v1/rpc/claim_prices_live_refresh`, callable with the anon key out of the
-- public bundle. The first direction is the obvious one: anon must not be able to refresh.
-- The second is the one that actually bites, and it is the reason SECURITY DEFINER here is
-- paired with a REVOKE rather than left open:
--
--   ANON MUST NOT BE ABLE TO **BURN** THE LEASE. Every call to this function that returns
--   true moves `claimed_at` forward. An attacker who can call the RPC directly — without
--   ever touching the edge function, and therefore without causing a single Finnhub
--   call — can claim the window over and over, and every claim they take is a claim the
--   cron does not get. The cron's next invocation finds the lease fresh and skips. Loop
--   that and the live feed simply stops updating. The rate guard becomes the outage: a
--   DENIAL OF FRESHNESS, cheaper for the attacker than the quota exhaustion it was built
--   to prevent, because burning the lease costs one HTTP request and no upstream work.
--
-- So the REVOKE is not tidiness around a SECURITY DEFINER function; it is half the
-- control. `service_role` (which the edge function authenticates as, and which carries
-- `rolbypassrls`) is the only grantee. Do not add `anon` or `authenticated` to the GRANT,
-- and do not "expose the lease state" through a convenience view or a wrapper function —
-- read access is harmless, but anything that can EXECUTE this can starve the feed.
--
-- THE RATE ARITHMETIC — AND WHY IT IS A GUARANTEE RATHER THAN A BEST CASE
-- ----------------------------------------------------------------------
-- The edge function passes MIN_REFRESH_SECONDS = 50. At most one fetch per 50s, and at
-- most MAX_SYMBOLS = 40 calls per fetch:
--
--     40 symbols x (60s / 50s) = 48 Finnhub calls/min   <   60/min free tier
--
-- pg_cron fires every 60s, which is >= 50s, so every legitimate invocation claims and the
-- feed never skips a scheduled beat; the 10s of slack absorbs cron and cold-start jitter.
-- In cron-only steady state the real load is 40 calls/min. Be precise about what the 48 is:
-- it is a RATE over the 50-second claim window, not a cap on every arbitrary 60-second
-- span. Claims landing at t=0 and t=50 put 80 calls inside that one sliding minute. That is
-- the accepted worst case under continuous hammering and it is on the record here so the
-- next person to touch either constant knows which number they are moving.
--
-- The arithmetic is only sound BECAUSE THE CLAIM IS ATOMIC. Under the freshness-SELECT
-- design above, "one fetch per 50s" is what happens when requests arrive one at a time —
-- a best case, silently unbounded under parallelism. Here it is an invariant enforced by a
-- row lock. If MAX_SYMBOLS ever rises or MIN_REFRESH_SECONDS ever falls, recheck the
-- inequality: a test asserts MAX_SYMBOLS x (60 / MIN_REFRESH_SECONDS) stays under 60.
--
-- FAIL CLOSED, AND WHAT THAT MEANS FOR DEPLOY ORDER
-- ------------------------------------------------
-- The caller treats an error, a thrown exception, or any result that is not exactly `true`
-- as NOT CLAIMED and returns without fetching. That makes the deploy order forgiving in
-- the safe direction: ship the edge function before this migration lands and the RPC
-- 404s as `PGRST202 Could not find the function public.claim_prices_live_refresh` — every
-- invocation then fetches NOTHING, rather than everything. The same applies for the few
-- seconds after apply while PostgREST reloads its schema cache (Supabase's DDL event
-- trigger does this automatically; no NOTIFY is needed here). A briefly dark feed is the
-- correct failure mode for a quota guard; the alternative is an unguarded one.
--
-- The other side of fail-closed: if the singleton row is ever DELETEd, the UPDATE matches
-- zero rows forever and the feed goes permanently dark with no error logged anywhere. The
-- function does NOT self-heal by re-inserting, on purpose — an upsert-then-update would
-- make a reader re-derive the atomicity proof above from two statements instead of reading
-- it off one. The remedy is to re-run this migration, which re-seeds at `-infinity` so the
-- next claim wins immediately.
--
-- Idempotent throughout, and it WILL be re-run: CREATE TABLE IF NOT EXISTS,
-- INSERT ... ON CONFLICT DO NOTHING (which is also what stops a replay from resetting a
-- live lease), CREATE OR REPLACE FUNCTION (which preserves the function's ACL, so the
-- REVOKE/GRANT below are not undone by a replace), ENABLE ROW LEVEL SECURITY is a no-op
-- when already enabled, and REVOKE/GRANT are re-runnable by nature.
--
-- The one edit that would BREAK that idempotence: renaming the `min_age_seconds` parameter.
-- CREATE OR REPLACE FUNCTION cannot rename an input parameter — it raises `42P13 cannot
-- change name of input parameter` wherever the old signature already exists, and under
-- db-migrate's `--single-transaction` that rolls back this entire file, table and grants
-- included. The name is pinned by the RPC wire contract anyway (supabase-js sends it as a
-- JSON key, so a mismatch is a silent PGRST202 rather than a build error), so there is no
-- reason to rename it; if it ever must change, that is a DROP FUNCTION in its own
-- migration, and the DROP resets the ACL, so the REVOKE/GRANT below must be repeated there.
--
-- No `BEGIN;` anywhere on purpose — db-migrate.yml greps for one case-insensitively and
-- does NOT skip `--` comments, and would then run this file bare, dropping
-- `--single-transaction` and splitting the ledger INSERT into a separate psql call. The
-- `BEGIN` opening the plpgsql body below carries no semicolon and so does not match. If
-- you edit the prose above, keep every mention of that token backticked exactly as it is
-- here; one unquoted one in a sentence flips the branch, and only the unit test for this
-- file will catch it.

-- ---------------------------------------------------------------------------
-- The lease. A single-row table, enforced as such: `CHECK (id = 1)` with the
-- primary key on the same column means a second lease row cannot be inserted
-- even by a superuser typo. That matters because the guard's whole correctness
-- argument is "concurrent callers contend for THE SAME ROW" — two rows would be
-- two independent windows and two simultaneous winners.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.prices_live_lease (
  id         smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  claimed_at timestamptz NOT NULL DEFAULT '-infinity'
);

-- Seed exactly one row, idempotently, so the first ever claim wins. See the
-- '-infinity' section in the header: the default is what makes a fresh apply or
-- a restore immediately claimable, and DO NOTHING is what keeps a replay from
-- resetting a lease that is mid-window on a live project.
INSERT INTO public.prices_live_lease (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

-- RLS ENABLED WITH ZERO POLICIES — the omission is the control, exactly as in
-- migration 063. Under RLS, absent policy = deny, so of the roles that could
-- otherwise reach a row here only `rolbypassrls` holders (`postgres`, which also
-- owns the table, and `service_role`) get past it. Do not "complete" the policy
-- set: there is no client that has any business reading, let alone advancing,
-- the lease.
--
-- Note the ORDER of the two controls, because it decides which error a
-- misconfiguration produces: table privileges are checked BEFORE row security,
-- so a role with no grant gets a loud `42501 permission denied for table` and
-- never reaches RLS at all. `rolbypassrls` waives row security, not privilege.
--
-- Do NOT read this as "service_role cannot touch the table". A bare Postgres
-- shows that denial, but this project is not bare: Supabase's `pg_default_acl`
-- for tables in schema `public` grants `service_role=arwdDxtm`, and migration
-- 060 revoked only from anon/authenticated (060:53-55, 060:90-92). So here the
-- lease is created with `service_role` holding SELECT/UPDATE directly, and
-- `SET ROLE service_role; UPDATE public.prices_live_lease ...` SUCCEEDS.
--
-- That is precisely WHY the claim is SECURITY DEFINER rather than relying on the
-- caller's grants: the guard's integrity rests on the FUNCTION's ACL (revoked
-- from the client roles below), not on this table's ACL. The REVOKE here is
-- defense in depth for `anon`/`authenticated`, who genuinely are stripped —
-- verified live: anon has no privilege on this table. Nobody should conclude
-- from this block that the table grant is what stops a determined caller.
ALTER TABLE public.prices_live_lease ENABLE ROW LEVEL SECURITY;

-- Belt and braces behind RLS, the convention migrations 050, 052, 057, 060 and
-- 063 established. RLS removes row access; this removes the PostgREST table
-- grant, so neither anon nor authenticated can reach the table even if a future
-- migration re-widens schema-level privileges. Unlike `prices_live` there is no
-- paired `GRANT SELECT` — nothing outside the publisher has a reason to read
-- this, and this file grants `service_role` nothing on the table either: the
-- SECURITY DEFINER function below is the single audited path that advances the
-- lease, and it does not need the caller to hold any table privilege. Whether
-- Supabase's bootstrap default ACL on schema `public` happens to give
-- `service_role` privileges here anyway is deliberately not relied upon in
-- either direction — that is exactly why the function is SECURITY DEFINER.
REVOKE ALL ON public.prices_live_lease FROM PUBLIC, anon, authenticated;

COMMENT ON TABLE public.prices_live_lease IS
  'Single-row rate lease for the `prices-live` edge function — the atomic replacement for '
  'the #1756 invocation secret. One conditional UPDATE per invocation decides whether that '
  'caller may spend Finnhub quota, so at most one refresh happens per MIN_REFRESH_SECONDS '
  'window no matter how many callers arrive at once. NOT a freshness check on '
  'prices_live.updated_at: that timestamp is written ~6s after a fetch starts, so every '
  'concurrent caller would read the same stale value and all would fetch. RLS enabled with '
  'no policies and all grants revoked; reachable only via '
  'public.claim_prices_live_refresh(integer).';

COMMENT ON COLUMN public.prices_live_lease.id IS
  'Singleton pin. PRIMARY KEY plus CHECK (id = 1) means this table can hold exactly one '
  'row, which the guard depends on: contention for ONE row is what serializes callers. Two '
  'rows would be two independent windows and therefore two concurrent winners.';

COMMENT ON COLUMN public.prices_live_lease.claimed_at IS
  'When the refresh window was last claimed — set to clock_timestamp() by the winning '
  'UPDATE, i.e. the real instant of the claim rather than the transaction start now() '
  'would give. Defaults to ''-infinity'' so the first claim after a fresh apply or a '
  'restore wins immediately; NULL or now() would leave the feed dark (a NULL age predicate '
  'is never true). This is claim time, not publish time — prices_live.quoted_at and '
  'prices_live.updated_at remain the freshness signals for the DATA.';

-- ---------------------------------------------------------------------------
-- The claim. ONE conditional UPDATE, reported through plpgsql's FOUND.
--
-- SECURITY DEFINER so the claim is correct regardless of what the calling role
-- holds on the lease table — which this file deliberately does not arrange. Both
-- non-definer outcomes are bad, and one of them is bad quietly: a caller with no
-- table grant raises `42501 permission denied for table` (loud, but a dark feed
-- every minute), while a caller that HAS the grant and is subject to RLS matches
-- zero rows and reads that as "somebody else already claimed" — a feed that
-- never refreshes and never errors, indistinguishable from healthy contention.
-- Running as the owner removes the dependence on either.
--
-- The usual SECURITY DEFINER caveats are all handled: the injection surface is
-- one integer that is range-validated before use, `search_path` is pinned empty
-- so every name resolves schema-qualified, and EXECUTE is revoked from PUBLIC
-- below so this is not reachable as a PostgREST RPC by the bundled anon key.
--
-- VOLATILE is stated rather than left implicit even though it is the default,
-- because the wrong marking here fails in a confusing place: marked STABLE or
-- IMMUTABLE, PostgREST serves the function over GET in a READ ONLY transaction
-- and the UPDATE raises `25006 cannot execute UPDATE in a read-only
-- transaction`. Do NOT mark this STABLE.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.claim_prices_live_refresh(min_age_seconds integer)
RETURNS boolean
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = ''
AS $fn$
BEGIN
  -- A 0 would disable the guard SILENTLY: `claimed_at < clock_timestamp()` is
  -- true for any claim already committed, so every caller would win and the
  -- Finnhub quota would be wide open again with the lease still in place and
  -- looking healthy. A negative value is the same failure, and NULL makes the
  -- whole predicate NULL, which never matches — the opposite failure, a
  -- permanently dead feed. Neither is a value a caller can plausibly MEAN, so
  -- raise instead of clamping: the edge function fails closed on an exception,
  -- so a bad argument costs a dark feed and a loud log line, not silent abuse.
  IF min_age_seconds IS NULL OR min_age_seconds < 1 THEN
    RAISE EXCEPTION
      'claim_prices_live_refresh: min_age_seconds must be >= 1, got %', min_age_seconds
      USING HINT = 'The caller passes MIN_REFRESH_SECONDS (50 as of #1807). A 0 or NULL '
                   'would let every concurrent caller claim, which is the exact abuse '
                   'this lease exists to stop.';
  END IF;

  -- THE atomic claim. Test-and-consume in one statement; see the header for why
  -- splitting this into a SELECT and an UPDATE reopens the whole hole.
  --
  -- clock_timestamp(), not now(): now() is transaction START time, frozen for
  -- the life of the transaction. In the WHERE clause it would be conservative
  -- (an older threshold is harder to satisfy, never easier), but in the SET it
  -- stamps the claim EARLIER than it really happened, which SHORTENS the next
  -- window by however long the transaction had already been open — the guard
  -- silently loosening in the one direction that costs quota. It would also let
  -- a caller that claimed twice inside one transaction see an unchanging clock.
  -- Use the real one in both places.
  UPDATE public.prices_live_lease
     SET claimed_at = clock_timestamp()
   WHERE id = 1
     AND claimed_at < clock_timestamp() - make_interval(secs => min_age_seconds);

  -- true  => this caller owns the window and MUST do the refresh.
  -- false => somebody else already owns it (or the singleton row is missing);
  --          the caller skips and fetches nothing.
  RETURN FOUND;
END
$fn$;

-- Half the security control, not tidiness — see the "BOTH DIRECTIONS" section
-- in the header.
--
-- Naming `anon, authenticated` is what actually does the work here; PUBLIC is
-- named for portability and is a no-op on this project. Do NOT reduce this to
-- `FROM PUBLIC` on the theory that the client roles inherit through it —
-- measured against this project's catalog, they do not. Supabase installs a
-- `pg_default_acl` entry for functions in schema `public` that REPLACES
-- Postgres's built-in EXECUTE-to-PUBLIC default, so a new function is created
-- with `anon=X/postgres` and `authenticated=X/postgres` granted DIRECTLY and no
-- PUBLIC entry to revoke. The sibling definer function confirms the shape:
-- live `prune_langgraph_checkpoints` has `proacl = {postgres=X/postgres,
-- service_role=X/postgres}`. Revoking only PUBLIC leaves anon holding EXECUTE,
-- which makes the next paragraph live rather than hypothetical.
--
-- Without the revoke this is
-- `POST /rest/v1/rpc/claim_prices_live_refresh` to any holder of the published
-- anon key, and every call they win is a claim the cron loses: an attacker
-- starves the live feed with one cheap HTTP request per window and no upstream
-- work at all.
REVOKE ALL ON FUNCTION public.claim_prices_live_refresh(integer)
    FROM PUBLIC, anon, authenticated;

-- The single caller, stated rather than inherited — same argument as the
-- `prices_live` writer grant in migration 063. The `prices-live` edge function
-- authenticates with SUPABASE_SERVICE_ROLE_KEY, i.e. as `service_role`. Note
-- that `rolbypassrls` does not help it here: that bypasses row-level security,
-- not EXECUTE privilege, so without this GRANT the function would 42501 on
-- every run and the feed would go dark.
GRANT EXECUTE ON FUNCTION public.claim_prices_live_refresh(integer) TO service_role;

COMMENT ON FUNCTION public.claim_prices_live_refresh(integer) IS
  'Atomically claim the right to refresh the digiquant.io live price feed: returns true '
  'iff this caller advanced public.prices_live_lease, i.e. iff the last claim was more '
  'than min_age_seconds ago. Exactly one concurrent caller can win a window — a single '
  'conditional UPDATE, so blocked callers re-check the committed row under READ COMMITTED '
  'and match zero rows. Replaces the #1756 invocation secret: the Finnhub free tier is a '
  'RATE limit, so bounding the rate makes an unauthorized invocation worthless instead of '
  'merely forbidden. Callers MUST fail closed — anything other than true means not '
  'claimed, so fetch nothing. Raises if min_age_seconds is NULL or < 1, because a 0 would '
  'let every caller claim and disable the guard silently. service_role only: EXECUTE by '
  'anon would let an attacker BURN the lease and starve the cron.';
