# Forgejo branch protection (localhost:3000)

Verified against the live forge on **2026-10-26**. The forge carries **9 rules
across 5 repos**, and they are deliberately not uniform: `main` is the strict
branch, while the integration branch (`develop`, or `master` on paperclip) is
lighter because agents merge into it continuously.

## Current matrix

| Repo | Branch | push | approvals | status | signed | admins | rejected | stale | outdated |
|---|---|---|---|---|---|---|---|---|---|
| digithings | `main` | off | 1 | on | off | on | on | on | on |
| digithings | `develop` | off | 1 | off | off | on | on | off | off |
| twelve-x | `main` | off | 1 | on | off | on | on | on | on |
| twelve-x | `develop` | off | 1 | off | off | on | on | off | off |
| `<client-web>` | `main` | off | 1 | off | off | on | on | off | off |
| paperclip | `main` | off | 1 | on | off | on | on | on | on |
| paperclip | `master` | off | 1 | off | off | on | on | off | off |
| digiforge | `main` | off | 1 | on | off | on | on | on | on |
| digiforge | `develop` | off | 1 | off | off | on | on | off | off |

`enable_status_check` is on for the four `main` rules, but **their
`status_check_contexts` lists are empty** — the setting exists without naming a
required context. That is a gap, not a pass.

The verifier asserts this **current** state:

```bash
scripts/forgejo-branch-protection-verify.sh
```

The repo/branch inventory is not in the script: one of those repos carries a
client name, and this tree is public (the R0 client-literals guard in
`scripts/check_r0_no_client_literals.py`). It is read from
`FORGEJO_PROTECTED_REPOS` in the local forge env file
(`$LOCAL_FORGE_ENV`, default `~/Code/source-control/deploy/local-forge/local-forge.env`),
as a comma-separated list of `repo:branch:profile` with `strict` or `light` as
the profile:

```bash
FORGEJO_PROTECTED_REPOS="digithings:main:strict,digithings:develop:light,<client-web>:main:light"
```

The token is exported, never passed as an argument, so it does not appear in
`ps`. An unset inventory, an unreachable forge or a wrong token all exit
non-zero: the verifier fails closed and never reports a clean run it did not
measure.

It exits non-zero for a missing rule or any flag mismatch, and prints the
mismatch with the repo/branch/field.

## Known gaps (hardening follow-up)

The target is stricter than the current state:

- `<client-web>/main` has status checks, stale dismissal and outdated blocking
  all off; the other `main` rules have them on.
- The four `main` rules that enable status checks name no required context.
- The `admins` team has access to **0 repos**; `agent-writers`, `ci-runners`,
  `reviewers` and `Owners` each have all five.
- Signed commits are off everywhere (left as an optional follow-up).

The live rules are intentionally left unchanged by this documentation change.
Follow-up: local forge issue #7 tracks applying the target matrix and the team
grant, with its own review and rollback.

## Branch-protection consequence

With `enable_push: false`, the `/git/refs` endpoint returns 405. Create
branches with:

```bash
POST /api/v1/repos/{owner}/{repo}/branches
{"new_branch_name":"<new>","old_branch_name":"develop"}   # 201
```

Use the repo's actual integration branch (`develop` or `master`).
