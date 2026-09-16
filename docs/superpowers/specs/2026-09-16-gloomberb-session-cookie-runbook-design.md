# Gloomberb session-cookie runbook (free account + per-deployment env) — Design Spec

> **For agentic workers:** This is a DESIGN SPEC, not an implementation plan.
> Do not implement from this file. The implementation plan (writing-plans skill)
> is written only after the user approves this spec.

**Date:** 2026-09-16
**Status:** draft — awaiting user review
**Issue:** [#4099](https://github.com/digithings-ai/digithings/issues/4099) — follow-up to
[#4069](https://github.com/digithings-ai/digithings/issues/4069) / PR
[#4085](https://github.com/digithings-ai/digithings/pull/4085)
**Grounding:** every path and line below was verified in this worktree
(`.worktrees/gloomberb-specs`) at `origin/develop` = `118966117` on 2026-09-16.

---

## 1. Goal and scope

Ship one short operational runbook — `docs/ops/gloomberb-session-cookie.md`
(home decision in §3) — that an operator can follow to:

1. create a free Gloomberb account (signup + email verification),
2. extract the session cookie from the web app,
3. place it per deployment (local `.env`, GitHub Actions, hosted MCP
   container) with the exact secret steps,
4. keep it private (never log, never echo, never paste),
5. understand the failure mode when it is absent: the gated tools answer a
   typed `auth_required` error **with no HTTP request**, and Pro-only tools
   answer `pro_required` for a valid free session.

**In scope:** the runbook, a repo-level test pinning its load-bearing facts to
the code, one pointer from `digiquant/ARCHITECTURE.md`, a commented placeholder
in `.env.example`, and a tracked follow-up issue for the hosted-container
forwarding gap (§3 D2).

**Out of scope:** any runtime code change; forwarding the cookie to the hosted
container (follow-up issue); enabling `mcp.digithings.ai` (human gate, §8);
Pro-plan purchase guidance (no verified upgrade flow exists in-tree); cookie
automation of any kind.

**Human gate: does not apply to this change.** The diff is documentation plus a
repo-level unit test — no `digikey/` auth/JWT/crypto code, no broker or
live-trading path, no new external service dependency or network exposure. Two
adjacent actions stay gated and are explicitly untouched: enabling the
`mcp.digithings.ai` route (`cloudflare/digithings-stack-cloudflare/wrangler.toml`
lines 63–73, "HUMAN GATE — infra/network"), and any future Worker change that
forwards the cookie to the container (a config follow-up, not a new dependency —
the container already talks to `api.gloom.sh`).

---

## 2. Background (verified 2026-09-16 against `118966117`)

### 2.1 The shipped client

`digiquant/src/digiquant/data/gloomberb/client.py` is the one place the
`api.gloom.sh` URL and session logic live:

- `GLOOMBERB_BASE_URL = "https://api.gloom.sh"` (line 152);
  `GLOOMBERB_ENABLED_ENV = "GLOOMBERB_ENABLED"` (153);
  `GLOOMBERB_SESSION_COOKIE_ENV = "GLOOMBERB_SESSION_COOKIE"` (154).
- The cookie is read once at construction: `session_cookie` argument wins,
  otherwise `os.environ.get(GLOOMBERB_SESSION_COOKIE_ENV, "").strip()`
  (lines 482–486). "No environment variables are read at import time"
  (module docstring, lines 16–17).
- Accepted forms: a bare token **or** `name=value` (`GloomberbClient`
  docstring, lines 437–439). `_session_cookies()` (lines 2143–2154) sends a
  `name=value` pair under that name; a bare token is sent under **every**
  upstream session cookie name in `SESSION_COOKIE_NAMES`
  (`__Secure-gloomberb.session_token`, `gloomberb.session_token`, lines
  180–183) — the same fallback the TypeScript client uses when it has not
  observed the name.
- Zero-HTTP gating: `_request_json(..., gated=True)` returns a
  `DigifetchError(code="auth_required", message="... GLOOMBERB_SESSION_COOKIE
  is not set", retryable=False)` **before** any request when
  `self._session_cookie is None` (lines 2248–2254).
- Kill switch: `gloomberb_enabled()` / `_env_flag` (lines 248–272) — default
  ON; only `1/true/yes/on` enable it, any other value (a typo included) disables
  the family and every call returns a typed `upstream_error` with no request.
- Failure vocabulary: `DigifetchError` with `code` in the §5.3 table
  (`digiquant/src/digiquant/data/gloomberb/models.py` lines 334–344);
  `auth_required` = no/misconfigured session; `pro_required` = valid free
  session, unentitled Pro route (`_plan_required_error`, client.py lines
  307–322); `digifetch_equity_diagnostic` free sessions get a labeled
  `access="preview"` report instead of a hard gate
  (`PREVIEW_ACCESS_WARNING`, models.py line 306).
- Privacy mechanics already shipped: the cookie is never logged (module
  docstring, line 14, and client.py line 439); the 900s TTL cache is keyed by a
  truncated SHA-256 fingerprint, not the cookie
  (`session_cache_fingerprint`, lines 186–197); per-call cookies are forwarded
  only to same-origin redirect hops (`digifetch/src/digifetch/http.py` line 224).

### 2.2 Which tools need the cookie

`digiquant/src/digiquant/data/gloomberb/entitlements.py`
(`TOOL_ENTITLEMENTS`, lines 58–96) declares 33 digifetch tools: **22 `free`**,
**8 `session`**, **1 `preview`**, **2 `pro`**. The 11 cookie-gated names:

| Entitlement | Tools |
|---|---|
| `session` (8) | `digifetch_holders`, `digifetch_analyst_research`, `digifetch_corporate_actions`, `digifetch_research_search`, `digifetch_statements`, `digifetch_ticker_tweets`, `digifetch_tweet_search`, `digifetch_short_interest` |
| `preview` (1) | `digifetch_equity_diagnostic` (free session gets `access="preview"`) |
| `pro` (2) | `digifetch_transcripts`, `digifetch_screener` (free session → `pro_required`) |

`digiquant/src/digiquant/mcp_server.py` registers all 33 in
`READ_SCOPE_TOOLS` (lines 489–535, comment lines 486–488) and appends the
entitlement sentence to every registered description via `_maybe_tool`
(lines 561–578) — so the MCP surface **advertises** gated tools and answers
the typed error per call.

The pipeline's in-process surface behaves differently by design:
`digiquant/src/digiquant/data/gloomberb/agent_tools.py::available_digifetch_tools`
(lines 265–292) **drops** session/preview/pro tools when
`GLOOMBERB_SESSION_COOKIE` is unset (`_session_cookie_present`, lines 261–262)
and drops the whole family when the kill switch is off — CI has neither, so
pipeline LLMs are never offered a tool that can only error.

### 2.3 Where the cookie lives today (and where it does not)

- **Local runs:** the repo-root `.env` (gitignored — `.gitignore` lists `.env`
  and `.env*`), read by the client at construction. `.env.example` has **no**
  `GLOOMBERB_*` entry today (verified by grep, 2026-09-16), so the placement is
  currently undiscoverable from the template.
- **GitHub Actions pipeline:** **no** `GLOOMBERB_*` name appears in any
  `.github/workflows/` file (verified by grep, 2026-09-16). Session tools are
  therefore filtered from the agent surface in CI — the documented #4146
  behavior — and there is nothing to rotate there yet.
- **Hosted MCP container:** `DigiQuantMcpContainer.envVars`
  (`cloudflare/digithings-stack-cloudflare/src/index.ts` lines 177–185)
  forwards only `DIGIQUANT_MCP_SCOPE`, `DIGIQUANT_MARKET_DATA_BACKEND`,
  `FRED_API_KEY`, and the four `R2_*` names. The cookie is **not** forwarded.
  That is pinned by `tests/scripts/test_mcp_container.py`
  (`MCP_SCOPED_VARS`, lines 35–42; `test_stack_container_env_has_no_mcp_duplication`,
  lines 141–149) and by the secrets comment in
  `cloudflare/digithings-stack-cloudflare/wrangler.toml` lines 135–164.
- The hosted MCP route itself is **not enabled**: the `mcp.digithings.ai`
  `[[routes]]` entry is commented out (`wrangler.toml` lines 63–73) pending
  Worker-edge digikey JWT enforcement (`digiquant/ARCHITECTURE.md`
  § "MCP hosting — dedicated container (#3780 Task 8)", lines 348–407).
- The container entrypoint intentionally never needs the cookie for the free
  tools: `digiquant/Dockerfile.mcp` (line 34) pins `DIGIQUANT_MCP_SCOPE=read`.

### 2.4 Docs conventions

- `docs/runbooks/` does **not** exist. `docs/ops/` does, and is the operator
  home for exactly this kind of secret/deployment note:
  `docs/ops/digiquant-digikey-service-key.md` (a service key + rotation doc),
  `docs/ops/core-postgres-uri-secret.md`, `docs/ops/vectorize-cutover.md`,
  `docs/ops/checkpoint-archive-vacuum.md`.
- `make doc-check` (Makefile lines 46–47) runs
  `scripts/check_doc_links.py`, which rglobs the repo for Markdown — all of
  `docs/` plus an allowlist of root docs and every `AGENTS.md`/`CLAUDE.md`/
  `DIGI*.md`, minus an exclude list — and validates relative link targets;
  fenced code blocks are stripped.

### 2.5 The signup surface

The only verified Gloomberb web surfaces in-tree are the API host
`https://api.gloom.sh` (client.py line 152) and the terminal app
`https://term.gloom.sh/` (`digiquant/src/digiquant/data/gloomberb/attribution.py`
line 23; mirrored in `cloudflare/digiweb/web/src/lib/gloomberb.ts` lines
11–13). No signup URL, account flow, or email-verification wording is recorded
anywhere in the repo. The runbook therefore must not invent UI steps: an
operator dry-run (§6 step 2) captures the exact wording, and if self-serve
signup turns out to be unavailable the runbook records that finding instead
(§10 Q2).

---

## 3. Approved decisions

- **D1 — Home: `docs/ops/gloomberb-session-cookie.md`.** `docs/runbooks/` does
  not exist and `docs/ops/` is the established home for operator secret docs
  (§2.4). Creating a parallel `docs/runbooks/` tree for one file would be a new
  convention with no owner.
- **D2 — Document the gap, track it, do not paper over it.** The runbook states
  plainly that the hosted container does not forward the cookie today and gives
  the exact future wiring (envVars line, `wrangler secret put`, test list
  update, wrangler.toml secrets comment) under a follow-up issue filed in the
  same PR. An operator must never be told to set a secret that silently does
  nothing.
- **D3 — No code changes; fidelity is pinned by a test.**
  `tests/scripts/test_gloomberb_session_cookie_runbook.py` reads the runbook and
  asserts: env names are exactly the code's names (imported from `client.py`),
  every cookie-gated tool name appears, `auth_required`/`pro_required` are
  distinguished, the hosted placement mentions `DigiQuantMcpContainer` and the
  `wrangler secret put GLOOMBERB_SESSION_COOKIE` command, the cross-links are
  present, and no literal cookie value exists in the doc.
- **D4 — Pointers from the component docs.** `digiquant/ARCHITECTURE.md`
  gets a link from the `GLOOMBERB_SESSION_COOKIE` env-table row (line 1638) and
  a one-sentence note in the MCP-hosting secrets paragraph (line 395)
  that the cookie is not forwarded yet, linking the runbook. No other
  `ARCHITECTURE.md` change.
- **D5 — Discoverability:** `.env.example` gains a commented
  `# GLOOMBERB_SESSION_COOKIE=` placeholder with a pointer to the runbook
  (a template line, never a value).

---

## 4. Contracts (load-bearing)

- **Env names:** only `GLOOMBERB_SESSION_COOKIE` and `GLOOMBERB_ENABLED` may be
  presented as deployment env vars; `GLOOMBERB_LIVE_SMOKE` may appear only as
  the opt-in test marker (`tests/dq/test_gloomberb_live_smoke.py` lines 15–21).
  The test derives the first two from `client.py` constants, so a rename fails
  the suite.
- **Cookie value forms:** `name=value` (preferred; cookie name
  `__Secure-gloomberb.session_token` or `gloomberb.session_token`) or a bare
  token (fallback: sent under both names). Any value shown in the runbook must
  be an obvious placeholder (`<cookie>`, `$GLOOMBERB_SESSION_COOKIE`,
  `${...}`).
- **Failure codes:** `auth_required` (absent/misconfigured session; no HTTP
  request), `pro_required` (valid free session on
  `digifetch_transcripts`/`digifetch_screener`), `upstream_error` (family
  disabled by the kill switch; no request). The runbook must say where each is
  produced (`client.py` lines 2248–2254, 307–322).
- **Privacy invariant:** never logged, never echoed into payloads, never pasted
  into issues/PRs/chat; cache discriminator is a truncated SHA-256 fingerprint,
  not the cookie; rotated cookies are separated by that fingerprint.
- **Routing contract:** the change is docs (`docs/ops/`, markdown pointers) plus
  a repo-level test, i.e. `component:root` → PR base `develop`.
- **Link contract:** all relative links in the runbook must resolve from
  `docs/ops/` and pass `make doc-check`.

---

## 5. Normative values

- Runbook path: `docs/ops/gloomberb-session-cookie.md`.
- Test path: `tests/scripts/test_gloomberb_session_cookie_runbook.py`.
- Cross-references required in the runbook: `#4069`, `#4110`, `#4101`, and the
  family spec `docs/superpowers/specs/2026-09-12-digifetch-scoping-design.md`.
- Gated-tool inventory in the runbook: exactly the 11 names from §2.2, each
  marked `session` / `preview` / `pro`; total family count stated as 33
  (22 free) with the date qualifier.
- Hosted follow-up wiring sequence (verbatim in the runbook):
  1. add `GLOOMBERB_SESSION_COOKIE: env.GLOOMBERB_SESSION_COOKIE ?? ""` to
     `DigiQuantMcpContainer.envVars`;
  2. `printf '%s' "$VALUE" | env -u CLOUDFLARE_API_TOKEN npx wrangler secret put GLOOMBERB_SESSION_COOKIE`
     (the `$VALUE` / `env -u` convention from `digiquant/ARCHITECTURE.md`
     § MCP hosting operator block);
  3. add the name to `MCP_SCOPED_VARS` in `tests/scripts/test_mcp_container.py`
     and to `test_wrangler_documents_mcp_secrets`;
  4. add it to the wrangler.toml secrets comment (lines 135–164).
- Local placement: repo-root `.env` only (gitignored); the `.env.example`
  placeholder must stay commented and value-free.

---

## 6. Rollout order

1. Operator dry-run: create the free account, verify email, extract the cookie
   into the local `.env`, run the local verification command, and capture the
   exact UI wording (or the finding that self-serve signup is unavailable).
2. Land the runbook + docs test + `ARCHITECTURE.md` pointers + `.env.example`
   placeholder; file the hosted-forwarding follow-up issue and link it from the
   runbook.
3. Nothing else changes: no container env, no route enablement, no CI secret.
4. Future (separate, human-gated or small-config PRs): route enablement and
   container forwarding, both already tracked.

---

## 7. Verification (measurable)

- `pytest tests/scripts/test_gloomberb_session_cookie_runbook.py -v` → PASS.
  The test's RED premise is file absence: at creation it fails with
  `FileNotFoundError` reading the runbook (same pattern and rationale as
  `tests/scripts/test_mcp_container.py`, header lines 9–14).
- `make doc-check` → `check_doc_links: OK`.
- Operator dry-run: the local verification command prints
  `OK holders rows = <n>` (`n > 0`), never the cookie. Any `auth_required`
  result means the cookie was not read — the runbook's troubleshooting note
  must cover quoting and `set -a` export.
- Fidelity: the test imports `GLOOMBERB_ENABLED_ENV` /
  `GLOOMBERB_SESSION_COOKIE_ENV` from `client.py` and
  `TOOL_ENTITLEMENTS` from `entitlements.py`, so env renames and tool
  additions fail the suite and force the runbook to be updated in the same
  change.

---

## 8. Risks and fallbacks

- **Upstream cookie-name change.** Mitigated by the bare-token fallback
  (`SESSION_COOKIE_NAMES`, client.py lines 180–183, 2152–2154); the runbook
  prefers `name=value` but records the fallback.
- **Signup flow is invite-only or changes.** The dry-run captures reality; if
  self-serve signup is not available, the runbook records that and #4099 is
  re-scoped in a comment rather than documenting invented steps.
- **Runbook drifts from code.** The fidelity test (D3) fails on rename/add.
- **Operator leaks the cookie.** Privacy section + value-free doc (enforced by
  the test's literal-value scan) + the shipped fingerprint/same-origin
  mechanics; rotation instructions replace the value everywhere it is placed.
- **Route enablement temptation.** The runbook states the hosted route is
  human-gated; enabling it without Worker-edge JWT enforcement is prohibited
  by the wrangler.toml comment.

---

## 9. Out of scope

- Forwarding `GLOOMBERB_SESSION_COOKIE` to `DigiQuantMcpContainer` (follow-up
  issue filed by the plan).
- Enabling `mcp.digithings.ai` (human gate).
- Wiring a GitHub Actions secret for the pipeline (session tools are filtered
  in CI by design today; if the pipeline ever needs them, that is its own
  issue).
- Pro-plan purchase/upgrade guidance (no verified in-tree flow).
- Any client/entitlements code change; any new dependency.

---

## 10. Open questions

1. **Exact signup/email-verification UI wording.** Not recorded anywhere in the
   tree. Resolved by the operator dry-run (plan Task 2); the runbook mirrors
   what the operator observes.
2. **Is free self-serve signup available today?** If not, the runbook records
   the actual path (invite/web form) and the issue gets a scope note. This is
   the only way to keep the doc truthful without an upstream API reference.
3. **GitHub Actions placement** is deliberately deferred: nothing consumes the
   cookie in CI today (`available_digifetch_tools` filters it out), so
   documenting a secret nobody reads would be noise. Revisit if a pipeline
   phase ever needs a gated tool.
