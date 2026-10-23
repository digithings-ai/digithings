# Code review policy (digithings-ai org)

Canonical for **digithings**, **twelve-x**, and any other digithings-ai repo. Apply in Cursor, Claude Code, Copilot, and similar coding agents. Do **not** invent a custom review skill — use existing repo commands and built-in review agents/skills.

## Review requests go to the Code Reviewer, never to a substitute

A code review request is not a question for the chain. It is a gate issue for the Code Reviewer on the leaf, plus a merge-gate fact. If the Code Reviewer is unavailable, the EM holds the review on the leaf and the requester waits. A review request is **never** re-addressed to a substitute reviewer, and nobody above the Code Reviewer — not the EM, not the CTO, not the CEO — answers a "review PR X" card. (DIG-2408)

## Default: in-session review

Prefer **in-session** review on a **fresh-context subagent** (author session must not review its own diff):

| Tooling | How |
|---------|-----|
| digithings (Claude) | `/review <N>` — see `agents/sources/commands/review.md` |
| digithings / Cursor | Same `/review` path (or equivalent fresh-context subagent). Optional: Bugbot / security-review when they fit. **Not** the CodeRabbit Cursor plugin `code-review` / `code-reviewer` skills. |
| twelve-x / other org repos | Same idea: fresh subagent + findings posted on the PR |

Post findings on the record (PR comment). digithings requires `<!-- in-session-review -->` + `reviewed:agent` for the coverage gate, and a `<!-- digithings-review agent=… run=… head=… -->` provenance marker beside it for the merge queue's reviewer-independence gate and for the seat the verdict belongs to — see [Reviewer independence](#reviewer-independence-merge-queue-gate). The merge queue is a second, separate gate on the comment — see [Posted verdicts](#posted-verdicts-merge-queue-gate).

## Posted verdicts (merge-queue gate)

A verdict can be delivered as a **PR comment**. The merge queue reads two things: the marker below, and a `Review verdict:` line ([`scripts/merge_queue.py`](../../scripts/merge_queue.py), DIG-2253, DIG-4878):

```html
<!-- opencode-power-pack:code-review verdict=approved scope=@<sha> -->
```

Post that marker in a comment of its own. Do not paste this block into a comment to show someone the syntax — the parser reads the raw comment, so a quoted example is a live verdict.

| Field | Effect |
|-------|--------|
| `verdict=` **inside the marker** | `changes_requested` and `changes_needed` **block** the merge. `approved` and `approve` do not block. |
| `scope=` inside the marker | Carries the reviewed commit as `@<sha>`. It is the only head a marker verdict names — see below. |
| A `Review verdict:` line | The same two verdicts, in prose: `changes requested`, `changes needed`, `approved`, `approve`. Bold markers (`**Review verdict: changes requested**`) are read too. |
| Everything outside the marker and the verdict line | Ignored. |

