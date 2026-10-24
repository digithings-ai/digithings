# Forgejo access review (localhost:3000)

Cadence: quarterly (Jan/Apr/Jul/Oct) and on any seat offboarding or suspected
compromise. Owner: Security & Risk (or Chris in solo mode).

## Checklist
1. Run `scripts/forgejo-access-review.sh` and save the report to
   `docs/ops/access-reviews/YYYY-MM-DD-forgejo.md`.
2. Users: confirm the 7 expected accounts exist; no unexpected accounts.
   Admins must be exactly `sctl` and (via team `admins`) `chris`.
3. Teams: `admins` = {sctl, chris}; `agent-writers` = the four agents;
   `ci-runners` = {ci-runner}; `reviewers` = {chris, paperclip-bot}; `Owners` = {sctl}.
   Remove any seat that has been offboarded.
4. 2FA: `sctl` and `chris` must show 2FA=true; agents/bots must be false.
5. Tokens: every `*.expires` sidecar must be in the future. Rotate any that are
   expired or expiring within 14 days (scripts/forgejo-token-rotate.sh).
6. Branch protection: run `scripts/forgejo-branch-protection-verify.sh` (must exit 0).
7. Gitleaks: confirm the Woodpecker `gitleaks` step is present in each repo's
   `.woodpecker.yml` on `develop` (spot-check one repo).
8. Audit log: review `access.log` for 401/403 spikes and non-2xx mutations
   (docs/ops/forgejo-audit-log.md).
9. Record the review outcome (pass / findings) in the report file and file
   follow-up issues for any finding.

## Offboarding a seat
1. Revoke all tokens: `DELETE /api/v1/admin/users/{u}/tokens/*`.
2. Remove from all teams and org.
3. Optionally delete the account: `forgejo admin user delete --username {u}`.
4. Rotate any shared secrets the seat could read.
5. Log in the rotation log.

## Next review date
First Monday of the next quarter. Report stored under `docs/ops/access-reviews/`
(usernames are not secrets; commit the report).
