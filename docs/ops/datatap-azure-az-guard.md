# The `az` guard — how the DataTap Azure access register is enforced (DIG-1725)

**Status:** runbook. Installing this changes what `az` means on your machine, for every shell, until you roll it back.
**Owner:** Platform (Security owns the register the guard reads)
**Scope:** every `az` command run by a human or an agent on a machine where the guard is installed.
**Verified:** 2026-10-07 on the developer Mac (`az` 2.87.0 at `/opt/homebrew/bin/az`, register empty).

---

## What this is

The DataTap Azure access register ([DIG-1674 document](https://paperclip.local/DIG/issues/DIG-1674), document id `7089f97b-9f0f-4b57-be10-26e787ecf583`) lists the subscriptions an agent may touch. Its machine-readable copy is [`config/datatap_azure_access_register.json`](../../config/datatap_azure_access_register.json). Today it lists **zero** subscriptions, which is the correct state: only DataTap, in writing, can classify a subscription, and it has not done so.

Until now that register was enforced by agent memory. The register itself says why that is not enough: *"A remembered rule is not a control."* Memory failed once, on a SEV1.

[`scripts/az-guard/az`](../../scripts/az-guard/az) is the control. It is a single Python file, standard library only, installed on `PATH` **ahead of** the real `az`. Every `az` command goes through it. It reads the register, decides whether the target subscription is authorised, and either `exec`s the real `az` or refuses with exit code **78** and logs why.

**With the register as it stands today, every `az` command is refused.** That is not a broken install. That is the door being locked before the key exists.

---

## Install

```bash
cd <digithings repo>
scripts/az-guard/install.sh
```

That writes one symlink, `$HOME/.local/bin/az` → `scripts/az-guard/az`, and nothing else. It is a symlink rather than a copy so `git pull` updates the guard with no second step.

`$HOME/.local/bin` is already first on `PATH` in `~/.zshrc` on the developer machines in this stack. If your shell does not have it, either add it or pass `--bindir`:

```bash
scripts/az-guard/install.sh --bindir /usr/local/bin     # needs your own sudo
```

Requirements: Python 3.9+ (macOS ships 3.9; the repo venv is 3.12) and `bash`. No packages, no `pip install`, no plugin.

## Verify

```bash
scripts/az-guard/install.sh --check
```

It prints where the shim, the link, the register and the log are, and then runs one refusal probe: `az account show --subscription fc64972f-…` (the production subscription). Expected:

```text
  PASS    : the production subscription id is refused (exit 78, nothing executed)
```

The probe makes **no network call** — the guard refuses before it ever looks for the real `az`. If `--check` cannot confirm that `az` on `PATH` is the guard, it exits 1 and stops there.

To see it by hand:

```bash
$ az account show --subscription fc64972f-8c1e-46f1-a2b0-bd2407c0cdf0
az guard: REFUSED (subscription-not-authorised)
  target subscription : fc64972f-8c1e-46f1-a2b0-bd2407c0cdf0
  register            : …/config/datatap_azure_access_register.json (0 authorised subscription(s))
  command             : az account show --subscription fc64972f-8c1e-46f1-a2b0-bd2407c0cdf0

Nothing was executed. This refusal is enforced, not advisory:
scripts/az-guard/az has no bypass flag and no bypass environment variable.
See docs/ops/datatap-azure-az-guard.md.
$ echo $?
78
```

## Roll back

```bash
scripts/az-guard/install.sh --uninstall
```

Removes the symlink and nothing else. It refuses to touch a link that is not the guard's, so it cannot delete a real `az`. Verified: the four observed DataTap subscriptions, the register, and the log file all survive a rollback.

---

## What the guard decides

Order of operations, because the order is the fail-closed property:

1. Resolve the target subscription — from `--subscription`, or from `[defaults] subscription` in the local Azure profile file when no flag is given. No `az` command runs and no network call is made to decide this.
2. Check the resolved id against `authorized_subscriptions`.
3. Only then look for the real `az` to `exec`.

Each of the four observed Azure contexts is refused, with the resolved id recorded:

| Context | Subscription id | Reason |
|---|---|---|
| Datatap Trials | `0071922f-05ec-48aa-b20e-2a12333b0adf` | `register-empty` |
| Subscription - dev | `8042941f-87db-4546-b3a4-0b720c1da146` | `register-empty` |
| DataTap WebSite (PRODUCTION) | `fc64972f-8c1e-46f1-a2b0-bd2407c0cdf0` | `register-empty` |
| Test Subcription for Greenfield Deployment | `d4a34253-aa31-446e-b819-888af08ccf68` | `register-empty` |

(With the register as committed today the reason is `register-empty` for all four. Once a row exists, an unlisted id reads `subscription-not-authorised`.)

### Refusal reasons

| Reason | Means |
|---|---|
| `register-missing` | no register file at all |
| `register-unreadable` | present but unreadable (permissions, it is a directory, bad bytes) |
| `register-malformed` | not JSON, not an object, or no `authorized_subscriptions` list |
| `register-empty` | the list exists and authorises nothing |
| `indeterminate-subscription` | no flag and no default in the profile — "could not tell" means no |
| `subscription-not-an-id` | a subscription **name**, or a malformed id. Refused, never looked up |
| `ambiguous-subscription` | two different targets on one command line |
| `subscription-not-authorised` | resolved fine, not on the register |
| `real-az-not-found` | authorised, but there is no real `az` to `exec` |
| `recursive-invocation` | the guard re-entered itself; refused rather than looping |

Exit code is always **78** (`sysexits.h EX_CONFIG`) for every refusal, so it cannot be mistaken for one of `az`'s own codes. An authorised command is `exec`'d and its exit code is `az`'s own.

### Refusal log

Every refusal appends one JSON line to `~/.digithings/az-guard-refusals.log`:

```json
{"command":["group","list","--subscription","fc64972f-8c1e-46f1-a2b0-bd2407c0cdf0"],"cwd":"/Users/…","event":"az-guard refusal","reason":"register-empty","register":"…/config/datatap_azure_access_register.json","register_authorized_count":0,"subscription":"fc64972f-8c1e-46f1-a2b0-bd2407c0cdf0","subscription_source":"command-line","ts":"2026-10-07T02:14:31Z","user":"chrisstefan"}
```

The log carries the timestamp, the resolved subscription and where it came from, the reason, and the command **shape**. Values of password/secret/token/sas/key/cert-looking options are replaced with `<redacted>` in both the log and the stderr block, so a refused command that carried a secret does not turn the refusal log into a credential store. If the log is unwritable the refusal still stands, with a warning on stderr — a broken log never turns a refusal into a pass.

---

## What this does not cover

Read these before you treat the guard as more than it is.

- **PATH order is the whole control.** The guard works because `~/.local/bin/az` is found before `/opt/homebrew/bin/az`. An absolute path (`/opt/homebrew/bin/az …`) bypasses it completely, and so does any agent that resolves `az` rather than calling it. `--check` exists to catch the first case; nothing catches the second.
- **The unit is a subscription, not a resource.** A non-empty register authorises a *whole* subscription. `--scope /subscriptions/<id>/resourceGroups/prod` passes today only because no subscription is authorised. Do not add a row for "just one resource group" — the guard cannot enforce that.
- **`--sub`, `--subs` and `--subscriptions` are all caught.** `az` resolves long options by unambiguous prefix, so `--sub <id>` selects the subscription exactly as `--subscription` does; a guard reading only the long spelling would have a bypass in it. `-s` is caught too. This is pinned by a parametrised test.
- **A subscription name is refused, not resolved.** `--subscription "DataTap WebSite"` exits 78. Deciding which id that name means would mean asking Azure — the act the rule forbids.
- **`AZURE_SUBSCRIPTION_ID` is ignored on purpose.** The Azure CLI does not read it, so honouring it would authorise a command that lands somewhere else.
- **There is no bypass flag and no bypass environment variable.** A test asserts this, and asserts that setting `AZ_GUARD_BYPASS`, `AZURE_SUBSCRIPTION_ID` or `DIGI_ALLOW_PROTECTED` changes nothing. If you need one, that is a change of the rule, not a change of the guard.
- **`AZ_GUARD_REAL_AZ` pins the exec target.** When set it is the *only* candidate. It cannot authorise anything — the subscription was already accepted against the register — it only chooses which executable receives an already-authorised command. `AZ_GUARD_REGISTER` and `AZ_GUARD_LOG` point the guard at a different register or log; a different register can refuse more, never less than the row it contains.
- **The profile default is trusted to be the real default.** The guard reads `[defaults] subscription` out of `$AZURE_CONFIG_DIR/config` (else `~/.azure/config`) — the same file and key `az` itself reads. It does not re-authenticate or verify the session.

### Environment variables it reads

`AZ_GUARD_ACTIVE`, `AZ_GUARD_LOG`, `AZ_GUARD_REAL_AZ`, `AZ_GUARD_REGISTER`, `AZURE_CONFIG_DIR`, `HOME`, `LOGNAME`, `PATH`, `TMPDIR`, `USER`. Nothing else. A test asserts that list, and that no variable name matching `BYPASS|ALLOW|SKIP|DISABLE|OVERRIDE` appears anywhere in the source.

---

## Changing the register

Only DataTap, in writing, can classify a subscription (DIG-1687). So:

1. Security edits `config/datatap_azure_access_register.json` — `authorized_subscriptions` gains a full subscription UUID, and `last_changed` / `changed_by` are updated.
2. Security updates the DIG-1674 document in the same PR and records who confirmed it.
3. Security opens the PR. The guard's test suite runs in CI on it.

Adding a row is a security decision with an owner. It is not a configuration tweak an agent makes to unblock a task. The `_readme` array in the register says the same thing next to the key.

---

## Tests

[`tests/scripts/test_az_guard.py`](../../tests/scripts/test_az_guard.py) — 41 tests, all marked `unit`, so they run in the `ruff-and-scripts` CI lane with no workflow change. It uses a fake `az` on `PATH` and a temporary register, log, `HOME` and `AZURE_CONFIG_DIR` per test, so it never touches your real Azure profile and never appends to your real refusal log.

Covered: authorised id executes; unlisted id refused and the real `az` never called; all four observed contexts refused against the committed register; empty / missing / unreadable / malformed register refuses; indeterminate subscription refused; profile default = production refused (the SEV1 shape); all five selector spellings; ambiguous double-target; refusal log contents, timestamp format and secret redaction; no environment variable bypasses; installer round-trip.

```bash
pytest tests/scripts/test_az_guard.py -m unit -v
ruff check tests/scripts/test_az_guard.py
```

---

## Related

- [`credential-ownership.md`](credential-ownership.md) — the same rule applied to credentials held by hand; this file is its enforcement half.
- [`digichat-datatap-aca.md`](digichat-datatap-aca.md) — the deploy runbook this guard covers. Its `az` commands will now be refused until a subscription is registered, which is the point: they are writes to a customer's tenant.
- DIG-1674 (register, Security) · DIG-1686 (credential scope ruling, CTO) · DIG-1687 (who may classify a subscription)