- **Only the marker and the verdict line count.** `## Verdict: changes requested` in the body is prose, and so is the marker with its `<!--` `-->` stripped or escaped. The queue reads those as *no verdict*, not as a block.
- **A fence does not hide the marker.** The `<!--` `-->` are read from the raw comment, so a marker inside a code fence, an indented block, or inline backticks still posts a live verdict — and a fenced example of an *approval* clears a live block.
- **Spelling.** `_normalise_verdict()` lowercases and turns `-` into `_`, so `changes-requested` is the same as `changes_requested`. It does not collapse spaces, so `verdict=changes requested` is not readable. Any other spelling is ignored. In prose, write the verdict in full: `changes requested` or `changes needed`.
- **A missing or misspelled `verdict=` neither blocks nor clears.** The comment is skipped, so an earlier blocking verdict still stands.
- **A block belongs to the seat that posted it.** A `changes_requested` on the current head stands until **that seat** posts a later approve that names the head the PR stands at. Another seat's approve does not clear it, and an approve naming another head clears nothing. The queue reads the seat from the provenance marker's `agent=` field, so post that marker with every verdict — without it the queue cannot tell your block from another seat's and falls back to the newest-verdict rule. `#6170` (DIG-4911) merged on 2026-10-21 with the security desk's `changes requested` on the branch, because the code reviewer's later approve on the head was the newest readable verdict. The ordering rule is written once, in [`docs/MERGE_QUEUE.md`](../MERGE_QUEUE.md#the-verdict-rule) — read it there, not here (DIG-4878).
- **A block is scoped to the head it names.** A verdict is a statement about one commit. A `changes_requested` naming a head the PR has left does not hold the current head, and it does not ask the seat that posted it to review code it never saw (`#6263`: approved at 01:01 on `177278b680f4`, handed back at 01:05 because a block on `a87fc55760e9` still stood). A block naming the current head stands exactly as before, and an old approve still clears nothing — the scope cuts both ways, so it never lets an old verdict vouch for new code. This replaces the DIG-4878 rule ("a block is not spent by the branch moving"); what remains of that concern is the coverage gate, which still requires review evidence on the head.
- **An approve counts only when it names the head the PR stands at.** A marker verdict names the head through its own `scope=`; the provenance marker's `head=` is the fallback for a marker that carries no `scope=`, and it is never a second binding for one that does. A prose verdict names the head through any sha written in the comment, the provenance marker's `head=` included. A binding of 7 characters or more that prefixes the head binds it — post the full sha. An approve that names another head, or names no head at all, clears nothing. So an approve whose `scope=` names a stale commit clears nothing, whatever the provenance marker says (DIG-4878).
- **A `reviewed:agent` label cannot carry a PR past a block.** The verdict gate runs before the coverage gate, so the label never rescues a PR whose newest verdict blocks.
- **The parser filters on no author and no association**, so anyone who can comment on the PR can post a verdict — an approved marker is not evidence that a review happened. Check the comment thread before you merge.

`verdict=` is not emitted by the marker producer yet (DIG-2281). Until it is, the gate only fires on a marker posted by hand — post it in a comment of its own.

## Reviewer independence (merge-queue gate)

A marker is a claim, and a claim can be self-issued. The merge queue counts a
review marker as coverage only when the comment carries a provenance marker of its
own, next to `<!-- in-session-review -->`:

```html
<!-- digithings-review agent=<paperclip-agent-uuid> run=<paperclip-run-uuid> head=<40-char-head-sha> -->
```

The first marker says a review ran; the second says which seat ran it, in which
run, and on which head. Fill the values from the environment
(`PAPERCLIP_AGENT_ID`, `PAPERCLIP_RUN_ID`) and from
`gh pr view <N> --json headRefOid --jq .headRefOid` — never by hand.

| Field | Effect |
|-------|--------|
| `agent=` | The seat that claims the review. The queue resolves the run to the seat that owned it and refuses a marker whose two disagree. |
| `run=` | The Paperclip run the review came from. The queue reads `/api/heartbeat-runs/{run}`; a run the API does not know is refused. |
| `head=` | The head the review covered. It must be the PR's current head; a marker naming an older head is refused. The sha may be written at any length of 7 characters or more and is read as a prefix of the head — post the full sha, but a short one still binds. |

The marker is read only when it **stands alone on its own line** — a list bullet may
carry it and the `<!-- in-session-review -->` marker may sit beside it, but no other
text may share the line — so a comment that quotes the marker to explain it is prose
about the marker, not the claim. Its values are records: a placeholder, a typo or
an example is refused by name and never sent to the API, because a value that is
not a run id has no answer to give and a failed read stops every merge in the queue
(DIG-4809, 21 Oct 2026). A run the API does not know, and a run id the API refuses
outright (a bad address is an answer, not a broken API), are both refusals of the
marker; a run the API knows but that carries no seat is refused too, because the
queue cannot then say who reviewed. A seat id is the same id in any case, so the
queue compares one spelling of it.

Two rules follow:

- **The author's own seat does not count.** The seat that *wrote the PR's code*
  cannot be the seat whose review counts — neither its own comment, nor a
  subagent or same-session review it posted while its own run on that ticket was
  still active. The author is read from the branch (the `Paperclip-Agent-Id:` and
  `Paperclip-Run-Id:` commit trailers, and the runs on the PR's own ticket that
  were open when the commits were written — the commit's author date, which a
  rebase preserves), **not** from the ticket's assignee: owning the ticket is not
  authorship, and a reviewer that owns the ticket still reviews. The author's run
  window is not a veto on other seats — a review from another seat posted while the
  author was still working counts.
