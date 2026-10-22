# DIG-4342 design: one writer for question-log.csv

CTO decision, 19 Oct 2026. This pins the contract for leaves A, B and C.

## Measured facts (this run)

| Fact | How measured |
|---|---|
| 160 `rung` events in route-log.jsonl, 13-19 Oct | `event=="rung"`, ts >= 2026-10-13 |
| question-log.csv has 10 rows in the same window | `csv.reader`, field 0 in 13-19 Oct |
| dt-decide-poll never writes question-log.csv | read of `kit/bin/dt-decide-poll`, no reference to the file |
| The CSV is written by hand | `decision-making/SKILL.md` step 5, `agents/decider.md` step 3 |
| 252 parsed data rows, field counts 8/9/10/11/12 | `csv.reader`, under a 10-column header |
| 10/10 recent rows are `GOOD` | column 4 of the 13-19 Oct rows |

The CoS's measurement (DIG-4327) is correct. Coverage is 10/160 = 6%.

## Why the rows that exist are not trustworthy either

Two writers, one file, no enforced schema:

1. **the router** (`dt-decide-poll`) - writes route-log.jsonl, never the CSV;
2. **each rung, by hand** - told to by the skill.

Hand rows are ragged: 118 rows have 8 fields (no `class`, no `source_path`), 89 have
10, **38 have 11**, 3 have 9, 2 have 12. Under a 10-column header, `row[4]` is
`quality` in one row and something else in another. One row (DIG-1134, 2026-10-06)
carries a 4337-character multi-line run essay in its last field. Two DIG-3395 rows
carry truncated 8-character pseudo-ids instead of a UUID. Several `asking_agent`
values are raw UUIDs instead of names.

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
| answered at rung 0 | `GOOD` |
| answered only after a hand-up (the card reached rung 2 or later) | `ANSWERABLE` |

`OUT_OF_SCOPE` is a new value. Without it, correctly-escalated money and security
cards pollute the quality rate. The Monday review must exclude it from the
denominator and say so.

### The hand-up rung is 2 (confirmed 22 Oct 2026)

The table above used to read "answered only after >= 1 hand-up". That was ambiguous
and was resolved by measurement, not by taste. In the DIG-4327 vocabulary the
hand-up happens at **rung 2**: a card answered at rung 0 or 1 never left the first
line of the chain, so nobody handed it up.

Implemented as `HANDUP_RUNG = 2` in `kit/bin/dt-qlog.py`. Measured on the 13-19 Oct
window: with the threshold at rung 1, 45 of the 49 threshold-dependent cards become
`ANSWERABLE` (92 percent), which mirrors `GOOD` and leaves the metric with no
discriminating power. At rung 2 the window yields 5 `ANSWERABLE` cards out of a
169-card denominator, and 6 rows that were wrongly filed as `GOOD` become `BAD`.

The empty `ANSWERABLE` bucket in the first review was plumbing, not definition:
`dt-decide-poll` deletes a retired card's route entry, so the writer read rung 0
and called it `GOOD`. The writer now recovers the rung from the route log.
Confirmed by the R&D Engineer on [DIG-4355](/DIG/issues/DIG-4355).

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

`decision-making/SKILL.md` step 5 and `agents/decider.md` step 3 are deleted in the
same leaf as the writer. A second writer racing the machine writer on the same file
is how the file got ragged. Shipping the writer without removing the ask leaves two
writers and re-creates the defect.

## Known limitation, to be measured not assumed

dt-decide-poll polls every 5 minutes. A card created **and** resolved between two
ticks is never seen and gets no row. Leaf C must report how many of the 13-19 Oct
cards fall in this hole, so the coverage claim is bounded by evidence. Closing it
means hooking the interaction-create path, a second surface; out of scope here,
tracked by the measurement.

## Delivery model (states a constraint the implementer would otherwise re-discover)

`~/paperclip-workspace/kit` is a git repo, but:

- launchd execs `/Users/chrisstefan/paperclip-workspace/kit/bin/dt-decide-poll`
  directly, so **the working tree is production**;
- there is **no remote**, so there is no PR, no CI and no merge queue;
- the checkout sits on `fix/DIG-1959-mirror-resolves-ticket-numbers`, an unrelated
  old branch;
- the tree carries **204 uncommitted modifications**;
- the branch list holds many `rescue/kit-*` and `backup/main-*` refs, so this
  condition has been rescued before.

So leaf A does not go through the develop PR queue. It is a commit on its own branch
in the kit repo, with an agentic review pass recorded on the issue
(`<!-- in-session-review -->` + `reviewed:agent`) before it is considered landed.
Raising the structural fix separately as a governance issue, owned by the EM.

## Status update, 22 Oct 2026

The three leaves are done and the 13-19 Oct window is measurable. Two defects keep
the ticket open, and neither is a measurement problem: the file is complete, the
question is whether one writer keeps it complete.

1. **The writer drops a card row when the asking seat cannot be resolved.**
   `dt-qlog.py` refuses the row when the asking seat is gone or unresolvable
   ("asking_agent is a raw uuid; refusing the row"), and that card then has no line
   at all, so it falls out of the denominator instead of being counted. The refusal
   protects the column; the defect is that it protects the column by dropping the
   card. The row is still written, with `asking_agent = unknown` and the raw uuid
   kept out of the column, so the card stays in the denominator. Reopened on
   [DIG-4353](/DIG/issues/DIG-4353) with a test that pins it.
2. **A second writer is still live in the seat-facing skill.** The kit source
   `kit/skills/decision-making/SKILL.md` carries "Never hand-write
   question-log.csv. dt-decide-poll is its only writer" (commit `559dfe5`, on kit
   `develop` and `main`). The copy the seats actually load,
   `~/.claude/skills/decision-making/SKILL.md`, still carries the old step 5 that
   asks the seat to write the line by hand, with the old 8-column schema and the
   old human vocabulary (its `ANSWERABLE` means the opposite of the machine's).
   Since 19 Oct that text has produced 20 hand-written rows, 4 of them
   schema-invalid. The deployed copy also carries two CoS rules that kit `develop`
   does not have, so the fix is a merge of both texts into the kit copy, then a
   deploy, not a plain copy.

The "Delivery model" section below was written on 19 Oct and is stale on one point:
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
