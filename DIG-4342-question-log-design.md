# DIG-4342 design: one writer for question-log.csv

CTO decision, 19 Oct 2026. This pins the contract for leaves A, B and C.

## Measured facts (this run)

| Fact | How measured |
|---|---|
| 160 `rung` events in route-log.jsonl, 13-19 Oct | `event=="rung"`, ts >= 2026-10-13 |
| question-log.csv has 10 rows in the same window | `csv.reader`, field 0 in 13-19 Oct |
| dt-decide-poll never writes question-log.csv | read of `kit/bin/dt-decide-poll`, no reference to the file |
| The CSV is written by hand | `decision-making/SKILL.md` step 5, `agents/decider.md` step 3 |
| 252 parsed data rows (19 Oct snapshot), 250 of them accounted for by the field counts below | `csv.reader`, under a 10-column header |
| 10/10 recent rows are `GOOD` | column 4 of the 13-19 Oct rows |
| 595 data rows on 22 Oct, of which exactly 4 break the 10-column schema | `csv.reader`, field counts 8:1, 9:1, 10:591, 11:2 |

The CoS's measurement (DIG-4327) is correct. Coverage is 10/160 = 6%.

Both figures are a 19 Oct snapshot of a window that was still being written, so they
are not the numbers the Monday review uses. The cohort table below reconciles every
number that appears in this document.

## Why the rows that exist are not trustworthy either

Two writers, one file, no enforced schema:

1. **the router** (`dt-decide-poll`) - writes route-log.jsonl, never the CSV;
2. **each rung, by hand** - told to by the skill.

Hand rows are ragged: 118 rows have 8 fields (no `class`, no `source_path`), 89 have
10, **38 have 11**, 3 have 9, 2 have 12. That accounts for 250 of the 252 parsed
rows; the other two did not parse. Under a 10-column header, `row[4]` is
`quality` in one row and something else in another. One row (DIG-1134, 2026-10-06)
carries a 4337-character multi-line run essay in its last field. Two DIG-3395 rows
carry truncated 8-character pseudo-ids instead of a UUID. Several `asking_agent`
values are raw UUIDs instead of names.

On 22 Oct the file holds 595 data rows and exactly 4 rows that break the
10-column schema: DIG-2040 (8 fields), DIG-4835 (9 fields), DIG-2698 and DIG-3816
(11 fields each). All four are dated 19 Oct or later.

So the fix is not "tell seats to log harder". It is **one machine writer**.

## Decision 1: the router is the writer

`dt-decide-poll` is the only component that sees 100% of cards, runs unattended
every 5 minutes, and already records the same lifecycle in route-log.jsonl. Asking
160 rungs a week to remember a CSV line is the defect, not the solution.

New module `kit/bin/dt-qlog.py`, pure functions, imported by `dt-decide-poll` so the
daemon does not grow. dt-decide-poll passes it the card, the issue, the agents map
and the route record.

## Decision 2: write on first sight, complete on disposition

The brief asks for the line at creation, not at resolution. Correct: a
resolution-only writer loses cards that die between ticks and makes the week's
completeness unverifiable until the week closes.

- **first sight** of a pending agent-created `ask_user_questions` /
  `request_confirmation` card: append one row,
  `quality=PENDING`, `outcome=open`.
- **disposition**: rewrite that row's `quality` and `outcome`.

## Decision 3: quality is mechanical, never self-reported

This is the part the "all GOOD" symptom points at. A rung grading its own asker's
card cannot produce a measurement, and a machine writing `GOOD` on every row would
reproduce the same fiction. So the router derives quality from signals it already
has. No model call.

| Router signal | quality |
|---|---|
| `duplicate` (deduped against an open card) | `BAD` |
| `chain_exhausted` (board, no class tag) | `BAD` |
| `chris_only`, **no** `[money]/[scope]/[external]/[security]/[client]` tag | `BAD` (unclassified question) |
| `chris_only` **with** a class tag | `OUT_OF_SCOPE` + class recorded; excluded from the quality denominator |
| retired `expired`/`superseded`/`withdrawn`, never answered | `STALE` |
| answered at rung 0 or 1 (never handed up) | `GOOD` |
| answered only after a hand-up (the card reached rung 2 or later) | `ANSWERABLE` |

`OUT_OF_SCOPE` is a new value. Without it, correctly-escalated money and security
cards pollute the quality rate. The Monday review must exclude it from the
denominator and say so.

### The hand-up rung is 2 (confirmed 22 Oct 2026)

The table above used to read "answered only after >= 1 hand-up". That was ambiguous
and was resolved by measurement, not by taste. In the DIG-4327 vocabulary the
hand-up happens at **rung 2**: a card answered at rung 0 or 1 never left the first
line of the chain, so nobody handed it up.

