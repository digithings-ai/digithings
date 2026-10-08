# Code review policy (digithings-ai org)

Canonical for **digithings**, **twelve-x**, and any other digithings-ai repo. Apply in Cursor, Claude Code, Copilot, and similar coding agents. Do **not** invent a custom review skill — use existing repo commands and built-in review agents/skills.

## Default: in-session review

Prefer **in-session** review on a **fresh-context subagent** (author session must not review its own diff):

| Tooling | How |
|---------|-----|
| digithings (Claude) | `/review <N>` — see `agents/sources/commands/review.md` |
| digithings / Cursor | Same `/review` path (or equivalent fresh-context subagent). Optional: Bugbot / security-review when they fit. **Not** the CodeRabbit Cursor plugin `code-review` / `code-reviewer` skills. |
| twelve-x / other org repos | Same idea: fresh subagent + findings posted on the PR |

Post findings on the record (PR comment). digithings requires `<!-- in-session-review -->` + `reviewed:agent` for the coverage gate. The merge queue is a second, separate gate on the comment — see [Posted verdicts](#posted-verdicts-merge-queue-gate).

## Posted verdicts (merge-queue gate)

A verdict can be delivered as a **PR comment**. The merge queue reads one field, and only inside an HTML marker comment — never the prose ([`scripts/merge_queue.py`](../../scripts/merge_queue.py), DIG-2253 / PR #5268):

```html
<!-- opencode-power-pack:code-review verdict=approved scope=@<full-40-char-sha> -->
```

Post that marker in a comment of its own. Do not paste this block into a comment to show someone the syntax — the parser reads the raw comment, so a quoted example is a live verdict.

| Field | Effect |
|-------|--------|
| `verdict=` **inside the marker** | `changes_requested` and `changes_needed` **block** the merge. `approved` and `approve` do not block. |
| `scope=` inside the marker | Carries the reviewed commit as `@<full-40-char-lowercase-sha>`. |
| Everything outside the marker | Ignored. |

- **Only fields inside the marker count.** `## Verdict: changes requested` in the body is prose, and so is the marker with its `<!--` `-->` stripped or escaped. The queue reads all three as *no verdict*, not as a block.
- **A fence does not hide the marker.** The `<!--` `-->` are read from the raw comment, so a marker inside a code fence, an indented block, or inline backticks still posts a live verdict — and a fenced example of an *approval* clears a live block.
- **Spelling.** `_normalise_verdict()` lowercases and turns `-` into `_`, so `changes-requested` is the same as `changes_requested`. It does not collapse spaces, so `verdict=changes requested` is not readable. Any other spelling is ignored.
- **A missing or misspelled `verdict=` neither blocks nor clears.** The comment is skipped, so an earlier blocking verdict still stands.
- **`scope=` must carry a full 40-character lowercase sha.** `_on_pr_history()` applies a blocking verdict only while that sha is the PR head or still in the PR's commits, and it compares the whole string, so a 7-character prefix is read and then never matches. A blocking verdict with no sha, with an uppercase sha, or with a sha that a force-push or rebase removed silently stops applying. Post a new verdict after the fix.
- **The newest readable verdict wins.** A later `verdict=approved` clears an earlier block. The parser filters on no author and no association, so anyone who can comment on the PR can clear it — an approved marker is not evidence that a review happened. Check the comment thread before you merge.

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
- Do not skip review coverage just to merge faster. Use **`/review` / in-session / `review-and-ship`** when a hatch is required; skip a full pass on a typo-only one-liner if another hatch already applies. After CI is green and threads are triaged, **merge** the task PR into its base ([AGENTS.md § Merge-when-ready](../../AGENTS.md#merge-when-ready)). `reviewed:agent` still requires the `<!-- in-session-review -->` comment. A posted `verdict=` blocks the merge until a newer readable verdict clears it — see [Posted verdicts](#posted-verdicts-merge-queue-gate).

## After review: merge

Review is a skill you run when the diff warrants it, not a hand-off that leaves the PR open. When required CI is green, threads are triaged, and a coverage hatch is on the record (when required), the authoring agent merges into the PR's base unless a human-gate exception in AGENTS.md applies (including PRs into `main`).
