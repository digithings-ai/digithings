# The develop merge queue

This document is the merge path for `develop`. It answers three questions:

1. **Who merges.** The CTO and the Engineering Manager. Nobody else.
2. **What may be merged.** A PR that has passed the required checks and carries a
   review from the review path.
3. **Where the queue lives.** In `scripts/merge_queue.py`, in this order, oldest
   first.

If you are here because you need a merge and you do not want to open a card asking for
permission: you do not need one. Run the queue.

## Scope: `develop` merges, and how this meets AGENTS.md

This document governs **merges whose base is `develop`**, in every repo of this org. It
does not govern merges into a stacked `module/<component>` base, and it does not govern
promotions into `main` — for those, [AGENTS.md § Merge-when-ready](../AGENTS.md#merge-when-ready)
still tells the authoring agent to merge its own task PR, and still applies its
"still stop and ask" list.

`AGENTS.md` is the file every adapter loads as canonical rules, and its
[Merge-when-ready](../AGENTS.md#merge-when-ready) section predates this queue. It has
carried the same rule in prose ever since: **when a task PR is merge-ready, merge it.**
Left alone that sentence and the roster below are a direct contradiction — one tells
DevOps to run `gh pr merge` on a `develop` PR, the other refuses that same agent with
exit 2 — and an agent picking the wrong one fails silently either way. So
`AGENTS.md` § Merge-when-ready now carries this roster and points at `merge_queue.py`
for `develop` bases, and this document is the authority on what that queue requires.
Both files agree; neither needs to be read with the other in mind.

---

## The problem this solves

Every merge into a protected branch was becoming a decision. Someone opened a card, a
human decided, the decision got written down, and the branch sat still until then. That
put a person in the path of routine work for no reason other than the absence of a
defined path.

A merge queue turns "should this land?" into "is this landable?". The second question has
an answer that can be computed, so it does not need a human.

---

## Who merges

| Role | Key | In `digithings-ai` |
|---|---|---|
| CTO | `cto` | `chrizefan` |
| Engineering Manager | `em` | `chrizefan` |
| QA | — | **reviews, does not merge** |

`scripts/merge_queue_policy.json` is the machine-readable roster. QA reviews. QA does not
merge — a reviewer cannot be the one who signs off on their own pass, and the CEO's
instruction was that the EM and the CTO are the merge path. The same table is in
[AGENTS.md § `develop` merges go through the merge queue](../AGENTS.md#develop-merges-go-through-the-merge-queue),
so an agent that only ever loads `AGENTS.md` still learns who merges.

**One GitHub login, two roles.** Both authorities merge with the same org credential, so
GitHub records the same committer for either. The role is an *assertion*, not something
GitHub can verify: pass it with `--acting-role`, and the queue writes it into the audit
comment on the PR so the record names who acted. Adding a role to the roster is a policy
change and needs the CEO — it is not something an agent does on its own initiative.

A review cannot be asserted the same way. `--attest-review <role>` was removed on
2026-10-17: with one login, no agent can give a non-author approval, so the old review gate
could only be met by an attestation, and the launchd wrapper stamped `qa` on every merge
without QA doing anything. PRs #5489 and #5277 had already shown the cost (merged attested
with zero reviews and zero comments). The review that counts is an artifact on the PR: a
review pass by the board's reviewer seats that left its findings there, with those comments
resolved or addressed (Chris's 2026-10-15 definition). No formal approval is required. QA is
not in the review path, and a `qa/gate` commit status is ignored in both directions.

## What may be merged

`scripts/merge_queue.py` refuses a PR unless all of the following hold.

| Gate | Rule |
|---|---|
| Base branch | `develop` only. `main`, `master` and `release/*` are refused (exit 3), and a PR whose `baseRefName` is anything else is refused too. |
| Required check | The names in `required_checks_by_repo` for this repo must each have **reported** and concluded `SUCCESS`. Both repos currently require `local-ci`: `digithings` because its branch protection names it, and `twelve-x` since 2026-10-19 because its Actions job `test` cannot start while billing is blocked (DIG-4454). `local-ci` arrives as a commit StatusContext, never as a workflow run, so the names in `status_context_checks` are exempt from the workflow-run evidence rule (DIG-3707) — see the cost stated below. |
| CI provenance | The newest `local-ci` status on the head must name a Woodpecker build, and the queue must read that build back from the Woodpecker API: the same repo, the same commit sha, and the repo's own check step concluded `success`. A `local-ci` status without that URL, or whose build does not verify, is not a pass. Ships in **shadow** mode — see the section below. |
| Other checks | Any other check in a failing conclusion blocks the merge. |
| Mergeable | `mergeable == MERGEABLE`. Drafts and `CONFLICTING` do not queue. |
| Up to date | `mergeStateStatus` must be `CLEAN`. `BEHIND`, `DIRTY`, `UNKNOWN` and `BLOCKED` do not queue. `BEHIND` is the one stale state a `run` clears by itself — see the stale-branch rule below — so it is not left for a human. |
| Review | No outstanding `CHANGES_REQUESTED` review, and the **newest** readable review verdict is an approve that names the head the PR stands at. A verdict is read from the `opencode-power-pack:code-review` marker or from a `Review verdict:` line, whichever is newer; the marker wins inside one comment. Review *evidence* is the row below: the non-author approval demand was **retired on 2026-10-18** (every seat pushes under one GitHub login, so GitHub refuses a self-approval), and `--attest-review` is **removed** — the queue no longer reads an attestation in place of evidence. |
| Review coverage | The same evidence `scripts/check_review_coverage.py` enforces at promotion: a completed Bugbot run, a reviewer bot (CodeRabbit, Copilot, Claude, …), an in-session review with its findings comment (`reviewed:agent` plus the marker comment), an approval, or `reviewed:owner`. |
| Reviewer independence | A review marker counts only if it names the head the PR stands at now **and** comes from a seat that did not write the PR's code. The last marker on the PR is the one judged: an earlier marker does not rescue a failing one. A marker from an authoring seat, or that seat's own marker posted while its own run was still active, is dropped — the PR then waits for a review from another seat. See [Reviewer independence](#reviewer-independence). |
| Review comments addressed | No review thread on the current code may be open: each must be resolved, or outdated by a later commit. An unreadable thread list holds the PR. |
| Change requests | A `CHANGES_REQUESTED` review decision, or a posted code-review verdict of `changes_requested`, blocks **whatever it is scoped to**. Only a later approve clears it, and only an approve that names the head the PR stands at — a new commit, a rebase or a merge from `develop` does not spend a block (DIG-4878). |
| Ignored | `qa/gate` commit statuses: neither a pass nor a block. |

Three of these are deliberate choices worth stating plainly.

**An unreadable review record is not a clearance.** The verdict gate reads the PR's
comments, so the row it is handed must carry them. The host tick is what fetches rows,
so its `gh pr list --json` field list must include `comments` and `commits`; `fetch_queue`
already does. If the key is absent the row is completed by one `gh pr view --json comments`
*before* both review gates run: the coverage gate's own lazy fetch comes too late, because
it runs after the verdict gate and so cannot repair a row the verdict gate has already read
as verdict-free. If even that is impossible — no repo to read from, or a read that failed —
the PR is refused, not queued. This is the sentence `_marker_verdict` already applies to a
marker it cannot parse, one level up: *a missing signal, not a clearance.* `#5903` merged on
2026-10-19 08:23 with four review passes on it and the newest a `changes_requested`, because
its row arrived without comments — the coverage gate authorised the merge, and the queue's
own audit comment names that gate.

**A verdict is not spent by the branch moving.** The verdict gate reads the newest verdict
on the PR and asks whether that verdict clears the head the PR stands at. It does not ask
whether the commit the verdict named is still on the branch. That was the rule until
2026-10-21, and it was the hole: the block was retired the moment a new commit, a rebase or
a merge from `develop` rewrote the branch's commit list, and the coverage gate then carried
the PR to a merge on a `reviewed:agent` label. Six `digithings` PRs merged that way between
2026-10-20 and 2026-10-21 (`#6115`, `#6074`, `#6071`, `#6019`, `#5968`, `#5761`). A
blocking verdict now stands until a later approve names the head it covers, and a `reviewed:agent`
label cannot carry a PR past it. See the gate table above and `docs/agents/CODE_REVIEW_POLICY.md`.

**`NEUTRAL` and `SKIPPED` fail a required check.** A required check that reports nothing
is indistinguishable from a check that was never asked to run — which is exactly the hole
being closed. This has a real cost: Bugbot reports `neutral` when it is out of quota, so a
required Bugbot check would block merges indefinitely. Do not put a metered third-party
service on the required list. See `reviews/archive/CODE_REVIEW_BASELINE.md`.

**A green commit status is not a passing build — except where the alternative is no gate at
all.** GitHub's commit status docs are explicit that "any person or integration with write
permissions can set the state of any status check". So a required check normally only
satisfies the gate if it arrived as a *check run* — one bound to an Actions workflow — not as
a bare status anyone with write access can type.

Two names are exempt, and the exemptions are not free. `digithings` requires `local-ci`,
posted by the host mirror rather than by a workflow, so the exemption is what makes the queue
work there at all (DIG-3707). Since 2026-10-19 `twelve-x` requires the same name for a
different reason: its only Actions job (`test`) cannot start while the org's billing is
blocked (DIG-4454), so a commit status is the only verdict that can exist. The cost is real —
**any write token can post `local-ci: success`, and `twelve-x` has no branch protection behind
the queue**, so on that repo the queue is the only gate. What still stands between a forged
status and an unreviewed merge is the review row: a status clears the check gate but not
review coverage. The exemption is time-boxed — revert `twelve-x` to `test` when the minutes
reset.

### The `local-ci` provenance gate (DIG-4794)

The exemption above leaves one hole: `local-ci` is a commit status, so any writer with a
token can type `success` into it. On `twelve-x`, where the queue is the only gate, that is
the difference between a build and a claim. The provenance gate closes it by asking a
question the status itself cannot answer: **which build is this?**

The newest `local-ci` status on the PR head must carry a `target_url` that names a
Woodpecker build. The queue then reads that build back from the Woodpecker API, read-only,
and requires all of the following:

| Requirement | What it proves |
|---|---|
| A `local-ci` status on the head, and it is the newest one | the receipt belongs to this commit, not to an older one |
| A `target_url` is present and absolute | the status names a build at all |
| The host is in `ci_provenance.hosts` | the build lives on the Woodpecker we run, not on a page anybody controls |
| The path is a pipeline link (`/repos/<id>/pipeline/<n>`, `/api/repos/<id>/pipelines/<n>`, `/repo/<owner>/<name>/pipelines/<n>`) | the URL points at one build, not at an arbitrary page |
| The build is in the Woodpecker repo the policy maps this GitHub repo to | the build is ours |
| The API answers `200` for that pipeline | the build exists |
| The build has finished (its status is not `created`, `pending`, `running`, `started`, `waiting`, `blocked` or `skipped`) | the verdict is a verdict |
| The step the policy maps this repo to (`digithings-check`, `twelve-x-check`) is `success`, and it appears exactly once in the build | the build ran *this* repo's checks |
| The build reports a `commit`, the PR head has a sha, and the two are equal | the build is about this code |

Any one of them missing is a refusal with a named reason: the queue logs which one.

The pipeline's **overall** status is deliberately not decisive. The launcher pipeline runs
the two repos' checks side by side, so a failure in `twelve-x-check` must not refuse a
`digithings` PR. The per-repo step is what decides; the pipeline status only says whether
the run is over.

The gate reads a token from `WOODPECKER_TOKEN` if it is in the environment, else from the
`token_file` the policy names (a `KEY=value` file; only the named key is read, and the
value is never logged). Without a token the build cannot be read, and that is itself a
refusal with a reason — a missing token is not a pass. The launchd job's environment
carries only `HOME` and `PATH`, so **no** `WOODPECKER_TOKEN` and no `MQ_CI_PROVENANCE`
reach it today: `token_file` is where the queue finds the token, and changing the mode on
the running host means editing `com.digithings.merge-queue.plist` and reloading the launchd
job. That is a DevOps or Chris action, not a seat's.

`ci_provenance.hosts` is a **deployment address**, not a rule. It lists the Woodpecker as
this Mac serves it today, including the LAN address the DHCP lease handed out, because
`CI_PIPELINE_URL` carries whatever host the Woodpecker was told about. A change of local
IP means a change of that list, and the shadow log names the host it saw when it happens.

Those addresses are plain HTTP on the LAN. The evidence channel is therefore only as
trustworthy as the LAN: anything able to answer on that address could serve a green
build that never ran. A TLS endpoint for the Woodpecker is the fix, and it is a deploy
change outside this change — but the gate does not pretend the risk is not there.

Three modes, in `ci_provenance.mode`, and `MQ_CI_PROVENANCE` in the environment overrides
the file:

- `off` — the gate reads nothing and refuses nothing.
- `shadow` — the gate verifies as above and **logs** what it would have refused, on stderr
  and in `~/.config/digithings/merge-queue/ci-provenance.log` (override with
  `MQ_CI_PROVENANCE_LOG`). Each line reads
  `<UTC timestamp> CI provenance (shadow): PR #<n> <repo> — would refuse '<check>': <reason>`,
  the file is written `0600` and is rotated at 1 MB. The PR is still merged.
- `enforce` — a refusal is a refusal.

An unrecognised `MQ_CI_PROVENANCE` value is treated as `enforce`: the switch fails closed.
An unrecognised `mode` **in the policy file** is a different thing: the file is read once
per tick, so a typo there aborts the tick loudly rather than failing closed, and the
traceback lands in the job's error log. A `ci_provenance` block with no `mode` means
`shadow`, and no `ci_provenance` block at all means `off`, so an older policy file stays
loadable.

Each read has a timeout — 2 s in shadow, 5 s in enforce — and the queue reads at most one
build per pull request per tick, with the reads and the token cached for the life of the
process. The launchd job fires every 180 s and holds a lock, so a Woodpecker that does not
answer must not be able to outlast the interval: that is the reason for the short timeouts.

**It ships in `shadow`, and that is honest, not a setting to forget.** Woodpecker binds a
pipeline to the commit it checked out, and the launcher pipeline today is the cron run of
the launcher repo itself — its `commit` is the launcher's own sha, never a PR head. So the
"same commit sha" requirement cannot pass for any PR until the CI runs **one build per PR
head**. Until then, enforcing would refuse every PR in the org. The shadow log is how that
is measured: if the reasons are all "the build ran another commit", the launcher is the
next thing to change (DIG-4809).

Enforce mode is a separate change, made once the shadow log is clean, and it is not only
a matter of flipping a switch. Three things have to be true first: the CI runs one build
per PR head, the worker image is rebuilt and pullable, and the launcher's lock-skip path
stops reporting a skipped check as a success (below).

Three more limits, stated so nobody reads more into the gate than it is:

- The host runner (the launchd host run, currently disabled for `twelve-x`) has no
  Woodpecker build, so it posts `local-ci` with **no** `target_url`. The queue refuses it
  and names the missing build. A host run is not a build and is not treated as one.
- The Woodpecker agent currently cannot pull the `local-ci-worker` image, so the launcher
  pipeline fails before any check runs. That is a separate fault and is reported on the
  issue, not fixed here. The image also bakes the worker in, so a rebuilt image is needed
  before a status carries a build URL.
- The launcher takes a lock so that one check runs at a time, and the step that loses the
  lock **exits 0**, which Woodpecker records as `success`. A build in which the check never
  ran therefore looks green to this gate. Fixing that is a launcher change in digiforge
  and it is required before enforce mode is switched on; until then, a `success` step means
  "the step did not fail", not "the check ran".

**Required check names are per repo, and a name that matches nothing is called out
separately.** The two repos in this org report different names for the same idea:
`twelve-x` runs one job called `test`, while `digithings` drives every suite through
reusable workflows, so GitHub reports `digibase / test`, `digiclaw / test` and ten
more, and names nothing `test` at all. A single global list can therefore only be
right for one of them — and when it is wrong it is *silently* wrong, because an
unmatched required name produces `required check 'test' has not reported`, which is
byte-identical to the message for an untested PR. That is exactly how DIG-690 blocked
all 28 open `digithings` PRs with a gate that could never pass and no way to tell it
apart from CI being broken.

So `required_checks_by_repo` carries the real names, an unlisted repo falls back to
`defaults.required_checks` (never to nothing — a queue that stops checking is worse
than one that refuses), and `list`/`run` additionally compare the required names
against everything the queue *did* report. A name absent from **every** open PR while
other checks did report is announced on stderr as a misconfiguration, naming the gate
that cannot match, what CI is really reporting, and the file to edit. It is compared
against the union rather than per PR, so the legitimate path-filtered case — one
Python-only PR with no `digichat / test` — stays quiet. **It only ever warns; it never
unblocks.** A gate that cannot match must still block.

**A bot's approval is not a review.** `coderabbitai[bot]` approving a PR means a linter
found nothing to complain about, not that a person owns the change. GitHub's own review
summary ignores bot reviews for the same reason, so the queue does too.

**A PR behind its base does not queue.** After PR #1 lands, PR #2's checks have not
re-run — its green `test` is from the run against the *previous* base, and GitHub reports
it `MERGEABLE + BEHIND`. Merging on that evidence is precisely what a merge queue exists to
prevent, and nothing in the check rollup reveals it. This is what the ruleset path calls
`strict_required_status_checks_policy`; a local queue has to enforce it itself. It also
means each merge in a batch has to wait for the next PR's CI, which is the cost of doing
it correctly. `run` re-reads the queue after every merge for the same reason: a verdict
computed before a merge is stale the moment that merge lands.

**A stale branch is updated, not dead-ended.** Refusing `BEHIND` is only half the rule, and
the other half is easy to miss: this queue's own merge is what puts every other PR behind.
With no step that clears it, the queue drains exactly one PR and then stops on a state
nothing in it can fix — measured on `digithings` on 2026-10-19, a single merge left 23 PRs
blocked, and one of them had to be brought up to date by hand before it could queue again.
So each `run` brings **one** stale branch up to date: the oldest PR whose *only* remaining
reason is `BEHIND`. Never more than one by default, because a merge moves the base for every
other PR, so updating a whole stale set at once queues CI runs the next merge invalidates.
Never a PR with any other reason, because an update spends a full CI run and would not make
it queueable. `--max-updates N` raises the cap and `--max-updates 0` disables the step;
`list` names the candidates and changes nothing. Like the merge, the update is pinned to the
head SHA the gates were read from, so it is never applied to a branch that moved underneath
the verdict — and the PR is re-evaluated on a later tick, never merged on the read that
prompted the update.

**Order is FIFO, not greenest-first.** Sorting by check status turns a queue into a race
that the loudest PR wins. Oldest-eligible-first is the only ordering that is fair and only
one that is easy to explain to whoever has been waiting.

**A vendor-content gate failure is not an emergency, and it is not overridable.** The
`Vendor-content gate` job runs on every PR — `push` to `develop` and `main`, and every
`pull_request` base — and it fails closed. A red gate means the change publishes something
the vendor-content boundary forbids: a method-shaped step (naming the browser route to a
credential, or the act of reading it out), or a vendor identifier that is new since the
merge base with `main`. Do not add the finding to the allowlist to get a merge through, do
not mark it flaky and retry, and do not merge past it. Fix the change, or raise it on the
issue. If the gate reports that it cannot find the merge base, that is the workflow's
`actions/checkout` `fetch-depth: 0`, not a content verdict — it still fails closed, and it
still blocks. The rules and the approved allowlist are in
[`VENDOR_CONTENT_BOUNDARY.md`](VENDOR_CONTENT_BOUNDARY.md).

### Reviewer independence

A review marker is a claim, and a claim can be self-issued. Two things must hold
before a marker counts as review coverage, and the merge queue checks both in one
gate (`scripts/merge_queue.py`, `_review_coverage`):

1. **The marker names the head.** A marker that reviewed an older head says
   nothing about the code the PR stands at now. Measured on
   `digithings-ai/digithings` PR #5994 on 2026-10-21: the only marker on the PR was
   a `changes requested` verdict naming head `22d4b3126`, while the head was
   `15414f011d` — a stale verdict, on a stale head, counting as coverage.
   The sha is compared as a **prefix** of the head, not at one fixed width: the
   QA Lead's census of the open develop PRs on 2026-10-21 found markers naming
   the head as 7, 8, 12 and 40 characters, and a check that wanted exactly 12
   would read a valid 7-character marker as naming nothing at all. Fewer than
   7 characters binds no head.
2. **The marker comes from another seat.** The seat that *wrote the PR's code*
   cannot be the seat whose review counts: not through its own comment, and not
   through a subagent or same-session review it posted while its own run on that
   ticket was still active. **Ownership is not authorship.** The seat a ticket is
   assigned to is the seat asked to move the ticket along, not the seat that
   wrote the code, and a reviewer that owns the ticket still reviews — reading
   the assignee as the author refused the review of the very seat that owns the
   ticket (the QA Lead's finding on #6145, 21 Oct 2026).

**This gate is not the value gate.** The question here is *who* reviewed, not *which
way* the review went. Whether the newest verdict blocks is the verdict gate's
question (`_verdict_value_reason`), and it runs first: PR #5994 above is refused by the
verdict gate before this gate is reached (DIG-4878). The two gates stay apart on purpose —
this one is about provenance, that one about the verdict.

**Who wrote the code.** The author is read from the branch, not from the ticket
header:

* the seat the commits declare — `Paperclip-Agent-Id: <uuid>` in a commit body,
  and `Paperclip-Run-Id: <uuid>` resolved through the Paperclip API to the seat
  that owned that run;
* the seat whose run **on the PR's own ticket** was open when the PR's commits
  were **written** — the commit's **author date**, which a rebase preserves. A
  run that was about a different ticket says nothing about who wrote this PR —
  the reviewer that works from its own review ticket is not the author of the PR
  it reviews;
* a merge commit is not one of the PR's own commits: merging `develop` into a
  branch is branch maintenance, and the seat that ran the merge did not write the
  code the PR carries.

**The stamp is the author date, never the committer date.** A rebase rewrites
every commit it replays: the author date and the message stay, the committer date
becomes the rebasing seat's. Read from the committer date, the seat that rebased
a branch became the PR's author, the real author's own review counted as coverage
of the PR it wrote, and a rebase that landed outside every run window left the PR
with no author and no way to merge (the QA Lead's finding on #6145, 21 Oct 2026).
So the gate reads `authoredDate`, and a commit that carries no author date is
left out — nothing is guessed from the committer date, which is exactly the date
a rewrite moves.

**The attribution is per commit.** A commit that falls inside exactly one seat's
window was written by that seat, so that seat is an author — a seat that pushed
one commit of a PR is an author even when the other seat pushed more of them.
Only a commit that falls inside several windows is ambiguous, and there the seat
the most commits fall into is the author; a tie leaves both as authors, because
calling a seat an author costs that seat its own coverage and nobody else's.
That is what keeps a reviewer woken on the ticket while the author pushes a fix
a reviewer: it shares the window, it does not have the commit.

Measured on the open develop PRs on 2026-10-21 (30 PRs, 21 of them naming a
ticket): the rule names **exactly one** author seat for 20 of the 21, **no
commit in the whole queue falls inside two windows**, and the seat it names
agrees with the commit trailer wherever a trailer exists — no disagreement, no
ambiguity. The old rule (the ticket's assignee) named the wrong seat whenever
the assignee was not the author: on #6145 the assignee was the Code Reviewer
while the code was written by the Repo, CI & Release Engineer.

Two limits are known and measured, and both are the reason the gate ships in
shadow: 9 of the 31 open develop PRs name no DIG ticket in their title or their
branch (the QA Lead's census on 2026-10-21), so they carry neither run-window
evidence nor a trailer — 6 of the 9 are drafts, and of the 3 that are not,
#6105 carries a trailer while #6096 and #5441 do not, so those two would be
refused as unverifiable once the gate enforces; and one PR (#5964) has a commit
that falls outside every run window, so it has no author either. A PR with no
author evidence at all is refused as **unverifiable** — the gate will not guess,
and it will not fall back to the ticket's assignee. A seat that wrote a commit
outside every window on the ticket is not named by that commit; it is named by
the commits that fell inside one.

**The last marker governs.** The queue has always read the last review marker
on a PR, so the gate judges that one and no other. A stale last marker is a
refusal, not a cue to look further back: the head only moves forward, so an
earlier marker can only ever bind an older head, and the remedy for a stale
last marker has to be a *new* review — posted by another seat — rather than an
older one. Every other marker on the PR is dropped from the coverage evidence
alongside the failing one, so no earlier review stands in for it.

The reviewer declares itself in the comment, next to the marker it already posts:

```html
<!-- in-session-review -->
<!-- digithings-review agent=<paperclip-agent-uuid> run=<paperclip-run-uuid> head=<40-char-head-sha> -->
```

The queue resolves `run` through the Paperclip API (`/api/heartbeat-runs/{run}`) to
the seat that owned the run, and resolves the author seat from the code, as above.
A marker whose declared seat and run disagree, whose run the API does not know,
that carries neither a seat nor a run, or that names a different head, is
**dropped** — dropped, not forgiven: the PR then fails the coverage gate and waits
for a review from another seat. The refusal names the head the queue expected, so
the PR says what it is waiting for.

The author seat's own run window is a **second reason attached to that seat's own
marker**, not a veto on the queue. A review from another seat posted while the
author was still working is that seat's review, and it counts: a window that
refuses other seats refuses every honest review (the QA Lead's finding on #6145,
21 Oct 2026).

A marker the gate could not judge at all is dropped on the same terms. That is
the case when the Paperclip API cannot be read, or when the PR's authoring seat
cannot be identified at all — a PR with no commit trailer and no commit that
falls inside a run on its ticket, for instance. A partial judgement is not a
judgement, so the queue concludes nothing about the marker and refuses the PR,
naming the reason. It refuses only that: a PR covered by Bugbot or by a human
approval still merges, because the marker was never what cleared it.

**What this cannot prove.** Every seat pushes under one GitHub login, so GitHub
cannot tell who typed a comment. The gate checks the marker's *declared*
provenance against the Paperclip record — it cannot check the keystroke. Per-seat
GitHub identity is the other half of the epic (DIG-4803); until it lands, this is
an accountability record like the labels, except that the queue enforces it.

**Rollout.** The gate ships in **shadow** mode (`review_independence.mode` in
`scripts/merge_queue_policy.json`, overridable with `MQ_REVIEW_INDEPENDENCE`;
`off` disables it, an unreadable value fails safe to `enforce`). Shadow measures:
the queue logs what it *would* refuse to
`~/.config/digithings/merge-queue/reviewer-independence.log` and merges anyway.
Enforce drops the markers and refuses. The flip to enforce is a separate small
change, once the shadow log shows the measurement is stable (DIG-4809).

The log is a measurement, not an archive: it rotates at 1 MiB, it is readable by
its owner only (`0600`), and it carries a line only when the measurement
**changes** — one line per PR, not one per tick, so a refused PR does not write
on every run.

## Running it

```bash
# What is waiting, and why anything is not.
python3 scripts/merge_queue.py list --repo digithings-ai/twelve-x --acting-role cto

# Merge the oldest eligible PR. Default is one merge per run.
python3 scripts/merge_queue.py run --repo digithings-ai/twelve-x --acting-role em

# See the plan without touching anything.
python3 scripts/merge_queue.py run --repo digithings-ai/twelve-x --acting-role cto --dry-run
```

`run` re-reads the queue **after every merge**. Merging a PR moves the base, which can
turn the next PR into `CONFLICTING`; re-reading is what makes that visible instead of
sending a stale-base merge. The queue stops and reports when it happens.

`run` also brings stale branches up to date per tick — the oldest PRs whose only
remaining reason is `BEHIND` — for the reason above: a merge is what puts every other PR
behind, and nothing else here can clear that. `--max-updates 0` merges only; `--max-updates N`
allows up to N (the default is 1). Each refreshed branch spends a full CI run, so N is a
budget on CI runs per tick, not a formality: the branches are refreshed oldest first, and
the first refusal stops the batch rather than skipping past the oldest PR. An updated PR is never merged on the same read: its checks have to report
against the new base first, so it queues on a later tick.

Each merge passes `--match-head-commit`, so a push landing between evaluation and merge
aborts the merge rather than landing a commit that was never gated. The queue never passes
`--admin`.

Every merge leaves an audit comment on the PR naming the role, the head SHA, the merge
method, the review basis and the checks that were green. That comment is the answer to
"who merged this and on what authority".

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Merged, or nothing was eligible. |
| 1 | Operational failure — `gh` could not read the queue. |
| 2 | The role you claimed is not on the merge-authority roster. |
| 3 | The base branch is one that needs a human. |

Exit 2 and 3 are refusals with a reason. They are not failures to retry.

## What this does not do

**It cannot stop a direct push to `develop`.** The queue governs the merge path; it does
not gate the branch. Only [branch protection](BRANCH_PROTECTION.md) does that, and see the
next section for why that is currently not available on `twelve-x`.

That is the real limitation, and it is worth being blunt about it: an agent with push
access can still push to `develop` directly, and this queue will not notice.

## Branch protection and the native merge queue: blocked by plan

DIG-506 asked for two things: native branch protection on `develop` with a required `test`
check, and GitHub's own merge queue. Neither is available on `digithings-ai` today.

`digithings-ai` is on the GitHub Free plan with one seat. GitHub's plans page lists
**Protected branches** under the paid org plan's "Advanced tools and insights in private
repositories", not under Free, and the pricing comparison marks *Repository rules*
"Public repositories" on Free and "Public repositories / Private repositories" on Team.

`twelve-x` is private, so both are paid-plan features. The merge queue is a branch
protection setting ("Require merge queue" on the About-protected-branches page), so it is
gated the same way.

Note the naming: GitHub's per-seat paid plan is **GitHub Team**, at **$4/user/month for the
first 12 months**. Older docs and blog posts call it "GitHub Pro" for organizations. The
API's error message says "Upgrade to GitHub Pro", and this doc uses "Pro" when quoting that
message; the plan to actually buy is Team.

The refusal is reproduced by the tooling, not asserted:

Verbatim output, trimmed only where marked:

```console
$ python3 scripts/enable_branch_protection.py status --repo digithings-ai/twelve-x --branch develop
repo:        digithings-ai/twelve-x
visibility:  private
org plan:    free
admin:       yes

BLOCKED: digithings-ai/twelve-x is private and org 'digithings-ai' is on the 'free' plan; branch protection, rulesets and the server-side merge queue all require GitHub Pro for private repositories

Unblocking this is a billing decision, not a config change:
  1. Upgrade the owning org to GitHub Pro. This is the supported route and it
     also unblocks the server-side merge queue for every private repo in the org.
     (The plan GitHub actually sells per seat is 'Team', $4/user/month for the
     first 12 months; 'Pro' is the name in the API's own error message.)
  2. Making the repository public unblocks protection on the Free plan, but it
     publishes the code and the history — never a client repo's decision to take
     here, and never an agent's.
Until one of those happens, use scripts/merge_queue.py: it applies the same gates
on the merge path, under a named merge-authority role, but it cannot stop a
direct push to the branch.

protection on develop: NOT READABLE — gh: Upgrade to GitHub Pro or make this repository public to enable this feature. (HTTP 403)
rulesets: NOT READABLE — gh: Upgrade to GitHub Pro or make this repository public to enable this feature. (HTTP 403)
```

`status` exits 0 here: it succeeded in reporting the gate. Callers that branch on the
exit code must read the `BLOCKED:` line, or use `apply`, which exits 3.

This is a plan limit, not a misconfiguration. The decisive test: the identical API call
succeeds on the **public** `digithings-ai/digithings` and is refused on the private
`digithings-ai/twelve-x`, same org, same token, same admin permission. Visibility and plan
are the only variables. There is no permission, token, or org-setting fix.

### The two real options

1. **Upgrade `digithings-ai` to the paid org plan.** GitHub's per-seat plan is **Team**,
   $4/user/month for the first 12 months — about $4/month at one seat. (The API's 403
   names it "Pro", which is the wording it has always used; `github.com/pricing` no longer
   lists a per-seat Pro tier. Either way the gate is the same: Free orgs get repository
   rules and protected branches on **public repositories only**.) This unblocks branch
   protection, the native merge queue, and rulesets across all three org repos at once.
   This is a billing decision.
2. **Make the repo public.** Not an agent's call, and never a client repo's call. The
   CEO's own boundary for DIG-506 was to come back rather than touch client repo settings.

Until one of those happens, `scripts/merge_queue.py` is the merge path and
`scripts/enable_branch_protection.py` is the unblock script, ready to apply the moment the
plan allows it.

## Apply protection when the plan allows it

```bash
# What is there now, and whether it can be changed.
python3 scripts/enable_branch_protection.py status \
  --repo digithings-ai/twelve-x --branch develop

# Rehearse the exact payloads. Writes nothing.
# This is also what it does today: on a plan-blocked repo it refuses with exit 3
# before printing anything, because there is no payload that would be accepted.
# Run it once the plan allows it to see the payload.
python3 scripts/enable_branch_protection.py apply \
  --repo digithings-ai/twelve-x --branch develop \
  --check test --mode ruleset --merge-queue --dry-run

# Apply.
python3 scripts/enable_branch_protection.py apply \
  --repo digithings-ai/twelve-x --branch develop \
  --check test --require-approvals 1 --mode ruleset --merge-queue
```

Rulesets are created with `POST` and updated with `PUT` to the ruleset's own id, looked up
by name — GitHub has no upsert, and a `POST` per run would stack up same-named rulesets
whose combined effect nobody could reason about.

Applying never *reduces* protection. The check list is a union of `--check` and whatever
the branch already requires, so naming one check on a branch that requires three keeps all
three. `--replace-checks` opts out and is the only way to drop one.

`--mode ruleset` is required for `--merge-queue`: classic branch protection has no
merge-queue field, so the ask would be silently dropped rather than refused. The script
refuses that combination instead.

`--check` is mandatory. A branch with no required check looks protected and enforces
nothing, which is worse than an unprotected branch because it is believed.

## Repo survey

The CEO asked whether the same gap exists elsewhere. It does — on every private repo in
both orgs. Only the public `digithings-ai/digithings` has protection, and it has it
precisely because public repos are not Pro-gated.

| Repo | Visibility | Default branch | Protection | Rulesets |
|---|---|---|---|---|
| `digithings-ai/digithings` | public | `develop` | **yes** — 3 required checks, `strict` | 1 |
| `digithings-ai/twelve-x` | private | `develop` | Pro-gated (403) | Pro-gated (403) |
| `digithings-ai/digithings-ops` | private | `main` | Pro-gated (403) | Pro-gated (403) |
| `DataTapStream/datatap-web` | private | `main` | Pro-gated | Pro-gated (403) |
| `DataTapStream/datatap-mcp` | private | `master` | Pro-gated | Pro-gated (403) |
| `DataTapStream/apollo` | private | `master` | Pro-gated | Pro-gated (403) |
| `DataTapStream/gaia` | private | `master` | Pro-gated | Pro-gated (403) |
| `DataTapStream/zeus` | private | `master` | Pro-gated | Pro-gated (403) |

Both orgs are on the Free plan, so a Pro upgrade in one does not cover the other. The
`DataTapStream` repos are client repos: changing their visibility or their billing is a
client conversation, routed through the CSM.

`digithings-ai/digithings` currently has `required_pull_request_reviews: null` — no review
is required on `develop`, only checks. That is a separate gap from the plan limit and can
be closed with `--require-approvals 1` today, since the repo is public.

Regenerate this table with one command per repo:

```bash
python3 scripts/enable_branch_protection.py status --repo OWNER/NAME --branch BRANCH
```

## See also

- [BRANCH_PROTECTION.md](BRANCH_PROTECTION.md) — required checks per branch, why a
  path-filtered required check is a trap, the emergency bypass.
- [VENDOR_CONTENT_BOUNDARY.md](VENDOR_CONTENT_BOUNDARY.md) — the vendor-content boundary:
  the rules the `Vendor-content gate` enforces, and the one reviewed allowlist. A gate
  failure is not to be overridden.
- `scripts/merge_queue_policy.json` — the roster.
- `scripts/merge_queue.py` — the queue.
- `scripts/enable_branch_protection.py` — status and apply.
- [`BRANCHING.md`](../BRANCHING.md) — the branch taxonomy this queue sits on top of.