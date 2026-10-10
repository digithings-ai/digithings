# Gloomberb session-cookie runbook (#4099)

Forty-two of the 89 `digifetch_*` tools read session-gated endpoints and
need a session cookie: 41 take `GLOOMBERB_SESSION_COOKIE` (37 `session` + 1
`preview` + 3 `pro`) and `digifetch_substack` takes its own
`SUBSTACK_SESSION_COOKIE` (`venue_session`); the other 47 are anonymous and
keep working with no cookie at all. This runbook covers the
free-account signup, the cookie extraction, where the cookie is placed per
deployment, the privacy rules, and exactly what an operator sees when the cookie
is absent. It is a follow-up to #4069 (the family landed in PR #4085) and was
last widened by #4837 (130-function coverage: 15 probe-backed Cloud reads and
13 inert workspace/broker tools joined the gated set).

> **Credential ownership (changed 10 Oct 2026, DIG-2752)**: the cookie belongs to
> **whoever deploys the digithings stack**, and to their own Gloomberb account. digithings
> does not hold one, mints one, shares one or replays one on anyone's behalf. A deployer
> who wants the 41 gated tools supplies their own secret through their own store — their
> Cloudflare Worker secret, their own gitignored `.env`, or their own macOS Keychain.
> See `docs/ops/credential-ownership.md` for the general single-owner rule and
> **"Bring your own Gloomberb account"** below for the deployer guide.
>
> The GitHub Actions `cron` environment secret described in earlier revisions of this
> runbook is **retired as the canonical store**. A pipeline that still holds a copy is
> carrying a credential nobody owns: rotate it and delete it (see **Rotate or expire**).

## Tools are advertised only when the cookie is authenticated

Before this change the family was gated on **presence**: any non-empty value in
`GLOOMBERB_SESSION_COOKIE` advertised all 41 gated tools, and an expired or
mistyped value only discovered itself when a call came back `auth_required`.
Advertising a tool the deployment cannot use is a lie the operator pays for in a
failed call, so the gate now **validates** (DIG-2752).

The rules, in order:

1. **No secret, no tools, no request.** With no cookie the gated tools are simply not
   listed, and **no HTTP request is made** to decide that. The 47 free tools are
   untouched.
2. **A secret is probed once per cache window.** When a cookie *is* configured, one
   authenticated read of `/market/quote` is made to confirm api.gloom.sh accepts it.
   Gloomberb publishes no `/me` or `/session` route, so the probe reuses the cheapest
   side-effect-free read and pins a single attempt, so a probe never spends the shared
   rate limit. The verdict is cached for the client's normal TTL (900 s), keyed on a
   non-reversible fingerprint of the cookie, so repeated listings make no further
   requests and swapping the cookie invalidates the verdict immediately.
3. **Anything unproven hides the tools.** A rejected cookie, a transport failure, a
   timeout or an unparseable answer all hide the family and log one warning that names
   the remediation below. The gate fails closed: there is no path where an
   unvalidated cookie advertises a tool.

Run `digiquant gloomberb status` at any time to see which of these you are in. It
prints the kill switch, which local stores hold a cookie, a non-reversible
fingerprint of the value, the validation verdict and whether the gated tools are
currently advertised — and never the value itself.

`GLOOMBERB_ENABLED` stays an **independent kill switch that overrides**: off means
the whole family is disabled regardless of the cookie, and a typo in its value fails
closed. The cookie gate and the kill switch are two separate gates, and a
deployment needs both open.

## Bring your own Gloomberb account

You need an account to get a cookie; there is no shared digithings account to sign
into. Follow **Get a free account** below, then extract your own cookie with
**Extract the session cookie**. What differs from the old shared-cookie model is only
whose credential it is:

- **It is yours.** It comes from your Gloomberb login, it is stored in your own
  deployment's secret store, and it is removed when you revoke it.
- **We never ask you for it.** No agent, comment or ticket ever needs the value. If
  something asks you to paste a Gloomberb cookie into a conversation, that is not
  digithings.
- **Terms of service (DIG-1233, Counsel).** Counsel's finding is that a hosted
  digithings surface must **not replay a shared cookie** on your behalf, and that
  anonymous, credential-free reads are the supported hosted behaviour. That is why
  this is your cookie in your deployment and never a company-held credential: the
  arrangement has to match the account's terms, and it is yours to accept. If your
  use is not an ordinary personal or single-tenant use of the account you created,
  ask Counsel before deploying.
- **Access class.** Counsel recorded the service as an **"Unclear"** class-B
  integration (DIG-1232): anonymous reads are fine, and anything that depends on
  cookie replay has an open licence question. This runbook does not resolve it.

### Onboarding with `digiquant gloomberb login`