- **The head must be the current one.** A verdict on an older head says nothing
  about the code the PR stands at now.

The queue reads the **last** review marker on the PR, and the gate judges that
one and no other. A stale last marker is a refusal, not a cue to look further
back: the head only moves forward, so an earlier marker can only bind an older
head, and the remedy is a new review — by another seat — not an older one.

A marker that breaks either rule is **dropped**, not forgiven: the PR then fails
the coverage gate and waits for a review from another seat, and the refusal names
the head the queue expected. Every other marker on the PR is dropped with it, so
no earlier review stands in for the failing one. A marker the queue could not
judge at all — the Paperclip API could not be read, or the PR's authoring seat
could not be identified from the branch — is dropped on the same terms. The gate
measures in **shadow** mode while it rolls out (DIG-4809); see
[MERGE_QUEUE.md § Reviewer independence](../MERGE_QUEUE.md#reviewer-independence).

This is an **accountability record, not proof**: every seat pushes under one
GitHub login, so GitHub cannot tell who typed a comment. The queue checks the
declared provenance against the Paperclip record — not the keystroke. Per-seat
GitHub identity is DIG-4803.

## Blocking verdicts

Posting the findings is **not** the same as delivering the verdict. A verdict that
blocks approval **must also be submitted as a GitHub review with state
`CHANGES_REQUESTED`**, not only as a comment.

The merge queue reads review state, one marker field, and one line of prose.
`scripts/merge_queue.py` `_gate_review` takes an `APPROVED` review from someone
other than the author as a pass, but blocks on `pr.reviewDecision ==
"CHANGES_REQUESTED"`, on a posted `verdict=` marker, and on a `Review verdict:`
line (see [Posted verdicts](#posted-verdicts-merge-queue-gate)). **A comment
that says "changes requested" in prose blocks too, as long as it says it in the
review rule's own form — `Review verdict: changes requested`.** A comment that
only hints at it ("one finding blocks approval") is still not a verdict.

Submitting the review as `CHANGES_REQUESTED` remains the right thing to do: it
is what a human sees on the PR, and it is the half of the signal that does not
depend on the queue's parser.

The comment is where the evidence lives. The review state is what the gate can
see. **A blocking verdict wants both:**

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

Do **not** hand-author the summary marker, and do not add fields to it. A
hand-written marker with an extra field would not match, and the tool would
`POST` a duplicate summary comment. A new field — `verdict=` included — has to be
added upstream in that `SKILL.md`, not here (DIG-2281). The skill also never
submits a review, so a tool review on its own leaves no verdict the gate can see:
either post a `verdict=` marker in a comment of its own (see
[Posted verdicts](#posted-verdicts-merge-queue-gate)) or submit a
`CHANGES_REQUESTED` review.

The `<!-- digithings-review … -->` provenance marker is **not** this marker and is
not third-party: it is the reviewing seat's own declaration, written on purpose
next to `<!-- in-session-review -->` (see
[Reviewer independence](#reviewer-independence-merge-queue-gate)). Do not carry
provenance by adding fields to the power-pack marker.

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
- Do not skip review coverage just to merge faster. Use **`/review` / in-session / `review-and-ship`** when a hatch is required; skip a full pass on a typo-only one-liner if another hatch already applies. After CI is green and threads are triaged, **merge** the task PR into its base ([AGENTS.md § Merge-when-ready](../../AGENTS.md#merge-when-ready)) — a `develop` base via [the merge queue](../MERGE_QUEUE.md), a stacked base directly. `reviewed:agent` still requires the `<!-- in-session-review -->` comment. A posted `verdict=` blocks the merge until a newer readable verdict clears it — see [Posted verdicts](#posted-verdicts-merge-queue-gate).

## After review: merge

Review is a skill you run when the diff warrants it, not a hand-off that leaves the PR open. When required CI is green, threads are triaged, and a coverage hatch is on the record (when required), the authoring agent merges into the PR's base — unless a human-gate exception in AGENTS.md applies (including PRs into `main`), or the base is `develop`, which goes through [the merge queue](../MERGE_QUEUE.md) instead ([AGENTS.md § `develop` merges go through the merge queue](../../AGENTS.md#develop-merges-go-through-the-merge-queue)).
