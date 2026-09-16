# digifetch Post-Deploy Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the post-deploy verification checklist `docs/ops/digifetch-post-deploy-verification.md` (13-tool cohort on the served MCP surface, live smoke against `api.gloom.sh`, results recording, drift-escalation criteria), pinned by a repo-level test, then run it once and record the evidence on #4101.

**Architecture:** Docs-only deliverable plus one `tests/scripts/` assertion test (same pattern as `tests/scripts/test_mcp_container.py`), a one-time operator run against the local serving path (matching the hosted `read` scope) and the live upstream smoke, and a results comment on #4101. No runtime code, no scheduled probe (YAGNI — escalation is documented, not built).

**Tech Stack:** Markdown under `docs/ops/` (link-checked by `scripts/check_doc_links.py`), pytest (unit-marked) reading the doc and importing `READ_SCOPE_TOOLS` from `digiquant.mcp_server`, the `mcp` Python client (`streamablehttp_client` + `ClientSession.list_tools`) for the operator surface check, and the existing `GLOOMBERB_LIVE_SMOKE=1` harness for the upstream smoke.

**Spec:** `docs/superpowers/specs/2026-09-16-gloomberb-post-deploy-verification-design.md` — the plan argues from the spec; executors read both.

## Global Constraints

- The 13 phase-0 cohort names are the pass gate (`cohort_missing == []`); the family count (33 on 2026-09-16) is reported, not gated (D4).
- Exact cohort: `digifetch_quote`, `digifetch_quotes_batch`, `digifetch_price_history`, `digifetch_ticker_financials`, `digifetch_options_chain`, `digifetch_sec_filings`, `digifetch_holders`, `digifetch_analyst_research`, `digifetch_corporate_actions`, `digifetch_earnings_calendar`, `digifetch_exchange_rate`, `digifetch_search`, `digifetch_news`.
- Serving path for the surface check: `python -m digiquant.mcp_server --scope read` on `127.0.0.1:8767`, streamable-http path `/mcp` (the hosted container's scope and port; `Dockerfile.mcp:31-34`).
- Smoke command exactly as in the doc: `GLOOMBERB_LIVE_SMOKE=1 pytest tests/dq/test_gloomberb_live_smoke.py -v` → expected `1 passed`; anonymous, no cookie.
- Never print or echo any `.env` value (`set -a; . ./.env; set +a` exports silently); results evidence is commands + observed outputs only.
- No scheduled workflow probe in this plan. Escalation criteria and probe shape are documented (spec §5/§8); the probe ships only when the trigger fires.
- No invented endpoints: the only hosted URL that may appear is the reserved `mcp.digithings.ai` (`ports.ts:22`, `wrangler.toml:63-73, 97`), and the doc marks the hosted row blocked until the route is enabled (human gate).
- `api.gloom.sh` is an existing runtime dependency (`client.py:152`); the doc must say so and that a future probe is **not new network exposure**.
- Digi names are always lowercase (`digithings`, `digiquant`, `digichat`); code identifiers keep their casing.
- TDD: write the test, run it, watch it fail (file-absence RED), then write the doc and watch it pass.
- Routing: docs + repo-level test → `component:root` → **PR base `develop`** (open with `gh pr create --base develop`; #4101 carries `component:digiquant`, so `make task` cuts from `origin/module/digiquant`).
- `make doc-check` must be green; relative links resolve from `docs/ops/`.

---

### Task 1: Branch, RED test, verification doc (GREEN), commit

**Files:**
- Create: `tests/scripts/test_digifetch_post_deploy_verification_doc.py`
- Create: `docs/ops/digifetch-post-deploy-verification.md`
- Test: `tests/scripts/test_digifetch_post_deploy_verification_doc.py`

**Interfaces:**
- Consumes: `READ_SCOPE_TOOLS` from `digiquant.mcp_server` (the 13 cohort at lines 501–513; 33 family names at lines 489–535); the smoke module `tests/dq/test_gloomberb_live_smoke.py`.
- Produces: the verification doc this plan delivers, pinned by the test; the exact commands Task 2 executes unchanged.

- [ ] **Step 1: Cut the task branch**

Run:
```bash
git fetch origin develop
make task ISSUE=4101
```
Expected: a worktree on `task/4101-...` branched from `refs/remotes/origin/module/digiquant` (label-derived), with the stale-module guard silent. All later commands run inside it.

- [ ] **Step 2: Write the failing test**

Create `tests/scripts/test_digifetch_post_deploy_verification_doc.py`:

```python
"""Pin the digifetch post-deploy verification doc (#4101) to the code.

RED premise: at creation this module fails with ``FileNotFoundError`` — the
doc does not exist yet (``docs/ops/digifetch-post-deploy-verification.md``).
After creation every assertion pins a fact the code owns (cohort names, the
served path, the smoke command, the escalation wording), so drift fails here
instead of in an operator's terminal. Pattern precedent:
``tests/scripts/test_mcp_container.py`` (header lines 9-14).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
DOC = REPO_ROOT / "docs" / "ops" / "digifetch-post-deploy-verification.md"

#: The #4069/#4101 phase-0 cohort: the 13 tools the post-deploy check must
#: find on the served surface (mcp_server.py:501-513). #4110 later grew the
#: family to 33 — the count is reported, the cohort is required.
PHASE0_COHORT = (
    "digifetch_quote",
    "digifetch_quotes_batch",
    "digifetch_price_history",
    "digifetch_ticker_financials",
    "digifetch_options_chain",
    "digifetch_sec_filings",
    "digifetch_holders",
    "digifetch_analyst_research",
    "digifetch_corporate_actions",
    "digifetch_earnings_calendar",
    "digifetch_exchange_rate",
    "digifetch_search",
    "digifetch_news",
)


def _text() -> str:
    return DOC.read_text(encoding="utf-8")


def test_doc_lists_the_phase0_cohort() -> None:
    text = _text()
    missing = [name for name in PHASE0_COHORT if name not in text]
    assert not missing, missing


def test_cohort_names_are_registered_read_scope_tools() -> None:
    pytest.importorskip("mcp.server.fastmcp")
    from digiquant.mcp_server import READ_SCOPE_TOOLS

    assert set(PHASE0_COHORT) <= READ_SCOPE_TOOLS
    assert len({n for n in READ_SCOPE_TOOLS if n.startswith("digifetch_")}) >= 13


def test_doc_commands_match_the_shipped_serving_path() -> None:
    text = _text()
    assert "python -m digiquant.mcp_server --scope read" in text
    assert "http://127.0.0.1:8767/mcp" in text
    assert "GLOOMBERB_LIVE_SMOKE=1" in text
    assert "tests/dq/test_gloomberb_live_smoke.py" in text


def test_doc_records_results_on_the_issue() -> None:
    text = _text()
    assert "gh issue comment 4101" in text
    assert "#4101" in text


def test_doc_documents_drift_escalation() -> None:
    text = _text()
    assert "api.gloom.sh is an existing" in text
    assert "not new network exposure" in text


def test_doc_never_contains_a_literal_cookie_value() -> None:
    text = _text()
    for value in re.findall(r"session_token=(\S+)", text):
        assert value.startswith(("<", "$", "{")), value
    assert not re.search(r"eyJ[A-Za-z0-9_-]{10,}", text)
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `PATH="$PWD/.venv/bin:$PATH" pytest tests/scripts/test_digifetch_post_deploy_verification_doc.py -v`
Expected: FAIL — 5 errors + 1 passed: the five tests that read the file error with `FileNotFoundError: ... docs/ops/digifetch-post-deploy-verification.md`, while `test_cohort_names_are_registered_read_scope_tools` never calls `_text()` and passes (file-absence RED).

- [ ] **Step 4: Write the verification doc**

Create `docs/ops/digifetch-post-deploy-verification.md`. Required sections and content (facts cite the spec's verified file:line references):

1. `# digifetch post-deploy verification (#4101)` — scope paragraph: confirms the 13 phase-0 cohort (`#4069`) is on the served MCP surface and that the live smoke against `api.gloom.sh` passes; the family has since grown to 33 (`#4110`) so the count is reported, the cohort is the pass gate.
2. `## Preconditions` — the deploy that carries the family is live; repo venv installed; `mcp` extra available (`pip install -e "digiquant[mcp]"`, `digiquant/ARCHITECTURE.md:1642-1651`); `.env` present; the hosted route is still reserved (`mcp.digithings.ai`, `wrangler.toml:63-73`) unless a later note enables it.
3. `## Check 1 — list the served MCP surface tools` — two exact blocks:
   - start the server: `PATH="$PWD/.venv/bin:$PATH" python -m digiquant.mcp_server --scope read`; expected log line `Starting digiquant MCP server on 127.0.0.1:8767 (transport=streamable-http scope=read)` (`mcp_server.py:1996-2010`); run it in a second terminal.
   - list tools (the repo's own client shape, `digigraph/src/digigraph/orchestration/mcp_client.py:611-623`):

```bash
PATH="$PWD/.venv/bin:$PATH" python - <<'PY'
import asyncio
import json

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

COHORT = [
    "digifetch_quote", "digifetch_quotes_batch", "digifetch_price_history",
    "digifetch_ticker_financials", "digifetch_options_chain",
    "digifetch_sec_filings", "digifetch_holders", "digifetch_analyst_research",
    "digifetch_corporate_actions", "digifetch_earnings_calendar",
    "digifetch_exchange_rate", "digifetch_search", "digifetch_news",
]


async def main() -> None:
    async with streamablehttp_client("http://127.0.0.1:8767/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
    names = sorted(t.name for t in listed.tools if t.name.startswith("digifetch_"))
    print(json.dumps({
        "digifetch_count": len(names),
        "cohort_missing": [n for n in COHORT if n not in names],
        "names": names,
    }, indent=2))


asyncio.run(main())
PY
```

   Expected: `"digifetch_count": 33` (2026-09-16 value) and `"cohort_missing": []`. PASS = empty `cohort_missing`.
4. `## Check 2 — production smoke against api.gloom.sh` — exact command:

```bash
set -a; . ./.env; set +a
GLOOMBERB_LIVE_SMOKE=1 PATH="$PWD/.venv/bin:$PATH" pytest tests/dq/test_gloomberb_live_smoke.py -v
```
   What it asserts: one anonymous quote returns a `QuoteResult` with `provider_id == "gloomberb-cloud"` (`tests/dq/test_gloomberb_live_smoke.py:24-33`). Expected: `1 passed`. Notes: the smoke is anonymous — it does not exercise the cookie (that is `docs/ops/gloomberb-session-cookie.md`); `set -a` exports silently and no value is ever printed.
5. `## Check 3 — hosted-surface row (reserved route)` — the reserved hostname `mcp.digithings.ai` (`ports.ts:22`) has no live route today (`wrangler.toml:63-73`); when enabled, the same listing command runs with `streamablehttp_client("https://mcp.digithings.ai/mcp", headers=...)` behind the Worker-edge digikey JWT (scope `digiquant:backtest`, `digiquant/ARCHITECTURE.md` § MCP hosting). Mark this row BLOCKED until then; do not invent a token command that is not documented yet.
6. `## Record results` — the comment template:

```markdown
## Post-deploy verification (#4101) — <YYYY-MM-DD>

Surface: local served path (python -m digiquant.mcp_server --scope read, 127.0.0.1:8767).
Build/commit under test: <sha>.

| Check | Result | Evidence |
|---|---|---|
| 13-tool cohort on the served MCP surface | PASS/FAIL | cohort_missing=[...], digifetch_count=<n> (tools/list) |
| Production smoke vs api.gloom.sh | PASS/FAIL | GLOOMBERB_LIVE_SMOKE=1 pytest tests/dq/test_gloomberb_live_smoke.py -v → <n> passed |
| Hosted row (mcp.digithings.ai) | BLOCKED/PASS | route commented out (wrangler.toml:63-73) / hosted tools/list output |
```
   and the exact posting command shape: `gh issue comment 4101 -R digithings-ai/digithings --body "$(cat <<'EOF' ... EOF)"`. Failures are filed as issues with the typed envelope and the request shape (never re-run in a loop for a pass).
7. `## Drift signals and escalation` — the normative criteria: S1 `not_found` on the pinned request shapes on 2 runs ≥24h apart; S2 payload field loss (`upstream_error` "unexpected payload") twice; S3 anonymous endpoint returns 401/403 or cookie names no longer match `SESSION_COOKIE_NAMES` (`client.py:180-183`); S4 smoke fails 2 consecutive days with non-rate-limit errors; S5 host/family-wide break. Escalation: file an issue (`component:digiquant`, `priority:medium`, `priority:high` for S5/S3) with envelope + request shape + dates. Scheduled probe trigger: ≥2 distinct drift events in 30 days or one family-wide break; probe = one anonymous quote + one anonymous history per day (`0 14 * * *` UTC), no cookie. State exactly: `api.gloom.sh is an existing runtime dependency of the client (client.py:152), so a scheduled probe is not new network exposure.` Rate limits (`rate_limited`) and free-tier delays are non-events.
8. `## Related` — links: `docs/superpowers/specs/2026-09-16-gloomberb-post-deploy-verification-design.md`, `docs/superpowers/specs/2026-09-12-digifetch-scoping-design.md`, issues `#4101`, `#4069`, `#4110` — and `gloomberb-session-cookie.md` **only once the #4099 runbook has merged** (that plan creates the file; until then omit the link so `make doc-check` stays green, and add it in a follow-up). One rule, no exceptions.

Link forms must resolve from `docs/ops/` (e.g. `../superpowers/specs/...`).

- [ ] **Step 5: Run the test to verify it passes**

Run: `PATH="$PWD/.venv/bin:$PATH" pytest tests/scripts/test_digifetch_post_deploy_verification_doc.py -v`
Expected: PASS — `6 passed`.

- [ ] **Step 6: Run the doc link check**

Run: `make doc-check`
Expected: `check_doc_links: OK (<N> markdown files scanned)` and exit 0. This holds only if Step 4 item 8's rule was followed: the `gloomberb-session-cookie.md` link is present only after the #4099 runbook has merged, omitted before then.

- [ ] **Step 7: Commit**

```bash
git add docs/ops/digifetch-post-deploy-verification.md \
  tests/scripts/test_digifetch_post_deploy_verification_doc.py
git commit -m "docs(digiquant): digifetch post-deploy verification checklist (#4101)"
```

---

### Task 2: Run the one-time verification and record it on #4101

**Files:**
- Create: none (operator run + issue comment)

**Interfaces:**
- Consumes: Task 1's doc (commands executed exactly as written); the deployed family; the local `mcp` extra and `.env`.
- Produces: three Check rows of evidence and the results comment on #4101 that Task 3 resolves.

- [ ] **Step 1: Precondition check (stop if not met)**

Confirm the deploy under test carries the digifetch family (`mcp_server.py` `READ_SCOPE_TOOLS`) and note its commit SHA. If the deploy predates the family, stop and comment the blocker on #4101 instead of running.

- [ ] **Step 2: Check 1 — served surface cohort**

Run the server in a second terminal exactly as in the doc:
```bash
PATH="$PWD/.venv/bin:$PATH" python -m digiquant.mcp_server --scope read
```
Expected log: `Starting digiquant MCP server on 127.0.0.1:8767 (transport=streamable-http scope=read)`.
Then run the doc's listing heredoc. Expected: `"cohort_missing": []` and `"digifetch_count": 33` (or the current count, recorded as-is). Copy the full JSON output.

- [ ] **Step 3: Check 2 — live smoke**

Run the doc's smoke command:
```bash
set -a; . ./.env; set +a
GLOOMBERB_LIVE_SMOKE=1 PATH="$PWD/.venv/bin:$PATH" pytest tests/dq/test_gloomberb_live_smoke.py -v
```
Expected: `1 passed` (`::test_live_anonymous_quote_smoke`). Copy the result line. If it fails with `rate_limited`/network errors, re-run once after a short wait (documented condition); two consecutive non-rate-limit failures → Task 2 Step 5 failure branch.

- [ ] **Step 4: Check 3 — hosted row**

If `https://mcp.digithings.ai/mcp` answers (route has been enabled since this spec), run the listing heredoc against it and record the output. Otherwise record `BLOCKED — route commented out (wrangler.toml:63-73)`.

- [ ] **Step 5: Post the results comment on #4101**

Run (fill the date, SHA, and observed values from Steps 2–4):
```bash
gh issue comment 4101 -R digithings-ai/digithings --body "$(cat <<'EOF'
## Post-deploy verification (#4101) — <YYYY-MM-DD>

Surface: local served path (python -m digiquant.mcp_server --scope read, 127.0.0.1:8767).
Build/commit under test: <sha>.

| Check | Result | Evidence |
|---|---|---|
| 13-tool cohort on the served MCP surface | PASS | cohort_missing=[], digifetch_count=<n> |
| Production smoke vs api.gloom.sh | PASS | 1 passed (test_live_anonymous_quote_smoke) |
| Hosted row (mcp.digithings.ai) | BLOCKED | route commented out (wrangler.toml:63-73) |

Notes: smoke is anonymous (cookie-gated verification is #4099's runbook);
rate limits and free-tier delays are expected conditions, not drift.
EOF
)"
```
Expected: the comment URL. If a check FAILED: instead file a follow-up issue per the doc's escalation section with the envelope and request shape, link it from the comment, and do not close #4101.

- [ ] **Step 6: Stop the server**

Stop the foreground process from Step 2 (Ctrl-C). No files changed in this task; no commit.

---

### Task 3: PR, review coverage, merge, resolve #4101

**Files:**
- Create: none (PR + issue operations)

**Interfaces:**
- Consumes: Task 1's commit; Task 2's results comment URL.
- Produces: merged docs PR into `develop`; #4101 resolved per the recorded evidence.

- [ ] **Step 1: Push and open the PR into `develop`**

Run:
```bash
git push -u origin "$(git branch --show-current)"
gh pr create --base develop --head "$(git branch --show-current)" \
  --title "docs(digiquant): digifetch post-deploy verification checklist (#4101)" \
  --body "$(cat <<'EOF'
## What
Docs-only checklist for the digifetch post-deploy verification: served-surface
cohort check (13 phase-0 tools, count reported), live smoke against
api.gloom.sh, results recording on #4101, and drift-escalation criteria
(scheduled probe deliberately not built — YAGNI).

## Why
Refs #4101 (follow-up to #4069 / PR #4085; family grew under #4110).
Doc: `docs/ops/digifetch-post-deploy-verification.md`; fidelity pinned by
`tests/scripts/test_digifetch_post_deploy_verification_doc.py`.

## Verification
- `pytest tests/scripts/test_digifetch_post_deploy_verification_doc.py -v` → 6 passed
- `make doc-check` → OK
- One-time run recorded on #4101: <comment URL>

## Notes
- No scheduled workflow probe; escalation criteria documented in the doc.
- `mcp.digithings.ai` stays reserved/human-gated — the hosted row is marked BLOCKED.
EOF
)"
```
Expected: prints the PR URL. Do not use `make pr` (its routing map would target `module/digiquant`).

- [ ] **Step 2: Review coverage on the record**

Per `docs/agents/CODE_REVIEW_POLICY.md`: in-session review on a fresh-context subagent (`/review <N>`); fix findings on the same branch; post the findings comment opening with `<!-- in-session-review -->`; apply `reviewed:agent`. Wait for required CI (including the docs link-check workflow) to be green.

- [ ] **Step 3: Merge when merge-ready**

Run:
```bash
gh pr merge <N> --merge
```
Expected: merged into `develop`.

- [ ] **Step 4: Resolve #4101**

If Task 2's results comment shows both required checks PASS (hosted row may be BLOCKED with the route citation and per the human-gated route note), close it:

```bash
gh issue close 4101 -R digithings-ai/digithings --reason completed \
  --comment "Verified per <comment URL>: cohort present on the served surface, live smoke green against api.gloom.sh. Hosted row remains blocked on the reserved mcp.digithings.ai route (wrangler.toml:63-73, human-gated) and is tracked by the doc's Check 3 row."
```

If any required check FAILED, leave #4101 open and link the follow-up issue filed in Task 2 Step 5.

- [ ] **Step 5: Confirm the close**

Run:
```bash
gh issue view 4101 -R digithings-ai/digithings --json state -q .state
```
Expected: `CLOSED` (or OPEN with the failure link, per Step 4).

---

## Self-Review

**1. Spec coverage:** §1 goal → Tasks 1 (procedure) + 2 (the run). §2.1 cohort-vs-count → Global Constraints, doc section 1, test D4 gate. §2.2 serving path/scope/route → doc sections 2–3 and Check 3 row; Global Constraint "no invented endpoints". §2.3 smoke harness → doc section 4 + Task 2 Step 3. §2.4 drift surface → doc section 7. §3 D1–D6 → no probe (Global Constraints), home (Task 1 Step 4), served surface (D3), count reported (test/doc), failure→issue (Task 2 Step 5), fidelity test (Task 1 Step 2). §4 contracts → test assertions + Global Constraints. §5 normative values → doc sections 3–4, 7; Task 2 Steps 2–5. §6 rollout order → Tasks 1→2→3. §7 verification → Task 1 Steps 5–6 + Task 2 Step 2. §8 risks/escalation → doc section 7 (S1–S5 trigger + probe shape + "not new network exposure"). §9 out of scope → Global Constraints + Check 3 blocked row. §10 Q1 → Task 2 Step 4 hosted row branch; Q2 → count recorded not gated.

**2. Placeholder scan:** bracketed tokens are runtime fills only: `<YYYY-MM-DD>`, `<sha>`, `<n>`, `<comment URL>`, `<N>` (PR number). The doc's Check 3 uses the two documented alternatives (BLOCKED citation or observed hosted output) — no invented URL or token command. No TBD/TODO/"add appropriate error handling".

**3. Type consistency:** the doc path, test path, cohort tuple, and command strings are identical across Global Constraints, Task 1 code, and Task 2; `READ_SCOPE_TOOLS`, `GLOOMBERB_LIVE_SMOKE`, `test_dq/test_gloomberb_live_smoke.py`, `mcp.digithings.ai`, `wrangler.toml:63-73`, and `client.py:152` match the spec and the tree at `118966117`; the `mcp` client calls (`streamablehttp_client` → `ClientSession.initialize` → `list_tools`) match `digigraph/orchestration/mcp_client.py:611-623`.
