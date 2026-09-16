# Gloomberb session-cookie runbook (#4099)

Eleven of the 33 `digifetch_*` tools read Gloomberb's session-gated endpoints and
need a Gloomberb session cookie supplied as `GLOOMBERB_SESSION_COOKIE`; the other
22 are anonymous and keep working with no cookie at all. This runbook covers the
free-account signup, the cookie extraction, where the cookie is placed per
deployment, the privacy rules, and exactly what an operator sees when the cookie
is absent. It is a follow-up to #4069 (the family landed in PR #4085).

## What happens without the cookie

The absent-cookie path is a **supported state**, not a failure: the 22 free tools
are unaffected, and the 11 gated tools answer a typed error instead of touching
the network.

- **Gated tools return `auth_required` with no HTTP request.** When
  `GLOOMBERB_SESSION_COOKIE` is unset the client short-circuits before any
  request and returns a non-retryable `DigifetchError(code="auth_required",
  message="… GLOOMBERB_SESSION_COOKIE is not set")` (`client.py:2248-2254`).
  Zero bytes leave the process.
- **Pro-only tools return `pro_required` for a valid free session.** A verified
  free session that calls `digifetch_transcripts` or `digifetch_screener` is
  entitled to be here but not to the route; the upstream plan gate is mapped to
  a typed, non-retryable `pro_required` (distinct from `auth_required`, so a
  caller can tell a missing session from a missing plan) (`client.py:307-322`).
- **The family kill switch is `GLOOMBERB_ENABLED` (default ON).** Only
  `1`/`true`/`yes`/`on` (case-insensitive) enable the family; **any other value —
  a typo included — disables it**, and every call then returns a typed
  `upstream_error` with no request (`client.py:248-272`). This fails closed on
  purpose.
- **The pipeline in-process surface filters rather than errors.** When the
  cookie is unset, `available_digifetch_tools` drops the session/preview/pro
  tools (and the whole family when the kill switch is off) so a pipeline LLM is
  never handed a tool that can only error (`agent_tools.py:261-292`). The MCP
  surface registers all 33 and answers the typed error per call.

## Which tools need it

11 of the 33 `digifetch_*` tools are cookie-gated, each carrying one
entitlement (`entitlements.py:58-96`), as of 2026-09-16:

| Entitlement | Tools |
|---|---|
| `session` (8) | `digifetch_holders`, `digifetch_analyst_research`, `digifetch_corporate_actions`, `digifetch_research_search`, `digifetch_statements`, `digifetch_ticker_tweets`, `digifetch_tweet_search`, `digifetch_short_interest` |
| `preview` (1) | `digifetch_equity_diagnostic` — a free session still gets a labeled `access="preview"` report instead of a hard gate |
| `pro` (2) | `digifetch_transcripts`, `digifetch_screener` — a free session is gated with `pro_required` |

The family total is **33 tools, 22 of them free** as of 2026-09-16; a rename or a
new gated tool updates this doc in the same change (the repo-level test in
`tests/scripts/test_gloomberb_session_cookie_runbook.py` fails otherwise).

This is enrichment data, not a pipeline primary: the free tier is **delayed up
to 15 minutes** (the client's own delay notice), so no trading or research path
should depend on a gated tool for a correctness-critical read.

## Get a free account

A free (email-verified) account is enough for the `session` and `preview`
tools; the two `pro` tools need a Gloomberb Pro plan, which this runbook does
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
stop here: the 22 free tools work without an account, and gated calls will
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

**The cookie is not forwarded to the hosted container today.** The gated tools
advertised on that surface therefore answer the typed `auth_required` until the
wiring below ships. `DigiQuantMcpContainer.envVars`
(`cloudflare/digithings-stack-cloudflare/src/index.ts:177-185`) forwards only
`DIGIQUANT_MCP_SCOPE`, `DIGIQUANT_MARKET_DATA_BACKEND`, `FRED_API_KEY`, and the
four `R2_*` names; that set is pinned by
`tests/scripts/test_mcp_container.py:35-42`. The `mcp.digithings.ai` route itself
is commented out and human-gated pending Worker-edge digikey JWT enforcement
(`wrangler.toml:63-73`).

The exact tracked wiring (follow-up issue **#4260**) is four edits in one PR:

1. add `GLOOMBERB_SESSION_COOKIE: env.GLOOMBERB_SESSION_COOKIE ?? ""` to
   `DigiQuantMcpContainer.envVars` in `src/index.ts`;
2. put the secret with the `$VALUE` / `env -u` convention from
   `digiquant/ARCHITECTURE.md` (never echoing the value):
   `printf '%s' "$VALUE" | env -u CLOUDFLARE_API_TOKEN npx wrangler secret put GLOOMBERB_SESSION_COOKIE`;
3. add the name to `MCP_SCOPED_VARS` in `tests/scripts/test_mcp_container.py`
   and to `test_wrangler_documents_mcp_secrets`;
4. add it to the `wrangler.toml` secrets comment (lines 135–164).

Do not enable `mcp.digithings.ai` as part of that work; the route and the
forwarding are separate, already-tracked decisions.

### GitHub Actions pipeline

No `GLOOMBERB_` variable is set in any workflow today (verified 2026-09-16), so
the pipeline's in-process agent surface filters the gated tools out
(`agent_tools.py:261-292`) and there is nothing to rotate there yet. If a
pipeline phase ever needs a gated tool, the placement is a repository secret
feeding that job — tracked as future work, deliberately not documented as live.

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
session is valid but not entitled to a Pro route (you called one of the two
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
  every placement (the local `.env` today, and the hosted secret once #4260 is
  wired). Because the fingerprint separates sessions, a rotated cookie cannot
  receive a response cached under the old one — no cache flush or restart is
  needed for correctness.

## Related

- Design spec: [`docs/superpowers/specs/2026-09-16-gloomberb-session-cookie-runbook-design.md`](../superpowers/specs/2026-09-16-gloomberb-session-cookie-runbook-design.md)
- Family spec: [`docs/superpowers/specs/2026-09-12-digifetch-scoping-design.md`](../superpowers/specs/2026-09-12-digifetch-scoping-design.md)
- Component map: [`digiquant/ARCHITECTURE.md`](../../digiquant/ARCHITECTURE.md)
- Origin / tracking issues: [#4069](https://github.com/digithings-ai/digithings/issues/4069), [#4110](https://github.com/digithings-ai/digithings/issues/4110), [#4101](https://github.com/digithings-ai/digithings/issues/4101)
- Hosted-container forwarding follow-up: [#4260](https://github.com/digithings-ai/digithings/issues/4260)
