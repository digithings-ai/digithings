# Forgejo access review — 2026-10-24

## Users
- chris (admin=False, last_login=2026-10-24T20:59:05Z)
- ci-runner (admin=False, last_login=1970-01-01T00:00:00Z)
- claude-agent (admin=False, last_login=1970-01-01T00:00:00Z)
- cursor-agent (admin=False, last_login=1970-01-01T00:00:00Z)
- grok-agent (admin=False, last_login=1970-01-01T00:00:00Z)
- paperclip-bot (admin=False, last_login=1970-01-01T00:00:00Z)
- sctl (admin=True, last_login=2026-10-24T20:58:41Z)

## 2FA status (CLI)
```
ID   Username      Email                    IsActive IsAdmin 2FA
1    sctl          sctl@local-forge.invalid true     true    true
5    chris         chris@local.invalid      true     false   true
6    claude-agent  claude@local.invalid     true     false   false
7    grok-agent    grok@local.invalid       true     false   false
8    cursor-agent  cursor@local.invalid     true     false   false
9    paperclip-bot paperclip@local.invalid  true     false   false
10   ci-runner     ci@local.invalid         true     false   false
```

## Org members & teams
- team 2 (Owners): sctl
- team 3 (admins): sctl, chris
- team 4 (agent-writers): claude-agent, cursor-agent, grok-agent, paperclip-bot
- team 5 (ci-runners): ci-runner
- team 6 (reviewers): chris, paperclip-bot

## Tokens (expiry)
- chris: expires 2027-01-22
- ci-runner: expires 2027-01-22
- claude-agent: expires 2027-01-22
- cursor-agent: expires 2027-01-22
- grok-agent: expires 2027-01-22
- paperclip-bot: expires 2027-01-22
- sctl: expires 2027-01-22

## Branch protection matrix

Removed on 2026-10-26. The matrix printed here came from an older generation of
`scripts/forgejo-access-review.sh`: it listed a fixed five-repo list with both
branches for each, so it disagreed with the forge (9 rules, not 10) from the day
it was committed, and it printed a client repo name that the R0 client-literals
guard forbids in this public tree. The current matrix, and the verifier that
asserts it, are in `docs/ops/forgejo-branch-protection.md`.

## Stale-token check (expired sidecars)
## Done
