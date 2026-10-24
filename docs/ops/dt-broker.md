# The dt-broker

The broker hands a seat run a GitHub credential for exactly as long as the run lasts,
and for exactly one repository: the one the ticket is about.

Three rules, and everything else follows from them:

1. **One repository per token.** A token is minted for the repository the run's
   ticket names, never for the organization, never for a second repository.
2. **Only while the run is running.** The broker checks the run's status with
   Paperclip before it mints anything, and revokes what it minted when the run ends.
3. **Never a token in a log.** What is written down is the last four characters.

The point of the broker is that a seat process never holds a long-lived GitHub
credential. The four App private keys live with the `_dtbroker` account, and a seat
gets a short-lived installation token over a unix socket, for one repository, for the
length of one run.

## The parts

| Part | Where | What it does |
| --- | --- | --- |
| The daemon | `scripts/dt_broker/`, installed as `com.digithings.dt-broker` | Answers on a unix socket. Mints, refuses, revokes. |
| The policy | `/Users/_dtbroker/policy.json` | Who may have what, from which App, where. Chris owns it. |
| The keys | `/Users/_dtbroker/keys/*.pem` | The four App private keys. 0600, owned by `_dtbroker`. |
| The flag | `/Users/_dtbroker/.config/digithings/github-auth-mode` | `app` or `host`. The rollback switch. |
| The shim | `/usr/local/lib/dt-broker/bin/gh` | Wraps the seat's `gh`, hands the call to the guard. |
| The credential helper | `dt-broker git-credential` | What `git` asks when it wants to push. |

The daemon listens on `/Users/_dtbroker/run/dt-broker.sock`, mode 0660, group
`_dtseats`. The ticket's example was `/var/run/dt-broker.sock`; `/var/run` belongs to
root and a daemon running as `_dtbroker` cannot write there, so the socket lives in
the broker account's own run directory, which the daemon creates for itself.

## What a seat run does

```bash
eval "$(dt-broker seat-env)"          # the git config, the gh config, the identity
export PATH="/usr/local/lib/dt-broker/bin:$PATH"   # the shim, ahead of the real gh
git commit -m "..." -m "$(dt-broker trailers)"
```

`seat-env` writes three things:

- `GIT_CONFIG_GLOBAL` points at a fresh file with the credential section in it:

  ```ini
  [credential "https://github.com"]
  	helper =
  	helper = !/usr/local/lib/dt-broker/bin/dt-broker git-credential
  ```

  The **empty `helper =` line is not decoration**: git builds the helper list in
  config-file order, and the system config on this Mac sets
  `credential.helper = osxkeychain`. Without the reset, that system helper is
  consulted first, wins, and the push goes out under the host's own credential. The
  reset empties the list so the broker's helper is the only one. The seat's own git
  configuration is not read either, so a credential saved there is not used.
- `GH_CONFIG_DIR` points at an empty directory, so the `gh` that runs reads no
  configuration and no credential of the host's.
- `GIT_AUTHOR_NAME`, `GIT_AUTHOR_EMAIL`, `GIT_COMMITTER_NAME` and `GIT_COMMITTER_EMAIL`
  are the bot identity of the seat's App: `digithings-seat[bot]`, with the
  `BOTID+login@users.noreply.github.com` address, so GitHub attributes the commit to
  the bot and not to a person.

The helper is named with its absolute path, and `dt-broker` has to be on the seat's
PATH (`/usr/local/lib/dt-broker/bin/dt-broker` is a symlink to the script). Git runs
a helper with a sanitized environment: a helper that cannot be found is not an
error, it is a fall-through to the next helper, and the next one is the host's
credential.

`dt-broker trailers` prints the four trailers a seat commit carries:

```
Paperclip-Agent-Id: <agent uuid>
Paperclip-Run-Id: <run uuid>
Paperclip-Seat: <the seat's App>
Paperclip-Run: <run uuid>
```

`Paperclip-Agent-Id` and `Paperclip-Run-Id` are what the merge queue reads.
`Paperclip-Seat` and `Paperclip-Run` are what the ticket asked for. Both spellings
are written, so neither tool has to guess.

The commits are not signed. The ticket does not ask for them to be, and a signed
commit is a key the seat would have to hold.

## The gh shim

The shim is the seat's `gh`. It does four things, in this order.

