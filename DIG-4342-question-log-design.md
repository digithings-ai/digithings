# DIG-4342 design: one writer for question-log.csv

CTO decision, 19 Oct 2026. This pins the contract for leaves A, B and C.

## Measured facts (this run)

| Fact | How measured |
|---|---|
| 160 `rung` events in route-log.jsonl, 13-19 Oct | `event=="rung"`, ts >= 2026-10-13 |
| question-log.csv has 10 rows in the same window | `csv.reader`, field 0 in 13-19 Oct |
| dt-decide-poll never writes question-log.csv | read of `kit/bin/dt-decide-poll`, no reference to the file |
| The CSV is written by hand | `decision-making/SKILL.md` step 5, `agents/decider.md` step 3 |
| 252 parsed data rows (19 Oct snapshot): 250 in the five width buckets below, 2 at a width those buckets omit | `csv.reader`, under a 10-column header |
| 10/10 recent rows are `GOOD` | column 4 of the 13-19 Oct rows |
| 708 data rows on 22 Oct 13:00Z, of which exactly 4 break the 10-column schema; 444 of the 708 carry the writer's own `confidence=mechanical` label | `csv.reader`, field counts 8:1, 9:1, 10:704, 11:2 |

The CoS's counts on DIG-4327 are the ones this document uses: 160 distinct cards in the
window and 10 rows in `question-log.csv`. Coverage is therefore 10/160 = 6 percent, and
this document uses that one numerator throughout. The CoS summary and the DIG-4342 brief
pair the same two counts with 3 percent and "156 cards have no row"; 160 minus 10 is 150,
so neither figure follows from the counts they are quoted beside. The conclusion those
two documents draw is unaffected: at 6 percent coverage the per-asker quality column is
unmeasured for the week.

Both figures are a 19 Oct snapshot of a window that was still being written, so they
are not the numbers the Monday review uses. The cohort table below reconciles every
number that appears in this document.

## Why the rows that exist are not trustworthy either

Two writers, one file, no enforced schema:

1. **the router** (`dt-decide-poll`) - writes route-log.jsonl, never the CSV;
2. **each rung, by hand** - told to by the skill.

Hand rows are ragged: 118 rows have 8 fields (no `class`, no `source_path`), 89 have
10, **38 have 11**, 3 have 9, 2 have 12 - those five buckets hold 250 of the 252 rows
in the snapshot. The remaining 2 rows were read by the parser but are degenerate: their
width falls outside the five buckets, so the histogram does not classify them. Under a
10-column header, `row[4]` is `quality` in one row and something else in another. One row
(DIG-1134, 2026-10-06)
carries a 4337-character multi-line run essay in its last field. Two DIG-3395 rows
carry truncated 8-character pseudo-ids instead of a UUID. Several `asking_agent`
values are raw UUIDs instead of names.

On 22 Oct 13:00Z the file holds 708 data rows and exactly 4 rows that break the
10-column schema: DIG-2040 (8 fields), DIG-4835 (9 fields), DIG-2698 and DIG-3816
(11 fields each). All four are dated 19 Oct or later.

So the fix is not "tell seats to log harder". It is **one machine writer**.

## Decision 1: the router is the writer

`dt-decide-poll` runs unattended every 5 minutes and is the only component that already
records the same lifecycle in route-log.jsonl. It is the right writer, and it is not
because it sees every card: it does not. It sees every card the issue page it reads
reaches, and the 13-19 Oct window measures that at **205 of 257 cards, 80 percent** - 52
cards were never seen (see "Known limitation" below for the split and the pagination fix
that closes the hole for future windows). Asking 160 rungs a week to remember a CSV line
is the defect, not the solution.

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
both `GOOD` and only a handed-up card (rung 2 or later) is `ANSWERABLE`. Two of the
next counts are the R&D Engineer's, measured on the pre-backfill file and not
reproducible from this checkout because that file is gone: with the threshold at rung
1, **45 of the 49** threshold-dependent cards become `ANSWERABLE` (92 percent), which
mirrors `GOOD` and leaves the metric with no discriminating power; at the rung-2
threshold **six rows that were wrongly filed as `GOOD` become `BAD`**. At rung 2 the
window yields 4 `ANSWERABLE` cards in the 206-card cohort measured on 22 Oct (DIG-711,
DIG-2205, DIG-3664, DIG-3699); the R&D Engineer measured 5 at 06:55Z, before the writer
had completed every row of the window.

