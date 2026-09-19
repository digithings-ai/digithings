# Post-deploy verification of the digifetch_* MCP surface + upstream drift checks — Design Spec

> **For agentic workers:** This is a DESIGN SPEC, not an implementation plan.
> Do not implement from this file. The implementation plan (writing-plans skill)
> is written only after the user approves this spec.

**Date:** 2026-09-16
**Status:** draft — awaiting user review
**Issue:** [#4101](https://github.com/digithings-ai/digithings/issues/4101) — follow-up to
[#4069](https://github.com/digithings-ai/digithings/issues/4069) / PR
[#4085](https://github.com/digithings-ai/digithings/pull/4085); coverage expansion
[#4110](https://github.com/digithings-ai/digithings/issues/4110)
**Grounding:** every path and line below was verified in this worktree
(`.worktrees/gloomberb-specs`) at `origin/develop` = `118966117` on 2026-09-16.

---

## 1. Goal and scope

Prove, once, that the deployed digifetch tool family is actually on the served
MCP surface and that the live upstream (`api.gloom.sh`) still answers the
contract the offline tests pin — then record the evidence on #4101.

1. **Surface check (manual, now):** list the tools the MCP server registers and
   confirm the 13 phase-0 cohort from #4069/#4101 is present (the family has
   since grown to 33 under #4110; the count is *reported*, the cohort is
   *required*).
2. **Production smoke (manual, now):** run the opt-in live smoke against
   `api.gloom.sh` (`GLOOMBERB_LIVE_SMOKE=1`).
3. **Drift escalation (documented, not built):** a lightweight periodic
   re-probe (one quote + one history) is justified only when real drift is
   observed, against criteria defined in §8. **No monitoring is built now
   (YAGNI).**

**In scope:** a short ops doc `docs/ops/digifetch-post-deploy-verification.md`
(the repeatable checklist, exact commands, results-table template, escalation
criteria), a repo-level test pinning the doc's load-bearing facts, and one
results comment on #4101.

**Out of scope:** building a scheduled workflow probe; enabling
`mcp.digithings.ai`; cookie-gated live coverage (that is #4099's local
verification step); ToS/volume review (scoping spec §10/§12.5); any runtime
code change.

**Human gate: does not apply to this change.** The diff is documentation plus a
repo-level unit test. The smoke targets `api.gloom.sh`, which is already a
shipped runtime dependency of the client (`client.py:152`;
`digiquant/ARCHITECTURE.md:1165`; scoping spec §12.5 egress item) — running it
again is not new network exposure, and it needs no new secret (the current
smoke is anonymous). Enabling the `mcp.digithings.ai` route stays a separate
human-gated infra decision (`wrangler.toml:63-73`) and is untouched. If drift
escalation ever lands a scheduled probe, it would call the same existing
dependency with the same opt-in marker — still not new network exposure, and
deliberately still cookie-free so no secret wiring is needed.

---

## 2. Background (verified 2026-09-16 against `118966117`)

### 2.1 What #4101 asked for, and what the surface is today

- #4101 was filed when the family was the 13-tool phase-0 contract
  (scoping spec §12 item 3: "Register the 13 tools in `mcp_server.py` via the
  `_maybe_tool` pattern", `docs/superpowers/specs/2026-09-12-digifetch-scoping-design.md:390`).
- The family is now **33 tools** (#4110 phases 1–3): `READ_SCOPE_TOOLS` in
  `digiquant/src/digiquant/mcp_server.py:489-535` (comment lines 486–488 says
  "the 33 digifetch x Gloomberb enrichment reads"), with the phase-0 cohort at
  lines 501–513 and each tool registered via `_maybe_tool` from line 896
  onward. Offline registration is already pinned by
  `tests/dq/test_mcp_server_scope.py` (33 names in `DIGIFETCH_TOOLS`) and
  `tests/dq/test_mcp_gloomberb_tools.py`.
- The verification therefore separates two facts: the cohort must be present
  (the #4101 acceptance), and the total is reported for the record so an
  intentional addition is not mistaken for drift.

### 2.2 The served surface: build, scope, route

- Container image: `digiquant/Dockerfile.mcp` (entrypoint line 36
  `python -m digiquant.mcp_server`; `DIGIQUANT_MCP_HOST=0.0.0.0` /
  `DIGIQUANT_MCP_PORT=8767` line 31; `DIGIQUANT_MCP_SCOPE=read` line 34).
- Local serving path: `digiquant/src/digiquant/mcp_server.py::run_mcp`
  (lines 1996–2010) with argparse defaults `--host 127.0.0.1`,
  `--port 8767`, `--scope` from `DIGIQUANT_MCP_SCOPE` default `full`
  (lines 2016–2030); startup instructions in `digiquant/ARCHITECTURE.md`
  § "MCP Server Startup" lines 1642–1651.
- FastMCP streamable-http serves at the `/mcp` path (the documented warm ping
  is `curl -sS https://mcp.digithings.ai/mcp -H 'Accept: application/json'`,
  `wrangler.toml:97`).
- Hosted wiring: `DigiQuantMcpContainer` (`apps/digithings-stack-cloudflare/src/index.ts:159-205`;
  `envVars` lines 177–185; `sleepAfter = "24h"` warm policy), the
  `[[containers]]` entry in `wrangler.toml:88-113`, single replica
  (`max_instances = 1`, `MCP_CONTAINER_ID = "mcp-v1"` in
  `apps/digithings-stack-cloudflare/src/ports.ts:29`).
- **The hosted route is not enabled:** the `mcp.digithings.ai` `[[routes]]`
  entry is commented out (`wrangler.toml:63-73`, "HUMAN GATE — infra/network …
  Enable this route ONLY together with Worker-edge digikey JWT enforcement").
  `isMcpHostname` (`index.ts:308-310`) would forward the request to
  `MCP_STACK` once the route exists; today an unknown-host request answers 404
  with "(mcp.digithings.ai is reserved; its route is not yet enabled.)"
  (`index.ts:379-384`). Auth for the day it lands: digikey JWT, scope
  `digiquant:backtest` (`digiquant/ARCHITECTURE.md` § MCP hosting, lines
  368–369 and 510). `mcp.digithings.ai` is **not** on the `/_stack/mcp` edge-key map
  (`MCP_EDGE_SERVERS`, `index.ts:274-278`).

### 2.3 The live smoke harness

`tests/dq/test_gloomberb_live_smoke.py` (33 lines) is the only live-network
test in the family:

- Module marks `integration` + `skipif(os.environ.get("GLOOMBERB_LIVE_SMOKE") != "1")`
  (lines 15–21) — never runs in the default suite.
- One anonymous `client.quote({"symbol": "AAPL"})` against
  `https://api.gloom.sh`; asserts `isinstance(envelope.data, QuoteResult)`,
  a populated `symbol`, and `envelope.provider_id == "gloomberb-cloud"`
  (lines 24–33).
- It needs no cookie. Local `.env` carries `GLOOMBERB_SESSION_COOKIE` in
  `name=value` form for the gated tools (see #4099's runbook); the smoke
  commands in this plan source `.env` only for parity with operator sessions
  and **never print** any value.

The repo's own MCP client pattern is
`digigraph/src/digigraph/orchestration/mcp_client.py::_list_tools_async`
(lines 611–623): `streamablehttp_client(url, headers=…, httpx_client_factory=…)`
→ `ClientSession(read, write)` → `session.initialize()` →
`session.list_tools()`. The verification heredoc mirrors that shape without the
digigraph SSRF factory (an operator-side localhost call, not a
model-reachable proxy path).

### 2.4 Drift surface (why the escalation criteria exist)

The API is unofficial and undocumented (scoping spec §2: "api.gloom.sh is
undocumented and can change"; §12.5 open human-gate item). The client already
degrades typed: `upstream_error` for wire shape changes, `not_found` for moved
routes, `auth_required` for a changed auth model, and the circuit breaker
prevents retry storms. What no code can detect is an upstream *semantic*
change that still parses — which is what the manual check and the escalation
criteria are for.

---

## 3. Approved decisions

- **D1 — Manual now; no scheduled probe (YAGNI).** The deliverable is a
  repeatable checklist plus one recorded run. A workflow probe ships only if
  §8's trigger fires; the criteria and the probe shape are specified now so the
  decision is mechanical later.
- **D2 — Deliverable home: `docs/ops/digifetch-post-deploy-verification.md`.**
  Same reasoning as the #4099 runbook: `docs/ops/` is the operator-doc home
  (`docs/runbooks/` does not exist). The one-time result lives on #4101 as a
  comment; the doc is the procedure.
- **D3 — Verify the *served* surface via the repo's own client pattern.** The
  local serving path (`python -m digiquant.mcp_server --scope read`, matching
  the hosted default) is the surface that ships in the image; the surface check
  runs against it and records the tool list. When the hosted route is enabled,
  the same check gains a hosted row (§10 Q1) — the spec does not invent a URL
  or token flow for it.
- **D4 — Cohort required, count reported.** `cohort_missing == []` is the pass
  gate; `digifetch_count` is recorded (expectation 33 on 2026-09-16) but a
  change in count alone is not a failure — it is an intentional-addition
  signal to reconcile against `READ_SCOPE_TOOLS`.
- **D5 — Failures become issues, not retries.** A failed check is filed with
  the typed envelope and the request shape; the smoke is not re-run in a loop
  to "get a pass" (rate limits and 15-minute delays are expected conditions,
  documented, not failures).
- **D6 — Fidelity pinned by a test.** `tests/scripts/test_digifetch_post_deploy_verification_doc.py`
  asserts the doc carries the 13 cohort names (and that they are
  `READ_SCOPE_TOOLS` members), the exact serving/smoke/recording commands, the
  escalation wording, and no cookie value.

---

## 4. Contracts (load-bearing)

- **Cohort contract (the #4101 acceptance):** exactly these 13 names must be
  present on the served surface:
  `digifetch_quote`, `digifetch_quotes_batch`, `digifetch_price_history`,
  `digifetch_ticker_financials`, `digifetch_options_chain`,
  `digifetch_sec_filings`, `digifetch_holders`, `digifetch_analyst_research`,
  `digifetch_corporate_actions`, `digifetch_earnings_calendar`,
  `digifetch_exchange_rate`, `digifetch_search`, `digifetch_news`.
- **Surface contract:** local command `python -m digiquant.mcp_server --scope read`
  on `127.0.0.1:8767`, streamable-http path `/mcp`; tool listing via the
  `mcp` client (`initialize` → `list_tools`), reporting
  `{"digifetch_count": int, "cohort_missing": [names], "names": [...]}`.
- **Smoke contract:** `GLOOMBERB_LIVE_SMOKE=1 pytest tests/dq/test_gloomberb_live_smoke.py -v`
  → one anonymous quote accepted against productive upstream; no cookie needed;
  env values never printed.
- **Recording contract:** `gh issue comment 4101` with a Markdown table
  (columns: Check | Result | Evidence) where Evidence is the command and the
  observed output, never a secret.
- **Escalation contract:** a drift event is one of S1–S5 (§8); the scheduled
  probe requires the §8 trigger; the probe is one anonymous quote + one
  anonymous history call, using the existing smoke marker and the existing
  dependency — no cookie, no new endpoint.
- **Routing contract:** docs + repo-level test → `component:root` → PR base
  `develop`.

---

## 5. Normative values

- Doc path: `docs/ops/digifetch-post-deploy-verification.md`.
- Test path: `tests/scripts/test_digifetch_post_deploy_verification_doc.py`.
- Expected cohort count: 13; expected family count on 2026-09-16: 33
  (22 free / 8 session / 1 preview / 2 pro per `entitlements.py:58-96`).
- Local server bind: `127.0.0.1:8767`; MCP path `/mcp`; scope `read`
  (hosted default).
- Smoke command exactly:
  `set -a; . ./.env; set +a; GLOOMBERB_LIVE_SMOKE=1 PATH="$PWD/.venv/bin:$PATH" pytest tests/dq/test_gloomberb_live_smoke.py -v`
  → expected `1 passed`.
- Drift trigger for the scheduled probe: **≥2 distinct drift events within 30
  days, or one family-wide break** (auth model, host, or every tool erroring
  the same way).
- Probe shape: daily `0 14 * * *` UTC GitHub Actions job (after the
  market-data-refresh cron at `0 13 * * *`), one `digifetch_quote` + one
  `digifetch_price_history` anonymous call via the live-smoke harness, no
  cookie, artifact = the envelope JSON. (Specified for the trigger; not built
  now.)

---

## 6. Rollout order

1. Land the doc + its test (docs-only PR into `develop`).
2. Run the one-time verification post-deploy (Task 2 of the plan): surface
   check, smoke, results comment on #4101.
3. Resolve #4101 per the recorded evidence (close, or keep open with the
   hosted-route blocker named — §10 Q1).
4. Only if §8's trigger fires: file the probe issue with the evidence and
   propose the scheduled job.

---

## 7. Verification (measurable)

- `pytest tests/scripts/test_digifetch_post_deploy_verification_doc.py -v`
  → PASS (RED premise: file absence at creation).
- `make doc-check` → `check_doc_links: OK`.
- The one-time run: `cohort_missing: []` and `digifetch_count: 33` printed;
  smoke `1 passed`; both pasted into the #4101 comment's results table.
- The doc's fidelity test imports `READ_SCOPE_TOOLS` and asserts every cohort
  name is a member, so a renamed/unregistered tool fails the suite.

---

## 8. Risks and fallbacks

- **Upstream drift** (the reason for the check). Signals, normative:
  - **S1** — a cohort tool returns typed `not_found` for the request shapes
    the offline tests pin, on 2 runs ≥24h apart.
  - **S2** — a normalized payload loses a field the tests pin
    (`upstream_error` "unexpected payload") on 2 runs ≥24h apart.
  - **S3** — an anonymous endpoint answers 401/403, or the session cookie
    names observed in the browser no longer match `SESSION_COOKIE_NAMES`
    (`client.py:180-183`).
  - **S4** — the live smoke fails 2 consecutive days with a non-rate-limit
    error.
  - **S5** — the API host changes (DNS/TLS/proxy), or every tool errors the
    same way (family-wide break).
  Escalation: file an issue (`component:digiquant`; `priority:medium`, or
  `priority:high` for S5/S3) quoting the envelope, the request shape, and the
  dates. The scheduled probe fires on the §5 trigger; its justification is the
  evidence trail.
- **False alarm from expected conditions:** rate limits (`rate_limited`) and
  free-tier delays are documented conditions, not drift — the doc lists them
  as non-events so the probe is not proposed for noise.
- **Route still disabled:** the hosted row is recorded as blocked with the
  `wrangler.toml:63-73` citation; the local serving path + live upstream smoke
  is the available evidence (D3). No invented URL.
- **Doc rot:** the fidelity test pins names/commands; `make doc-check` pins
  links.

---

## 9. Out of scope

- Enabling `mcp.digithings.ai` (human gate) and any Worker auth change.
- Building the scheduled probe, dashboards, or alerting now.
- Cookie-gated live verification (owned by #4099's runbook).
- New digifetch tools or normalizer changes; ToS/volume review.

---

## 10. Open questions

1. **Hosted-surface URL/auth at execution time.** `mcp.digithings.ai` is
   reserved-not-enabled in this tree (`wrangler.toml:63-73`). If the route has
   been enabled by the time the verification runs, add the hosted row using the
   reserved hostname and the digikey JWT flow documented in
   `digiquant/ARCHITECTURE.md` § MCP hosting (scope `digiquant:backtest`); if
   not, record "local served surface verified; hosted row blocked on route
   enablement" and keep the blocker visible in the results table. The plan
   must not fabricate a token-acquisition command that is not yet documented.
2. **Exact expected count drift.** 33 is the 2026-09-16 value; if a later
   cohort lands between spec approval and execution, update the doc's stated
   count in the same PR (the test gates on the cohort, not the count).