Implemented as `HANDUP_RUNG = 2` in `kit/bin/dt-qlog.py` (line 94). The rule at
line 135 is `ANSWERABLE if rung >= HANDUP_RUNG else GOOD`, so rung 0 and rung 1 are
both `GOOD` and only a handed-up card (rung 2 or later) is `ANSWERABLE`. Measured
on the 13-19 Oct window: with the threshold at rung 1, 45 of the 49
threshold-dependent cards become `ANSWERABLE` (92 percent), which mirrors `GOOD`
and leaves the metric with no discriminating power. At rung 2 the window yields 4
`ANSWERABLE` cards in the 206-card cohort measured on 22 Oct (DIG-711, DIG-2205,
DIG-3664, DIG-3699); the R&D Engineer measured 5 at 06:55Z, before the writer had
completed every row of the window. Six rows that were wrongly filed as `GOOD`
become `BAD`.

The empty `ANSWERABLE` bucket in the first review was plumbing, not definition:
`dt-decide-poll` deletes a retired card's route entry, so the writer read rung 0
and called it `GOOD`. The writer now recovers the rung from the route log.
Confirmed by the R&D Engineer on [DIG-4355](/DIG/issues/DIG-4355).

The contract has not reached every copy of the code: the docstring at
`kit/bin/dt-qlog.py:28` still says "answered after >= 1 hand-up", the wording this
section replaces. That is kit-side text, and it is on the reopened leaf
[DIG-4353](/DIG/issues/DIG-4353).

## Cohorts and denominators (22 Oct 2026)

One window, several denominators. Every number the Monday review uses is in this
table, so no two documents count the same set twice.

| Number | What it counts | Measured by |
|---|---|---|
| 257 | cards created in the 13-19 Oct window (the API denominator) | R&D Engineer, [DIG-4355](/DIG/issues/DIG-4355) |
| 52 (20 percent) | cards the router never saw: 47 on medium and low priority issues the priority-ordered page could not hold, 3 with no route event, 2 withdrawn or expired inside a tick | R&D Engineer; all 52 issues are closed, so the fix closes the hole for future windows only |
| 205 | of the 257 that carry a question-log row | R&D Engineer |
| 178 | distinct cards with any route-log event in the window (169 `rung` events, 128 `board`, 192 `retired`; 109 of the cards have a `rung` event) | my count, 22 Oct |
| 206 | rows dated in the window, which are 206 distinct interaction ids; this is the cohort I measure quality on, taking the last row per card | my count, 22 Oct |
| 170 | the quality denominator: 206 minus the 36 `OUT_OF_SCOPE` cards | my count, 22 Oct |
| 79 | `ANSWERABLE` (4) plus `BAD` (75), which is 46.5 percent of 170 | my count, 22 Oct |
| 169 | the R&D Engineer's denominator: his 205-card cohort minus its 36 `OUT_OF_SCOPE` cards. One card away from 170 because the writer completes rows between the two measurements | R&D Engineer, 06:55Z |
| 139 | the R&D Engineer's denominator over the route-log-only cohort (178 cards) | R&D Engineer |

169 is also the number of `rung` events in the window. The two 169s are different
sets that happen to be the same size; do not read one as the other.

## Decision 4: idempotence is the property under test

One row per `interaction_id`, forever. The writer reads the ids already in the file
and appends only new ones. A card re-seen across 200 ticks still has one row.

This is why leaf A is lane V: the suite is the deliverable.

## Decision 5: the schema is enforced by construction

Fixed 10 columns, matching the existing header:
`date,source_issue,asking_agent,interaction_id,quality,outcome,confidence,category,class,source_path`

- `csv.writer` with `QUOTE_MINIMAL` - a field containing a comma or newline is
  quoted, which is what the hand-written rows failed to do.
- `asking_agent` resolves the uuid through the agents map the router already loads.
  No raw uuid, no empty.
- `interaction_id` is the full uuid. Never truncated.
- No free text field accepts a newline. The 4337-char essay fails to write rather
  than corrupting the file.

## Decision 6: the hand-written path is removed

The hand-written ask is removed in the same leaf as the writer. A second writer
racing the machine writer on the same file is how the file got ragged. Shipping the
writer without removing the ask leaves two writers and re-creates the defect.

- `kit/skills/decision-making/SKILL.md` step 5 is replaced by "Never hand-write
  question-log.csv. dt-decide-poll is its only writer" (commit `559dfe5`, on kit
  `develop` and `main`).
- `kit/agents/decider.md` item 3 now reads "dt-decide-poll writes question-log.csv
  itself; never hand-write a row". The file is not deleted: that seat is retired
  (DIG-4513, 20 Oct 2026), so it is a template rather than a live seat's
  instructions.