The command walks you through the whole flow and never prints, echoes or logs the
value — the paste is a hidden prompt, and `status` shows only a fingerprint.

```bash
digiquant gloomberb login                 # sign in to your own Gloomberb account,
                                          # paste the value here (input is hidden),
                                          # it is validated before anything is stored
digiquant gloomberb login --store env     # ...and written to a gitignored .env at 0600
digiquant gloomberb login --store keychain  # ...and written to the macOS Keychain
digiquant gloomberb login --store cloudflare  # ...and NOT stored: prints the exact
                                          # wrangler command to run in your shell
digiquant gloomberb status                # which stores hold a cookie, and the verdict
digiquant gloomberb shell digiquant prices quote --symbol AAPL
                                          # run a command with the cookie injected into
                                          # its environment, without writing it to a file
digiquant gloomberb logout --yes          # remove it from the Keychain and .env, and
                                          # print the commands that remove it elsewhere
```

Nothing is stored until api.gloom.sh has accepted the value, and nothing is stored
outside a 0600 file or the OS Keychain. For a shared host prefer `--store env` (or
`shell`): the Keychain path hands the value to `/usr/bin/security` as a command-line
argument, which is visible to any process listing arguments on that machine.

### Rotate or expire

A cookie is as good as the login behind it, so treat it like one:

- **Rotate** when you are asked to, when you suspect it leaked, or on your own
  schedule: sign in again, run `digiquant gloomberb login` again, and
  `digiquant gloomberb logout` in the store you are replacing.
- **Expire it for real** at `term.gloom.sh` (sign out, or revoke the session), not
  only locally. Deleting the local copy does not end the session.
- **In Cloudflare**, remove the Worker secret with
  `npx wrangler secret delete GLOOMBERB_SESSION_COOKIE`. Until it is replaced the
  deployer has no gated tools, which is the intended fail-closed state.
- **In CI**, delete the retired `cron` environment secret if a pipeline still holds a
  copy, then store the new cookie through whatever secret store that pipeline uses.

## What happens without the cookie

The absent-cookie path is a **supported state**, not a failure: the 47 free tools
are unaffected, and the 42 gated tools answer a typed error instead of touching
the network.

- **Gated tools return `auth_required` with no HTTP request.** When
  `GLOOMBERB_SESSION_COOKIE` is unset the client short-circuits before any
  request and returns a non-retryable `DigifetchError(code="auth_required",
  message="... GLOOMBERB_SESSION_COOKIE is not set")` (`client.py:2248-2254`).
  Zero bytes leave the process.
- **Pro-only tools return `pro_required` for a valid free session.** A verified
  free session that calls `digifetch_transcripts`, `digifetch_screener`, or
  `digifetch_options_flow` is
  entitled to be here but not to the route; the upstream plan gate is mapped to
  a typed, non-retryable `pro_required` (distinct from `auth_required`, so a
  caller can tell a missing session from a missing plan) (`client.py:307-322`).
- **The family kill switch is `GLOOMBERB_ENABLED` (default OFF in every
  environment, local included).** Only
  `1`/`true`/`yes`/`on` (case-insensitive) enable the family; **any other value —
  a typo included — keeps it off**, and every call then returns a typed
  `upstream_error` with no request (`client.py:248-272`). This fails closed on
  purpose. **The cookie above does nothing while the switch is off** — set
  `GLOOMBERB_ENABLED=1` in `.env` (see `.env.example`) to opt back in.
- **The pipeline in-process surface filters rather than errors.** When the
  cookie is unset, `available_digifetch_tools` drops the session/preview/pro
  tools (and the whole family when the kill switch is off) so a pipeline LLM is
  never handed a tool that can only error (`agent_tools.py:261-292`). The MCP
  surface registers all 89 and answers the typed error per call.
- **Read-scope membership is not a read-only guarantee.** Every digifetch tool
  — including the 13 write-shaped workspace/broker tools — is registered in
  the `read` MCP scope, but that is a surfacing decision, not a safety
  property. What makes the write-shaped tools safe is the Task 7 read-only
  verdict (below): without a cookie they answer `auth_required` with zero
  HTTP, and with one they answer the typed read-only `upstream_error`, also
  with zero HTTP. Scope never substitutes for that verdict.

## Which tools need it

