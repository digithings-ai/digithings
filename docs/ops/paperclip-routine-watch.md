# Paperclip routine-firing observer (`dt-routine-watch`)

Source: Paperclip issue DIG-1220. Filed by the twelve-x FDE on 2026-10-05: a Paperclip routine on
a `schedule` trigger fires and opens a run issue, and if it does not fire, **nothing is written
anywhere** — so "the routine went silent" and "the routine ran and found nothing" look identical
from outside. `nextRunAt` is the scheduler's claim about the future, not an observation of the
past, and nothing read it.

`scripts/dt-routine-watch` takes that claim and makes it falsifiable. It is a house local clock in
the same family as `dt-it-watch`, `dt-backup` and `dt-merge-queue`, and it is listed in
[HOUSEKEEPING.md](../agents/HOUSEKEEPING.md) so the gap is visible rather than assumed covered.

## What it does

Every tick (launchd, `StartInterval 300`):

1. Reads `GET /api/companies/{companyId}/routines` — the one call that lists every routine **and**
   embeds each `triggers[]` entry with `nextRunAt`, `lastFiredAt` and `lastResult`.
2. For each watched trigger, reads the scheduler's own `nextRunAt`. Until now is past
   `nextRunAt + graceSeconds`, the boundary is not judged at all and no per-routine call is made.
3. Once judged, it asks **another system** whether the firing is visible: the routine's run history
   `GET /api/routines/{id}/runs`, plus the trigger's `lastFiredAt` / `lastResult`.
4. Files a Paperclip issue per outcome that deserves one, assigned to the routine's own
   `assigneeAgentId`, parented to DIG-1220.

### Verdicts

| Verdict | What it saw | Pages? |
|---|---|---|
| `ok` | a run at the boundary with `source == "schedule"` or the watched `triggerId` | no |
| `coalesce` | the scheduler recorded the firing and a reason (`lastResult`), but produced no run | not alone — but 3 in a row pages |
| `missed` | the boundary passed and no run **and** no `lastFiredAt` | yes |
| `self-gap` | state says this clock itself has not run for `maxSelfGapSeconds` | yes, once |
| `api-gap` | the routines API stayed unreadable for `maxApiGapSeconds` | yes, once it can file again |

`coalesce` is not silence: Paperclip already records coalesced and skipped firings at trigger level
in `lastResult` (confirmed on the hourly DataTap routine: `"Skipped because a live execution issue
already exists"`). What it does *not* do is read that field, so a routine that stops producing work
while the clock keeps turning is invisible. `skipStreakBeforeFiling` closes exactly that.

The evidence test is deliberately strict: a run counts only when `triggerId` equals the watched
trigger or `source == "schedule"`. Manual probes carry `triggerId: null` and `source: "manual"`, so
they can never be mistaken for a firing — treating one as proof is precisely the false negative
DIG-1220 was filed for.

