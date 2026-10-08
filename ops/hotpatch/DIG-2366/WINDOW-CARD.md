# DRAFT — production window card for DIG-2366. NOT SENT.

> **Status: drafted, unsent.** DevOps does not own this decision. It is staged here
> so the mechanism half of the decision is paste-ready the moment Chris books a
> window. Nothing in this file has been sent to Chris, and no production card has
> been opened by DIG-2366.
>
> **This is not a new window.** Per the CEO's scope note on DIG-2232 (2026-10-08
> 02:11Z): *"No new production card. I deliberately did not open one. This card
> already carries the mechanism for the same host, so DIG-871 folds in here rather
> than putting a second production change in front of Chris."* This draft is the
> **bundle half of the single existing window** — the answer to "how does the fix
> reach the running instance", which is the question already on card `b94459a7`.
> It rides alongside the DIG-871 / DIG-1663 checkout hunk: **one booked window,
> one restart, one rollback, for all of it.**
>
> Decided by: **Chris.** Recommended by: CTO + CEO (level 2 of 2, recommendation
> `fork-and-upgrade` corrected to *fork patch as a revertible hotpatch on the
> pinned 2026.1001.0 bundle*, plus a fork PR for durability — not a CLI upgrade).
> Implemented by: DevOps.

---

## 1. The change

Two files in the pinned bundle. Nothing else.

```
~/.paperclip/cli/installs/npm/2026.1001.0/node_modules/@paperclipai/server/dist/
```

| File | Fault | Change |
|---|---|---|
| `services/documents.js` | 1 — a write addressed by a **document id** finds no row (every lookup filters `issue_documents.key` only), creates a **second** document keyed by the uuid, answers **201**. That shadow row is what makes later reads disagree. | Add `resolveIssueDocumentKey()`: a `:key` that parses as a uuid is resolved through `documents.id`, so it lands on the original row. An id belonging to no document of this issue is refused **409** naming `details.resolvedBy: "documents.id"`. Applied to all 7 service sites. Bulk import untouched. |
| `routes/issues.js` | 2 — `reviewInteractionId` is accepted by `updateIssueSchema` and read by nobody outside an `in_review` transition, so it was dropped behind a **200 with an empty `changes` map**. | 17-line guard: **422** with `details.code: "review_interaction_requires_in_review"` and the accepted kinds named, when `reviewInteractionId` is present without `status: "in_review"` in the same request. The field is **not** stripped from the schema; it still works during a transition. |

- Diff: `DIG-2366.compact.patch` — 147 lines, **65 insertions, 8 deletions**, two files.
- Bytes and digests: `SHA256SUMS`. Originals kept beside the patched copies under `stage/bundle/dist/__original__/`.
- Total diff: **one helper plus seven call sites, and one guard.** No schema change, no migration, no data change.

**Explicitly not in this window:** no CLI upgrade, no `install`/`update`, no change to `~/.paperclip/cli/current`, no change to the other ten locally-modified bundle files, and no attempt at the six already-orphaned rows from DIG-2232 — they become *addressable*, which is what makes them repairable, but repairing them is a separate data operation.

## 2. Expected interruption

**Short, and the runs survive it.** The service is a launchd agent,
`ing.paperclip.paperclipai` (`KeepAlive true`, `ThrottleInterval 5`).

| | |
|---|---|
| Restart route | `paperclipai service restart` — the CLI's own help calls it *"Hot-restart the service while preserving active agent runs"*. |
| Measured behaviour | `hot-restart-report.json` from a real restart on 2026-10-08: `previousServerPid 27911 → newServerPid 28379`, `drainRequired: true`, `completedAt − requestedAt = **4.3s**`, `lostRunIds: []`. |
| What an agent sees | In-flight runs drain, then are adopted or finalized. **No run is lost.** Board UI and API are unreachable for roughly 4–5s. |
| Blast radius | One local instance on `127.0.0.1:3100`. Nothing else, because nothing else consumes this tree. |
| If it goes wrong | `KeepAlive true` means launchd respawns the server within 5s regardless. The worst case is a server that keeps coming back on the same bytes. |
| Stop/start instead | `service stop` + `service start` is the cold route. It costs a full boot (~12–32s measured on an identical clone) instead of 4s, for no benefit. Do not use it. |

**Applying while the server runs is safe**, provided the restart follows immediately: Node has already loaded the old bytes into memory, so the running process keeps serving current behaviour and never re-reads the file. The gap between apply and restart is exactly today's behaviour, not a new risk. Do **not** kill the process by hand — use `service restart`, which drains.