**It never bypasses the guard.** The shim hands the call to
`~/paperclip-workspace/tools/seat-gh-guard/bin/gh`, which hands it to the real `gh`.
A shim configured to point at `/opt/homebrew/bin/gh` is a refusal, not a
configuration, and the guard's path is a constant of the program, not something the
environment can move: a seat process cannot point the shim at its own program.
A guard that is not there at all is exit 70, never a fall-through to the real
`gh`.

**It is in the chain by the seat's shell hook, not by the PATH alone.** The seat's
`gh` is a shell function (`gh() { "$_SEAT_GH_GUARD" "$@"; }`) in
`~/paperclip-workspace/tools/seat-gh-guard/shell-guard.sh`, and a function wins over
the PATH. So the hook's `_SEAT_GH_GUARD` has to point at the shim, and the shim points
back at the guard. That hook is Board-owned; the change is one line, and it is
Chris's to make (`infra/self-host/dt-broker/INSTALL.md` has the exact diff). The PATH
entry matters for the calls that are not a seat shell: the shim's directory comes
before the guard's directory and before `/opt/homebrew/bin`.

**It expands `@path` field values.** `gh api -F body=@file` reads the file, but
`gh api -f body=@file` sends the literal text `@file`. A seat that wrote `-f` meant
to send the body and sent the path instead, and the comment on the pull request was
damaged (DIG-4914). The shim now reads the file for both spellings and sends its
content. Only the expanded field changes shape — it is sent as a raw field, so
the content is never read again as a path. The other fields keep the flag they
were written with, so `gh`'s own typed fields (`true`, `42`, `{owner}`) still mean
what they mean.

**It refuses a body that is a path.** A field called `body` whose value looks like a
path to a file that exists is refused instead of posted. The cheap rule catches the
mistake even where the expansion does not apply, and it catches a relative path
(`review.md`) as well as an absolute one.

**It refuses a pull request outside the organization.** `gh pr create` against a
repository that is not in `digithings-ai`, `gh api repos/{owner}/{repo}/pulls`
outside it, and the GraphQL `createPullRequest` mutation are all refused, with the
reason on stderr. The endpoint is looked for in **every** argument, not only the
first one, so `gh api -X POST repos/someone-else/their-project/pulls` is refused
as well; a mutation hidden in an `--input` file is read and refused too. This
holds in both authentication modes, and for a process that is not a seat run: no
upstream pull request, ever, under any identity.

The organization is compared without regard to case, and the path is resolved
before it is compared, so `REPOS/evilorg/evil/pulls` and
`repos/digithings-ai/../evilorg/evil/pulls` are refused as well.

**It asks the broker on the broker's socket, and nowhere else.** The socket path is
a constant of the program (`/Users/_dtbroker/run/dt-broker.sock`), not something
the environment can move: a seat that named its own socket would have asked its own
broker for a token, and the one-repository wall, the run-scoped lifetime and the
audit trail would have gone with it. The answer must also be about this run — the
broker returns the run it minted for, and the shim refuses an answer about
another run.

**It decides on the credential, not on the markers.** What tells the shim that this
is a seat run is the run credential in the environment (`PAPERCLIP_API_KEY`), which
the broker verifies against the Paperclip API for every mint. The seat markers are
not the switch: a process that has no run credential is refused in `app` mode
(exit 66) instead of being passed through with the host's own credentials.

**It never hands the host's credentials through.** In `app` mode the shim removes
`GITHUB_TOKEN`, `GH_ENTERPRISE_TOKEN`, `GITHUB_ENTERPRISE_TOKEN` and `GH_HOST`
from the environment, points `GH_CONFIG_DIR` at an empty directory it makes itself,
and sets `GH_TOKEN` for that one call. The host's `~/.config/gh` is never read and
the host's token is never inherited. `--hostname` is refused, so a minted token
cannot be presented to a host nobody controls, and `gh auth token` is refused, so
it cannot be printed out of the guard's chain.

In `app` mode the shim asks the broker for a token, sets `GH_TOKEN` for that one
call, and removes the host's credentials from the environment, so the call cannot
fall back to them. In `host` mode the call is passed through unchanged.

The refusals are the same in both modes. The rollback turns off the broker, not
the rules.

## The credential helper

`git` asks the helper for a credential when it pushes. The helper refuses a host
that is not `github.com` and a repository outside the organization, then asks the
broker for a token scoped to the ticket's repository. The answer is
`username=x-access-token` and the token, on stdout, for git.

