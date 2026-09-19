# Gloomberb Session-Cookie Runbook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the operator runbook `docs/ops/gloomberb-session-cookie.md` (free account, cookie extraction, per-deployment placement, privacy, absent-cookie failure mode) with a repo-level test pinning every load-bearing fact to the shipped code.

**Architecture:** Documentation-only deliverable plus one `tests/scripts/` assertion test (same pattern as `tests/scripts/test_mcp_container.py`), a pointer edit in `digiquant/ARCHITECTURE.md`, a commented `.env.example` placeholder, and one tracked follow-up issue for the hosted-container forwarding gap. No runtime code changes.

**Tech Stack:** Markdown under `docs/ops/` (link-checked by `scripts/check_doc_links.py`), pytest (unit-marked) reading the doc and importing `digiquant.data.gloomberb.client` / `.entitlements` to derive the facts it pins.

**Spec:** `docs/superpowers/specs/2026-09-16-gloomberb-session-cookie-runbook-design.md` — the plan argues from the spec; executors read both.

## Global Constraints

- The runbook MUST NOT contain real cookie values or account details; every sample value is a placeholder (`<cookie>`, `$GLOOMBERB_SESSION_COOKIE`, `${...}`). The test scans for literal `session_token=<value>` and JWT-looking blobs.
- Only these `GLOOMBERB_*` names may appear in the runbook: `GLOOMBERB_SESSION_COOKIE`, `GLOOMBERB_ENABLED`, `GLOOMBERB_LIVE_SMOKE` (test marker only). Never cite the `GLOOMBERB_*_ENV` Python constant identifiers as env vars.
- The runbook must state the absent-cookie failure mode exactly: typed `auth_required` with **no HTTP request** for gated tools; `pro_required` for Pro tools with a valid free session; family kill switch `GLOOMBERB_ENABLED` (default ON; a typo disables → typed `upstream_error`, no request).
- All 11 cookie-gated tool names must appear, each marked `session` / `preview` / `pro`; the family total is stated as 33 (22 free) with a date qualifier.
- Cross-links required: `#4069`, `#4110`, `#4101`, and `docs/superpowers/specs/2026-09-12-digifetch-scoping-design.md`.
- Digi names are always lowercase (`digithings`, `digiquant`, `digichat`); code identifiers such as `DigiQuantMcpContainer` keep their casing.
- TDD: write the test, run it, watch it fail (file-absence RED), then write the doc and watch it pass. RED-first applies once per docs artifact, exactly as `tests/scripts/test_mcp_container.py` documents.
- Routing: this diff is repo-level docs + a repo-level test → `component:root` → **PR base `develop`**. Because #4099 carries the `component:digiquant` label, `make task ISSUE=4099` cuts from `origin/module/digiquant`; open the PR with `gh pr create --base develop` explicitly (do not use `make pr`, which would compute `module/digiquant`).
- Never echo or print the cookie in any command, shell history-safe form preferred; the plan's verification commands print only codes/counts.
- Do not touch runtime code, `cloudflare/` config, `.github/workflows/`, or any dependency. The hosted-forwarding gap is a tracked follow-up issue, not this PR.
- `make doc-check` must be green; relative links in the runbook resolve from `docs/ops/`.

---

### Task 1: Branch, tracking, and the hosted-forwarding follow-up issue

**Files:**
- Create: none (platform steps only)

**Interfaces:**
- Consumes: issue #4099 (labels: `component:digiquant`, `priority:low`), current `origin/develop` = `118966117`.
- Produces: worktree branch `task/4099-docs-digiquant-runbook-for-gloomberb-session-cookie-free-account-per-deployment-env` (slug from `scripts/worktree_task.sh`), and the follow-up issue number that Task 3's runbook links.

- [ ] **Step 1: Cut the task branch**

Run:
```bash
git fetch origin develop
make task ISSUE=4099
```
Expected: a worktree on `task/4099-...` branched from `refs/remotes/origin/module/digiquant` (the label-derived base), with the stale-module guard silent (base current). All later commands run inside that worktree.

- [ ] **Step 2: File the hosted-forwarding follow-up issue**

