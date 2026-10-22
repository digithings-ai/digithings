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

The probe also refuses to follow a redirect off `/healthz`: a redirect leaves the wake-hygiene
path, and if the target boots the container, the daily check starts costing money.

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
- every later failure is a **comment on that same ticket**, never a second ticket. At most one
  comment a day, and one straight away when the symptom changed;
- a green run says so once on the ticket, and the ticket stays open: a recurrence is commented
  there, not filed again. Each new failure opens a new episode, so each recovery is announced
  again;
- the symptom of the first failure is kept in the ticket and in the state file, because it is the
  record of what went wrong first. Later symptoms are in the comments;
- the ticket title names the symptom when it was filed, so the comments say which symptom is
  current.

The ticket is parented to DIG-2904 (the epic that owns the container), assigned to the DevOps
Lead, and carries the goal of DIG-2910.

Two things protect the "one ticket" rule:

- **A lost state file does not become a second ticket.** The state file is the first record of the
  ticket; when it is gone, the job looks the open `[run-watch] container-health:` ticket up on the
  board and comments on that one. A ticket whose comments are refused three times in a row (closed
  or deleted) is treated as unreachable and replaced, so a failure is never swallowed.
- **A create that failed after the create is still a ticket.** `dt-create-issue` checks the
  read-back after the POST, so a non-zero exit can mean the issue exists. The identifier in the
  output is the evidence, and it wins.

If there is no agent credential in the environment, the check still runs and still reports: a
failure that cannot be filed is logged as `not-filed`, never filed as Chris.

### What a run did

The action is written to the state file, to the log and to stdout:

| action | meaning |
|---|---|
| `filed` | a new ticket was filed |
| `commented` | the failure was written on the ticket that is already open |
| `throttled` | the failure is the same as yesterday's, and the ticket was already told today |
| `skipped` | there was nothing to say (no ticket open yet, or the comment did not land) |
| `not-filed` | the ticket could not be filed: no credential, or the create script refused |

## Install

Loading a launchd job is Chris's call, so the installer writes the plist and leaves the load to an
explicit flag.

```sh
scripts/container-health/install.sh --dry-run          # print the plist, change nothing
scripts/container-health/install.sh --status           # is it installed and loaded?
scripts/container-health/install.sh --install          # write ~/Library/LaunchAgents/com.digithings.container-health.plist
scripts/container-health/install.sh --install --load   # write it and load it (Chris's OK)
scripts/container-health/install.sh --unload           # unload the job
```

Point it at a dedicated clone on `develop`, not a working tree: the job runs every day, long after
the session that installed it is over, and it must find the same script it was installed with. The
installer refuses a linked worktree unless `--allow-worktree` is passed, warns when the checkout is
not on `develop`, lints the rendered plist with `plutil` before it puts it in place, keeps the
previous plist, and puts the previous plist back if the load fails.

Two things about launchd are worth knowing:

- **launchd does not re-read a plist that changes on disk.** A job that is already loaded keeps the
  definition it was bootstrapped with, so a re-install only takes effect after the job is booted
  out and loaded again. The installer says so when the job is already loaded.
- **Unloading is by service target**, not by path: a path-based bootout only removes a service that
  was bootstrapped from that exact file, and a job that keeps running with its plist deleted is the
  worst outcome. The installer checks the exit status and tells you when the job is still loaded.

The job runs every day at 07:40 local (`StartCalendarInterval`), does not run at load
(`RunAtLoad false`). A Mac that is asleep at 07:40 runs the check when it wakes up, so a closed
laptop can move the check by hours.

### The credential

The job reads the **agent** key `digithings/paperclip-api-key` from the login keychain, the same
way `com.digithings.it-watch` does, and exports it as `PAPERCLIP_API_KEY`. It has to be the agent
key: `dt-create-issue` asks `/api/agents/me` first and refuses anything else, and a board key
would file the ticket and the comments in Chris's name. The board key is not needed here and is not
read.

The credential is withheld when its rotation deadline (`digithings/paperclip-api-key-rotate-by`)
has passed, and also when the deadline is missing or is not a number. Both checks fail closed: a
deadline that cannot be read never exports the key. Rotating the credential is Security's call.

A missing credential does not stop the job: the check is read-only, so it keeps running and says
in the log that a failure cannot be filed.

## Run it by hand

```sh
scripts/container-health/container_health.py --dry-run   # probe and print, write nothing
scripts/container-health/container_health.py --json      # the report as JSON
scripts/container-health/container_health.py --status    # the last run from the state file
```

With `--json` the report on stdout stays machine readable and the action line goes to stderr.

State: `~/.config/digithings/state/container-health.json` (the last run, and the ticket it opened).
Log: `~/.config/digithings/logs/container-health.log`, one JSON line per run. launchd's own output
lands in `~/.config/digithings/logs/container-health/`.

## Two traps worth knowing

**The edge answers `Python-urllib/3.9` with `403`** (measured 2026-10-22), so a probe that does not
name itself reads the firewall and reports a failure that is not there. The probe sends
`User-Agent: digithings-container-health/1.0 (launchd, read-only)`, and there is a test that keeps
it from being dropped.

**`PAPERCLIP_API_URL` names the server, not the API path.** The kit's convention is a server root
(`http://127.0.0.1:3100`) and every script appends `/api` itself. A script that does not append it
posts its comments to a 404, and the ticket goes quiet without a word.

## The files

| | path | role |
|---|---|---|
| the probe | `scripts/container-health/container_health.py` | the check, stdlib only |
| the launchd unit | `scripts/container-health/com.digithings.container-health.plist.template` | copy of record for the unit |
| the installer | `scripts/container-health/install.sh` | renders, lints, installs, loads (only on an explicit flag) |
| the suite | `tests/scripts/test_container_health.py` | the checks, no network |
| the free guarantee | `apps/digithings-stack-cloudflare/src/wake-hygiene-free.test.js` | pins that a `/healthz` probe never fetches the container |

## Rollback

```sh
scripts/container-health/install.sh --unload
rm ~/Library/LaunchAgents/com.digithings.container-health.plist
```

Leave `~/.config/digithings/state/container-health.json` alone: it holds the link to the open
ticket. If it is deleted anyway, the job finds the open `[run-watch] container-health:` ticket on
the board and comments on that one, so no second ticket is filed. The log can go.

Unloading a launchd job is Chris's call too, so the `--unload` flag is the whole of it. The three
files in this repository are removed by reverting the commit that added them; do not roll this back
by naming a sha, because the branch this landed on is not `main`.