When the credential is erased, the token behind it is revoked.

In `host` mode the helper refuses (exit 76) and writes no git configuration at
all: the rollback restores today's behaviour, and today's behaviour is the host's
own credential. A seat that still asks the broker in `host` mode would be running
half a rollback.

## What this control does not do

The broker governs the calls a seat run makes through `gh` and through `git`. It
does **not** keep a token out of the seat's hands. The credential helper has to
hand the token to `git` on stdout, because that is the only way git
authenticates, and a process that can run `git` can run the helper and read what
it prints. The guard governs `gh`; it is not a wall around a token a process
already holds.

What the token is worth is what limits the damage:

- it is scoped to one repository, so it is worth nothing against another one;
- it carries only the permissions of the seat's class, and `secrets` is never one
  of them;
- GitHub stops honouring it within the hour, whatever the seat does with it;
- the daemon revokes it when the run ends.

And what refuses a merge is not the broker. `develop` is agent-maintained: the
merge queue is what merges into it, a pull request needs an approval from a seat
that did not write it, and `main` is Chris's alone. The broker makes the
credential a seat holds small; the review gate and the queue are what stop a
change from landing on its own.

The broker also has no command that prints a token. `github-token` answers with
the token's metadata -- the app, the seat class, the repositories, the
permissions, the expiry and the last four characters -- and the credential
helper's stdout is the only place the value itself is written.

## The exit codes

| Code | Meaning |
| --- | --- |
| 0 | The call went through. |
| 64 | The command line was wrong. |
| 66 | No run credential in the environment, or the broker could not verify it. |
| 69 | The broker did not answer. The daemon is down or the socket is gone. |
| 70 | The broker answered, but it could not do the work (a broken policy, a missing guard). |
| 76 | A refusal. The broker said no and said why. |

A refusal (76) and an outage (69) are different answers and they are told apart:
a refusal is a decision, an outage is a fact about the host.

## One token per run

The broker mints **one token per run, per repository, per permission set**, and
reuses it for the rest of the run: a run that makes ten `gh` calls holds one
installation token, not ten. When the run ends, every token the broker minted for
that run is revoked, so nothing outlives the work. A token that has expired on
GitHub's side is pruned and a fresh one is minted.

The revocation does not wait for the seat to remember it. Every tick the daemon
asks Paperclip about the runs it has tokens for and revokes the tokens of the runs
that are no longer `running`, so a run that comments on a pull request and never
pushes loses its token when it ends, like any other run. A revocation GitHub
refuses does not drop the token: it stays in the ledger and the next tick tries
again.

The one hole in this is a restart of the daemon. The ledger of what it minted
lives in the daemon's memory, so a daemon that restarts forgets the tokens it
issued, and those can only be left to expire on GitHub's side — an hour, and not
one minute. The tokens a restart forgets are the ones minted in the hour before
it.

The rule that makes this safe is the same one that makes it useless to steal: the
token is scoped to the repository of the ticket, it carries only the permissions
of the seat's class, and it dies with the run.

## What the broker refuses

| Refusal | Why |
| --- | --- |
| A run whose JWT does not verify | The caller is not a seat run. |
| A run that is not `running` | The token would outlive the work. |
| An agent with no entry in the policy | Nobody decided what it may have. |
| A repository outside `digithings-ai` | The outer wall. |
| A repository the seat's binding does not name | The seat is bound to one repository. |
| A repository that is not the ticket's own | A token is scoped to the ticket. |
| A permission the seat's class does not hold | An escalation is refused, not trimmed. |
| `secrets`, ever | No seat holds it. |
| `statuses` and `workflows`, for a seat or a reviewer | Not part of the job. |
| A reviewer reviewing its own change | The head commit names the requesting seat as an owner, or names nobody at all. |
| A reviewer that did not name a pull request | The head commit is read from the pull request, not from the caller. |
| A review token used on another pull request | A review token is bound to one pull request. |
| A mint while the flag says `host` | The rollback is on: the broker hands out nothing. |

A refusal is an answer, not an error: the broker says what it refused and why, and
the caller sees it. A refusal never repeats back what the caller asked for: the
value is redacted before it reaches the message, so a credential-shaped value that
was refused does not land in the run log.

## The review path

A seat of the `reviewer` class gets a `digithings-review` token only for a change
somebody else wrote, and only for one pull request.

