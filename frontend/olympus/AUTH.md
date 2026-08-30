# Olympus access gating

The Olympus dashboard at `digiquant.io/olympus/` is a **static export** (D6) that
reads Supabase with the **publishable anon key baked into the JS bundle**. Until
app auth cutover, every relevant table still has an `anon` RLS policy of
`USING (true)`, so **anyone with the URL can read all published data**. The anon
key cannot be hidden in a static bundle.

## App auth (T1)

Product login is **Supabase Auth** with **Google + GitHub OAuth** over the
browser PKCE flow (`@supabase/supabase-js` only — no custom cookies or token
storage). Routes:

| Path | Role |
|------|------|
| `/olympus/login/` | Start OAuth (`signInWithOAuth`) |
| `/olympus/auth/callback/` | Client-side PKCE completion (static page — no route handlers) |

Everything is behind `NEXT_PUBLIC_OLYMPUS_AUTH=1` (build-time). Flag **off**
(default) ⇒ no behavior change; prerendered DOM verified identical to today's
shell: `AuthGate` passes children through and queries use the classic anon client.

Flag **on** + signed out ⇒ login UI (never empty chrome). Flag on + signed in ⇒
dashboard shell; the same PKCE client attaches the user JWT so RLS can scope
rows after the coordinated anon-policy drop.

### Env / build

```bash
# .env.local (local) or Cloudflare Pages build env (prod)
NEXT_PUBLIC_SUPABASE_URL=…
NEXT_PUBLIC_SUPABASE_ANON_KEY=…
NEXT_PUBLIC_OLYMPUS_AUTH=1
```

Static export inlines `NEXT_PUBLIC_*` at build — there is no runtime server env.

### Supabase dashboard (human performs)

1. Authentication → Providers → enable **Google** and **GitHub** (D4).
2. Authentication → URL configuration → Redirect URLs, allow:
   - `https://digiquant.io/olympus/auth/callback/`
   - `http://localhost:3000/olympus/auth/callback/` (dev)
3. Do **not** add custom cookie/session wiring in the app — session storage stays
   inside supabase-js (`flowType: 'pkce'`, `persistSession: true`).

### Cutover checklist (coordinated release — human)

1. Merge T0 workspaces/RLS (incl. drafted anon-policy drop) when ready.
2. Flip `NEXT_PUBLIC_OLYMPUS_AUTH=1` on the digiquant.io Cloudflare Pages build.
3. Redeploy the static Olympus bundle.
4. Owner removes Cloudflare Access from production `/olympus/*` (D7).
5. Keep Access on **staging** only (below).

**HUMAN GATE:** auth flow review before merge; production cutover is owner-led.

## Cloudflare Access (staging-only overlay after T1)

Cloudflare Access remains useful as a **staging** allow-list overlay (D7). It is
**not** the production product login once T1 ships — production identity is
Supabase Auth + RLS. Production Access removal is a dashboard change (human-
owned); do not encode it in this repo.

### Staging setup (owner)

1. Cloudflare dashboard → **Zero Trust → Access → Applications → Add an
   application → Self-hosted**.
2. Point it at the **staging** hostname / path for Olympus (not production
   digiquant.io after cutover).
3. **Add a policy** → Action **Allow** → Include **Emails** (or domain) for the
   staging allow-list.
4. Identity provider: one-time PIN and/or Google/GitHub under Zero Trust →
   Settings → Authentication.

### Historical production Access (pre-cutover)

Before T1 cutover, production `/olympus/*` may still use Access as the only
gate. Until Access is live on that path, treat the URL as public. Migration
[`033_revoke_anon_run_diagnostics.sql`](../../digiquant/supabase/migrations/033_revoke_anon_run_diagnostics.sql)
already drops anon SELECT on operator cost telemetry (`atlas_run_diagnostics`);
`positions.pm_notes` stays readable (PM commentary the dashboard renders).

## Why not the alternatives

- **Passphrase / client-side gate alone** — friction only. The anon key is in the
  bundle; a determined viewer replays it against Supabase. Not shipped as the
  product login.
- **Next.js route handlers / server components for OAuth** — forbidden under
  `output: 'export'` (D6). PKCE completes in the browser on static pages.
- **digikey for end-user login** — digikey remains the machine/API plane (D4);
  Olympus consumer identity is Supabase Auth.

## Status

- [x] T1 code path: flag-gated PKCE login, `/login` + `/auth/callback`, AuthGate.
- [ ] **Owner:** enable Google/GitHub providers + redirect URLs in Supabase.
- [ ] **Owner:** staging Access overlay retained; production Access removed at
  cutover with `NEXT_PUBLIC_OLYMPUS_AUTH=1` + anon-policy drop.
- [ ] **Do not share an ungated production URL** while anon `USING (true)` still
  applies and Access is not on that host.
