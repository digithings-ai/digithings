# Container health check from the Mac (`com.digithings.container-health`)

Source: Paperclip issue DIG-2910, child of DIG-2904 "Cloudflare cost minimum".

The `smoke-stack` cron job probes the worker-only `/_stack/status` endpoints on graph, key and
search (DIG-2908, PR #5413). Those endpoints are answered by the stack Worker itself, so the probe
never boots the paid 6 GiB container. That is the right trade for a cost epic, and it leaves one
thing unsaid: the cron can see the Worker, never the container.

This check is the other half. It reads `/healthz` on the same three hosts from Chris's Mac, once a
day, under launchd.

## What it costs

Nothing, and that is the whole design. The stack Worker has wake hygiene
(`apps/digithings-stack-cloudflare/src/wake-hygiene.ts`): `/health` and `/healthz` are answered by
the Worker itself while the container sleeps, so a liveness probe can never boot the container and
bill the boot plus the whole `sleepAfter` tail. Traced on 2026-10-13: the stack was woken all night
by liveness probes and by internet scanners, and every wake billed the tail.

The body says which of the two answers came back:

| body | meaning | cost |
|---|---|---|
| `200 {"ok": true}` | the container was awake and the service answered | free |
| `200 {"status":"ok","service":"digithings-stack","container":"sleeping",…}` | the Worker is up, the container is asleep | free |
| anything else | a failure | free |

A sleeping container is **not** a failure. Waking it would cost money to answer a question the
daily check does not need answered, and the container sleeps on purpose.

## What a failure means

Only three things, and one of them is the class the cron cannot see:

1. the edge is not answering (DNS, TLS, timeout, a non-200 status);
2. the Worker is not answering;
3. the container is awake and the service inside it is broken — the deep proxy returned an error
   while the container was running.

`/_stack/status` cannot see (3): it asks the Worker, not the container.

## The ticket flow

One ticket per job, for the life of the job:

- the first failure files `[run-watch] container-health: <symptom>` through
  `kit/bin/dt-create-issue` (never a bare `POST /api/issues`: a bare POST writes no workspace
  fields and the issue lands on another issue's worktree, DIG-2040 and DIG-1635);
- every later failure is a **comment on that same ticket**, never a second ticket (at most one
  comment a day, and one straight away when the symptom changed);
- a green run says so once on the ticket, and the ticket stays open: a recurrence is commented
  there, not filed again.

The ticket is parented to DIG-2904 (the epic that owns the container) and assigned to the DevOps
Lead.

If there is no credential in the environment, the check still runs and still reports: a failure
that cannot be filed is logged as NOT FILED, never filed as Chris.

## Install

Loading a launchd job is Chris's call, so the installer writes the plist and leaves the load to an
explicit flag.

```sh
scripts/container-health/install.sh --dry-run          # print the plist, change nothing
scripts/container-health/install.sh --status           # is it installed and loaded?
scripts/container-health/install.sh --install          # write ~/Library/LaunchAgents/com.digithings.container-health.plist
scripts/container-health/install.sh --install --load   # write it and load it (Chris's OK)
```

Point it at a dedicated clone on `develop`, not a working tree: the job runs every day, long after
the session that installed it is over, and it must find the same script it was installed with. The
installer refuses a linked worktree unless `--allow-worktree` is passed, warns when the checkout is
not on `develop`, lints the rendered plist with `plutil` before it puts it in place, keeps the
previous plist, and puts the previous plist back if the load fails.

The job runs every day at 07:40 local (`StartCalendarInterval`), does not run at load
(`RunAtLoad false`), and reads the credential the way `com.digithings.it-watch` does: from the
login keychain, account `digithings/paperclip-api-key-board`, withheld when its rotation deadline
has passed. A missing credential does not stop the job: the check is read-only, so it keeps
running and says in the log that a failure cannot be filed.

## Run it by hand

```sh
scripts/container-health/container_health.py --dry-run   # probe and print, write nothing
scripts/container-health/container_health.py --json      # the report as JSON
scripts/container-health/container_health.py --status    # the last run from the state file
```

State: `~/.config/digithings/state/container-health.json` (the last run, and the ticket it opened).
Log: `~/.config/digithings/logs/container-health.log`, one JSON line per run. launchd's own output
lands in `~/.config/digithings/logs/container-health/`.

## One trap worth knowing

The edge answers `Python-urllib/3.9` with `403` (measured 2026-10-22), so a probe that does not
name itself reads the firewall and reports a failure that is not there. The probe sends
`User-Agent: digithings-container-health/1.0 (launchd, read-only)`, and there is a test that keeps
it from being dropped.

## The files

| | path | role |
|---|---|---|
| the probe | `scripts/container-health/container_health.py` | the check, stdlib only |
| the launchd unit | `scripts/container-health/com.digithings.container-health.plist.template` | copy of record for the unit |
| the installer | `scripts/container-health/install.sh` | renders, lints, installs, loads (only on an explicit flag) |
| the suite | `tests/scripts/test_container_health.py` | the checks, no network |

## Rollback

```sh
scripts/container-health/install.sh --unload
rm ~/Library/LaunchAgents/com.digithings.container-health.plist
rm ~/.config/digithings/state/container-health.json ~/.config/digithings/logs/container-health.log
```

Unloading a launchd job is Chris's call too, so the `--unload` flag is the whole of it. The three
files in this repository are removed by reverting the commit that added them; do not roll this back
by naming a sha, because the branch this landed on is not `main`.
