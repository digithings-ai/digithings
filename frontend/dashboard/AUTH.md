# digiquant dashboard access gating

The digiquant dashboard at `digiquant.io/dashboard/` is a **static export** (D6) that
reads Supabase with the **publishable anon key baked into the JS bundle**. Until
app auth cutover, every relevant table still has an `anon` RLS policy of
`USING (true)`, so **anyone with the URL can read all published data**. The anon
key cannot be hidden in a static bundle. The public path is `/dashboard/` only.

## App auth (T1)

Product login is **Supabase Auth** with **Google + GitHub + X OAuth** (and email/password) over the
browser PKCE flow (`@supabase/supabase-js` only — no custom cookies or token
storage). The login UI is the compact `AuthCard` from `@digithings/web`: tool
mark + **`digiquant`** wordmark beside it, then email, password, and one row of
icon-only OAuth (`[G][GH][X]`) plus **Sign in** / **Sign up**. Provider id for X
is `x` (OAuth 2.0; the legacy Twitter OAuth 1.0a provider stays off); visible
label/aria is **X** (never Twitter). No olympus branding. Compact has no live
password-strength meter (that lives on the desk specimen); signup still requires
8+ characters in `LoginScreen`. Routes:

| Path | Role |
|------|------|
| `/dashboard/login/` | Start OAuth / email sign-in (`signInWithOAuth`, `signInWithPassword`) |
| `/dashboard/signup/` | Same card, create-account mode (`signUpWithPassword`) |
| `/dashboard/auth/callback/` | Client-side PKCE completion (static page — no route handlers) |

Everything is behind `NEXT_PUBLIC_DASHBOARD_AUTH=1` (build-time). Flag **off**
(default) ⇒ no behavior change; prerendered DOM verified identical to today's
shell: `AuthGate` passes children through and queries use the classic anon client.

Flag **on** + signed out ⇒ login UI (never empty chrome). Flag on + signed in ⇒
dashboard shell; the same PKCE client attaches the user JWT so RLS can scope
rows after the coordinated anon-policy drop.

OAuth starts with `skipBrowserRedirect: true` so the app assigns `data.url`
itself (Google otherwise drops the redirect on the static `/dashboard/` basePath).
Google also sends `queryParams.access_type=offline` and `prompt=select_account`.
The PKCE client sets `detectSessionInUrl: false` so only the callback page
exchanges `?code=` (`exchangeCodeForSession`). Auto-detect would race the
one-shot code. The callback reads `error` / `error_description`, and fails
closed if neither a code nor a session appears. While `?code=` is present,
`onAuthStateChange` ignores `INITIAL_SESSION` / `TOKEN_REFRESHED` from a
persisted session so PKCE can finish; `SIGNED_IN` (or a successful
`exchangeCodeForSession`) is what navigates home. If Google still fails after
that, the provider is disabled or the Google Cloud client redirect
(`https://<ref>.supabase.co/auth/v1/callback`) is missing — dashboard work,
not an app bug. Email/password sign-in replaces to `/` (AuthGate will not
keep a signed-in user on `/login/` or `/signup/`). Email **sign-up** only
replaces home when `signUp` returns a **session** (Confirm email off). When
confirm-email is on, the card must not claim the confirmation message arrived —
Auth SMTP (and Cloudflare Access PIN, if Access is still on the host) often
never delivers until custom SMTP is wired. Prefer Google/GitHub; first-time
OAuth **is** account creation. Google still has to be **Enabled** in the
Supabase dashboard (Authentication → Providers) plus Redirect URLs; a disabled
provider is not an app bug.

### Env / build

```bash
# .env.local (local) or Cloudflare Pages build env (prod)
NEXT_PUBLIC_SUPABASE_URL=…
NEXT_PUBLIC_SUPABASE_ANON_KEY=…
NEXT_PUBLIC_DASHBOARD_AUTH=1
```

Static export inlines `NEXT_PUBLIC_*` at build — there is no runtime server env.

### Supabase dashboard (human performs)

1. Authentication → Providers → enable **Google**, **GitHub**, and **X**
   (provider id `x`; leave legacy **Twitter** OAuth 1.0a off).
2. Authentication → URL configuration → Redirect URLs (Alpaca `redirect_uri` is
   exact-match; list only dashboard paths):
   - `https://digiquant.io/dashboard/auth/callback/`
   - `https://www.digiquant.io/dashboard/auth/callback/`
   - `http://127.0.0.1:3001/dashboard/auth/callback/` (dev)
   - `http://localhost:3001/dashboard/auth/callback/` (dev)
3. Alpaca OAuth app → Redirect URI:
   - `https://digiquant.io/dashboard/settings/brokers/callback/`
4. Cloudflare Access (Zero Trust → Access → Applications) — **owner console**, no
   API token in this environment. Point the self-hosted application (same Allow
   email policy) at **`digiquant.io/dashboard*`**:
   - Destination: `https://digiquant.io/dashboard*`
   - If a separate app exists for FX Hub: `https://digiquant.io/dashboard/twelve-x*`
   Alpaca / Supabase callback URLs are exact-match and are listed in steps 2–3;
   Access is the path gate in front of those URLs.
5. Do **not** add custom cookie/session wiring in the app — session storage stays
   inside supabase-js (`flowType: 'pkce'`, `persistSession: true`).

### Pages Auth UI (without anon-drop cutover 900)

`/dashboard/login` and `/dashboard/auth/callback` are static routes. They must exist
on `main` for Cloudflare Pages to stop 404ing those paths. Enabling
`NEXT_PUBLIC_DASHBOARD_AUTH=1` (build-time; `scripts/build-digiquant.sh` defaults
`NEXT_PUBLIC_DASHBOARD_AUTH=1` when `CF_PAGES=1` and the var is unset) shows the LoginScreen / AuthGate
**without** applying `migrations/cutover/900_*`. Anon RLS stays until the
coordinated cutover below — do **not** treat Auth-UI-on as full tenancy cutover.

