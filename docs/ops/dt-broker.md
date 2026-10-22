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

- `GIT_CONFIG_GLOBAL` points at a fresh file with one line in it:
  `[credential "https://github.com"] helper = !dt-broker git-credential`. The seat's
  own git configuration is not read, so a credential saved there is not used.
- `GH_CONFIG_DIR` points at an empty directory, so the `gh` that runs reads no
  configuration and no credential of the host's.
- `GIT_AUTHOR_NAME`, `GIT_AUTHOR_EMAIL`, `GIT_COMMITTER_NAME` and `GIT_COMMITTER_EMAIL`
  are the bot identity of the seat's App: `digithings-seat[bot]`, with the
  `BOTID+login@users.noreply.github.com` address, so GitHub attributes the commit to
  the bot and not to a person.

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
configuration.

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
content.

**It refuses a body that is a path.** A field called `body` whose value looks like a
path to a file that exists is refused instead of posted. The cheap rule catches the
mistake even where the expansion does not apply.

**It refuses a pull request outside the organization.** `gh pr create` against a
repository that is not in `digithings-ai`, `gh api repos/{owner}/{repo}/pulls`
outside it, and the GraphQL `createPullRequest` mutation are all refused, with the
reason on stderr. This holds in both authentication modes: no upstream pull request,
ever, under any identity.

In `app` mode the shim then asks the broker for a token, sets `GH_TOKEN` for that one
call, and removes `GITHUB_TOKEN`, `GH_ENTERPRISE_TOKEN` and `GITHUB_ENTERPRISE_TOKEN`
from the environment, so the call cannot fall back to the host's credentials. In
`host` mode the call is passed through unchanged.

The three refusals are the same in both modes. The rollback turns off the broker, not
the rules.

## The credential helper

`git` asks the helper for a credential when it pushes. The helper refuses a host
that is not `github.com` and a repository outside the organization, then asks the
broker for a token scoped to the ticket's repository. The answer is
`username=x-access-token` and the token, on stdout, for git.

When the credential is erased, the token behind it is revoked.

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
| A reviewer reviewing its own change | The head commit's owner trailer is the seat itself. |

A refusal is an answer, not an error: the broker says what it refused and why, and
the caller sees it.

## The review path

A seat of the `reviewer` class gets a `digithings-review` token only for a change
somebody else wrote. The broker reads the head commit's trailers, finds the owner,
and refuses when the owner is the requesting seat. The head commit's sha has to be
supplied: a review without one is refused.

## The rollback flag

`/Users/_dtbroker/.config/digithings/github-auth-mode` holds `app` or `host`.

- `app` — the broker mints the token. The default, and what a missing or damaged
  flag reads as.
- `host` — the seat falls back to the host's own `gh` credentials, the way it works
  today. The merge queue's provenance check drops back to shadow.

The flag is written by Chris with sudo and by nobody else. The directory belongs to
root, so a seat process cannot write it. A seat cannot turn the broker off.

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
| `dt-broker: refusing: ... is outside the digithings-ai organization` | The shim caught a pull request outside the organization. |
| `dt-broker: refusing: a body that is a path` | The shim caught a body that would have been posted as a path. |
| `gh` is not the shim | The seat's shell hook still points `_SEAT_GH_GUARD` at the guard, or the PATH does not have `/usr/local/lib/dt-broker/bin` in front of the guard's directory. |
| `git` asks for a username | The credential helper could not reach the broker, or the repository is outside the policy. |

The last two are the ones that bite. A seat that cannot see the shim will happily
call the real `gh` with the host's credential, so the PATH entry is not optional.

## The tests

`tests/scripts/test_dt_broker.py` covers the broker: the refusals in the table
above, the token never reaching a log, and the revoke at the end of a run.
`tests/scripts/test_dt_broker_shim.py` covers the shim: the `@path` expansion for
both spellings, the refused bare path, the refused out-of-organization pull request,
the guard in the chain, and the host-mode pass-through.
