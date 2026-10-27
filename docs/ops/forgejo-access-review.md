# Forgejo access review (localhost:3000)

Cadence: quarterly (Jan/Apr/Jul/Oct) and on any seat offboarding or suspected
compromise. Owner: Security & Risk (or Chris in solo mode).

## Checklist
1. Run `scripts/forgejo-access-review.sh`. It discovers the repo inventory from
   the forge, so the report names a client repo; keep the report in the
   gitignored `.agent-tmp/access-review/` (the script's default), not in this
   public tree. Commit a dated pass/finding summary to
   `docs/ops/access-reviews/YYYY-MM-DD-forgejo.md` without the repo names, or
   link the branch-protection matrix in `docs/ops/forgejo-branch-protection.md`.
2. Users: confirm the 7 expected accounts exist; no unexpected accounts.
   Admins must be exactly `sctl` and (via team `admins`) `chris`.
3. Teams: `admins` = {sctl, chris}; `agent-writers` = the four agents;
   `ci-runners` = {ci-runner}; `reviewers` = {chris, paperclip-bot}; `Owners` = {sctl}.
   Remove any seat that has been offboarded. The `admins` team currently has no
   repo grants; that is a known hardening gap, not a user-membership problem.
4. 2FA: `sctl` and `chris` must show 2FA=true; agents/bots must be false.
5. Tokens: every `*.expires` sidecar must be in the future. Rotate any that are
   expired or expiring within 14 days (scripts/forgejo-token-rotate.sh).
6. Branch protection: run `scripts/forgejo-branch-protection-verify.sh` (must exit 0).
7. Gitleaks: `scripts/forgejo-gitleaks-woodpecker-step.yml` is a **template**;
   no `.woodpecker.yml` exists yet. The local guard is the gitleaks check in
   `scripts/hooks/pre-push.sh` (installed by `make hooks-install`); confirm it
   is present, and that `gitleaks` is on the operator's PATH — the hook refuses
   a push when the binary or `.gitleaks.toml` is missing rather than skipping
   the scan (DIG-5722). Server-side scanning arrives with the Woodpecker pipeline.
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
First Monday of the next quarter. Usernames are not secrets, so a short dated
summary is committed under `docs/ops/access-reviews/`. The full report stays in
the gitignored `.agent-tmp/access-review/`: it lists the repo inventory, and one
of those names is a client name.