42 of the 89 `digifetch_*` tools are cookie-gated, each carrying one
entitlement (`entitlements.py`), as of 2026-09-30 (#4837):

| Entitlement | Tools |
|---|---|
| `session` (37) | Original nine reads: `digifetch_holders`, `digifetch_analyst_research`, `digifetch_corporate_actions`, `digifetch_research_search`, `digifetch_statements`, `digifetch_ticker_tweets`, `digifetch_tweet_search`, `digifetch_short_interest`, `digifetch_saved_searches` · 15 probe-backed Cloud reads (#4837 Task 5): `digifetch_time_and_sales`, `digifetch_quote_recap`, `digifetch_estimate_revisions`, `digifetch_short_volume`, `digifetch_hiring`, `digifetch_central_bank_rates`, `digifetch_cdx`, `digifetch_sovereign_cds`, `digifetch_cot`, `digifetch_crypto_markets`, `digifetch_iv_screen`, `digifetch_iv_history`, `digifetch_iv_surface`, `digifetch_debt_maturities`, `digifetch_session_movers` · 13 inert workspace/broker tools (#4837 Task 7): `digifetch_portfolio_view`, `digifetch_watchlist_add`, `digifetch_watchlist_remove`, `digifetch_portfolio_add`, `digifetch_portfolio_remove`, `digifetch_alert_add`, `digifetch_alert_list`, `digifetch_note_add`, `digifetch_thesis_add`, `digifetch_view_add`, `digifetch_broker_positions`, `digifetch_ibkr_preview_order`, `digifetch_ibkr_execute_order` |
| `preview` (1) | `digifetch_equity_diagnostic` — a free session still gets a labeled `access="preview"` report instead of a hard gate |
| `pro` (3) | `digifetch_transcripts`, `digifetch_screener`, `digifetch_options_flow` — a free session is gated with `pro_required` |
| `venue_session` (1) | `digifetch_substack` — needs its own `SUBSTACK_SESSION_COOKIE` (your own Substack account); without it the tool answers `auth_required` with login instructions and makes no request |

The family total is **89 tools, 47 of them free** as of 2026-09-30; a rename or a
new gated tool updates this doc in the same change (the repo-level test in
`tests/scripts/test_gloomberb_session_cookie_runbook.py` fails otherwise —
it requires every non-free tool name to appear above).

**Read-only posture of the write-shaped tools (#4837 Task 7).** The 13
workspace/broker tools look like writes but cannot write in this phase: no
personal Cloud write route was verified (the 2026-09-30 source probe found
only team-scoped account APIs). Without a cookie they answer `auth_required`
with zero HTTP; with one they answer the typed read-only `upstream_error`,
also with zero HTTP. `digifetch_ibkr_preview_order` mints a local HMAC
approval ticket (single-use, 15-minute TTL) without touching any brokerage;
`digifetch_ibkr_execute_order` ships DISABLED pending human review of the
approval-gate design — only `dry_run` returns data (the would-be request,
zero brokerage traffic). Supplying a cookie therefore does not enable any
write; it only changes which typed read-only answer these tools give.

This is enrichment data, not a pipeline primary: the free tier is **delayed up
to 15 minutes** (the client's own delay notice), so no trading or research path
should depend on a gated tool for a correctness-critical read.

## Get a free account

A free (email-verified) account is enough for the `session` and `preview`
tools; the three `pro` tools need a Gloomberb Pro plan, which this runbook does
not cover (there is no in-tree upgrade flow).

The steps below mirror the shipped terminal app's own copy at
<https://term.gloom.sh/> (observed 2026-09-16; the app may reword its UI):

1. Open <https://term.gloom.sh/> in a browser.
2. Open the command palette with `Ctrl+P` and choose **Sign Up**. The app
   advertises this directly: "Create an account anytime: Ctrl+P → Sign Up."
3. Enter your **Email** and a **Password** (the app enforces a minimum new-
   password length of 8 characters), confirm the password, and choose
   **Create Account**. **Log in instead** switches to the sign-in form;
   **Continue without an account** keeps you anonymous and cookie-less.
4. The app confirms "Confirmation link sent. Check your inbox and spam
   folder." Open the emailed link to verify the address — gated tools unlock
   only after verification ("Create the free account now. Cloud features unlock
   after you verify your email."). If the mail does not arrive, use **Resend
   Verification Email**.

If your environment cannot reach a browser or the signup flow is unavailable,
stop here: the 47 free tools work without an account, and gated calls will
simply answer `auth_required`.

## Extract the session cookie

1. Signed in at <https://term.gloom.sh/>, open the browser devtools.
2. Go to **Application** / **Storage** → **Cookies** → `term.gloom.sh`.
3. Copy the value of `__Secure-gloomberb.session_token`. If that name is not
   present, use the fallback `gloomberb.session_token` (the two upstream session
   cookie names are pinned at `client.py:180-183`).

The client accepts either a **`name=value`** pair (preferred — it sends exactly
that cookie) or a **bare token** (sent under both upstream session-cookie names,
the same fallback the TypeScript client uses). Only ever paste the value into a
secret store, never into chat, an issue, a PR, or a commit. The example value
below is a placeholder:

```
GLOOMBERB_SESSION_COOKIE=__Secure-gloomberb.session_token=<cookie-value>
```

## Place it per deployment

### Local runs

Append the line above to the repo-root `.env` (the file is gitignored; never
commit a value). The client reads the variable once at construction — "no
environment variables are read at import time" (`client.py:16-17`) — so a
running process must be restarted after the value changes. `.env.example` now
carries a commented `# GLOOMBERB_SESSION_COOKIE=` placeholder pointing at this
runbook.

### Hosted MCP container

`GLOOMBERB_SESSION_COOKIE` **is forwarded** to the hosted container
(wiring shipped in #4260): the name is in `DigiQuantMcpContainer.envVars`
(`apps/digithings-stack-cloudflare/src/index.ts`) beside
`DIGIQUANT_MCP_SCOPE`, `DIGIQUANT_MARKET_DATA_BACKEND`, and the
four `R2_*` names; that set is pinned by `tests/scripts/test_mcp_container.py`.
Until an operator sets the secret the variable is empty, so the gated tools on
that surface still answer the typed `auth_required`.

Set the secret from `apps/digithings-stack-cloudflare/` with the `$VALUE`
/ `env -u` convention from `digiquant/ARCHITECTURE.md` (never echoing the
value):

```bash
printf '%s' "$VALUE" | env -u CLOUDFLARE_API_TOKEN npx wrangler secret put GLOOMBERB_SESSION_COOKIE
```

The `mcp.digithings.ai` route itself is commented out and human-gated pending
Worker-edge digikey JWT enforcement (`wrangler.toml`). Enabling the route and
forwarding this variable are separate decisions — do not enable the route as
part of setting the cookie.

### GitHub Actions pipeline

No `GLOOMBERB_` variable is set in any workflow today (verified 2026-09-16), so
the pipeline's in-process agent surface filters the gated tools out
(`agent_tools.py:261-292`) and there is nothing to rotate there yet. If a
pipeline phase ever needs a gated tool, the placement is the **GitHub Actions
`cron` environment secret** `GLOOMBERB_SESSION_COOKIE` (canonical store per
`docs/ops/credential-ownership.md`) — tracked as future work, deliberately not
documented as live.

## Verify the cookie works

With the value exported into the environment (this prints only a code or a row
count, never the value):

```bash
set -a; . ./.env; set +a
python -c "
from digiquant.data.gloomberb import GloomberbClient
from digiquant.data.gloomberb.models import DigifetchError
with GloomberbClient(enabled=True) as client:
    envelope = client.holders({'symbol': 'AAPL'})
if isinstance(envelope.data, DigifetchError):
    print('FAIL', envelope.data.code)
else:
    print('OK holders rows =', len(envelope.data.holders))
"
```

Expected: `OK holders rows = <n>` with `n > 0`. If it prints
`FAIL auth_required`, the cookie was not read — check the quoting and that the
value was actually exported (`set -a` before sourcing `.env`), and that a
`name=value` form still carries its `name=` prefix. `FAIL pro_required` means the
session is valid but not entitled to a Pro route (you called one of the three
`pro` tools).

## Privacy rules

- **Never log, never echo, never paste.** The cookie is never logged by the
  client (module docstring line 14, `client.py:439`); keep it out of shell
  history, issue bodies, PR descriptions, chat, and screenshots.
- **The cache discriminator is a fingerprint, not the cookie.** The 900s TTL
  cache is keyed by a truncated SHA-256 fingerprint of the session
  (`session_cache_fingerprint`, `client.py:186-197`), so no response cache ever
  stores the secret.
- **The cookie only crosses same-origin redirect hops.** Per-call cookies are
  forwarded to a redirect target only when it shares the origin; a hop to
  another host drops them (`digifetch/src/digifetch/http.py:224`).
- **Rotation is a replacement, not a flush.** To rotate, replace the value in
  every placement (the local `.env` and the hosted
  `GLOOMBERB_SESSION_COOKIE` secret). Because the fingerprint separates
  sessions, a rotated cookie cannot
  receive a response cached under the old one — no cache flush or restart is
  needed for correctness.

## Related

- Credential ownership register: `docs/ops/credential-ownership.md`
- Design spec: `docs/superpowers/specs/2026-09-16-gloomberb-session-cookie-runbook-design.md`
- Family spec: `docs/superpowers/specs/2026-09-12-digifetch-scoping-design.md`
- Component map: `digiquant/ARCHITECTURE.md`
- Origin / tracking issues: [#4069](https://github.com/digithings-ai/digithings/issues/4069), [#4110](https://github.com/digithings-ai/digithings/issues/4110), [#4101](https://github.com/digithings-ai/digithings/issues/4101), [#4837](https://github.com/digithings-ai/digithings/issues/4837)
- Hosted-container forwarding (shipped): [#4260](https://github.com/digithings-ai/digithings/issues/4260)