The hosted MCP container does not forward the cookie today (`apps/digithings-stack-cloudflare/src/index.ts:177-185`; pinned by `tests/scripts/test_mcp_container.py:35-42`); the runbook must not pretend otherwise.

Run:
```bash
gh issue create -R digithings-ai/digithings \
  --label component:digiquant --label priority:low \
  --title "feat(digiquant-mcp): forward GLOOMBERB_SESSION_COOKIE to the hosted MCP container" \
  --body "$(cat <<'EOF'
Follow-up from #4099 (runbook: docs/ops/gloomberb-session-cookie.md).

The gated digifetch tools (11 names, `data/gloomberb/entitlements.py`)
answer typed `auth_required` on the hosted MCP surface because
`DigiQuantMcpContainer.envVars` (apps/digithings-stack-cloudflare/src/index.ts:177-185)
does not forward `GLOOMBERB_SESSION_COOKIE` and no `wrangler secret` exists for it
(wrangler.toml secrets comment:135–164).

Wiring (4 edits, one PR):
1. index.ts envVars: `GLOOMBERB_SESSION_COOKIE: env.GLOOMBERB_SESSION_COOKIE ?? ""`
2. `printf '%s' "$VALUE" | env -u CLOUDFLARE_API_TOKEN npx wrangler secret put GLOOMBERB_SESSION_COOKIE`
3. tests/scripts/test_mcp_container.py: add the name to `MCP_SCOPED_VARS` + `test_wrangler_documents_mcp_secrets`
4. wrangler.toml secrets comment: add the name

Not a new service dependency (the container already talks to api.gloom.sh);
the cookie is a credential for an already-shipped client. The mcp.digithings.ai
route stays reserved/human-gated (wrangler.toml:63-73).
EOF
)"
```
Expected: prints the new issue URL. Record the number as `<FWD>` for Task 3 Step 4.

- [ ] **Step 3: Commit nothing yet**

No files changed in this task. Proceed.

---

### Task 2: Operator dry-run — free account, cookie extraction, local verification

**Files:**
- Modify (local only, never committed): `.env` (repo root, gitignored; the file may be absent in a fresh worktree — create it locally in that case)

**Interfaces:**
- Consumes: the shipped client (`digiquant/src/digiquant/data/gloomberb/client.py:152-154, 482-486, 2143-2154`), `term.gloom.sh` as the only in-tree web surface (`attribution.py:23`).
- Produces: (a) the verbatim signup/email-verification steps (or the finding that self-serve signup is unavailable) for Task 3's runbook section; (b) a local `GLOOMBERB_SESSION_COOKIE` in `.env`; (c) one `OK holders rows = <n>` verification output recorded for the PR body.

- [ ] **Step 1: Create the free account**

Open `https://term.gloom.sh/`, create a free account, complete email verification, and sign in. **Write down every step exactly as it appears** (control labels, order, any "check your inbox" screen). If there is no self-serve signup (invite/web-form only), stop and record that finding verbatim instead — the runbook must describe reality, not an assumed flow.

- [ ] **Step 2: Extract the session cookie**

In the browser, open devtools → Application/Storage → Cookies for `term.gloom.sh`, and copy the value of `__Secure-gloomberb.session_token` (the fallback name is `gloomberb.session_token`; names per `client.py:180-183`). Do not paste the value into chat, an issue, or a commit.

- [ ] **Step 3: Place it in the local `.env`**

Append to the repo-root `.env` (gitignored) using the `name=value` form the client accepts (`client.py:437-439, 2143-2154`):

```
GLOOMBERB_SESSION_COOKIE=__Secure-gloomberb.session_token=<paste-value-here>
```

- [ ] **Step 4: Verify the cookie locally (prints codes/counts only, never the value)**