The copy the seats actually load was not covered by either change. See the status
update below.

## Known limitation, to be measured not assumed

dt-decide-poll polls every 5 minutes. A card created **and** resolved between two
ticks is never seen and gets no row. Closing it means hooking the
interaction-create path, a second surface; out of scope here, tracked by the
measurement.

**Measured on 22 Oct (leaf C, [DIG-4355](/DIG/issues/DIG-4355)).** The 13-19 Oct
window holds 257 cards created. 52 of them (20 percent) carry neither a row nor a
route event, so no row can be derived for them:

- 47 sit on medium and low priority issues. The old router read one
  priority-ordered page of 500 issues and could never hold them.
- 3 have no route event at all.
- 2 were withdrawn or expired inside a tick.

The review therefore measures 205 of 257 cards, 80 percent of the window. The
pagination fix in `dt-decide-poll` closes the hole for future windows; the 52
cards are on closed issues, so no row can be written for them now. The coverage
claim is bounded by this measurement, not assumed.

## Delivery model (states a constraint the implementer would otherwise re-discover)

`~/paperclip-workspace/kit` is a git repo, and on 19 Oct it had no remote. As of
22 Oct it has one (`kit.git`), so commits reach `develop` and `main` through a
branch and a merge. What still holds:

- launchd execs `/Users/chrisstefan/paperclip-workspace/kit/bin/dt-decide-poll`
  directly, so **the working tree is production**;
- the checkout sits on `DIG-4355-question-log-backfill`, a ticket branch;
- the tree carries **317 uncommitted entries, 62 of them under `bin/`**;
- the branch list holds many `rescue/kit-*` and `backup/main-*` refs, so this
  condition has been rescued before.

So leaf A landed as commits on ticket branches in the kit repo, with the landing
step on `develop` owned by the DevOps Lead. The structural fix was raised
separately as a governance issue, owned by the EM.

## Status update, 22 Oct 2026

The three leaves are done and the 13-19 Oct window is measurable: every card the
router saw in the window has a row. The file is not complete and was never going
to be - 52 of the 257 cards created in the window were never seen by the router
(see the known limitation above). Two defects keep the ticket open, and neither is
a measurement problem.

1. **The writer drops a card row when the asking seat cannot be resolved.**
   `dt-qlog.py` refuses the row instead of writing it, and that card then has no
   line at all, so it falls out of the denominator instead of being counted. Two
   refusals are involved, and which one fires depends on the seat:
   - a seat that is gone from the agents map makes `agent_name()` return an empty
     string (`dt-qlog.py:200-207`), which trips "question-log field
     'asking_agent' is empty; refusing the row" (`dt-qlog.py:251`);
   - a seat whose resolved value is itself a uuid trips "asking_agent is a raw
     uuid; refusing the row" (`dt-qlog.py:258`).

   The refusal protects the column; the defect is that it protects the column by
   dropping the card. The target state is that the row is still written, with
   `asking_agent = unknown` and the raw uuid kept out of the column, so the card
   stays in the denominator. No kit branch implements that yet. Reopened on
   [DIG-4353](/DIG/issues/DIG-4353) with a test that pins it.
2. **A second writer is still live in the seat-facing skill.** The kit source
   `kit/skills/decision-making/SKILL.md` carries "Never hand-write
   question-log.csv. dt-decide-poll is its only writer" (commit `559dfe5`, on kit
   `develop` and `main`). The copy the seats actually load,
   `~/.claude/skills/decision-making/SKILL.md`, still carries the old step 5 that
   asks the seat to write the line by hand, with the old 8-column schema and the
   old human vocabulary (its `ANSWERABLE` means the opposite of the machine's).
   Since 19 Oct that text has produced at least 20 hand-written rows, and exactly
   4 rows in the whole file break the 10-column schema (DIG-2040, DIG-4835,
   DIG-2698, DIG-3816). The deployed copy also carries two CoS rules that kit
   `develop` does not have, so the fix is a merge of both texts into the kit copy,
   then a deploy, not a plain copy. Tracked on
   [DIG-5216](/DIG/issues/DIG-5216).

The "Delivery model" section above was written on 19 Oct and is stale on one point:
the kit repo now has a remote (`kit.git`) and commits reach `develop` and `main`,
so the landing goes through a branch and a merge, not through a bare commit on a
lonely branch.

## Definition of done for the whole ticket

1. A card the router touches writes exactly one row, whatever the tick count.
2. `quality` is derived from router signals, and the 13-19 Oct backfill is not 100%
   GOOD.
3. The Monday review can produce "per asking agent, percent ANSWERABLE or BAD"
   from the file with no human transcription.
4. The 13-19 Oct window is backfilled, with the polling-hole size measured and
   reported.
