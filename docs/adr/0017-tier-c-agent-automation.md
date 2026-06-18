# ADR 0017 — Tier C Agent Automation: gh-aw + Cursor Automations

**Status:** Accepted  
**Date:** 2026-06-06  
**Issue:** [#613](https://github.com/digithings-ai/digithings/issues/613)

---

## Context

Tier B automated agent dispatch used a custom Python + scheduled GitHub Actions stack:

| Component | Role |
|-----------|------|
| `auto-assign-copilot.yml` | Fired on `issues:labeled` with `exec:copilot`; called `assign_copilot_agent.py` via REST API |
| `assign_copilot_agent.py` | Assigned `copilot-swe-agent[bot]` to issues + injected custom instructions |
| `copilot-pr-orchestrator.yml` | Scheduled (10 min) trusted-actor loop — drove targeted CI, review, fix rounds, automerge |
| `copilot_pr_pipeline.py` | Python state machine backing the orchestrator |
| `cursor-agent-dispatch.yml` | Fired on `exec:cursor`; installed Cursor CLI and ran `cursor-agent` in the runner |

Pain points with Tier B:
- Bot-triggered `pull_request` CI resulted in `action_required` on every Copilot PR, requiring the orchestrator to re-dispatch targeted CI as a workaround.
- The scheduled orchestrator ran every 10 minutes but had no native retry semantics.
- The Cursor CLI dispatch inside a GitHub Actions runner was fragile (install failures, runner memory limits).
- The custom state machine duplicated logic that platform agents already handle natively.

---

## Decision

Replace Tier B with **GitHub Agentic Workflows (`gh aw`)** for Copilot dispatch and lifecycle, and **Cursor Automations** for Cursor dispatch.

### Tier C dispatch map

| Trigger | Tier B (removed) | Tier C (added) |
|---------|-----------------|----------------|
| `exec:copilot` issue | `auto-assign-copilot.yml` + `assign_copilot_agent.py` | `copilot-issue-dispatch.lock.yml` (gh-aw) |
| `copilot/*` PR lifecycle | `copilot-pr-orchestrator.yml` + `copilot_pr_pipeline.py` | `copilot-pr-lifecycle.lock.yml` (gh-aw) |
| `exec:cursor` issue | `cursor-agent-dispatch.yml` + Cursor CLI | Cursor Automation (cloud, no GH runner) |

### CI gate change

GitHub's **Skip approval for Copilot coding agent Actions workflows** setting is enabled in repo Settings → Actions → General. This removes the `action_required` gate on Copilot PRs, allowing main `CI` to run directly.

`copilot-pr-targeted-ci.yml` is **kept as fallback** and dispatched by the lifecycle workflow only when main CI has not yet run (missing/action_required).

`agent_pr_checks.py` now accepts either `Copilot targeted CI` success **or** main `CI` success as green for `copilot/*` branches.

### Policy gates (unchanged)

The following DigiThings-specific components remain **unchanged**:

| Asset | Role |
|-------|------|
| `scripts/verify_agent_automerge_pr.py` | Protected-path deny-list |
| `scripts/agent_pr_checks.py` | CI gate for auto-merge eligibility |
| Quota issue #387 | `quota:copilot-exhausted` / `quota:cursor-exhausted` state |
| `automerge-agent-prs.yml` | Human-gated squash merge |
| `agent-pr-autolabel.yml` | Adds `automerge-agent` when CI passes |
| `pr-linkage.yml` | `Fixes #N` enforcement |

### gh-aw source files

The `.md` source files are the canonical authoring surface. Never hand-edit the `.lock.yml` compiled outputs. Compile with:

```bash
gh aw compile copilot-issue-dispatch copilot-pr-lifecycle
```

CI validates compilation on any PR touching `*.md` workflow sources (see `CI_CONVENTIONS.md`).

---

## Consequences

**Positive:**
- Copilot PRs run main CI without the `action_required` workaround.
- Cursor dispatch moves off GitHub Actions runners (no CLI install step, no runner cost).
- The copilot PR loop uses platform-native safe outputs instead of a bespoke Python state machine.
- Fewer moving parts: 3 YAML workflows + 2 Python scripts removed.

**Negative / risks:**
- `gh aw` is early-development software; API churn is possible. Pin the extension version in CI_CONVENTIONS.md and monitor the [gh-aw changelog](https://github.github.com/gh-aw/).
- The gh-aw agent prompt is AI-driven; the Tier B Python state machine was fully deterministic. Monitor lifecycle workflow runs for unexpected actions in the first sprint.
- Cursor Automations requires configuration through the Cursor UI (no code-as-config). The configuration is documented in `CURSOR_AGENT_ONBOARDING.md`.
- `agent-pr-finalizer.yml` still handles `cursor/*` PR backstop; it will be narrowed further once Cursor Automations prove stable.

---

## Rollback

If the big-bang cutover fails within 48 hours:

1. Revert this PR on `develop` (`git revert <merge-sha>`).
2. The reverted commit restores `auto-assign-copilot.yml`, `cursor-agent-dispatch.yml`, `copilot-pr-orchestrator.yml`, and the removed scripts.
3. Disable the gh-aw workflows via `gh aw` if needed (they can be removed with `gh aw remove`).
4. Re-run **Agent dispatch replay** for stuck `exec:*` issues.
5. Post-mortem on #387 quota issue if relevant.

The **Skip approval** repo setting can remain on — it is safe and does not need reverting.

---

## References

- [gh-aw documentation](https://github.github.com/gh-aw/)
- [GitHub changelog: Skip approval for Copilot coding agent Actions workflows](https://github.blog/changelog/2026-03-13-optionally-skip-approval-for-copilot-coding-agent-actions-workflows/)
- [Cursor Automations](https://cursor.com/settings/automations)
- PR #604, #611, #612 — Tier B implementation history
