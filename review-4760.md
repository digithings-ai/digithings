<!-- in-session-review -->
# Review — PR #4760 (diff-scoped, fresh context)

- Reviewer: fresh-context subagent (diff-scoped review; no prior session context)
- Subject: PR #4760 `chore: rotate MCP_EDGE_KEY + attach occ zammad server` (digithings-ai/digithings, `chore/rotate-mcp-edge-key` → `develop`)
- Scope: diff only — the live rotation work (secret puts, Worker deploy, edge/tenant/tools-list verification) is taken as done/green per brief and was not re-litigated.
- Verdict: **APPROVE**
- Counts: critical 0 · major 0 · minor/advisory 1 · informational 0

## Checks (all pass)

1. **Container-id bump is exactly v8→v9, no other code change** — PASS
   - `apps/digichat-cloudflare/src/paths.ts:23`: `shared-v8` → `shared-v9`, single line; verified base (`origin/develop`) has `shared-v8`, head has `shared-v9`, and the full diff touches no other code line.
2. **Rotation-log row is accurate and follows table format** — PASS
   - `docs/ops/SECRETS_ROTATION.md:288`: new row fills all 5 columns of the existing `| Date (UTC) | Secret | Actor | Ticket | Verification evidence |` table, replacing the empty placeholder row; date `2026-09-29`, secrets named, actor `agent (user-authorized rotation)`, ticket `occ zammad Unknown tool`, evidence string names the edge 401/406 gate, zammad server now listed, 5 tools via tools/list, Worker `e6901a69`, container `shared-v9` — consistent with the PR body.
3. **Nothing else in the diff** — PASS
   - `git diff origin/develop...origin/chore/rotate-mcp-edge-key --stat`: 2 files changed, 2 insertions, 2 deletions. Name-only: `apps/digichat-cloudflare/src/paths.ts`, `docs/ops/SECRETS_ROTATION.md`.
   - No secret material in the diff (grep for key-like tokens: clean).

## Findings

### Advisory-1 (non-blocking follow-up): stale `shared-v8` literal pin in stack mount test
- `apps/digithings-stack-cloudflare/src/digichat-mount.test.js:88` (on PR head): `expect(SHARED_DIGICHAT_CONTAINER_ID).toBe("shared-v8")` — after this PR's bump the imported constant is `"shared-v9"`, so this literal assertion will fail while the adjacent `toBe(standaloneContainerId)` re-export check still passes.
- Evidence: `git grep "shared-v[0-9]"` on PR head shows this as the only non-historical `shared-v8` reference (the `SECRETS_ROTATION.md:25` and `docs/plans/2026-09-18-dev-cloudflare-containers.md` hits are historical prose, correctly untouched).
- Recommendation: one-line follow-up (same branch or immediate follow-up PR) updating the pin to `"shared-v9"`. Not held as blocking because it is outside the scoped diff, test-only (no production behavior impact), and the rotation record itself is time-sensitive (prevents a clean-main deploy from reverting the live container id).