This follows `.github/workflows/feed_confirm_watchdog.yml` (twelve-x PR #291), which asks another
system's run history instead of writing its own heartbeat stamp: a stamp you write yourself is only
ever as reliable as the thing writing it. Hence it files on absence **and** on its own lookup
failing, and is silent only when a run exists inside the window.

## Why it runs on the operator's Mac and not in Cloudflare or Actions

Paperclip is loopback-only and private (`~/.paperclip/instances/default/config.json`:
`server.deploymentMode: local_trusted`, `server.exposure: private`, `server.bind: loopback`, host
`127.0.0.1`, port `3100`; the only listener on the host). No off-host clock — the `digithings-cron`
Worker, a GitHub Actions workflow, a tunnel — can read the routines API at all. launchd is also an
*independent* scheduler from Paperclip's own, which matters: a sibling Paperclip routine would share
the failure domain it is meant to watch.

## Scope: the watch list is derived from the board

With `"watchAllScheduleTriggers": true` the list is read from the routines API rather than
hardcoded: a routine created tomorrow is watched tomorrow, and a hand-maintained list would go
stale quietly — the same failure one level up. Included are active, non-archived, enabled
`schedule` triggers with a `nextRunAt`; excluded are paused routines, disabled or archived
triggers, non-schedule kinds, and triggers with no boundary (nothing to falsify). Measured
2026-10-06: 29 routines, 29 schedule triggers, **21 watchable** (8 paused).

Explicit `watch[]` entries may still be added for a note or a different owner; they win over the
derived entry for the same `(routineId, triggerId)` and are never double-watched. If neither
`watch` nor `watchAllScheduleTriggers` is set, or the derived list comes back empty, the script
**exits non-zero** — "the API answered and I found nothing" must never read as "everything is
fine".

## Known limits (accepted on the board, 2026-10-06)

- **Pages are unauthenticated and land as `local-board`.** Paperclip mints no durable credential for
  a non-interactive process: agent JWTs are run-scoped and expire, and `POST /api/board-api-keys` is
  account-level, which is Chris-only. Rather than borrow a run credential and misattribute the write,
  every issue this files names in its body which agent installed it and on which issue. The same gap
  affects the existing `dt-it-watch`. Tracked for Security/IT.
- **A powered-off host is unobservable.** Sleep is covered — `self-gap` catches it. A machine that is
  off cannot report its own silence, and closing that would mean exposing Paperclip off-host, which is
  a Chris-only decision and was explicitly declined for now.
- **One extra GET per judged boundary.** A tick with N boundaries past grace makes N+1 loopback
  requests: one routines list, one run history per judged boundary. Boundaries inside grace cost
  nothing.

## Two homes, one suite body

| | path | role |
|---|---|---|
| running copy | `~/paperclip-workspace/kit/bin/dt-routine-watch` | what launchd executes |
| repo copy | `scripts/dt-routine-watch` | the review surface, on `module/paperclip-board` |
| launchd unit | `infra/self-host/routine-watch/com.digithings.routine-watch.plist` | copy of record |

`tests/scripts/test_dt_routine_watch.sh` resolves the script from either home and fails loudly if
neither has it. Only the header comment differs between this repo's copy and the kit's
(`tests/dt-routine-watch-test.sh`) — the 15 checks are byte-identical. That is deliberate: a forked
suite would be a second thing to forget to update, which is the failure mode this issue is about.
**Until someone picks one canonical home, an edit to one copy must be made in the other.** The kit
has no git remote, so the repo copy is currently the only reviewed one.

## Install

```sh
cp scripts/dt-routine-watch ~/paperclip-workspace/kit/bin/dt-routine-watch   # if changing the running copy
cp infra/self-host/routine-watch/com.digithings.routine-watch.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.digithings.routine-watch.plist
launchctl kickstart -k gui/$(id -u)/com.digithings.routine-watch   # one real tick, then read the log
```

Config is `~/.config/digithings/routine-watch.json` (`api`, `companyId`, `parentIssueId`, `goalId`,
`defaultOwnerAgentId`, `graceSeconds`, `maxSelfGapSeconds`, `maxApiGapSeconds`,
`skipStreakBeforeFiling`, `watch`, `watchAllScheduleTriggers`); state is
`~/.config/digithings/routine-watch-state.json`, written atomically. Log:
`~/.config/digithings/routine-watch.log`.

Dry run against fixture files instead of the API:

```sh
bash tests/scripts/test_dt_routine_watch.sh              # the 15 checks, no network
scripts/dt-routine-watch --dry --config /path/c.json --state /tmp/s.json
```

## Rollback

```sh
launchctl bootout gui/$(id -u)/com.digithings.routine-watch
rm ~/Library/LaunchAgents/com.digithings.routine-watch.plist
rm ~/.config/digithings/routine-watch.json ~/.config/digithings/routine-watch-state.json
git -C ~/paperclip-workspace/kit revert 8d4eda7
```