The pull request has to be named: a review without one is refused. The broker reads
the pull request from GitHub and takes **its own head commit** as the commit under
review, not the sha the caller wrote down. A caller that names a different sha is
refused, so a reviewer cannot point the broker at a commit that is not the head of
the pull request it is about.

The broker then reads that head commit's trailers, finds every owner it names, and
refuses when one of them is the requesting seat. It also refuses when the commit
names **no** owner at all: a change with no author trailer is not a change somebody
else wrote, it is a change nobody can be compared with.

The token that comes back is bound to that pull request, and the shim refuses to
use it on another one: a review token is for one pull request and not for the next
one.

The commit is read with the App's own credentials, not anonymously, so the check
works on the private repositories of the organization.

## The rollback flag

`/Users/_dtbroker/.config/digithings/github-auth-mode` holds `app` or `host`.

- `app` — the broker mints the token. The default, and what a missing or damaged
  flag reads as.
- `host` — the seat falls back to the host's own `gh` credentials, the way it works
  today. The daemon stops minting, the credential helper refuses, the shim passes
  the call through, and the merge queue's provenance check drops back to shadow.

The flag is read by the daemon, by the shim and by the credential helper, so a
rollback is complete rather than half a rollback. It is written by Chris with sudo
and by nobody else. The directory belongs to root, so a seat process cannot write
it. A seat cannot turn the broker off.

## Health

The daemon ticks every minute. A tick checks that the policy file still loads and
that the socket is still there. Two consecutive failures write
`/Users/_dtbroker/state/alert.json`.

The daemon never posts to the Board: it has no credential to post with, and it does
not sign anything in Chris's name. The alert file is what a Board-side watcher reads.

## When it goes wrong

| Symptom | What it means |
| --- | --- |
| `dt-broker: the broker did not answer ...` | The daemon is down. Exit 69. The call is not made with host credentials, on purpose. |
| `dt-broker: refusing: ... is outside the digithings-ai organization` | The shim caught a pull request outside the organization. Exit 76. |
| `dt-broker: refusing: a body that is a path` | The shim caught a body that would have been posted as a path. Exit 76. |
| `dt-broker: refusing: ... --hostname ...` | The shim caught a call aimed at a host nobody controls. Exit 76. |
| `dt-broker: refusing: gh auth token` | The shim caught a call that would have printed the token. Exit 76. |
| `dt-broker: refusing: no run credential` | `app` mode, and the environment has no run credential. Exit 66. The call is not made with the host's credential, on purpose. |
| `dt-broker: the gh guard is not at ...` | The guard is gone or moved. Exit 70. The shim refuses rather than calling the real `gh` without it. |
| `gh` is not the shim | The seat's shell hook still points `_SEAT_GH_GUARD` at the guard, or the PATH does not have `/usr/local/lib/dt-broker/bin` in front of the guard's directory. |
| `git` asks for a username | The credential helper could not reach the broker, or the repository is outside the policy. |
| A push goes out under the host's name | The gitconfig has no empty `helper =` reset, or `dt-broker` is not on the PATH, so git fell through to the system helper. |

The last three are the ones that bite. A seat that cannot see the shim will happily
call the real `gh` with the host's credential, and a seat that cannot find the
helper will happily push with the host's credential, so neither entry is optional.

## The tests

`tests/scripts/test_dt_broker.py` covers the broker: the refusals in the table
above, the token never reaching a log, the revoke at the end of a run, the sweep
that revokes what it minted when the run ends, the revocation GitHub refuses being
retried rather than lost, the forged credential that cannot revoke another run,
the reviewer that cannot review its own change, the reviewer that cannot point the
broker at a commit that is not the head of the pull request, the host mode that
mints nothing, and the launchd arguments as they are really parsed.
`tests/scripts/test_dt_broker_shim.py` covers the shim: the `@path` expansion for
both spellings, the refused bare path, the refused out-of-organization pull request
(including the endpoint behind a flag, the mutation in a file, an organization name
in another case and a `..` in the path), the guard in the chain, the socket that
cannot be named by the environment, the scratch directory that cannot be named by
the environment and cannot be made to point at the host's own configuration, the
run credential that decides, the host's token that never reaches the child, the
refused `--hostname` and `gh auth token`, the answer that has to be about this run,
the token that cannot be used on another pull request, and the host-mode
pass-through.
`tests/scripts/test_merge_queue.py` covers the flag's effect on the provenance
gate: it lowers a gate, and it never raises one.