Run:
```bash
set -a; . ./.env; set +a
PATH="$PWD/.venv/bin:$PATH" python -c "
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
Expected: `OK holders rows = <n>` with `n > 0`. If it prints `FAIL auth_required`, the cookie was not read — check quoting/export (`set -a`) and that the value still has the `name=` prefix when the cookie name is present. Copy the exact output line into the PR body later.

- [ ] **Step 5: Record the dry-run artifacts**

Keep the exact UI steps from Step 1 and the Step 4 output in the session (they are inputs to Task 3). No commit.

---

### Task 3: Runbook test (RED) + runbook + pointers (GREEN)

**Files:**
- Create: `tests/scripts/test_gloomberb_session_cookie_runbook.py`
- Create: `docs/ops/gloomberb-session-cookie.md`
- Modify: `digiquant/ARCHITECTURE.md` (env-table row `GLOOMBERB_SESSION_COOKIE` at line 1638; MCP-hosting per-component secrets paragraph ending "set it to `\"r2\"` explicitly via env for the hosted path." at line 395)
- Modify: `.env.example` (insert after `DIGIQUANT_BITVIEW_FETCH=1`, line 141)
- Test: `tests/scripts/test_gloomberb_session_cookie_runbook.py`

**Interfaces:**
- Consumes: `GLOOMBERB_ENABLED_ENV` / `GLOOMBERB_SESSION_COOKIE_ENV` from `digiquant.data.gloomberb.client`; `TOOL_ENTITLEMENTS` from `digiquant.data.gloomberb.entitlements`; the dry-run artifacts from Task 2; `<FWD>` from Task 1.
- Produces: the runbook this plan delivers, pinned by the test; `ARCHITECTURE.md` and `.env.example` pointers other docs/tasks can rely on.

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_gloomberb_session_cookie_runbook.py`:

```python
"""Pin the Gloomberb session-cookie runbook to the shipped code (#4099).

RED premise: at creation this module fails with ``FileNotFoundError`` — the
runbook does not exist yet (``docs/ops/gloomberb-session-cookie.md``). The
file-absence RED applies once; every assertion afterwards pins a fact the
code owns, so a doc edit that drifts from the implementation fails here
instead of misleading an operator. Pattern precedent:
``tests/scripts/test_mcp_container.py`` (header lines 9-14).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNBOOK = REPO_ROOT / "docs" / "ops" / "gloomberb-session-cookie.md"

#: The only GLOOMBERB_* names the runbook may carry: the two env vars the
#: client reads (client.py) and the opt-in live-smoke marker
#: (tests/dq/test_gloomberb_live_smoke.py:18). The first two are cross-checked
#: against the module constants below so a rename fails here, not in prod.
ALLOWED_ENV_NAMES = frozenset(
    {"GLOOMBERB_ENABLED", "GLOOMBERB_SESSION_COOKIE", "GLOOMBERB_LIVE_SMOKE"}
)

#: Cross-references the runbook must carry: origin (#4069), coverage
#: expansion (#4110), and the post-deploy verification plan (#4101).
REQUIRED_ISSUE_REFS = ("#4069", "#4110", "#4101")

#: Documented sample values must be visibly placeholders.
PLACEHOLDER_PREFIXES = ("<", "$", "{")


def _text() -> str:
    return RUNBOOK.read_text(encoding="utf-8")


def test_runbook_names_only_real_env_vars() -> None:
    from digiquant.data.gloomberb.client import (
        GLOOMBERB_ENABLED_ENV,
        GLOOMBERB_SESSION_COOKIE_ENV,
    )

    assert {GLOOMBERB_ENABLED_ENV, GLOOMBERB_SESSION_COOKIE_ENV} <= ALLOWED_ENV_NAMES
    named = set(re.findall(r"\bGLOOMBERB_[A-Z0-9_]+\b", _text()))
    assert named, "runbook names no GLOOMBERB_* env var"
    assert named <= ALLOWED_ENV_NAMES, sorted(named - ALLOWED_ENV_NAMES)


def test_runbook_lists_every_cookie_gated_tool() -> None:
    from digiquant.data.gloomberb.entitlements import TOOL_ENTITLEMENTS

    gated = sorted(name for name, ent in TOOL_ENTITLEMENTS.items() if ent != "free")
    text = _text()
    missing = [name for name in gated if name not in text]
    assert not missing, missing
    named = set(re.findall(r"\bdigifetch_[a-z0-9_]+\b", text))
    assert named <= set(TOOL_ENTITLEMENTS), sorted(named - set(TOOL_ENTITLEMENTS))


def test_runbook_distinguishes_absent_session_from_missing_plan() -> None:
    text = _text()
    assert "auth_required" in text
    assert "pro_required" in text


def test_runbook_places_the_cookie_for_local_and_hosted_runs() -> None:
    text = _text()
    assert "DigiQuantMcpContainer" in text
    assert "wrangler secret put GLOOMBERB_SESSION_COOKIE" in text


def test_runbook_carries_the_cross_links() -> None:
    text = _text()
    for ref in REQUIRED_ISSUE_REFS:
        assert ref in text, ref


def test_runbook_never_contains_a_literal_cookie_value() -> None:
    text = _text()
    for value in re.findall(r"session_token=(\S+)", text):
        assert value.startswith(PLACEHOLDER_PREFIXES), value
    assert "never log" in text.lower()
    assert not re.search(r"eyJ[A-Za-z0-9_-]{10,}", text)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `PATH="$PWD/.venv/bin:$PATH" pytest tests/scripts/test_gloomberb_session_cookie_runbook.py -v`
Expected: FAIL — every test errors with `FileNotFoundError: ... docs/ops/gloomberb-session-cookie.md` (file-absence RED).

- [ ] **Step 3: Write the runbook**

Create `docs/ops/gloomberb-session-cookie.md`. Required sections and content (facts must cite the spec's verified file:line references; sample values are placeholders only):

1. `# Gloomberb session-cookie runbook (#4099)` — one-paragraph scope: the 11 gated digifetch tools need a Gloomberb session cookie; free tools work without it; this doc covers account, extraction, placement, privacy, and the absent-cookie failure mode.
2. `## What happens without the cookie` — must state: gated tools return the typed `auth_required` error **without making an HTTP request** (`client.py:2248-2254`); Pro-only tools return `pro_required` for a valid free session (`client.py:307-322`); the family kill switch `GLOOMBERB_ENABLED` is default-ON and a typo disables it, returning a typed `upstream_error` with no request (`client.py:248-272`); absent cookie is a supported state — the 22 free tools keep working.
3. `## Which tools need it` — the table from the spec §2.2 (11 names, each `session` / `preview` / `pro`), plus: family total 33 tools, 22 free, as of 2026-09-16 (`entitlements.py:58-96`); one line that this is enrichment data (free tier delayed up to 15 minutes), never a pipeline primary.
4. `## Get a free account` — the verbatim dry-run steps from Task 2 (numbered, naming the visible control labels), anchored on `https://term.gloom.sh/`. If Task 2 found no self-serve signup, state that finding verbatim and link the tracking issue.
5. `## Extract the session cookie` — browser devtools → Application/Storage → Cookies → `term.gloom.sh`; copy `__Secure-gloomberb.session_token` (fallback `gloomberb.session_token`; `client.py:180-183`). Accepted forms: `name=value` or a bare token (`client.py:437-439, 2143-2154`). Show only `GLOOMBERB_SESSION_COOKIE=__Secure-gloomberb.session_token=<cookie-value>` as the example.
6. `## Place it per deployment` — three subsections:
   - **Local runs:** add the line to the repo-root `.env` (gitignored); `.env.example` now carries a commented placeholder.
   - **Hosted MCP container:** NOT forwarded today — `DigiQuantMcpContainer.envVars` (`apps/digithings-stack-cloudflare/src/index.ts:177-185`) carries only scope/backend/FRED/R2, pinned by `tests/scripts/test_mcp_container.py:35-42`; the `mcp.digithings.ai` route is commented out (`wrangler.toml:63-73`, human gate). The tracked wiring (follow-up issue `#<FWD>`) is exactly: add `GLOOMBERB_SESSION_COOKIE: env.GLOOMBERB_SESSION_COOKIE ?? ""` to `envVars`; run `printf '%s' "$VALUE" | env -u CLOUDFLARE_API_TOKEN npx wrangler secret put GLOOMBERB_SESSION_COOKIE`; add the name to `MCP_SCOPED_VARS` in `tests/scripts/test_mcp_container.py` and to `test_wrangler_documents_mcp_secrets`; add it to the `wrangler.toml` secrets comment (lines 135–164).
   - **GitHub Actions pipeline:** no `GLOOMBERB_*` env is set in any workflow today (verified 2026-09-16); unset means session tools are filtered from the in-process agent surface (`agent_tools.py:261-292`). If the pipeline ever needs a gated tool, a repo secret feeding the pipeline job is the placement — tracked as future work, not documented as live.
7. `## Verify the cookie works` — the Task 2 Step 4 command verbatim and its expected output (`OK holders rows = <n>`) plus the `FAIL auth_required` troubleshooting note (quoting, `set -a` export). State that the command prints only a code or a row count, never the value.
8. `## Privacy rules` — never log, never echo, never paste into issues/PRs/chat; the TTL cache discriminator is a truncated SHA-256 fingerprint, not the cookie (`client.py:186-197`); cookies are forwarded only to same-origin redirect hops (`digifetch/src/digifetch/http.py:224`); rotate by replacing the value in every placement (local `.env`, and the hosted secret once wired) — the fingerprint separates sessions, so no cache flush or restart is required for correctness.
9. `## Related` — links: `docs/superpowers/specs/2026-09-16-gloomberb-session-cookie-runbook-design.md`, `docs/superpowers/specs/2026-09-12-digifetch-scoping-design.md`, `../digiquant/ARCHITECTURE.md`, issues `#4069`, `#4110`, `#4101`, and the follow-up `#<FWD>`.

Link forms must resolve from `docs/ops/` (e.g. `../superpowers/specs/...`, `../digiquant/ARCHITECTURE.md`).

- [ ] **Step 4: Add the `ARCHITECTURE.md` pointer and `.env.example` placeholder**

In `digiquant/ARCHITECTURE.md`, append to the end of the `GLOOMBERB_SESSION_COOKIE` env-table row (line 1638, before the closing ` |`):

```
— operator runbook: [docs/ops/gloomberb-session-cookie.md](../docs/ops/gloomberb-session-cookie.md)
```

In the same file, in the MCP-hosting secrets paragraph (line 395, immediately after "set it to `\"r2\"` explicitly via env for the hosted path."), append one sentence:

```
The Gloomberb session cookie is **not** forwarded to this container yet (gated digifetch tools answer the typed `auth_required`); the operator path and tracked wiring follow-up are in [docs/ops/gloomberb-session-cookie.md](../docs/ops/gloomberb-session-cookie.md).
```

In `.env.example`, insert after line 141 (`DIGIQUANT_BITVIEW_FETCH=1`):

```
# Gloomberb session cookie for the session-gated digifetch tools (#4099).
# Free account, extraction, placement: docs/ops/gloomberb-session-cookie.md.
# Never commit a value; local .env only.
# GLOOMBERB_SESSION_COOKIE=
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `PATH="$PWD/.venv/bin:$PATH" pytest tests/scripts/test_gloomberb_session_cookie_runbook.py -v`
Expected: PASS — `6 passed` (one test per pinned fact).

- [ ] **Step 6: Run the doc link check**

Run: `make doc-check`
Expected: `check_doc_links: OK (<N> markdown files scanned)` and exit 0.

- [ ] **Step 7: Commit**

```bash
git add docs/ops/gloomberb-session-cookie.md \
  tests/scripts/test_gloomberb_session_cookie_runbook.py \
  digiquant/ARCHITECTURE.md .env.example
git commit -m "docs(digiquant): Gloomberb session-cookie runbook (#4099)"
```

---

### Task 4: PR, review coverage, merge, close #4099

**Files:**
- Create: none (PR + issue operations)

**Interfaces:**
- Consumes: Task 3's commit; the Task 2 dry-run output; `<FWD>` from Task 1.
- Produces: merged PR into `develop` with `Fixes #4099`; #4099 closed by the merge.

- [ ] **Step 1: Push and open the PR into `develop`**

Run:
```bash
git push -u origin "$(git branch --show-current)"
gh pr create --base develop --head "$(git branch --show-current)" \
  --title "docs(digiquant): Gloomberb session-cookie runbook (#4099)" \
  --body "$(cat <<'EOF'
## What
Operator runbook for GLOOMBERB_SESSION_COOKIE: free-account signup + email
verification (operator dry-run verified), cookie extraction, per-deployment
placement (local .env / hosted container gap + tracked follow-up / GH Actions
note), privacy rules, and the absent-cookie failure mode (typed
`auth_required`, zero HTTP; `pro_required` for Pro tools).

## Why
Fixes #4099 (follow-up to #4069 / PR #4085). Runbook:
`docs/ops/gloomberb-session-cookie.md`; fidelity pinned by
`tests/scripts/test_gloomberb_session_cookie_runbook.py`.

## Verification
- `pytest tests/scripts/test_gloomberb_session_cookie_runbook.py -v` → 6 passed
- `make doc-check` → OK
- Operator dry-run output: `OK holders rows = <n>`

## Notes
- Docs-only diff; hosted-container forwarding is tracked separately (#<FWD>).
- `mcp.digithings.ai` stays reserved/human-gated — untouched.
EOF
)"
```
Expected: prints the PR URL. Do not use `make pr` (its routing map would target `module/digiquant`).

- [ ] **Step 2: Review coverage on the record**

Per `docs/agents/CODE_REVIEW_POLICY.md`: run the in-session review on a fresh-context subagent (`/review <N>`); fix findings on the same branch; post the findings comment opening with `<!-- in-session-review -->`; apply `reviewed:agent`. Wait for required CI (including `make doc-check`'s workflow) to be green.

- [ ] **Step 3: Merge when merge-ready**

Run:
```bash
gh pr merge <N> --merge
```
Expected: merged into `develop`; the `Fixes #4099` trailer closes the issue.

- [ ] **Step 4: Confirm the close and clean up**

Run:
```bash
gh issue view 4099 -R digithings-ai/digithings --json state -q .state
```
Expected: `CLOSED`. If it is still open, comment the PR link on #4099 and close it with `gh issue close 4099 --reason completed`, since the merge did not carry the trailer.

---

## Self-Review

**1. Spec coverage:** §1 goal → Tasks 3–4 (runbook + pointers + PR). §2.1 client facts → Task 3 Step 3 sections 2, 5, 8 (citations pinned by the test). §2.2 tool inventory → Task 3 sections 3 + `test_runbook_lists_every_cookie_gated_tool`. §2.3 placement → Task 3 section 6 + Step 4 pointers + Task 1 follow-up issue. §2.4 docs conventions → home `docs/ops/`, `make doc-check` Step 6. §2.5 signup surface → Task 2 dry-run. §3 D1–D5 → home (Task 3), gap+tracker (Task 1 Step 2 / Task 3 section 6), test fidelity (Task 3), ARCHITECTURE pointers (Step 4), `.env.example` (Step 4). §4 contracts → Global Constraints + test assertions. §5 normative values → Task 3 section 6 wiring list verbatim. §6 rollout order → Tasks 2→3→4 (dry-run before authoring). §7 verification → Task 3 Steps 5–6 + Task 2 Step 4. §8 risks → runbook sections 2/5/8 (fallback cookie names, privacy). §9 out of scope → Global Constraints. §10 open questions → Task 2 Step 1 fallback branch + section 6 GH Actions note.

**2. Placeholder scan:** the only bracketed tokens are deliberate runtime fills: `<FWD>` (issue number created in Task 1 Step 2, inserted in Task 3 sections 6 and 9 and the PR body) and `<n>` (dry-run row count). The dry-run steps are captured from a real operator run, not invented — the plan says exactly what to observe and what to do if the flow differs. No TBD/TODO/"add appropriate error handling" phrasing.

**3. Type consistency:** paths, env names, tool names, and line references match the spec and the tree at `118966117`; the test's `ALLOWED_ENV_NAMES` / `REQUIRED_ISSUE_REFS` / `PLACEHOLDER_PREFIXES` are referenced by name in the Global Constraints and Task 3 contract; the runbook path and test path are identical everywhere they appear. `DigiQuantMcpContainer`, `MCP_SCOPED_VARS`, and `test_wrangler_documents_mcp_secrets` are the exact identifiers in `apps/digithings-stack-cloudflare/src/index.ts` and `tests/scripts/test_mcp_container.py`.