### Cutover checklist (coordinated release — human)

1. Merge T0 workspaces/RLS (incl. drafted anon-policy drop) when ready.
2. Confirm `NEXT_PUBLIC_DASHBOARD_AUTH=1` on the digiquant.io Cloudflare Pages
   build (or leave unset so `build-digiquant.sh` defaults it on under `CF_PAGES=1`).
3. Redeploy the static dashboard bundle.
4. Apply cutover SQL `900_*` only after Access + Auth UI plan (never auto).
5. Owner removes Cloudflare Access from production `/dashboard/*` (D7).
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
2. Point it at the **staging** hostname / path for the dashboard (not production
   digiquant.io after cutover).
3. **Add a policy** → Action **Allow** → Include **Emails** (or domain) for the
   staging allow-list.
4. Identity provider: one-time PIN and/or Google/GitHub under Zero Trust →
   Settings → Authentication.

### Historical production Access (pre-cutover)

Before T1 cutover, production `/dashboard/*` may still use Access as the only gate. Until Access is live on that path, treat the URL as public. Migration
[`033_revoke_anon_run_diagnostics.sql`](../../digiquant/supabase/migrations/033_revoke_anon_run_diagnostics.sql)
already drops anon SELECT on operator cost telemetry (`atlas_run_diagnostics`);
`positions.pm_notes` stays readable (PM commentary the dashboard renders).

## Why not the alternatives

- **Passphrase / client-side gate alone** — friction only. The anon key is in the
  bundle; a determined viewer replays it against Supabase. Not shipped as the
  product login. FX Hub uses the same rule: **login remains required**; a hashed
  invite only INSERTs `client_product_grants` for the signed-in email (settings
  `POST /access/redeem-invite`). Do not put the plaintext invite in
  `NEXT_PUBLIC_*`. Login-optional FX Hub is not a real gate on this architecture.
- **Next.js route handlers / server components for OAuth** — forbidden under
  `output: 'export'` (D6). PKCE completes in the browser on static pages.
- **digikey for end-user login** — digikey remains the machine/API plane (D4);
  dashboard consumer identity is Supabase Auth.

## Status

- [x] T1 code path: flag-gated PKCE login, `/login` + `/signup` + `/auth/callback`, AuthGate.
- [ ] **Owner:** enable **Google** (still often Disabled on `core`) and GitHub + Redirect URLs.
- [x] **Owner:** X OAuth 2.0 enabled on `core` (`external_x_enabled`; authorize `provider=x`). App calls `provider: 'x'`. Legacy `twitter` stays off.
- [ ] **Owner:** Auth SMTP (Mailgun) or turn Confirm email off until SMTP delivers.
- [ ] **Owner:** set `FX_HUB_INVITE_HASH` (sha256 hex of the FX Hub invite) on the settings
      Edge Function, apply migration **112**, share the invite URL (or plaintext) out of band.
- [ ] **Owner:** staging Access overlay retained; production Access removed at
  cutover with `NEXT_PUBLIC_DASHBOARD_AUTH=1` + anon-policy drop.
- [ ] **Do not share an ungated production URL** while anon `USING (true)` still
  applies and Access is not on that host.

## FX Hub — invite link after login

Identity for FX Hub is the same Supabase Auth session as the rest of the dashboard.
The healthy medium is **short login (Google/GitHub/email)** plus a **rotatable hashed
invite** that writes the caller's email into `client_product_grants`. That is
preferable to the operator inserting every analyst address, and it is preferable to a
login-optional shared secret (which cannot hide the anon key).

Share one reusable desk URL on the dashboard origin:

`https://digiquant.io/dashboard?invite=<code>`

Unsigned visitors stash the token in `sessionStorage` (tab-scoped). After Google,
GitHub, or email signup/login **in that same tab**, the app POSTs that code to
settings `POST /access/redeem-invite` (SHA-256 compare against `FX_HUB_INVITE_HASH`
and/or `product_invite_codes`) and grants `fx_hub` for the **signed-in email**.
No session / no email → no grant. Do not put a code field on the OAuth card. The
FX Hub locked surface still has a paste-code form as fallback if someone forgets
the link, or if confirm-email opens a **new** tab (stash does not follow). Rate
limit stays 8 attempts / hour. Rotate the code if the URL leaks. Ops can still
`INSERT` emails into `client_product_grants`. Sign-out drops the stash so a later
session on the same tab cannot inherit it.

Operator steps:

1. Generate a high-entropy code (≥10 chars). Do not commit it.
2. `python -c "import hashlib,sys; print(hashlib.sha256(sys.argv[1].encode()).hexdigest())" '<code>'`
3. `supabase secrets set FX_HUB_INVITE_HASH=<hex>` and redeploy `settings`.
   Optional: `INSERT INTO product_invite_codes (product_key, code_hash, label) VALUES ('fx_hub', '<hex>', 'desk')`.
4. Share the invite URL (or the plaintext) out of band. Analysts open the link,
   create an account, and land granted. Paste-code remains on the locked FX Hub
   surface. `product_invite_redemptions` is the admin ledger (who registered).
   Mailgun digest is a separate secret; until it exists the notification is the
   table row + `notification_log` event `fx_hub_invite_redeemed`.

Cloudflare Access on FX Hub remains a human Zero Trust option if the team should
never see the rest of the dashboard — it is not encoded here.
Do not flip production Access or auth flags as part of the invite-link change.

