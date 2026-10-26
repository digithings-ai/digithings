
---

## Validation (2026-10-25) — end-to-end proof, current state

### End-to-end proof on `digithings-ai/digiforge`
1. Branch created from `develop` → 201
2. File committed → 201 (commit `b53a83dd25`)
3. PR opened → #1
4. **Self-approval by the PR author blocked → 422 "approve your own pull is not allowed"** ✅
5. Independent approval as `claude-agent` → 200, state `APPROVED` ✅
6. Merge → 200, `merged: true` ✅
7. Cleanup PR #2 merged, `VERIFY.md` gone from `develop` (404) ✅

### Component checks
| Component | Result |
|---|---|
| Forgejo healthz | 200 |
| Admin `sctl` | is_admin true, PAT 200 |
| Org repos | 5; default branches: digithings/twelve-x/digiforge `develop`, datatap-web `main`, paperclip `master` |
| Branch protection | 9 rules across 5 repos, not a uniform 2-per-repo matrix — see `docs/ops/forgejo-branch-protection.md` |
| Webhooks | 2 per repo (Woodpecker + Paperclip receiver) |
| OAuth apps | 3 (woodpecker-local, paperclip-local confidential, sctl-local PKCE) |
| Org secrets | 3 (FORGE_TOKEN, NPM_TOKEN, WOODPECKER_AGENT_SECRET) |
| Repo variables | 3 per repo (NODE_VERSION, PYTHON_VERSION, REGISTRY_URL) |
| Teams | admins, agent-writers, ci-runners, reviewers, Owners |
| Users | 7 |
| Woodpecker repos | 5, all active |
| Webhook receiver | `{"ok":true}` on :3200 |

### Known gaps (2026-10-26)

The live rules are documented as they are, not as the target:

- `datatap-web/main` has status checks, stale dismissal and outdated blocking off.
- The four `main` rules with status checks enabled name no required context.
- The `admins` team has 0 repo grants.
- Signed commits are off everywhere.

Follow-up: local forge issue #7 tracks applying the target matrix and the team grant.
The branch-protection verifier asserts the **current** matrix and exits 1 on a
missing rule or a flag mismatch.

### Important finding: teams need repo grants explicitly
Creating a team with `permission` + `units` does **not** grant access to org repos.
Each repo must be added to the team:
```bash
PUT /api/v1/teams/{team_id}/repos/{org}/{repo}   # 204
```
Without this, a team member gets 404 on the repo and cannot review or push.
Fixed for `agent-writers`, `ci-runners`, `reviewers` and `Owners` (5 repos each). The `admins` team still has 0 repo grants; that is a hardening gap.

### Branch-protection consequence
With `enable_push: false` on `develop`, the `/git/refs` endpoint returns 405.
Create branches with:
```bash
POST /api/v1/repos/{owner}/{repo}/branches
{"new_branch_name":"<new>","old_branch_name":"develop"}   # 201
```
