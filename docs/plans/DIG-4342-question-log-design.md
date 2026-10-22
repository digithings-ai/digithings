# DIG-4342 design: one writer for question-log.csv

CTO decision, 19 Oct 2026. This pins the contract for leaves A, B and C.

**Status, 22 Oct 2026 16:05 local (14:05Z).** The contract is settled, the 13-19 Oct
window is measurable from the file, and one of the two defects is closed. The
implementation is **not** complete on the tree that runs: the writer fix is on the kit
`develop` branch and not on the kit `main` branch that the launchd job executes. Read
[Status](#status-22-oct-2026-the-tree-that-runs) first; it names the tree and the
outstanding landing.

Every number in this document is dated and has a "measured by" next to it. The file
`question-log.csv` is live and the writer keeps appending, so a number without a date is
a defect in the document.

## Status (22 Oct 2026): the tree that runs

| Fact | How measured |
|---|---|
| The daemon runs the kit **working tree**, by absolute path, not a copy | the launchd job `com.digithings.decide-poll` (StartInterval 300) execs `/usr/bin/python3 /Users/chrisstefan/paperclip-workspace/kit/bin/dt-decide-poll` | `PlistBuddy -c Print ~/Library/LaunchAgents/com.digithings.decide-poll.plist` |
| That working tree is on `main` @ `ba07f68`, which is the `origin/main` tip. It was switched to `main` at 15:23:56 +0200 on 22 Oct, out of `rescue/2026-10-22-DIG-5289-kit-live-tree` | the switch is in the kit reflog | `git -C ~/paperclip-workspace/kit reflog --date=iso` |
| **The writer on that tree has no `resolve_asker` and no `UNKNOWN_ASKER`** | grep on the production file returns nothing | `grep -E 'resolve_asker\|UNKNOWN_ASKER' ~/paperclip-workspace/kit/bin/dt-qlog.py` |
| On that tree `agent_name()` returns `""` for a seat that is not in the agents map, and the row is then refused | `agent_name` at `main:188-195`, the empty-field refusal at `main:239`, the raw-uuid refusal at `main:246` | `git show main:bin/dt-qlog.py` |
| The fix is on `develop` @ `dc69e0c`, and on the branch `DIG-4353-land` | `resolve_asker` at `develop:227`, `UNKNOWN_ASKER` at `develop:110`; the commits are `fbaea9d` (merged as `92aacff`) and `50312e4` (merged as `37dc12b`) | `git show develop:bin/dt-qlog.py`, `git log` |
| The suite that pins the fix is on `develop` only | `develop` holds 42 tests in `tests/test_dt_qlog.py`, including `test_an_unresolvable_asking_agent_is_recorded_as_unknown_not_a_uuid`, `test_a_blank_asker_is_recorded_as_unknown` and `test_a_raw_uuid_asker_is_recorded_as_unknown`. `main` holds 29 and none of the three | `git show <branch>:tests/test_dt_qlog.py` |
| The module docstring contradicts the code on **both** branches | `develop:35` and `main:28` still read "answered after >= 1 hand-up  ANSWERABLE"; the code says `HANDUP_RUNG = 2` (`develop:102`, `main:93`) and the rule at `develop:152` / `main:123` | `git show <branch>:bin/dt-qlog.py` |
| The committed backfill script is on `develop` only | `bin/dt-qlog-backfill.py` exists on `develop`; `main` has no such file | `git ls-tree --name-only <branch> bin/` |
| Defect 2, the second writer in the seat skill, is closed and is branch-independent | the deployed `~/.claude/skills/decision-making/SKILL.md` carries the one-writer line and is byte-identical to **both** `develop`'s and `main`'s copy of `skills/decision-making/SKILL.md` | `diff` against `git show <branch>:skills/decision-making/SKILL.md` |

**Defect 1 - the writer dropped a card whose asking seat cannot be resolved - is OPEN on
the tree that runs.** The three cards the daemon refused 888 times (DIG-871 `6fe65075`,
DIG-1648 `cf21aed2`, DIG-2232 `392cc610`) hold a machine row with `asking_agent=unknown`
today, because they were written between 10:27 and 15:23 local, while the tree still
carried the fix. The router has not seen them since 22 Oct 08:39 local - the route log's
last event on `6fe65075` is at 08:39:31, and the other two have no route event left at
all, because the router deletes a retired card's route entry. So the daemon log is silent
after 09:36:50 local, and that silence is not evidence of a fix. The defect is **latent**:
any card from a seat that has left the company, that the router sees again, is dropped by
the running writer and falls out of the review denominator.

**Defect 2 - a second, hand-written writer was live in the seat skill - is CLOSED**, and
it is closed on the running tree as well, because the deployed copy is byte-identical to
both branches.

### What is owed on the tree that runs

Owned by the DevOps Lead as the kit landing owner. The CTO does not merge, and `main` is
production, so a promotion into it is a Chris-gated step.

1. `resolve_asker` and `UNKNOWN_ASKER` on `main` (`fbaea9d`, `50312e4`).
2. The docstring fix in `bin/dt-qlog.py`: "answered after >= 1 hand-up" must read "answered
   at rung 2 or later", on both branches. The side comment at `develop:98-101` already
   says it; the docstring is what the code and this document must agree with.
3. `bin/dt-qlog-backfill.py` on `main`, so the 13-19 Oct backfill is reproducible on the
   tree that runs and not only on a branch.
4. The three asker tests in `tests/test_dt_qlog.py` on `main` (29 tests to 42).

Landing `develop` on `main` is a **merge, not a fast-forward**: `main` carries 27 commits
that `develop` does not, and `develop` carries 41 that `main` does not. After the landing
the production tree is fast-forwarded to `main` and the daemon is re-measured.

## Measured facts

| Fact | How measured | When |
|---|---|---|
| 160 `rung` events in route-log.jsonl for 13-19 Oct | `event=="rung"`, ts >= 2026-10-13 | 19 Oct snapshot |
| question-log.csv held 10 rows for the same window | `csv.reader`, field 0, 13-19 Oct | 19 Oct snapshot |
| dt-decide-poll did not write question-log.csv | read of `kit/bin/dt-decide-poll`, no reference to the file | 19 Oct, before leaf A |
| the CSV was written by hand | `decision-making/SKILL.md` step 5, `agents/decider.md` step 3 | 19 Oct, before leaf A |
| 252 parsed data rows: 250 in the five width buckets below, 2 at a width those buckets omit | `csv.reader`, under a 10-column header | 19 Oct snapshot |
| 10 of the 10 recent rows were `GOOD` | column 4 of the 13-19 Oct rows | 19 Oct snapshot |
| 710 data rows, exactly 4 of them breaking the 10-column schema, 446 of them carrying the writer's own `confidence=mechanical` label | `csv.reader`, field counts 8:1, 9:1, 10:706, 11:2 | 22 Oct 16:30 local |

The CoS's counts on DIG-4327 are the ones this document started from: 160 distinct cards
in the window and 10 rows in `question-log.csv`. Coverage was therefore 10/160 = 6 percent,
and that numerator is the one this document used until the writer landed. The CoS summary
and the DIG-4342 brief pair the same two counts with 3 percent and "156 cards have no
row"; 160 minus 10 is 150, so neither figure follows from the counts they are quoted
beside. The conclusion those two documents draw is unaffected: at 6 percent coverage the
per-asker quality column was unmeasured for the week.

Both figures are a 19 Oct snapshot of a window that was still being written, so they are
not the numbers the Monday review uses. The cohort table below reconciles every number
that appears in this document.

## Why the rows that existed were not trustworthy either

Two writers, one file, no enforced schema:

1. **the router** (`dt-decide-poll`) - wrote route-log.jsonl, never the CSV;
2. **each rung, by hand** - told to by the skill.

Hand rows are ragged. In the 19 Oct snapshot 118 rows had 8 fields (no `class`, no
`source_path`), 89 had 10, **38 had 11**, 3 had 9 and 2 had 12 - those five buckets hold
250 of the 252 rows. The remaining 2 rows were read by the parser but are degenerate:
their width falls outside the five buckets, so the histogram does not classify them. Under
a 10-column header, `row[4]` is `quality` in one row and something else in another. One
row (DIG-1134, 2026-10-06) carried a 4337-character multi-line run essay in its last
field. Two DIG-3395 rows carried truncated 8-character pseudo-ids instead of a UUID.
Several `asking_agent` values were raw UUIDs instead of names.

**What the file looks like now (22 Oct 16:30 local).** The hand-written regime is gone and
the current numbers replace that narrative:

- 710 data rows; 446 machine rows (`confidence=mechanical`) and 264 hand-written rows.
- Exactly 4 rows break the 10-column schema, all of them hand-written: DIG-4835 (9
  fields, 2026-10-21), DIG-2040 (8 fields, 2026-10-21), DIG-2698 (11 fields, 2026-10-22)
  and DIG-3816 (11 fields, 2026-10-22).
- 0 rows carry a raw uuid in `asking_agent`, and 0 rows carry an 8-character interaction
  id. The three `asking_agent=unknown` rows are the ones the fix is for.
- 0 fields contain an embedded newline. The longest field in the file is 8035 characters
  (DIG-893, 2026-10-05, `GOOD`); DIG-1134's longest field is 130 characters.

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

Implemented as `HANDUP_RUNG = 2` in `kit/bin/dt-qlog.py` (`develop:102`, `main:93`). The
rule is `ANSWERABLE if (rung or 0) >= HANDUP_RUNG else GOOD` (`develop:152`, `main:123`),
so rung 0 and rung 1 are both `GOOD` and only a handed-up card (rung 2 or later) is
`ANSWERABLE`. The comment above the constant (`develop:98-101`, `main:89-92`) defines the
hand-up where the code uses it.

Two of the next counts are the R&D Engineer's, measured on the pre-backfill file and not
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
Confirmed by the R&D Engineer on DIG-4355.

**The docstring gap is still open, on both branches.** The module docstring still carries
the wording this section replaces: `develop:35` and `main:28` read "answered after >= 1
hand-up  ANSWERABLE", and `develop:34` and `main:27` read "answered at the first rung (or
before any wake)  GOOD". The code says `HANDUP_RUNG = 2`, so the docstring is one rung
loose. Fixing it is item 2 of the landing list above; it is not closed.

## Cohorts and denominators (22 Oct 2026)

One window, several denominators. Every number the Monday review uses is in this
table, so no two documents count the same set twice.

| Number | What it counts | Measured by | When |
|---|---|---|---|
| 160 | distinct cards the CoS measured in route-log.jsonl for 13-19 Oct | CoS, DIG-4327 | 19 Oct snapshot |
| 10 | rows question-log.csv held for the same window | CoS, DIG-4327 | 19 Oct snapshot |
| 252 / 250 / 118 / 89 / 38 / 3 / 2 | parsed rows in the file, the five width buckets and their counts, in the 19 Oct snapshot | me | 19 Oct snapshot |
| 257 | cards created in the 13-19 Oct window (the API denominator) | R&D Engineer, DIG-4355 | 22 Oct 06:55Z |
| 52 (20 percent) | cards the router never saw: 47 on medium and low priority issues the priority-ordered page could not hold, 3 with no route event, 2 withdrawn or expired inside a tick. All 52 issues are closed, so the fix closes the hole for future windows only | R&D Engineer, DIG-4355 | 22 Oct 06:55Z |
| 205 | of the 257 that carry a question-log row | R&D Engineer, DIG-4355 | 22 Oct 06:55Z |
| 169 | the R&D Engineer's denominator: his 205-card cohort minus its 36 `OUT_OF_SCOPE` cards. One card away from 170 because the writer completes rows between the two measurements | R&D Engineer, DIG-4355 | 22 Oct 06:55Z |
| 139 | the R&D Engineer's denominator over the route-log-only cohort (178 cards) | R&D Engineer, DIG-4355 | 22 Oct 06:55Z |
| 178 | distinct cards with any route-log event in the window (128 `board`, 169 `rung`, 192 `retired`; 109 of the cards have a `rung` event) | me | 22 Oct 16:00 local |
| 1832 | route-log events in the file, all time (566 `board`, 870 `rung`, 396 `retired`) | me | 22 Oct 16:00 local |
| 380 | distinct cards in route-log.jsonl, all time. 0 of them are without a row | me | 22 Oct 16:00 local |
| 229 / 169 | `rung` events since 2026-10-13, unbounded / bounded to the window. The 160 in the DIG-4327 brief was the 19 Oct snapshot of the unbounded count | me | 22 Oct 16:00 local |
| 206 | rows dated in the window, which are 206 distinct interaction ids. This is the cohort quality is measured on, taking the last row per card | me | 22 Oct 16:00 local |
| 170 | the quality denominator: 206 minus the 36 `OUT_OF_SCOPE` cards | me | 22 Oct 16:00 local |
| 81 | `ANSWERABLE` (4) plus `BAD` (77), which is 47.6 percent of 170 | me | 22 Oct 16:00 local |
| 27 | askers in the denominator | me | 22 Oct 16:00 local |
| 193 / 13 | machine rows / hand-written rows inside the 206-card cohort | me | 22 Oct 16:00 local |
| 710 | data rows in question-log.csv (708 at 13:00Z; the writer is live) | me | 22 Oct 16:30 local |
| 446 / 264 | rows carrying `confidence=mechanical` / hand-written rows in the file | me | 22 Oct 16:30 local |
| 4 | rows that break the 10-column schema: DIG-4835, DIG-2040, DIG-2698, DIG-3816 | me | 22 Oct 16:30 local |
| 888 | refusals the daemon logged between 19 Oct and 22 Oct; the last one at 22 Oct 09:36:50 local | me, over the daemon log | 22 Oct |
| 42 / 29 | tests in `tests/test_dt_qlog.py` on `develop` / on `main` | me | 22 Oct |
| 112 / 92 / 58 / 45 / 10 | cards the router last touched at or after 2026-10-19 08:27 / 2026-10-20 / 2026-10-21 / 2026-10-22 / 2026-10-22 13:00, all local time. At every one of those cutoffs, 0 of the cards is missing a row | me | 22 Oct 16:00 local |
| 49 / 45 / 6 | the rung-threshold experiment: threshold-dependent cards, cards that become `ANSWERABLE` at a rung-1 threshold, rows that were wrongly `GOOD` at the rung-2 threshold. Measured on the pre-backfill file, which is gone, so not reproducible from this checkout | R&D Engineer, DIG-4355 | 22 Oct 06:55Z |

### The Monday cohort, and why the quality distribution sums

Last row per interaction id, over the rows dated 2026-10-13 to 2026-10-19:

| quality | cards | in the denominator |
|---|---|---|
| `BAD` | 77 | yes |
| `GOOD` | 63 | yes |
| `STALE` | 25 | yes |
| `ANSWERABLE` | 4 | yes |
| `PENDING` | 1 | yes |
| `OUT_OF_SCOPE` | 36 | no, excluded |
| **total** | **206** | **170** |

`OUT_OF_SCOPE` excluded leaves a denominator of 170. The numerator is `ANSWERABLE` (4)
plus `BAD` (77) = 81, which is **47.6 percent**. `STALE` (25) is in the denominator: a
retired card that was never answered is a card the asker could not answer, and the review
measures quality per asker, so it counts. `PENDING` (1) is in the denominator too and is
a card still open inside the window.

The cohort moves while the writer is live. At 07:34Z it read BAD 75, GOOD 64, PENDING 2
and 79 of 170 (46.5 percent); at 13:00Z it read BAD 77, GOOD 63, PENDING 1 and 81 of 170
(47.6 percent), because the writer completed two rows in between. The Monday review
therefore recomputes from the file and does not quote a number frozen in this document.
The denominator stays 170 only as long as no card is added to the window.

169 is also the number of `rung` events in the window, and also the R&D Engineer's
denominator. The three 169s are different sets that happen to be the same size; do not
read one as the other.

### Per asker (22 Oct 16:00 local, 27 askers in the denominator)

| asking agent | cards in the denominator | `ANSWERABLE` or `BAD` | rate |
|---|---|---|---|
| Host & Runtime Engineer | 19 | 8 | 42.1% |
| Edge & Domains Engineer | 18 | 9 | 50.0% |
| Backend Engineer, Core Services | 15 | 11 | 73.3% |
| EM | 11 | 7 | 63.6% |
| Cursor consultant | 10 | 4 | 40.0% |
| R&D Engineer | 10 | 4 | 40.0% |
| Backend Engineer, Reliability | 9 | 4 | 44.4% |
| DevOps Lead | 9 | 4 | 44.4% |
| Repo, CI & Release Engineer | 9 | 4 | 44.4% |
| Software Architect | 8 | 2 | 25.0% |
| Frontend Engineer | 7 | 5 | 71.4% |
| Claude | 6 | 2 | 33.3% |
| Security Engineer | 5 | 2 | 40.0% |
| CSM | 4 | 2 | 50.0% |
| FDE twelve-x | 4 | 2 | 50.0% |
| ML/AI Engineer | 4 | 1 | 25.0% |
| Quant | 4 | 3 | 75.0% |
| Director Finance & Quant | 3 | 0 | 0.0% |
| CoS | 2 | 2 | 100.0% |
| Counsel | 2 | 2 | 100.0% |
| Data & Backups Engineer | 2 | 0 | 0.0% |
| EM (engineer) | 2 | 0 | 0.0% |
| OpenCode Go Consultant | 2 | 0 | 0.0% |
| QA Lead | 2 | 0 | 0.0% |
| Accountant | 1 | 1 | 100.0% |
| PM | 1 | 1 | 100.0% |
| QA Engineer | 1 | 1 | 100.0% |

Two hygiene notes for whoever reads the file: one seat appears under two spellings
("Backend Engineer, Reliability" and "Backend Engineer Reliability"), and the 36
`OUT_OF_SCOPE` cards carry no asker in this table because they are out of the
denominator by rule.

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
  No raw uuid, no empty. This is the rule leaf A has to land on the tree that runs:
  see the landing list.
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

The copy the seats actually load was not covered by either change. That gap is closed;
see the status section.

## Known limitation, to be measured not assumed

dt-decide-poll polls every 5 minutes. A card created **and** resolved between two
ticks is never seen and gets no row. Closing it means hooking the
interaction-create path, a second surface; out of scope here, tracked by the
measurement.

**Measured on 22 Oct (leaf C, DIG-4355).** The 13-19 Oct window holds 257 cards created.
52 of them (20 percent) carry neither a row nor a route event, so no row can be derived
for them:

- 47 sit on medium and low priority issues. The old router read one
  priority-ordered page of 500 issues and could never hold them.
- 3 have no route event at all.
- 2 were withdrawn or expired inside a tick.

The review therefore measures 205 of 257 cards, 80 percent of the window. The
pagination fix in `dt-decide-poll` closes the hole for future windows; the 52
cards are on closed issues, so no row can be written for them now. The coverage
claim is bounded by this measurement, not assumed.

## Delivery model (states a constraint the implementer would otherwise re-discover)

`~/paperclip-workspace/kit` is a git repo whose remote is a local bare repo
(`/Users/chrisstefan/paperclip-workspace/kit.git`), so commits reach `develop` and
`main` through a branch and a merge, and there is no GitHub copy of the kit. What
holds on 22 Oct 2026:

- launchd execs `~/paperclip-workspace/kit/bin/dt-decide-poll` by absolute path
  (`ProgramArguments` in `~/Library/LaunchAgents/com.digithings.decide-poll.plist`),
  so **the working tree is production**;
- the tree sits on `main` @ `ba07f68`, the `origin/main` tip;
- the tree carries **15 uncommitted entries**;
- `main` and `develop` have **diverged**: 41 commits only on `develop`, 27 only on
  `main`, so a landing is a merge, not a fast-forward;
- the branch list holds many `rescue/kit-*` and `backup/main-*` refs, so this
  condition has been rescued before.

So leaf A landed as commits on ticket branches in the kit repo (`DIG-4353-land`), and
the landing step on `develop` is owned by the DevOps Lead. The structural fix was
raised separately as a governance issue, owned by the EM.

## Definition of done for the whole ticket

1. A card the router touches writes exactly one row, whatever the tick count.
2. `quality` is derived from router signals, and the 13-19 Oct backfill is not 100%
   GOOD.
3. The Monday review can produce "per asking agent, percent ANSWERABLE or BAD"
   from the file with no human transcription.
4. The 13-19 Oct window is backfilled, with the polling-hole size measured and
   reported.

| | Measured, 22 Oct 16:30 local |
|---|---|
| 1 | 380 of 380 distinct route-log cards hold a row, 0 missing; at every cutoff from 2026-10-19 08:27 local to 2026-10-22 13:00 local, 0 of the cards the router touched is missing a row (112, 92, 58, 45 and 10 cards at those cutoffs); the writer suite is green on `develop` (42 tests) and does not carry the asker tests on `main` (29) |
| 2 | the 206-card window cohort reads GOOD 63 of 206, 31 percent, and BAD 77 - not 100 percent GOOD |
| 3 | the per-asker table is computable from the file with no transcription: 27 askers in the denominator, for example Host & Runtime Engineer 19 cards at 42.1 percent, Backend Engineer, Core Services 15 at 73.3 percent, EM 11 at 63.6 percent, Software Architect 8 at 25.0 percent |
| 4 | 178 of 178 window cards hold a row; the hole is 52 of 257 cards (20 percent), split 47 on medium and low priority issues, 3 with no route event, 2 withdrawn or expired inside a tick |

Item 1 is met for every card the router has touched, and the writer that runs on the
production tree is missing the asker fix. That is the landing list at the top of this
document, and it is the one thing between this ticket and done.
