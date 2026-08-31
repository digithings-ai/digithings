# Code review policy (digithings-ai org)

Canonical for **digithings**, **twelve-x**, and any other digithings-ai repo. Apply in Cursor, Claude Code, Copilot, and similar coding agents. Do **not** invent a custom review skill — use existing repo commands and built-in review agents/skills.

## Default: in-session review

Prefer **in-session** review on a **fresh-context subagent** (author session must not review its own diff):

| Tooling | How |
|---------|-----|
| digithings (Claude) | `/review <N>` — see `agents/sources/commands/review.md` |
| digithings / Cursor | Built-in `code-review` / `code-reviewer`, Bugbot, or security-review skills when they fit |
| twelve-x / other org repos | Same idea: fresh subagent + findings posted on the PR |

Post findings on the record (PR comment). digithings requires `<!-- in-session-review -->` + `reviewed:agent` for the coverage gate.

## Metered third parties (quota)

| Service | Policy |
|---------|--------|
| **CodeRabbit** | Optional / sunset. **Never** `@coderabbitai review` for small follow-ups (CI nits, docs, one-line fixes). Re-request **only** when a prior **major** finding was fixed and needs verification. Do not burn remaining subscription quota. |
| **Cursor Bugbot** | On demand when available (`bugbot run` once a diff is final). Never at PR open, never per push. Usage-limit `neutral` ≠ a review — fall back to in-session. |
| **Copilot PR review** | Off unless explicitly enabled for that repo. |

A green third-party **status check** is not an approving review. Check review decision / open threads before merge.

## Cost-efficient tiering

**General rule (all subagents):** best model for the job; prefer the token-efficient
choice that still clears the bar; **do not use fast mode** (`*-fast` / speed-optimized
Cursor slugs). Quality of fit first; cost second; latency never overrides either.

1. **Scope pass (token-efficient)** — map the diff, list risk areas, skip clean files. In Claude: haiku or sonnet. In Cursor: a cheaper non-fast slug (e.g. `composer-2.5`), not the expensive default and not `composer-2.5-fast`.
2. **Deep pass (strong model)** — only on flagged areas: correctness, auth, data integrity, races, claim accuracy. In Claude: opus. In Cursor: stronger non-fast model or dedicated review agent.
3. **Refute** — every surviving finding needs a command that was run; drop what a refuter can disprove.

Do not run every lens at opus on a tiny diff. Do not leave review `model` unset under an expensive orchestrator (inheritance tax).

## What not to do

- Do not maintain a bespoke “org CodeRabbit clone” skill.
- Do not re-review the same commit with a paid bot after trivial push-ups.
- Do not treat `risk:low` as “someone read it.”
- Do not skip review when Bugbot/CodeRabbit are unavailable — run in-session instead.
- Do not skip review coverage just to merge faster. After the hatches above are satisfied and CI is green, **merge** the task PR into its base ([AGENTS.md § Merge-when-ready](../../AGENTS.md#merge-when-ready)). `reviewed:agent` still requires the `<!-- in-session-review -->` comment.

## After review: merge

Review is a step in the loop, not a hand-off that leaves the PR open. When required CI is green, threads are triaged, and a coverage hatch is on the record, the authoring agent merges into the PR's base unless a human-gate exception in AGENTS.md applies (including PRs into `main`).