The empty `ANSWERABLE` bucket in the first review was plumbing, not definition:
`dt-decide-poll` deletes a retired card's route entry, so the writer read rung 0
and called it `GOOD`. The writer now recovers the rung from the route log.
Confirmed by the R&D Engineer on [DIG-4355](/DIG/issues/DIG-4355).

The contract did not reach every copy of the code at first: the docstring at
`kit/bin/dt-qlog.py:35` still said "answered after >= 1 hand-up", the wording this
section replaces. That gap was closed on the reopened leaf
[DIG-4353](/DIG/issues/DIG-4353): the module now defines the hand-up where it uses
it (`kit/bin/dt-qlog.py:99-102`), so "a hand-up" and "rung 2 or more" are the same
statement in the code and in this document.

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
| 81 | `ANSWERABLE` (4) plus `BAD` (77), which is 47.6 percent of 170 | my count, 22 Oct 13:00Z |
| 169 | the R&D Engineer's denominator: his 205-card cohort minus its 36 `OUT_OF_SCOPE` cards. One card away from 170 because the writer completes rows between the two measurements | R&D Engineer, 06:55Z |
| 139 | the R&D Engineer's denominator over the route-log-only cohort (178 cards) | R&D Engineer |

The cohort moves while the writer is live. At 07:34Z it read BAD 75, GOOD 64,
PENDING 2 and 79 of 170 (46.5 percent); at 13:00Z it reads BAD 77, GOOD 63,
PENDING 1 and 81 of 170 (47.6 percent), because the writer completed two rows in
between. The Monday review therefore recomputes from the file and does not quote
a number frozen in this document. The denominator stays 170 only as long as no
card is added to the window.

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

- launchd execs `~/paperclip-workspace/kit/bin/dt-decide-poll` by absolute path,
  so **the working tree is production**;
- the checkout sits on `DIG-4355-question-log-backfill`, a ticket branch;
- the tree carries **322 uncommitted entries, 64 of them under `bin/`**;
- the branch list holds many `rescue/kit-*` and `backup/main-*` refs, so this
  condition has been rescued before.

So leaf A landed as commits on ticket branches in the kit repo, with the landing
step on `develop` owned by the DevOps Lead. The structural fix was raised
separately as a governance issue, owned by the EM.

## Status update, 22 Oct 2026, 13:00Z

The three leaves are done and the 13-19 Oct window is measurable: every card the
router saw in the window has a row. The file is not complete and was never going
to be - 52 of the 257 cards created in the window were never seen by the router
(see the known limitation above).

Two defects were open at the start of this update. Both are closed, and both were
verified against the live surface, not against a branch.

