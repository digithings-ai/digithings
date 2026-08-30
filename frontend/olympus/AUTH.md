# Olympus access gating

The Olympus dashboard at `digiquant.io/olympus/` is a **static export** (D6) that
reads Supabase with the **publishable anon key baked into the JS bundle**. Until
app auth cutover, every relevant table still has an `anon` RLS policy of
`USING (true)`, so **anyone with the URL can read all published data**. The anon
key cannot be hidden in a static bundle.

## App auth (T1)

Product login is **Supabase Auth** with **Google + GitHub OAuth** (and email/password) over the
browser PKCE flow (`@supabase/supabase-js` only — no custom cookies or token
storage). Routes:

| Path | Role |
|------|------|
| `/olympus/login/` | Start OAuth / email sign-in (`signInWithOAuth`, `signInWithPassword`) |
| `/olympus/signup/` | Same card, create-account mode (`signUpWithPassword`) |
| `/olympus/auth/callback/` | Client-side PKCE completion (static page — no route handlers) |

Everything is behind `NEXT_PUBLIC_OLYMPUS_AUTH=1` (build-time). Flag **off**
(default) ⇒ no behavior change; prerendered DOM verified identical to today's
shell: `AuthGate` passes children through and queries use the classic anon client.

Flag **on** + signed out ⇒ login UI (never empty chrome). Flag on + signed in ⇒
dashboard shell.

**Two clients (required while anon_read is still live):** house Brief /
Portfolio / Pipeline reads use a session-less anon client (`supabaseHouse`,
`persistSession: false`). Login and Settings use the PKCE client, which
attaches the user JWT. `anon_read` policies are `TO anon` only — sending the
JWT (`role=authenticated`) hides house rows and 406s `daily_snapshots.single()`.
Do not point `lib/queries.ts` at the PKCE singleton until cutover 900 replaces
anon_read with authenticated house/teaser policies.

OAuth starts with `skipBrowserRedirect: true` so the app assigns `data.url`
itself (Google otherwise drops the redirect on the static `/olympus/` basePath).
Google also sends `queryParams.access_type=offline` and `prompt=select_account`.
The PKCE client sets `detectSessionInUrl: false` so only the callback page
exchanges `?code=` (`exchangeCodeForSession`). Auto-detect would race the
one-shot code. The callback reads `error` / `error_description`, and fails
closed if neither a code nor a session appears. If Google still fails after
that, the provider is disabled or the Google Cloud client redirect
(`https://<ref>.supabase.co/auth/v1/callback`) is missing — dashboard work,
not an app bug. Email/password sign-in replaces to `/` (AuthGate will not
keep a signed-in user on `/login/` or `/signup/`).

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

### Pages Auth UI (without anon-drop cutover 900)

`/olympus/login` and `/olympus/auth/callback` are static routes. They must exist
on `main` for Cloudflare Pages to stop 404ing those paths. Enabling
`NEXT_PUBLIC_OLYMPUS_AUTH=1` (build-time; `scripts/build-digiquant.sh` defaults
it on when `CF_PAGES=1` and the var is unset) shows the LoginScreen / AuthGate
**without** applying `migrations/cutover/900_*`. Anon RLS stays until the
coordinated cutover below — do **not** treat Auth-UI-on as full tenancy cutover.
House dashboard queries must keep using the session-less anon client until that
cutover; the PKCE JWT is for login/Settings only.

### Cutover checklist (coordinated release — human)

1. Merge T0 workspaces/RLS (incl. drafted anon-policy drop) when ready.
2. Confirm `NEXT_PUBLIC_OLYMPUS_AUTH=1` on the digiquant.io Cloudflare Pages build
   (or leave unset so `build-digiquant.sh` defaults it on under `CF_PAGES=1`).
3. Redeploy the static Olympus bundle.
4. Apply cutover SQL `900_*` only after Access + Auth UI plan (never auto).
5. Owner removes Cloudflare Access from production `/olympus/*` (D7).
6. Keep Access on **staging** only (below).

**HUMAN GATE:** auth flow review before merge; production cutover is owner-led.
**Never apply cutover 900** as part of the narrow Auth Pages PR.

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
