# In-session fresh-context review — PR #4740

- Reviewer: in-session fresh-context review (no prior repo context; diff via `gh pr diff`, file contents via `gh api` at merge commit)
- Subject: PR #4740 "fix(twelve-x): dedupe cross-source twin rows in the calendar read" — merge commit `4c9556e6b01ecb2a928348e12b59249ada5a8425`, base `develop`, head `fix/calendar-read-dedupe`, merged 2026-09-29
- Scope: this PR's diff only (4 files: `apps/dashboard/lib/twelve-x/fetch.ts`, `apps/dashboard/lib/twelve-x/fetch.test.ts`, `apps/dashboard/components/twelve-x/EventsTab.tsx`, `apps/dashboard/components/twelve-x/EventsTab.test.tsx`)
- Verdict: **APPROVE-WITH-MINORS**
- Severity counts: Critical 0 / Important 0 / Minor 2 / Trivia 2 (trivia file-only, not posted to PR)

## What the change does

`fetchCalendarWindow()` (`fetch.ts`) now passes raw `economic_calendar` rows through a pure order-preserving `dedupeCalendarTwins()` keyed on `event_date|country|normalized event_name`, preferring the gloomberb (`gb-`) twin. `EventsTab.tsx` drops the `continue` after exact-id registration so id-linked opinions also register name+date fallback keys (heals opinions orphaned when twin cleanup retires the exact `te-` id). 4 new fetch tests + 3 new EventsTab tests; 2 pre-existing fixtures renamed to avoid the new dedupe key.

## Verified clean (with commands run)

- Order preservation: node replica of `dedupeCalendarTwins` returns `[1,3,4]` for the twin-in-the-middle shape; matches `fetch.test.ts:973` expectation.
- gb-preference both positions + distinct-name/date untouched: covered by `fetch.test.ts:949` and `fetch.test.ts:961`; logic re-checked against `fetch.ts:431-444`.
- No pagination to break: `fetchCalendarWindow` query (`fetch.ts:462-471`) has no `.limit`/`.range` — filter-after-fetch cannot shrink a page.
- Opinion fallback parity: both snapshot and calendar sides normalize via the same `normalizeName` (`EventsTab.tsx:87-96`); replica confirms `US`→`us`, `EU`→`eu`, and identical CPI names match. Negative case covered by `EventsTab.test.tsx:249`.
- Null-safety of the EventsTab path: `normalizeName` tolerates non-strings and empty names hit `if (!full) continue` (`EventsTab.tsx:374-375`).
- CI signal: `dashboard / test` passed on the PR (`gh pr checks 4740`); PR body reports `fetch.test.ts` 55/55, `EventsTab.test.tsx` 18/18.
- Prior review thread already on the PR (data check: 5 of 8 `te-` snapshot ids deleted by twin cleanup; punctuation-strict key kept deliberately as the safe under-merge direction) — not re-litigated here.

## Findings

### M1 (Minor) — `calendarEventKey` throws on null `event_name` — `fetch.ts:385`

`fetch.ts:385`: `row.event_name.trim()` has no `?? ''` guard, while `row.country` on the same line does (`(row.country ?? '').trim()`). Node replica of the exact expression throws `TypeError` on `event_name: null`. Blast radius is small: `FxEconomicCalendarRow.event_name` is typed non-nullable (`types.ts:135-148`), so this fires only on contract-violating rows — but the asymmetry suggests the guard was intended on both. Suggested one-word fix: `(row.event_name ?? '').trim()`.

### M2 (Minor) — `isGloomberbRow` is case-sensitive — `fetch.ts:392`

`fetch.ts:392`: `(row.external_id ?? '').startsWith('gb-')` misses an uppercase `GB-` prefix (verified NO-MATCH via node replica). Unverified whether any uppercase-prefixed ids exist in production data — flagged as robustness, not a live defect. Suggested fix: `.toLowerCase().startsWith('gb-')`.

### T1 (Trivia, file-only) — same opinion renders on both twins when both rows are present — `EventsTab.test.tsx:269`

The exact-still-preferred test asserts the badge twice (`toHaveLength(2)`). Harmless in practice because `fetchCalendarWindow` dedupes before `EventsTab` ever sees twins; only a raw-twin prop (other callers/tests) double-shows. Documented behavior, no action needed.

### T2 (Trivia, file-only) — dedupe-before-narrow has a seconds-wide local-midnight straddle

Twins share `event_date` but `event_datetime_utc` can drift by seconds; if that drift straddled a viewer's local midnight, the kept (gb) twin could fall outside the local window while the dropped twin was inside. Window is ~4 seconds wide per event, unverified in prod data, and pre-existing windowing already has day-boundary behavior. Not actionable.

## Label

`reviewed:agent` applied (verdict APPROVE-WITH-MINORS, no Critical/Important findings).
