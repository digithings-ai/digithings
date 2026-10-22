# Installing the dt-broker

The broker is a host daemon that runs as the `_dtbroker` account and holds the four
GitHub App private keys. A seat process never holds a long-lived GitHub credential:
it asks the broker over a unix socket, and the broker mints an installation token
scoped to the one repository the ticket is about, for the length of the run.

Everything on this page needs `sudo`, so it is Chris's to run. The seat that wrote
the code ([DIG-4805](/DIG/issues/DIG-4805)) does not run any of it and cannot.

## 1. The account and the group

DIG-4804 owns the account. If it has not been created yet, these are the commands:

```bash
sudo dseditgroup -o create _dtseats
sudo dseditgroup -o edit -a _dtbroker _dtseats
sudo dseditgroup -o edit -a chrisstefan _dtseats
```

`_dtseats` is the group that decides who may talk to the socket. A seat process is
in it; so is the daemon.

The account itself is macOS's own, not Linux's: **`useradd` does not exist on this
platform** (`zsh: command not found: useradd`). The supported way is:

```bash
sudo sysadminctl -addUser _dtbroker \
  -shell /usr/bin/false \
  -home /Users/_dtbroker \
  -fullName "digithings broker"
```

macOS asks for an administrator password, and the Terminal needs Full Disk Access
for it. If `sysadminctl` is not allowed, the directory services equivalent is:

```bash
sudo dscl . -create /Users/_dtbroker RecordName _dtbroker
sudo dscl . -create /Users/_dtbroker RealName "digithings broker"
sudo dscl . -create /Users/_dtbroker UserShell /usr/bin/false
sudo dscl . -create /Users/_dtbroker NFSHomeDirectory /Users/_dtbroker
sudo dscl . -create /Users/_dtbroker UniqueID 499      # a free uid, 500 and up
sudo dscl . -create /Users/_dtbroker PrimaryGroupID 499
```

Pick a `UniqueID` that is free (`dscl . -search /Users UniqueID 499`) and matches
the `PrimaryGroupID`. The account has no shell: it runs the daemon, nothing else.

The home directory is traversable but not listable, so a seat process can reach the
socket inside it and cannot read what else is there:

```bash
sudo chmod 0711 /Users/_dtbroker
sudo install -d -o _dtbroker -g _dtseats -m 0770 /Users/_dtbroker/run
sudo install -d -o _dtbroker -g _dtseats -m 0750 /Users/_dtbroker/state
sudo install -d -o _dtbroker -g _dtbroker -m 0700 /Users/_dtbroker/keys
```

## 2. The keys

The four Apps are created by Chris in the GitHub settings and installed on all four
repositories of the `digithings-ai` organization: `digithings-seat`, `digithings-ci`,
`digithings-queue`, `digithings-review`. The private keys go to the broker account
and to nowhere else:

```bash
sudo install -o _dtbroker -g _dtbroker -m 0600 digithings-seat.pem   /Users/_dtbroker/keys/digithings-seat.pem
sudo install -o _dtbroker -g _dtbroker -m 0600 digithings-ci.pem      /Users/_dtbroker/keys/digithings-ci.pem
sudo install -o _dtbroker -g _dtbroker -m 0600 digithings-queue.pem   /Users/_dtbroker/keys/digithings-queue.pem
sudo install -o _dtbroker -g _dtbroker -m 0600 digithings-review.pem /Users/_dtbroker/keys/digithings-review.pem
```

The App ids and the installation ids are not secrets. They go in the policy file:

```bash
sudo install -o _dtbroker -g _dtseats -m 0640 policy.json /Users/_dtbroker/policy.json
```

`policy.example.json` next to this file is the shape. The `seats` map binds each
Paperclip agent id to a class; a seat with no entry is refused.

## 3. The rollback flag

