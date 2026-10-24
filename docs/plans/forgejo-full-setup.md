
---

## Validation (2026-10-25) — all systems functioning

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
| Org repos | 5, all `develop` |
| Branch protection | 2 per repo (develop + main) |
| Webhooks | 2 per repo (Woodpecker + Paperclip receiver) |
| OAuth apps | 3 (woodpecker-local, paperclip-local confidential, sctl-local PKCE) |
| Org secrets | 3 (FORGE_TOKEN, NPM_TOKEN, WOODPECKER_AGENT_SECRET) |
| Repo variables | 3 per repo (NODE_VERSION, PYTHON_VERSION, REGISTRY_URL) |
| Teams | admins, agent-writers, ci-runners, reviewers, Owners |
| Users | 7 |
| Woodpecker repos | 5, all active |
| Webhook receiver | `{"ok":true}` on :3200 |

### Important finding: teams need repo grants explicitly
Creating a team with `permission` + `units` does **not** grant access to org repos.
Each repo must be added to the team:
```bash
PUT /api/v1/teams/{team_id}/repos/{org}/{repo}   # 204
```
Without this, a team member gets 404 on the repo and cannot review or push.
Fixed for all three teams × 5 repos.

### Branch-protection consequence
With `enable_push: false` on `develop`, the `/git/refs` endpoint returns 405.
Create branches with:
```bash
POST /api/v1/repos/{owner}/{repo}/branches
{"new_branch_name":"<new>","old_branch_name":"develop"}   # 201
```