1. **The writer dropped a card row when the asking seat could not be resolved.
   CLOSED.**
   `dt-qlog.py` refused the row instead of writing it, and the card then had no
   line at all, so it fell out of the denominator instead of being counted. Two
   refusals were involved, and which one fired depended on the seat:
   - a seat that is gone from the agents map made `agent_name()` return an empty
     string, which tripped "question-log field 'asking_agent' is empty; refusing
     the row";
   - a seat whose resolved value was itself a uuid tripped "asking_agent is a raw
     uuid; refusing the row".

   The refusal protected the column; the defect was that it protected the column
   by dropping the card. The shipped writer resolves the asker first and then
   guards the column: `resolve_asker()` returns `UNKNOWN_ASKER` ("unknown") for an
   empty or uuid-shaped name, `build_row()` applies it before the empty-field
   guard, and the asker column can no longer be empty or a raw uuid
   (`kit/bin/dt-qlog.py:110`, `:227-244`, `:273-307`). The card stays in the
   denominator.

   Measured on the live surface: the three cards that had been refused 888 times
   between 19 Oct and 22 Oct - DIG-871 (`6fe65075`), DIG-1648 (`cf21aed2`) and
   DIG-2232 (`392cc610`) - now hold a machine row with `asking_agent=unknown`
   (`confidence=mechanical`), and the daemon has logged no refusal since the fix
   landed on 22 Oct at 10:27 local. The suite pins it:
   `kit/tests/test_dt_qlog.py` runs 42 tests green, among them
   `test_an_unresolvable_asking_agent_is_recorded_as_unknown_not_a_uuid`,
   `test_a_blank_asker_is_recorded_as_unknown` and
   `test_a_raw_uuid_asker_is_recorded_as_unknown`.
2. **A second writer was live in the seat-facing skill. CLOSED.**
   The kit source `kit/skills/decision-making/SKILL.md` carried "Never hand-write
   question-log.csv. dt-decide-poll is its only writer" (commit `559dfe5`, on kit
   `develop` and `main`), but the copy the seats actually load,
   `~/.claude/skills/decision-making/SKILL.md`, still carried the old step 5 that
   asked the seat to write the line by hand, with the old 8-column schema and the
   old human vocabulary (its `ANSWERABLE` meant the opposite of the machine's).
   Since 19 Oct that text produced at least 20 hand-written rows, and exactly 4
   rows in the whole file break the 10-column schema (DIG-2040, DIG-4835,
   DIG-2698, DIG-3816). The deployed copy also carried two CoS rules that kit
   `develop` did not have, so the fix was a merge of both texts into the kit copy
   and then a deploy, not a plain copy.

   Measured on the live surface: the deployed `~/.claude/skills/decision-making/SKILL.md`
   is now byte-identical to `kit develop:skills/decision-making/SKILL.md` and
   carries the never-hand-write line together with the two CoS rules. The suite
   pins both halves (`test_nobody_is_told_to_hand_write_the_file`,
   `test_skill_step_5_logging_is_gone`, `test_decider_step_3_logging_is_gone`).
   Tracked on [DIG-5216](/DIG/issues/DIG-5216).

The 4 schema-breaking rows are hand-written rows that predate the deploy, and
decision 4 keeps them: the writer never rewrites or removes a row it did not
write. A human row is the human record. The reader has to know that not every row
in the file is a machine row: of the 708 rows in the file, 444 carry the writer's
own `confidence=mechanical` label and 264 are hand-written, and the 4 rows that
break the 10-column schema are among the hand-written ones. Inside the Monday
cohort of 206 cards, 193 rows are mechanical and 13 are hand-written, so 13 of the
206 cards are graded by a human and the review should say so.

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

All four are met, measured on the live surface on 22 Oct 13:00Z:

| | Measured |
|---|---|
| 1 | 378 of 378 distinct route-log cards hold a row, 0 missing; 114 of 114 cards the router touched since the writer landed hold a row, 0 missing; the 42-test writer suite is green |
| 2 | the 206-card window cohort reads GOOD 63 of 206, 31 percent, and BAD 77 - not 100 percent GOOD |
| 3 | the per-asker table is computable from the file with no transcription: 27 askers in the denominator, for example Host & Runtime Engineer 19 rows at 42.1 percent, Backend Engineer Core Services 15 rows at 73.3 percent, EM 11 rows at 63.6 percent, Software Architect 8 rows at 25.0 percent |
| 4 | 178 of 178 window cards hold a row; the hole is 52 of 257 cards (20 percent), split 47 on medium and low priority issues, 3 with no route event, 2 withdrawn or expired inside a tick |
