# Forgejo token rotation policy (localhost:3000)

Baseline: 90 days for every PAT an agent or human uses against Forgejo
(aligns with docs/ops/SECRETS_ROTATION.md standing baseline).

| Identity | Token file | Scope | Cadence | Owner |
|---|---|---|---|---|
| sctl | local-forge.env FORGEJO_TOKEN | all | 90 days | admin (sctl) |
| chris | chris.token | all (human) | 90 days | chris |
| claude-agent | claude-agent.token | all | 90 days | Claude seat |
| grok-agent | grok-agent.token | all | 90 days | Grok seat |
| cursor-agent | cursor-agent.token | all | 90 days | Cursor seat |
| paperclip-bot | paperclip-bot.token | all | 90 days | Paperclip seat |
| ci-runner | ci-runner.token | all | 90 days | CI owner |

## Procedure
1. Mint a new token (CLI, does not invalidate the old one).
2. Write it to the token file (mode 600) and record expiry (today + 90 days).
3. Update every consumer (env files, CI secrets, agent configs) to the new token.
4. Verify the new token works (`GET /api/v1/user`).
5. Revoke the old token by name (`DELETE /api/v1/users/{u}/tokens/{name}`).
6. Log the rotation in the table at the bottom of this file.

## Revocation triggers (immediate, not on cadence)
- Suspected leak, lost device, offboarding of a seat, or a token appearing in
  any commit/issue/chat.

## Exemptions
None currently. Add a dated entry here if a token cannot meet 90 days.

## Rotation log

| Date | Identity | Old token name | New token name | Expiry | Operator |
|---|---|---|---|---|---|
