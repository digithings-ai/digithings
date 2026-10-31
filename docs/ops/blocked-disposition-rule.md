# Before you go idle: a block carries a disposition

Status: rule, 26 Oct 2026 (DIG-5595). Applies to every seat on every run.
Check: `kit/bin/dt-blocked-disposition-check` (exit 1 above 10; `--json` for reports). It reads
clauses 1 and 2 only: a block held open by a question card alone still reads as `NAKED`, because
the checker does not yet read interactions.

## The rule

`blocked` is not a place to park work. It is a wait, and every wait names who ends it.
Before a run ends, if its issue is `blocked` it carries **exactly one** of:

1. an unresolved `blockedBy` edge to a live issue, or
2. an `unblockDescriptor` with an owner and the exact step that ends the wait, or
3. an open question card or decision.

A comment is not a disposition. "Waiting on X" in prose is invisible to the queue: the
issue cannot be woken, and the watchdog retries it every tick and is refused every tick.

## What each clause exists to stop

| Clause | Evidence, week to 26 Oct 2026 |
|---|---|
| A comment is not a disposition | 3,730 `blocked_no_blockers` wake refusals in 7 days, 27% of the 13,701-row journal; 190 distinct issues were refused at least once. |
| Do not manufacture a descriptor to silence the check | The check reads `unblockDescriptor` as a disposition. A false wait stops the queue asking, which is worse than a naked block. |
| An edge to a finished issue is not a disposition | The server refuses `blocked` -> `todo` while any edge exists, including one to a `done` issue: DIG-4731 answered 409 "follow-up blocked by unresolved blockers" for an edge to DIG-4729 (done 24 Oct). Clear the dead edge first. |
| Terminal-run recovery is not a disposition | `server/src/services/execution-recovery-resolution.ts` sets `status: "blocked", executionRunId: null, checkoutRunId: null` and never sets `unblockDescriptor`. Measured live on 26 Oct between 08:36 and 08:38: DIG-4990 (`legacy_execution_requires_reconciliation`, run `dd9a92cb`), DIG-5585 (same cause, run `5d06e12f`, blocked 15 minutes after the Code Reviewer approved its PR), DIG-2915 (blocked after its owner opened human-only card `e13ec82c`). Root-cause tickets: DIG-4865 (recovery re-blocks a finished state), DIG-1648 (board-owned recovery actions resolve by no path). |
| A routine execution issue is not a work item | Six of the fourteen naked issues on 26 Oct were dead routine ticks from 21-23 Oct, each superseded by a later tick (DIG-5367, 5370, 5376, 4827, 4832, 5382). Cancelling them with a reason removed them from the class permanently. |
| An alert ticket whose subject is finished is finished | DIG-5475 alerted on DIG-5463; DIG-5463 was `done` on 24 Oct and no repeat arrived, yet the alert stayed `blocked` for two more days. |
| A board-owned recovery action cannot be fixed by a seat | DIG-5131 and DIG-5235 carried an active `stranded_assigned_issue` action with `ownerAgentId: null` until the CTO's writes on 26 Oct gave each an open blocker edge and a descriptor, which left the action stale and the server cancelled it (DIG-5235 at 18:03Z, DIG-5131 at 18:12Z). Every seat PATCH answers 403 "Agent cannot resolve another owner's recovery action"; `unblockDescriptor` is refused the same way, and an agent may only name itself as a descriptor owner. The manager holding checkout override must clear it (DIG-1648). |

## Why the count is the metric

The count is not bookkeeping: it is the input to the journal volume. Each naked issue is
re-attempted every tick, refused (daily cap, org-eff #4), and journalled by
`log_wake_withheld`. The re-log is a symptom with a floor: it stops when the class empties.

### The re-log half, measured

A refusal row is not one row per refusal. Counted over the full days 19-25 Oct 2026, all
classes, the journal holds 7,597 `wake withheld` / `retry withheld` rows:

| reason | rows | issue-days | share of rows |
|---|---|---|---|
| 2/day unblock/reopen cap spent | 6,384 | 509 | 84% |
| concurrency cap (12 running) | 554 | 449 | 7% |
| circuit breaker | 67 | 8 | 1% |
| start budget, Go crew, rest | 221 | 124 | 3% |
| transient (backoff, paused seat, no-wake) | 371 | 14 | 5% |

The first line is a cap that resets at the next UTC day. Hour 3 through hour 23 of the same
issue repeat hour 1 exactly, so those rows carry no information the first row did not. That
line is itself two sections, and the split matters:

| section | rows | issue-days |
|---|---|---|
| `blocked_no_blockers` | 3,258 | 256 |
| `ops_gate` (the gate refusal row) | 3,126 | 253 |

`kit` `d58b78e` journals a refusal whose reason is a spent daily cap (the 2/day unblock cap,
the daily retry cap) **once per issue per day** instead of once per issue per hour. The first
refusal of each day is still written, with a count of the refusals it suppressed, so a trapped
issue stays visible at one row per issue-day.

Two limits on that change, both measured:

1. **It covers `log_wake_withheld` only.** The `ops_gate` row is written by `ops_record_block`,
   which kept its own one-row-per-issue-per-hour budget. That half is routed by kit `d3aae13`
   (DIG-5677) under the same daily rule, so the two halves now stand or fall together.
2. **Both are committed, not loaded.** `dt-it-watch` is a long-lived process that loads its code
   at start, so the commit alone changes nothing. Proof it is not yet in effect: DIG-5131 has
   two `blocked_no_blockers` cap rows on 26 Oct after the commit (13:08Z and 13:36Z), which a
   once-per-issue-per-day rule cannot write. The deployment step is a restart of the watcher,
   and it was not taken from this issue.

So the honest projection, not a measured outcome: with both halves live the cap side of that
week is about 509 rows, one per section-day (256 `blocked_no_blockers` + 253 `ops_gate`), still
above the 500-row target. The target therefore needs the deployment and fewer refused
section-days: 509 section-days a week is 73 a day, and the target allows about 71. The
concurrency cap keeps the hourly cadence on purpose, because its next hour is new information;
its measured overhead is only 1.23 rows per issue-day, so it is not the next lever.

One floor stays and it is deliberate: a naked issue is still re-attempted every tick and
refused every tick, because the refusal must not stamp the issue (DIG-2204). Only the journal
row is downsampled. The repair for a naked issue is still a disposition, not a quieter log.

## Repair order when the count is over the limit

1. **Dead routine ticks and finished alert tickets** — cancel with a reason. Cheapest, and
   they never come back.
2. **Work that is ready** — set `todo`. Nothing is waiting on it; terminal recovery merely
   left it blocked.
3. **Work with a real precondition** — add the edge (for example both Cursor-consultant
   issues wait on DIG-5458, the monthly cap).
4. **Work only Chris can finish** — an `unblockDescriptor` naming him and the exact step.
5. **Board-owned recovery actions** — hand to the manager who holds checkout override.

## Outcome this rule is measured against

At most 10 issues blocked with no blocker edge and no disposition, and under 500 wake
refusal rows a week (DIG-5595). On 26 Oct 2026 the company read 125 blocked and 5 with no
live disposition at 12:16 UTC, and 126 blocked and none at 18:17 UTC. The last two members
left the class when the CTO, in one write per issue, gave each an open blocker edge to
`DIG-5458` and a CTO-owned descriptor: `DIG-5235` at 18:03 UTC and `DIG-5131` at 18:12 UTC.
Each board-owned recovery action was then cancelled as stale when the issue gained a
first-class blocker (18:03:26Z and 18:12:03Z). The row half is not yet measured: the cadence
change is committed but not deployed, as the section above records.