## 3. Verification

`verify.sh` is read-only and exits non-zero on any failure. Run it **before** applying, **after** applying, and again after any rollback.

```
ops/hotpatch/DIG-2366/verify.sh
```

It checks three independent things: (1) **bytes** — sha256 of each live file classified `PATCHED` / `BASELINE` / `UNKNOWN`; (2) **parse** — `node --check` on both files; (3) **fault markers** — `resolveIssueDocumentKey` present with `eq(documents.id, key)`, and `review_interaction_requires_in_review` present.

Then prove the behaviour on the live instance, on a scratch issue — the same probes the rehearsal ran:

```bash
ISSUE=<scratch issue id>
# Fault 1: read and write addressed by a document id must not fork a row
curl -s "http://127.0.0.1:3100/api/issues/$ISSUE/documents/spec" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["id"], d["latestRevisionId"])'
# -> then GET and PUT that id back; expect 200 on the same row, and a 409 naming documents.id for an id that is not a document of this issue
# Fault 2: reviewInteractionId without status: in_review must be refused
curl -s -o /dev/null -w '%{http_code}\n' -X PATCH "http://127.0.0.1:3100/api/issues/$ISSUE" \
  -H 'content-type: application/json' \
  -d '{"reviewInteractionId":"00000000-0000-4000-8000-000000000000"}'
# -> 422 with details.code = review_interaction_requires_in_review
# And the non-regression: a plain PATCH of a title must still be 200 with a non-empty changes map.
```

Both failure modes were proved **before** and **after** on a full isolated copy of this exact bundle (port 3199, its own postgres): control answered 201-with-a-second-row and 200-with-empty-changes; patched answers 409 and 422 with one row and an unchanged title. Transcripts in `rehearsal/results/`.

**The one step rehearsal cannot prove on this host is the restart itself** — I did not restart the live server, by instruction. The 4.3s drain-aware figure comes from a real restart this platform already performed, not from a rehearsal.

## 4. Rollback

Restores the original bytes and re-verifies sha256, so the operator proves the restore rather than assumes it.

```
ops/hotpack/DIG-2366/rollback.sh && paperclipai service restart
```

Restore source, sha256-checked against the recorded baseline before it is used, so a wrong or truncated source cannot be restored silently:

1. `rollback-originals/` — the live bytes captured by `apply.sh` at apply time. **This is the right one.**
2. `baseline/` — the byte-for-byte copies taken before any work started, on 2026-10-08 01:48Z.

A rollback leaves the live tree **byte-identical to how it was found** (`bd824c4d…`, `b5df4341…`), which is verifiable with `verify.sh` printing `BASELINE` for both.

**Note on `routes/issues.js`:** it already carried a local patch of unknown authorship when I found it (mtime Oct 7 03:45 against an install of Oct 4 01:11 — it is one of twelve modified bundle files). So its rollback target is *the current live bytes*, not the npm tarball. Restoring it returns it to the state I found, which is correct and is what the digests record, but it is **not** a pristine npm file. `services/documents.js` was clean as found and rolls back to pristine npm bytes.

## 5. What survives an upgrade

Nothing inside `~/.paperclip/cli/installs/`. An upgrade silently deletes local patches — this has already happened once on this box, which is why the mechanism is a tripwire rather than an overlay:

- **Source of truth** is this directory in the repo, not the install tree.
- `reapply.sh` **never writes to the install dir.** It reads the live version from `install.json`, classifies each live file, copies the live bytes to a scratch dir, and re-derives the patch against them. It returns `0` only if the patch is already applied *or* re-derives to byte-identical output. Anchor drift returns `3` — **nothing applied, a human must re-derive**. Re-derives but differs returns `4` — **a human must re-read the diff**. Version drift returns `3` unless `--allow-version-drift`.
- **Who runs it:** DevOps, after any CLI install/upgrade, before agents resume work. It is a check, not a patcher. Full disclosure: there is no install hook to hang this on — `~/.paperclip/cli/` has no hook surface at all — which is precisely why a hook living in the install tree would die with the upgrade it exists to survive.

## 6. The decision

Chris answers. Nothing in this bundle reaches the running instance until he does.

1. Book the single window that already exists on card `b94459a7` — the DIG-2232 window, with the DIG-871 / DIG-1663 checkout hunk in the same restart.
2. Confirm the window, and DevOps runs §3 verify → §1 apply → `service restart` → §3 verify.
3. If anything in §3 fails, §4 rollback. One restart either way.