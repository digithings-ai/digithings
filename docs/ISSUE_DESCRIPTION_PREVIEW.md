# Issue descriptions: the 1,200-character preview

**Status:** current. Owner: IT support. Origin: DIG-2478 (2026-10-08).

## The one thing to know

An issue description longer than **1,200 characters** is stored in full. It is
also shown in full on the issue page. It is shown as the **first 1,200
characters only** in every list: the board, the inbox, the CLI listing, and any
script that calls `GET /api/companies/{id}/issues`.

The list response says so, in a field almost nobody reads:

```json
{ "description": "<first 1200 characters>",
  "descriptionTruncated": true }
```

Nothing is marked in the text itself. A brief that stops mid-table looks exactly
like a brief that was written that way.

## Where the number comes from

`@paperclipai/server/dist/services/issues.js`:

```js
const ISSUE_LIST_DESCRIPTION_MAX_CHARS = 1200;
const ISSUE_LIST_DESCRIPTION_MAX_BYTES  = ISSUE_LIST_DESCRIPTION_MAX_CHARS * 4;
```

`issueListSelect` (used by `listIssues` and `listBlockedInboxIssues`) selects
`substring(description from 1 for 4800)` as base64 plus the
`descriptionTruncated` boolean. `GET /api/issues/{id}` selects the whole row.

Measured on the live company, 2026-10-08:

| issue | list row | `GET /api/issues/{id}` | DoD intact |
| --- | --- | --- | --- |
| DIG-1648 | 1,200 | 7,416 | yes |
| DIG-1569 | 1,200 | 2,968 | yes |
| DIG-2325 | 1,200 | 3,386 | yes |
| DIG-2327 | 1,200 | 3,092 | yes |
| DIG-2350 | 1,200 | 3,729 | yes |

So the wall at 1,200 is a **projection**, not a storage limit. 1,801 issues have a
description of exactly 1,200 characters in the list; none of them has a stored
description that was cut. There is no backlog to restore.

## How to file a brief that stays readable

1. **The first 1,200 characters carry the DoD, the constraints and the first
   acceptance criterion.** That is the window a reader in a list gets.
2. Evidence tables, long method, history and links go after it, or in the first
   comment. Comments are not capped (an 8,438-character comment round-trips
   byte-identical).
3. `~/paperclip-workspace/kit/bin/dt-create-issue` warns on stderr when a
   description is past the cap and prints the stored length in its read-back:

   ```
   dt-create-issue: WARNING --description is 5977 characters, past the
     1200-character list preview.
   DIG-2484  pref=isolated_workspace  settings.mode=isolated_workspace  ws=None
     description=5977/5977 chars stored
   ```

   `--strict-description-length` refuses instead of warning (exit 1, nothing
   written).

## How to read a description

- Full text: `GET /api/issues/{id}`.
- List row: `description` is a preview. Check `descriptionTruncated` before you
  quote it, and never measure or diff a description you got from a list row.
- A script that needs the brief needs the single-issue GET. `dt-it-watch` and
  `dt-relay` read early markers (`Signature:`, `Interaction id:`, `Level:`) out
  of list rows, which sit inside the window and are safe today; anything that
  needs the tail must not do that.

## The other silent field

List rows report `executionWorkspaceSettings: null` for issues whose stored row
has `{"mode": "isolated_workspace"}`. The list projection does not carry that
column. A read-back taken from a list row therefore reports a stored `null`
against a sent `isolated_workspace`, which is what DIG-2478 DoD 4 was about.
`dt-create-issue` reads back with `GET /api/issues/{id}` for this reason.

## Related

- Runbook entry `issue_description_preview_capped_at_1200` in
  `~/paperclip-workspace/it/runbook.md`.
- Client test `kit/tests/test_dt_create_issue_description_cap.py`.
- Upstream decision on an in-band truncation marker: filed for the platform.