# Code review policy (digithings-ai org)

Canonical for **digithings**, **twelve-x**, and any other digithings-ai repo. Apply in Cursor, Claude Code, Copilot, and similar coding agents. Do **not** invent a custom review skill — use existing repo commands and built-in review agents/skills.

## Default: in-session review

Prefer **in-session** review on a **fresh-context subagent** (author session must not review its own diff):

| Tooling | How |
|---------|-----|
| digithings (Claude) | `/review <N>` — see `agents/sources/commands/review.md` |
| digithings / Cursor | Same `/review` path (or equivalent fresh-context subagent). Optional: Bugbot / security-review when they fit. **Not** the CodeRabbit Cursor plugin `code-review` / `code-reviewer` skills. |
| twelve-x / other org repos | Same idea: fresh subagent + findings posted on the PR |

Post findings on the record (PR comment). digithings requires `<!-- in-session-review -->` + `reviewed:agent` for the coverage gate.

## Blocking verdicts

Posting the findings is **not** the same as delivering the verdict. A verdict that
blocks approval **must also be submitted as a GitHub review with state
`CHANGES_REQUESTED`**, not only as a comment.

The merge queue reads review state, not comment prose. `scripts/merge_queue.py`
`_gate_review` checks exactly two things: `pr.reviewDecision ==
"CHANGES_REQUESTED"`, and an `APPROVED` review from someone other than the
author. It never reads comment text. **A comment that says "changes requested"
does not block a merge; only a `CHANGES_REQUESTED` review does.**

The comment is where the evidence lives. The review state is what the gate can
see. **A blocking verdict needs both:**

1. **Comment** — the findings, with severity, `file:line`, evidence and
   fixability (the rule above).
2. **Review** — submit with `event: REQUEST_CHANGES`, so the submitted state is
   `CHANGES_REQUESTED`.

What happened on 2026-10-07 (`digithings-ai/twelve-x#347`): the review said
"changes requested — one finding blocks approval", was submitted as
`COMMENTED`, and the queue merged the PR 6m37s later. Both halves were present;
the state was invisible to the gate.

The GitHub MCP review path (create pending review → add comments →
`submit_pending`) does **not** pick the state for you. Stopping at
`submit_pending` without `REQUEST_CHANGES` posts a `COMMENTED` review. Check the
state you actually submitted:

```bash
gh api repos/<owner>/<repo>/pulls/<N>/reviews --jq '.[-1] | {state, submitted_at}'
gh pr view <N> --json reviewDecision
```

## Attestation evidence

A queue attestation (`review: attested by <role>`) is only useful with the review
evidence attached. Every `qa` attestation must record:

- **files / commits read**
- **checks run** — the commands, not only their names
- **verdict** — `approve` or `changes needed`

The evidence goes in the queue's record comment on the PR, not in the merge
commit message.

**Enforcement, stated plainly: this part is manual.** The merge queue does not
parse attestation prose and cannot tell an evidence-free attestation from an
evidence-carrying one. What the DevOps leaf *can* make machine-enforced is that
a posted blocking verdict blocks the queue, through the `CHANGES_REQUESTED`
review state. Carrying evidence inside a human-readable attestation stays a
reviewer and EM responsibility. Do not imply the queue verifies it.

## The review marker (do not hand-write it)

Tool-driven reviews post a marker:

```html
<!-- opencode-power-pack:code-review scope=<owner>/<repo>#<pr>@<head-sha> kind=<summary|finding-key> -->
```

The producer is third-party: [`waybarrios/opencode-power-pack`](https://github.com/waybarrios/opencode-power-pack),
file `skills/code-review/SKILL.md`, distributed as the `opencode-power-pack`
plugin / npm `@waybarrios/opencode-power-pack`. It matches the **exact** marker
plus the authenticated author to decide whether to `PATCH` an existing summary
or `POST` a new one.

Do **not** hand-author this marker, and do not add fields to it. A hand-written
marker with an extra field would not match, and the tool would `POST` a
duplicate summary comment. Any new marker field has to be added upstream in that
`SKILL.md`, not here. The skill also never submits a review, which is why the
`CHANGES_REQUESTED` rule above is the only thing standing between a tool review
and an invisible verdict.

## Metered third parties (quota)

| Service | Policy |
|---------|--------|
| **CodeRabbit** | Optional / sunset. Workspace: keep the CodeRabbit Cursor plugin **disabled** (`.cursor/settings.json`). **Never** run CodeRabbit CLI, `@coderabbitai review`, or plugin skills for routine review. Re-request GitHub auto-review **only** when a prior **major** finding was fixed and needs verification. Do not burn remaining subscription quota. |
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

## Severity is blast radius

Grade a finding by what breaks when it fires — not by diff size, and not by how confident the reviewer is that it *will* fire.

This grades a **finding**, not Cursor's Low/Medium/High risk label and not the retired `risk:*` family ([AGENTS.md § Review coverage](../../AGENTS.md#review-coverage-the-gate-before-production) explains why that axis is unreliable; the coverage gate stays path-based).

**A boot path has no fallback, so a defect there is blocking at any size.** Treat these as blocking — never Low, Nit, or Medium:

- an unguarded command under `set -e` / `set -eu` in a container entrypoint or PID-1 script **before** `exec` — one failing redirect aborts startup, PID 1 exits, and every endpoint 503s
- a startup check that can refuse to start a service (`create_engine`, config validation, a required env var)
- anything that turns a served endpoint into a crash loop

A failed best-effort feature is Low; a failed `exec` is the whole instance. (#4149: a `/etc/hosts` write in the stack entrypoint was reviewed as **Low**, shipped, and took digikey — and therefore every pipeline run — down for 25 minutes.)

**"Could not verify" never lowers severity.** State plainly what you could not exercise, and keep the grade the mechanism supports. An unverifiable finding whose *mechanism* is verified is retained and labelled unverified, not dropped — "defaulting to refuted when unsure" applies to the claim, not to whether it happened to be reproducible. For an ordinary service-scope finding with whole-service blast radius, Medium is the floor; for a boot-path defect, Medium is **not** enough and it stays blocking. The **findings comment** must record what was unverified — the coverage gate reads the comment, not the PR body. A finding downgraded *because* the reviewer could not reproduce it is how #4138's review passed a landmine.

The inverse also holds: a finding labelled Low whose failure mode is fatal on a boot path is misgraded. Reclassify it instead of accepting it.

## What not to do

- Do not maintain a bespoke “org CodeRabbit clone” skill.
- Do not follow CodeRabbit Cursor plugin alwaysApply routing (`code-review-routing.mdc`) — org rule `.cursor/rules/no-coderabbit.mdc` counter-instructs agents to ignore it; keep the plugin disabled.
- Do not re-review the same commit with a paid bot after trivial push-ups.
- Do not treat `risk:low` as “someone read it.”
- Do not skip review when Bugbot/CodeRabbit are unavailable — run in-session instead.
- Do not skip review coverage just to merge faster. Use **`/review` / in-session / `review-and-ship`** when a hatch is required; skip a full pass on a typo-only one-liner if another hatch already applies. After CI is green and threads are triaged, **merge** the task PR into its base ([AGENTS.md § Merge-when-ready](../../AGENTS.md#merge-when-ready)). `reviewed:agent` still requires the `<!-- in-session-review -->` comment.

## After review: merge

Review is a skill you run when the diff warrants it, not a hand-off that leaves the PR open. When required CI is green, threads are triaged, and a coverage hatch is on the record (when required), the authoring agent merges into the PR's base unless a human-gate exception in AGENTS.md applies (including PRs into `main`).
