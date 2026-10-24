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
### digithings
  - develop: push=false approvals=1 status=false signed=false admins=true dismiss_stale=true outdated=true
  - main: push=false approvals=1 status=true signed=false admins=true dismiss_stale=true outdated=true
### twelve-x
  - develop: push=false approvals=1 status=false signed=false admins=true dismiss_stale=true outdated=true
  - main: push=false approvals=1 status=true signed=false admins=true dismiss_stale=true outdated=true
### datatap-web
  - develop: push=false approvals=1 status=false signed=false admins=true dismiss_stale=true outdated=true
  - main: push=false approvals=1 status=true signed=false admins=true dismiss_stale=true outdated=true
### paperclip
  - develop: push=false approvals=1 status=false signed=false admins=true dismiss_stale=true outdated=true
  - main: push=false approvals=1 status=true signed=false admins=true dismiss_stale=true outdated=true
### digiforge
  - develop: push=false approvals=1 status=false signed=false admins=true dismiss_stale=true outdated=true
  - main: push=false approvals=1 status=true signed=false admins=true dismiss_stale=true outdated=true

## Stale-token check (expired sidecars)
## Done
