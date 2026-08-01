-- 062_realtime_broadcast_authorization.sql — Authorize the `prices:live` Realtime
-- channel so the public anon key can RECEIVE quotes but never BROADCAST them (#1807).
--
-- ⚠️ MUST BE APPLIED BY A ROLE THAT OWNS `realtime.messages` — see "Privilege" below.
-- ⚠️ APPLY AND VERIFY THIS BEFORE the `private: true` clients reach production, or the
--    live price feed goes dark. Ordered runbook: supabase/README.md → "Rolling out
--    Realtime authorization".
--
-- THE HOLE THIS CLOSES
-- --------------------
-- `prices:live` was a *public* Realtime channel: `useLivePrices.ts` joined it with no
-- `config: { private: true }`, and Realtime only consults RLS for channels joined as
-- private. Meanwhile `anon` holds INSERT on `realtime.messages` (a Supabase platform
-- grant) and `pg_policies where schemaname = 'realtime'` returned ZERO rows. So the anon
-- key that ships in plaintext in every digiquant.io JS bundle could POST to
-- /realtime/v1/api/broadcast and put forged quotes on `prices:live`, which every open tab
-- would render as live Finnhub data. The `prices-live` edge function was bypassed
-- entirely — so the invocation secret added in #1756/PR #1790 does not cover this path.
--
-- Realtime Authorization has exactly two moving parts, and BOTH are required:
--   1. RLS policies on `realtime.messages`  ← this file
--   2. `config: { private: true }` on every client that joins the topic
--      ← useLivePrices.ts (subscriber) and functions/prices-live/index.ts (publisher)
-- Half a fix is worse than none: policies alone are inert (a public channel never
-- consults them), and `private: true` alone refuses every join (no policy = no access).
--
-- WHAT THE POLICIES SAY
-- --------------------
--   * anon + authenticated may SELECT  → receive broadcasts on `prices:live` only.
--   * service_role may INSERT          → the edge function publishes.
--   * NOBODY else may INSERT. There is deliberately NO insert policy for anon or
--     authenticated, and that omission IS the fix — under RLS, absent policy = deny.
-- `extension = 'broadcast'` scopes both to broadcast traffic, so this grants nothing for
-- presence or postgres_changes. `realtime.topic()` is Supabase's helper returning the
-- topic the client is joining.
--
-- Not touched: the `anon` INSERT/UPDATE *grants* on `realtime.messages`. Those are
-- platform-managed by Supabase (revoking them is unsupported and would be reverted by
-- the platform); RLS is the intended control surface, which is why the missing INSERT
-- policy above is sufficient. Nothing here narrows `service_role`, which carries
-- rolbypassrls anyway — the explicit insert policy is there so the publisher's authority
-- is stated in the schema rather than inferred from a role attribute.
--
-- PRIVILEGE — why this migration can fail where every other one succeeds
-- ---------------------------------------------------------------------
-- `realtime.messages` is owned by `supabase_realtime_admin`, NOT by `postgres`, and
-- `CREATE POLICY` requires table ownership. Verified read-only against the live `core`
-- project on 2026-08-01:
--     realtime.messages owner ................................. supabase_realtime_admin
--     pg_has_role('postgres','supabase_realtime_admin','USAGE')  false
--     postgres rolsuper ....................................... false
-- So as `postgres` this raises `42501 must be owner of table messages`. Because
-- db-migrate.yml applies migrations above BASELINE_THROUGH with --single-transaction, a
-- failure here rolls back AND blocks every later migration in the same run. The guard
-- below turns that into a legible error instead of a bare 42501, and deliberately does
-- NOT swallow it: a silently skipped policy plus a shipped `private: true` client is the
-- exact silent outage this file is ordered to prevent.
--
-- Idempotent: DROP POLICY IF EXISTS before each CREATE, so re-running is safe.
-- No `BEGIN;` on purpose — db-migrate.yml greps for one and would then skip
-- --single-transaction; this file wants to be wrapped by the deploy script.

-- Preflight: fail loudly, with the remedy, if the executing role cannot create policies
-- on realtime.messages.
--
-- `pg_has_role(current_user, owner_oid, 'USAGE')` is EXACTLY Postgres's own ownership test
-- (`pg_class_ownercheck`), which is why it is the condition here rather than an approximation
-- of it. It does NOT need a separate superuser branch: a superuser is implicitly a member of
-- every role, so the check passes for one. Measured read-only on the live project (a review
-- pass raised the opposite concern, so it is recorded here rather than argued):
--     pg_has_role('supabase_admin','supabase_realtime_admin','USAGE') → TRUE   (rolsuper)
--     pg_has_role('postgres',      'supabase_realtime_admin','USAGE') → FALSE  (not a member)
-- Adding `OR rolsuper` would therefore be dead code, and hard-coding role NAMES here would
-- make the guard drift from the privilege it is standing in for. Do not "fix" this.
DO $$
DECLARE
  owner_oid oid;
BEGIN
  SELECT c.relowner INTO owner_oid
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'realtime' AND c.relname = 'messages';

  IF owner_oid IS NULL THEN
    RAISE EXCEPTION 'migration 062: relation realtime.messages does not exist'
      USING HINT = 'Realtime must be enabled on this project before broadcast '
                   'authorization can be configured.';
  END IF;

  IF NOT pg_catalog.pg_has_role(current_user, owner_oid, 'USAGE') THEN
    RAISE EXCEPTION
      'migration 062: current_user % cannot create policies on realtime.messages (owner: %)',
      current_user, owner_oid::regrole
      USING ERRCODE = 'insufficient_privilege',
            HINT = 'CREATE POLICY requires table ownership. Apply this migration as the '
                   'owner role (supabase_realtime_admin) or a superuser '
                   '(supabase_admin), or have an admin run '
                   '"GRANT supabase_realtime_admin TO postgres;" once. Re-check with: '
                   'select * from pg_policies where schemaname = ''realtime'';';
  END IF;
END
$$;

-- Receive: anon and authenticated may read broadcast messages on `prices:live` and
-- nothing else. Public market quotes are not privileged data, and an authenticated
-- visitor must not lose the feed — but neither role gets a matching insert policy.
DROP POLICY IF EXISTS prices_live_receive_broadcast ON realtime.messages;
CREATE POLICY prices_live_receive_broadcast
  ON realtime.messages
  FOR SELECT
  TO anon, authenticated
  USING (
    extension = 'broadcast'
    AND (SELECT realtime.topic()) = 'prices:live'
  );

-- Publish: only the service role (the `prices-live` edge function) may broadcast.
DROP POLICY IF EXISTS prices_live_service_role_broadcast ON realtime.messages;
CREATE POLICY prices_live_service_role_broadcast
  ON realtime.messages
  FOR INSERT
  TO service_role
  WITH CHECK (
    extension = 'broadcast'
    AND (SELECT realtime.topic()) = 'prices:live'
  );