The flag says which way the authentication goes: `app` (the broker mints the token)
or `host` (the seat falls back to the host's own `gh` credentials, as it does today).

The directory belongs to root, so a seat process cannot write the flag even if it
wants to turn the broker off:

```bash
sudo install -d -o root -g wheel -m 0755 /Users/_dtbroker/.config /Users/_dtbroker/.config/digithings
echo app | sudo tee /Users/_dtbroker/.config/digithings/github-auth-mode >/dev/null
sudo chmod 0444 /Users/_dtbroker/.config/digithings/github-auth-mode
```

To roll back to today's behaviour:

```bash
echo host | sudo tee /Users/_dtbroker/.config/digithings/github-auth-mode >/dev/null
```

and back again:

```bash
echo app | sudo tee /Users/_dtbroker/.config/digithings/github-auth-mode >/dev/null
```

A flag that is missing, unreadable or says something else reads as `app`: the broker
stays in charge, and a seat cannot turn it off by damaging the file.

## 4. The daemon

The package is installed from this repository, owned by root and readable by the
daemon:

```bash
sudo install -d -o root -g wheel -m 0755 /usr/local/lib/dt-broker
sudo cp -R scripts /usr/local/lib/dt-broker/
sudo install -o root -g wheel -m 0755 scripts/dt-broker /usr/local/lib/dt-broker/scripts/dt-broker
```

The plist runs `/usr/bin/python3`, which on macOS is **Python 3.9** — the daemon has
to import under it, so the code stays 3.9-compatible (no `X | Y` in a runtime
expression, `Optional[...]` in the type aliases). A newer interpreter is fine too,
but the plist names the system one, so the system one has to work.

The `dt-broker` command itself has to be on the PATH of the seat processes, not
only on the daemon's: the git credential helper and `dt-broker seat-env` are run by
a seat, by name. `/usr/local/lib/dt-broker/bin` is that directory (see §5), so:

```bash
sudo install -d -o root -g wheel -m 0755 /usr/local/lib/dt-broker/bin
sudo ln -sf /usr/local/lib/dt-broker/scripts/dt-broker /usr/local/lib/dt-broker/bin/dt-broker
```

The plist next to this file is the copy of record. It is installed as a system
daemon:

```bash
sudo install -o root -g wheel -m 0644 com.digithings.dt-broker.plist /Library/LaunchDaemons/com.digithings.dt-broker.plist
sudo launchctl bootstrap system /Library/LaunchDaemons/com.digithings.dt-broker.plist
```

`launchctl` is Chris's: no seat bootstraps or reloads a launchd job.

The daemon answers on `/Users/_dtbroker/run/dt-broker.sock`, mode 0660, group
`_dtseats`.

## 5. The gh shim

The shim wraps the seat's `gh` and hands the call to the guard, which hands it to the
real `gh`. The chain is the point: the guard is never skipped.

```bash
sudo install -d -o root -g wheel -m 0755 /usr/local/lib/dt-broker/bin
sudo tee /usr/local/lib/dt-broker/bin/gh >/dev/null <<'SH'
#!/bin/sh
exec /usr/bin/python3 /usr/local/lib/dt-broker/scripts/dt-broker gh "$@"
SH
sudo chmod 0755 /usr/local/lib/dt-broker/bin/gh
```

### The seat's `gh` is a shell function, not a PATH entry

This is the part that is easy to get wrong. The seat's shell hook
(`~/paperclip-workspace/tools/seat-gh-guard/shell-guard.sh`) defines

```sh
gh() { "$_SEAT_GH_GUARD" "$@"; }
```

and a shell function wins over the PATH, so a shim that is only on the PATH is
never called in a seat shell. The hook is Board-owned and this repository does
not change it: the change is one line in that file, and it is Chris's to make.

```sh
# before
_SEAT_GH_GUARD=/Users/chrisstefan/paperclip-workspace/tools/seat-gh-guard/bin/gh
# after
_SEAT_GH_GUARD=/usr/local/lib/dt-broker/bin/gh
```

The guard is still in the chain: the shim hands the call to
`~/paperclip-workspace/tools/seat-gh-guard/bin/gh`, and that hands it to the real
`gh`. A shim pointed at `/opt/homebrew/bin/gh` refuses the call rather than making
it, so a mistake here fails closed.

The zsh aliases in the same hook (`/opt/homebrew/bin/gh` and `/usr/local/bin/gh`
to `$_SEAT_GH_GUARD`) then route through the shim as well, which is what they are
for.

**This change is for the seat shells, not for Chris's own shell.** The hook is
loaded by the seat runs. If Chris's own interactive shell loads it as well, keep
`_SEAT_GH_GUARD` pointing at the guard in his shell: in `app` mode the shim
refuses a call that has no run credential (exit 66), and a person at the keyboard
has none, so routing his `gh` through the shim would break his own commands.
The seat shells are the ones that get the broker.

### The shim asks the broker on one socket, and it needs a run credential

Two things about the shim are fixed in the program and not configurable, on
purpose:

- **The socket is `/Users/_dtbroker/run/dt-broker.sock`**, the same path the daemon
  binds. There is no environment variable for it: a seat that named its own socket
  would have asked its own broker for a token, and the one-repository wall, the
  run-scoped lifetime and the audit trail would have gone with it. So the daemon
  has to bind that exact path, or the seats cannot reach it.
- **The run credential decides.** In `app` mode the shim mints only for a call
  that carries a run credential (`PAPERCLIP_API_KEY`), which the broker verifies
  against the Paperclip API for every mint. A call with no run credential is
  refused with exit 66 instead of being passed through with the host's own
  credential. `host` mode passes everything through unchanged.

### The PATH, for the calls that are not a seat shell

A script that calls `gh` by name, without the seat's shell hook, reads the PATH.
`/usr/local/lib/dt-broker/bin` has to come before
`/Users/chrisstefan/paperclip-workspace/tools/seat-gh-guard/bin` and before
`/opt/homebrew/bin`. The seat runs inherit their PATH from the Paperclip
adapter, so the entry belongs in the adapter's environment.

### The git credential helper

`gh` is only half of it: a seat also pushes with `git`. `dt-broker seat-env`
writes a `gitconfig` for the run and points `GIT_CONFIG_GLOBAL` at it, and that
file has to carry **an empty `helper =` line** before the broker's helper:

```ini
[credential "https://github.com"]
	helper =
	helper = !/usr/local/lib/dt-broker/bin/dt-broker git-credential
```

Git builds the helper list in config-file order and the **system** config on this
Mac sets `credential.helper = osxkeychain`
(`/Library/Developer/CommandLineTools/usr/share/git-core/gitconfig`). Without the
empty line that system helper wins, git never asks the broker, and the push goes
out under Chris's own personal credential. The reset line is what makes the
broker's helper the only one; `dt-broker seat-env` writes it.

The helper is named with its absolute path for the same reason `dt-broker` has to
be on the PATH: git runs the helper with a sanitized environment, and a seat that
cannot find `dt-broker` silently falls back to the host credential.

Nothing else is needed here: the seat does not configure git by hand, it runs
`eval "$(dt-broker seat-env)"` (see `docs/ops/dt-broker.md`).

## 6. Checking that it is up

```bash
sudo -u _dtbroker /usr/local/lib/dt-broker/scripts/dt-broker --socket /Users/_dtbroker/run/dt-broker.sock health
```

The answer is a JSON object with the last health tick. The tick counts consecutive
failures; after two of them the daemon writes `/Users/_dtbroker/state/alert.json`.
The daemon never posts to the Board itself: it has no credential to post with, and
it does not sign anything in Chris's name. The alert file is what a Board-side
watcher reads.
