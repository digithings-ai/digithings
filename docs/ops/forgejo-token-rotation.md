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
1. Mint and write the new token: `scripts/forgejo-token-rotate.sh <identity> [scope]`.
   It does **not** revoke anything; it writes `~/.config/digithings/forgejo-tokens/<identity>.token`
   and the `.expires` sidecar at mode 600.
2. Update every consumer (env files, CI secrets, agent configs) to the new token.
3. Verify the new token works against a repo endpoint.
4. Revoke the old token **by name** only after the consumers are updated:
   `scripts/forgejo-token-rotate.sh --revoke <identity> <old-name>`.
5. Log the rotation in the table at the bottom of this file.

The `sctl` admin token is stored in `local-forge.env`, not in the token
directory. The script refuses to rotate it automatically; update that file
deliberately and revoke the old admin token after the new one is verified.

## Revocation triggers (immediate, not on cadence)
- Suspected leak, lost device, offboarding of a seat, or a token appearing in
  any commit/issue/chat.

## Exemptions
None currently. Add a dated entry here if a token cannot meet 90 days.

## Rotation log

| Date | Identity | Old token name | New token name | Expiry | Operator |
|---|---|---|---|---|---|
