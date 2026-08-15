# Olympus access gating (before sharing)

The Olympus dashboard at `digiquant.io/olympus/` is a **static export** that reads
Supabase directly with the **publishable anon key baked into the JS bundle**, and
every relevant table has an `anon` RLS policy of `USING (true)`. So **anyone with
the URL can read all published data** — the anon key cannot be hidden in a static
bundle, and any client-side gate (passphrase, Supabase-Auth-without-RLS-rewrite)
is bypassable by reading the bundle and replaying the key directly against
Supabase. Treat the URL as public until the edge gate below is live.

## The exposure, concretely

With the URL alone, an anonymous reader can `SELECT` from every table carrying an
`anon … USING (true)` policy — `daily_snapshots`, `documents` (incl. the
`deliberation/*`, `risk-debate`, `pm-rebalance` payloads), `positions`,
`nav_history`, `price_history`, `price_technicals`, `macro_series_observations`,
etc. Migration [`033_revoke_anon_run_diagnostics.sql`](../../digiquant/supabase/migrations/033_revoke_anon_run_diagnostics.sql)
removes the one piece of operator-internal telemetry that leaked
(`atlas_run_diagnostics`: LLM spend, token counts) and that the dashboard never
reads. Everything else *is* the product (research, deliberations, the paper book)
and stays readable to allow-listed viewers once the gate is up.

> Note: `positions.pm_notes` is **not** scrubbed — it is PM commentary the
> dashboard renders and the owner reads; it is part of the decision narrative,
> not operator-internal leakage.

## The gate: Cloudflare Access (edge, before the bundle loads)

Cloudflare Access is the only option that actually closes the exposure for a
static export: it authenticates the request **at Cloudflare's edge, before the
browser ever receives the bundle or reaches Supabase**. Zero code, ~15 minutes,
and it fits Pages perfectly (no API routes / server runtime needed). It is a
**network-exposure change → human gate** (CLAUDE.md): the owner performs the
dashboard config below.

### One-time setup (owner)

1. Cloudflare dashboard → **Zero Trust → Access → Applications → Add an
   application → Self-hosted**.
2. **Application domain:** `digiquant.io`, path `/olympus` (covers `/olympus/*`).
   Leave the apex and `digiquant.io/` (the marketing site) **ungated**.
3. **Session duration:** e.g. 24h–1 week to taste.
4. **Add a policy** → Action **Allow** → Include **Emails** (or *Emails ending
   in* a domain) — the allow-list of people who may view the dashboard:
   ```
   chris.stefan@proton.me
   ```
   Add more viewers here (or an *Emails ending in* rule for a whole org).
5. Identity provider: the built-in **one-time PIN** (email code) needs no IdP
   setup; or wire Google/GitHub SSO under Zero Trust → Settings →
   Authentication.
6. Save. Visiting `digiquant.io/olympus/` now prompts for login; only
   allow-listed identities reach the bundle. The marketing site is unaffected.

### Verify

- Incognito → `digiquant.io/olympus/` → redirected to the Access login (not the
  dashboard). After allow-listed login → dashboard loads.
- `digiquant.io/` (marketing) still loads with no prompt.

## Why not the alternatives

- **Supabase Auth + per-row RLS** — the self-hostable long-term path, but it
  requires rewriting every `anon … USING (true)` policy to `auth.uid()`-scoped
  rules and adding a login flow; 6–8h and pointless until those policies are
  tightened. Defer unless multi-tenant/self-host hosting becomes a requirement.
- **Passphrase / client-side gate** — friction only. The anon key is in the
  bundle; a determined viewer replays it straight against Supabase. Not shipped.

## Status

- [x] `033` drops the anon SELECT RLS policy on `atlas_run_diagnostics` (cost/token
  telemetry) — anon reads return an empty result set; service-role writes unaffected.
- [ ] **Owner:** configure Cloudflare Access on `/olympus/*` (Zero Trust dashboard —
  not doable from the repo) with the allow-list above (currently
  `chris.stefan@proton.me`).
- [ ] **Do not share the URL until the Access app is live.**
