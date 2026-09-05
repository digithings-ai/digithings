# Linear migration — spec + plan (issue #3572)

Status: SPEC (no migration executed). Owner approves this doc first; a
separate execution task runs the dry-run, then the migration.

## 1. Why

GitHub Projects served as module boards during the single-repo build-out.
Pain points observed in the 2026-09 board cleanup:

- 10 org boards (~1.5k items) with overlapping membership; epics live on
  multiple boards at once.
- Legacy single-select fields (Phase / Area / Priority P0–P3 / Kind) mirror
  the retired label taxonomy (`phase:*`, `risk:*`, `type:*` deleted 2026-09)
  and are now a second, drifting source of truth.
- Four workflows exist only to feed the boards (see §4); board automation is
  queue pressure with no dispatch value — dispatch keys off issue labels.

Target: Linear for planning/tracking; GitHub Issues stay the system of
record for agent dispatch (labels are the contract — untouched by this move).

## 2. Current state (verified 2026-09-04)

| # | Board | Items | Role |
|---|-------|-------|------|
| 1 | digithings | ~733 | org rollup; epics + cross-cutting |
| 2 | digiquant | ~358 | module board |
| 3 | digigraph | ~58 | module board |
| 4 | digisearch | ~30 | module board |
| 5 | digichat | ~83 | module board |
| 6 | digikey | ~12 | module board |
| 7 | digismith | ~5 | module board |
| 8 | digiclaw | ~6 | module board |
| 9 | digibase | ~3 | module board |
| 11 | maintenance | ~198 | housekeeping rollup |

Board #1 custom fields: Status (Todo/In Progress/Review/Done), Phase
(Phase 2–6 + Client Pilot), Area (old module names incl. Atlas), Priority
(P0–P3), Kind (Epic/Feature/Task/Bug/Chore/Research). Module boards carry
the same field set (spot-checked #2).

## 3. Target structure

- One Linear team per repo module (digibase, digichat, digiclaw, digigraph,
  digikey, digiquant, digisearch, digismith, digivault, root, website —
  verify exact component list at execution against the 28-label set),
  plus a `housekeeping` team for the maintenance board and an org-level
  `digithings` team for epics/cross-cutting.
- Linear Projects (roadmap-level) ← GitHub `epic`-labeled issues on board #1.
- Linear workflow states ← board Status 1:1
  (Todo→Backlog/Todo, In Progress→In Progress, Review→In Review, Done→Done).
- Linear labels ← GitHub labels verbatim (`component:*`, `priority:*`,
  `agent-task`, `reviewed:*`, `bug`, `security:finding`, `client-pilot`).
  Do NOT import the legacy Phase/Area/Kind/Priority single-selects —
  they duplicate labels and are the drift source. Archive the mapping
  table in the execution PR for audit, then drop.
- Linear priority ← `priority:*` (critical/high→Urgent/High, medium→Medium,
  low→Low); unmapped → No Priority.

## 4. Automation impact

Unaffected (label-keyed, stay on GitHub Issues): agent-cursor-dispatch,
agent-claude-dispatch, dispatch-replay, quota-reset, pr-autolabel,
pr-automerge, finalization, score, readiness, ci-failure-triage.

Retire on migration day (board-only, in this order):

1. `project-enforce-assignment.yml` — nags issues missing board membership.
   Disable first (it would flag everything mid-migration).
2. `project-route-issues.yml` — adds issues to boards by `component:*`.
3. `project-status.yml` — Todo→Done status automation.
4. `project-stub-fields.yml` — already paused; delete file + `set_project_fields.sh`
   references once Linear is source of truth for Phase/Area-style fields
   (or map them to Linear custom fields if owner wants them preserved —
   default: drop, see §3).

`create_issue.sh` / backlog-batch scripts that set Project fields need the
same treatment; grep `projectV2|addProjectV2` at execution time.

## 5. Method

Linear's GitHub importer handles issues + labels + milestones but NOT
Projects V2 custom fields or multi-board membership cleanly. Hence:

- Phase A (dry-run): Linear trial workspace → import ONE small repo slice
  (digibase board, 3 items) via the official importer; verify labels,
  states, assignees. Document gaps.
- Phase B: scripted migration (`gh api` read boards → Linear API write)
  only for what the importer drops AND owner wants kept (likely: nothing
  beyond issues themselves — boards are views, Linear teams reproduce them
  via label filters). Prefer importer + label-filter views over scripts.
- Phase C: freeze (no new issues for ~1h) → final import → disable the
  four workflows → archive (NOT delete) the 10 GitHub Projects → verify
  dispatch smoke (open test agent-task, confirm dispatch fires) →
  announce.

## 6. Rollback

- GitHub Projects are archived, not deleted, for 30 days (unarchive = instant
  rollback of the view layer).
- The four workflows are disabled via `workflow_dispatch`-guarded pause
  (same pattern as stub-fields `STUB_TSV_ENABLED`), not deleted, until the
  30-day window lapses — re-enable = rollback of automation.
- GitHub Issues are never mutated by the migration (importer copies), so
  dispatch keeps working throughout; rollback criterion: dispatch smoke
  fails post-migration.

## 7. Owner decisions needed (blocking execution)

1. Linear workspace: exists? plan tier (API + GitHub importer need paid
   tier for some features)? Who owns billing?
2. Linear API key storage: repo secret name + who provisions.
3. Team-per-module (§3) vs fewer teams — confirm.
4. Legacy Phase/Area/Kind fields: confirm DROP (recommended).
5. Migration freeze window: propose a quiet hour.
