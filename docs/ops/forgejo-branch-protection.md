# Forgejo branch protection (localhost:3000)

Expected matrix (5 repos x 2 branches):

| Branch | enable_push | required_approvals | enable_status_check | require_signed_commits | apply_to_admins | block_on_rejected_reviews | dismiss_stale_approvals | block_on_outdated_branch |
|---|---|---|---|---|---|---|---|---|
| develop | false | 1 | false | false | true | true | true | true |
| main | false | 1 | true | false | true | true | true | true |

Verifier: `scripts/forgejo-branch-protection-verify.sh` (exit 0 only if all match).

Signed commits: left `false` (optional follow-up). Enabling requires each committer to register a GPG key (`/user/gpg_keys`) and set `require_signed_commits = true` on both branches; all agents must sign. Track as follow-up.
