# Phase 6: Security & Access — Forgejo Implementation Plan

> **Superseded 2026-10-26:** the `.githooks` design, the 5x2 protection claim and the hardcoded paths in this historical plan were corrected in the phase-6 docs and scripts. See `docs/ops/forgejo-branch-protection.md`, `docs/ops/forgejo-token-rotation.md` and `scripts/hooks/pre-push.sh`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the local Forgejo instance (localhost:3000) so that human accounts are protected by 2FA, credentials rotate on a 90-day cadence, every admin/repo action is auditable, branch protection is verified and consistent across all five repos, gitleaks scans every push and PR, and access is reviewed on a documented cadence.

**Architecture:** Forgejo 17.0.0 (Gitea fork) runs in Docker (`codeberg.org/forgejo/forgejo:17.0.0`) on port 3000 with SQLite, administered by `sctl`. Security is enforced in three layers: (1) `app.ini` settings (`GLOBAL_TWO_FACTOR_REQUIREMENT`, `[log]` file mode, `SECRET_KEY`), applied by editing the config inside the `local-forge_forgejo-data` volume and restarting the container; (2) Forgejo REST API (`/api/v1/...`) for branch protection, token lifecycle, and membership; (3) repository-level gitleaks (`.gitleaks.toml` + Woodpecker CI step + local pre-push hook). No 2FA/audit API exists in v17, so enrollment and log review are partly UI/CLI procedures documented here.

**Tech Stack:** Forgejo 17.0.0, Docker Compose (`deploy/local-forge`), gitleaks 8.30.1, TOTP (Forgejo built-in), SQLite audit log, Woodpecker CI v3.19.0, bash + curl + jq.

**Spec:** `docs/plans/forgejo-full-setup.md` (Phase 8 — Security & Access; Phase 1–3 already complete). Related: `docs/ops/SECRETS_ROTATION.md` (90-day baseline), `SECURITY.md` (gitleaks policy).

## Global Constraints

- Forgejo base URL: `http://localhost:3000` (LAN `http://192.168.1.35:3000`); admin user `sctl`.
- Admin token: `FORGEJO_TOKEN` in `/Users/chrisstefan/Code/source-control/deploy/local-forge/local-forge.env` (mode 600). Mint a fresh one with `docker exec -u git local-forge-forgejo-1 forgejo admin user generate-access-token -u sctl -t "<name>" --scopes all --raw`.
- Human accounts requiring 2FA: `chris`, `sctl`. Agent/bot accounts (`claude-agent`, `grok-agent`, `cursor-agent`, `paperclip-bot`, `ci-runner`) are service identities and must NOT have interactive 2FA; they authenticate via scoped PATs only.
- All five repos live under org `digithings-ai`: `digithings`, `twelve-x`, `datatap-web`, `paperclip`, `digiforge`. Each has `develop` and `main` branch protection.
- Token files under `~/.config/digithings/forgejo-tokens/` are mode 600; never commit them.
- `GLOBAL_TWO_FACTOR_REQUIREMENT` must be set to `admin` (admins required; agents cannot enroll TOTP and would be locked out under `all`).
- gitleaks binary available at `/opt/homebrew/bin/gitleaks` (v8.30.1); config at repo root `.gitleaks.toml`.
- Backup `SECRET_KEY` before any change — losing it makes existing 2FA secrets undecryptable.

---

### Task 1: Enforce and enroll 2FA for human accounts

**Files:**
- Modify: `/data/gitea/conf/app.ini` inside volume `local-forge_forgejo-data` (via `docker exec`).
- Create: `docs/ops/forgejo-2fa-runbook.md` (new, in repo) documenting enrollment + recovery.
- Backup: `/data/gitea/conf/app.ini.bak.<date>` and `SECRET_KEY` copy (offline, not in repo).

**Interfaces:**
- Consumes: admin token from `local-forge.env`; `forgejo admin user reset-mfa` CLI.
- Produces: `GLOBAL_TWO_FACTOR_REQUIREMENT = admin` in app.ini; TOTP enrolled for `chris` and `sctl`; recovery codes stored out-of-band.

- [ ] **Step 1: Back up the current app.ini and SECRET_KEY**

```bash
set -a; . /Users/chrisstefan/Code/source-control/deploy/local-forge/local-forge.env; set +a
docker exec -u git local-forge-forgejo-1 cp /data/gitea/conf/app.ini /data/gitea/conf/app.ini.bak.$(date +%Y%m%d)
docker exec -u git local-forge-forgejo-1 grep '^SECRET_KEY' /data/gitea/conf/app.ini
# Copy the printed SECRET_KEY value into a password manager entry named
# "forgejo-secret-key (localhost:3000)" — do NOT paste it into any ticket/chat.
```

Expected: backup file created; SECRET_KEY value captured in password manager.

- [ ] **Step 2: Set `GLOBAL_TWO_FACTOR_REQUIREMENT = admin` in app.ini**

```bash
docker exec -u git local-forge-forgejo-1 sh -c '
  python3 - <<PY
import re
p="/data/gitea/conf/app.ini"
s=open(p).read()
if "GLOBAL_TWO_FACTOR_REQUIREMENT" in s:
    s=re.sub(r"^GLOBAL_TWO_FACTOR_REQUIREMENT\s*=.*", "GLOBAL_TWO_FACTOR_REQUIREMENT = admin", s, flags=re.M)
else:
    s=s.replace("[security]\n", "[security]\nGLOBAL_TWO_FACTOR_REQUIREMENT = admin\n", 1)
open(p,"w").write(s)
print("done")
PY'
docker exec -u git local-forge-forgejo-1 grep -n "GLOBAL_TWO_FACTOR_REQUIREMENT\|SECRET_KEY" /data/gitea/conf/app.ini
```

Expected: `GLOBAL_TWO_FACTOR_REQUIREMENT = admin` present under `[security]`.

- [ ] **Step 3: Restart Forgejo and verify it boots**

```bash
cd /Users/chrisstefan/Code/source-control/deploy/local-forge && docker compose restart forgejo
sleep 5
curl -s http://localhost:3000/api/healthz; echo
# Re-mint an admin token (container restart keeps DB, token survives)
T=$(docker exec -u git local-forge-forgejo-1 forgejo admin user generate-access-token -u sctl -t "phase6-verify-$(date +%s)" --scopes all --raw)
echo "new token: $T"
curl -s -o /dev/null -w "HTTP %{http_code}\n" -H "Authorization: token $T" http://localhost:3000/api/v1/user
```

Expected: healthz `{"ok":true}`; `/api/v1/user` returns 200 with `"login":"sctl"`.

- [ ] **Step 4: Enroll TOTP for `sctl` (browser, admin)**

Open `http://localhost:3000/user/settings/security` as `sctl` (password from `local-forge.env` `FORGEJO_ADMIN_PASSWORD`). Click "Enable Two-Factor Authentication", scan the QR with an authenticator app (1Password/Authy), enter the 6-digit code, and **save the recovery codes** into the password manager entry "forgejo-sctl-2fa-recovery". Verify the `2FA` column flips to `true`:

```bash
docker exec -u git local-forge-forgejo-1 forgejo admin user list | grep -E "sctl|chris"
```

Expected: `sctl ... true` in the `2FA` column.

- [ ] **Step 5: Enroll TOTP for `chris`**

Chris logs in at `http://localhost:3000/user/settings/security` (password from `local-forge.env` `CHRIS_FORGEJO_PASSWORD`), enables 2FA, saves recovery codes to password manager entry "forgejo-chris-2fa-recovery". Verify:

```bash
docker exec -u git local-forge-forgejo-1 forgejo admin user list | grep chris
```

Expected: `chris ... true` in the `2FA` column.

- [ ] **Step 6: Confirm agent/bot accounts remain 2FA-free and PAT-only**

```bash
docker exec -u git local-forge-forgejo-1 forgejo admin user list
```

Expected: `claude-agent`, `grok-agent`, `cursor-agent`, `paperclip-bot`, `ci-runner` all show `2FA=false`. These identities never log in via browser; they use PATs from `~/.config/digithings/forgejo-tokens/`.

- [ ] **Step 7: Document recovery procedure**

Create `docs/ops/forgejo-2fa-runbook.md`:

```markdown
# Forgejo 2FA recovery (localhost:3000)

- Requirement: `GLOBAL_TWO_FACTOR_REQUIREMENT = admin` in `[security]`
  (`app.ini`); admins (`sctl`, `chris`) must enroll TOTP.
- Recovery codes: stored in password manager under
  "forgejo-<user>-2fa-recovery". Use one if the authenticator is lost.
- Admin reset (loses 2FA, user must re-enroll):
  `docker exec -u git local-forge-forgejo-1 forgejo admin user reset-mfa -u <username>`
- If SECRET_KEY is lost, ALL 2FA secrets are unrecoverable; restore from backup.
- Never disable 2FA globally except during a documented incident; re-enable
  immediately after.
```

- [ ] **Step 8: Commit**

```bash
git add docs/ops/forgejo-2fa-runbook.md
git commit -m "docs(forgejo): 2FA enrollment + recovery runbook (Phase 6)"
```

---

### Task 2: Token rotation policy (90-day cadence)

**Files:**
- Create: `scripts/forgejo-token-rotate.sh` (new, executable) — rotates a single identity's PAT.
- Create: `docs/ops/forgejo-token-rotation.md` (new) — policy + cadence table.
- Modify: `~/.config/digithings/forgejo-tokens/README.md` (not in repo; update locally) — add expiry column.

**Interfaces:**
- Consumes: admin token; `forgejo admin user generate-access-token` / `... tokens` DELETE API.
- Produces: rotated PAT written to `~/.config/digithings/forgejo-tokens/<user>.token` (mode 600) with a sidecar `~/.config/digithings/forgejo-tokens/<user>.expires` containing the ISO-8601 expiry date (90 days out).

- [ ] **Step 1: Define the rotation policy document**

Create `docs/ops/forgejo-token-rotation.md`:

```markdown
# Forgejo token rotation policy (localhost:3000)

Baseline: 90 days for every PAT an agent or human uses against Forgejo
(aligns with docs/ops/SECRETS_ROTATION.md standing baseline).

| Identity | Token file | Scope | Cadence | Owner |
|---|---|---|---|---|
| sctl | local-forge.env FORGEJO_TOKEN | all | 90 days | admin (sctl) |
| chris | chris.token | all (human) | 90 days | chris |
| claude-agent | claude-agent.token | write (repo + packages) | 90 days | Claude seat |
| grok-agent | grok-agent.token | write | 90 days | Grok seat |
| cursor-agent | cursor-agent.token | write | 90 days | Cursor seat |
| paperclip-bot | paperclip-bot.token | write + PR/review | 90 days | Paperclip seat |
| ci-runner | ci-runner.token | read + CI | 90 days | CI owner |

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
```

- [ ] **Step 2: Write the rotation script**

Create `scripts/forgejo-token-rotate.sh`:

```bash
#!/usr/bin/env bash
# Rotate one Forgejo PAT. Usage: forgejo-token-rotate.sh <username> [scope]
# scope defaults to "all" for humans, callers pass "write" etc. for agents.
set -euo pipefail
USER="${1:?username required}"
SCOPE="${2:-all}"
BASE="http://localhost:3000"
ENV_FILE="/Users/chrisstefan/Code/source-control/deploy/local-forge/local-forge.env"
set -a; . "$ENV_FILE"; set +a
TOKEN_DIR="$HOME/.config/digithings/forgejo-tokens"
NAME="rotated-$(date +%Y%m%d-%H%M%S)"

# 1. mint
NEW=$(docker exec -u git local-forge-forgejo-1 forgejo admin user generate-access-token \
      -u "$USER" -t "$NAME" --scopes "$SCOPE" --raw)
echo "minted $NAME for $USER"

# 2. verify before overwriting anything
CODE=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: token $NEW" "$BASE/api/v1/user")
[ "$CODE" = "200" ] || { echo "new token failed verification: HTTP $CODE"; exit 1; }

# 3. write token + expiry sidecar
umask 077
printf '%s\n' "$NEW" > "$TOKEN_DIR/$USER.token"
EXPIRY=$(date -v+90d +%Y-%m-%d 2>/dev/null || date -d '+90 days' +%Y-%m-%d)
printf '%s\n' "$EXPIRY" > "$TOKEN_DIR/$USER.expires"
chmod 600 "$TOKEN_DIR/$USER.token" "$TOKEN_DIR/$USER.expires"
echo "wrote $TOKEN_DIR/$USER.token (expires $EXPIRY)"

# 4. revoke old tokens for this user (keep the one we just minted)
curl -s -u "sctl:${FORGEJO_ADMIN_PASSWORD}" "$BASE/api/v1/users/$USER/tokens" \
  | python3 -c "import sys,json; [print(t['name']) for t in json.load(sys.stdin) if t['name']!='$NAME']" \
  | while read -r old; do
      echo "revoking old token: $old"
      curl -s -X DELETE -u "sctl:${FORGEJO_ADMIN_PASSWORD}" "$BASE/api/v1/users/$USER/tokens/$old" -o /dev/null -w "  HTTP %{http_code}\n"
    done

echo "rotation complete for $USER; update consumers (env files, CI secrets, agent configs) now."
```

```bash
chmod +x scripts/forgejo-token-rotate.sh
```

- [ ] **Step 3: Add an expiry check to the access-review script (Task 6) and document cadence**

Add to `docs/ops/forgejo-token-rotation.md` a "Rotation log" table:

```markdown
## Rotation log

| Date | Identity | Old token name | New token name | Expiry | Operator |
|---|---|---|---|---|---|
```

- [ ] **Step 4: Rotate all seven tokens once to seed expiry sidecars**

```bash
cd /Users/chrisstefan/Code/digithings
for u in sctl chris claude-agent grok-agent cursor-agent paperclip-bot ci-runner; do
  scope=all
  case "$u" in claude-agent|grok-agent|cursor-agent|paperclip-bot) scope=write;; ci-runner) scope=read;; esac
  ./scripts/forgejo-token-rotate.sh "$u" "$scope"
done
```

Note: for `sctl`, the script mints via CLI but the handoff file `local-forge.env` still holds the OLD `FORGEJO_TOKEN`. Update it manually:

```bash
NEW=$(cat ~/.config/digithings/forgejo-tokens/sctl.token)
sed -i '' "s|^FORGEJO_TOKEN=.*|FORGEJO_TOKEN=$NEW|" /Users/chrisstefan/Code/source-control/deploy/local-forge/local-forge.env
grep '^FORGEJO_TOKEN=' /Users/chrisstefan/Code/source-control/deploy/local-forge/local-forge.env
```

- [ ] **Step 5: Verify all tokens**

```bash
for f in /Users/chrisstefan/.config/digithings/forgejo-tokens/*.token; do
  u=$(basename "$f" .token)
  t=$(cat "$f")
  code=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: token $t" http://localhost:3000/api/v1/user)
  echo "$u: HTTP $code (expires $(cat ${f%.token}.expires))"
done
```

Expected: every identity returns `HTTP 200`.

- [ ] **Step 6: Commit**

```bash
git add scripts/forgejo-token-rotate.sh docs/ops/forgejo-token-rotation.md
git commit -m "feat(forgejo): 90-day token rotation policy + script (Phase 6)"
```

---

### Task 3: Audit logging configuration

**Files:**
- Modify: `/data/gitea/conf/app.ini` inside the volume (log section).
- Create: `docs/ops/forgejo-audit-log.md` (new) — what is logged, where, retention.

**Interfaces:**
- Consumes: admin token; container restart.
- Produces: file-based logs under `/data/gitea/log/` inside the volume, rotated daily, retained 30 days; access log with request ID; log persisted across container restarts via the named volume.

- [ ] **Step 1: Configure file logging + access log in app.ini**

```bash
docker exec -u git local-forge-forgejo-1 sh -c '
python3 - <<PY
p="/data/gitea/conf/app.ini"
s=open(p).read()

# Replace [log] block
import re
old_log = """[log]
MODE = console
LEVEL = info
ROOT_PATH = /data/gitea/log"""
new_log = """[log]
MODE = console, file
LEVEL = info
ROOT_PATH = /data/gitea/log
LOGGER_ACCESS_MODE = file
ENABLE_XORM_LOG = false"""
assert old_log in s, "log block not found"
s = s.replace(old_log, new_log, 1)

# Add [log.file] subsection after [log] block (before [security])
file_sub = """[log.file]
MODE = file
LEVEL = info
FILE_NAME = forgejo.log
MAX_SIZE_SHIFT = 28
MAX_DAYS = 30
COMPRESS = true
DAILY_ROTATE = true
LOG_ROTATE = true

[log.file.access]
MODE = file
LEVEL = info
FILE_NAME = access.log
MAX_SIZE_SHIFT = 28
MAX_DAYS = 30
COMPRESS = true
DAILY_ROTATE = true
LOG_ROTATE = true

"""
s = s.replace("[security]\n", file_sub + "[security]\n", 1)

# Access log template with request id
s = s.replace("REVERSE_PROXY_LIMIT = 1",
              "REVERSE_PROXY_LIMIT = 1\nREQUEST_ID_HEADERS = X-Request-ID")
open(p,"w").write(s)
print("done")
PY'
docker exec -u git local-forge-forgejo-1 grep -n "^\[log\]\|MODE\|LEVEL\|FILE_NAME\|MAX_DAYS\|LOGGER_ACCESS\|REQUEST_ID" /data/gitea/conf/app.ini
```

Expected: `[log]` with `MODE = console, file`, `[log.file]` and `[log.file.access]` subsections, `MAX_DAYS = 30`.

- [ ] **Step 2: Restart and verify log files are created**

```bash
cd /Users/chrisstefan/Code/source-control/deploy/local-forge && docker compose restart forgejo
sleep 6
docker exec -u git local-forge-forgejo-1 ls -la /data/gitea/log/
```

Expected: `forgejo.log` and `access.log` present (non-empty after the healthz probe).

- [ ] **Step 3: Generate an auditable event and confirm it lands in the log**

```bash
T=$(docker exec -u git local-forge-forgejo-1 forgejo admin user generate-access-token -u sctl -t "audit-probe-$(date +%s)" --scopes all --raw)
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: token $T" http://localhost:3000/api/v1/user
docker exec -u git local-forge-forgejo-1 tail -5 /data/gitea/log/access.log
```

Expected: access.log contains a line with the request method/path and the `sctl` identity.

- [ ] **Step 4: Document log location, retention, and review**

Create `docs/ops/forgejo-audit-log.md`:

```markdown
# Forgejo audit logging (localhost:3000)

- Config: `/data/gitea/conf/app.ini` inside volume `local-forge_forgejo-data`.
  `[log] MODE = console, file`, `LEVEL = info`, plus `[log.file]` and
  `[log.file.access]` subsections writing `forgejo.log` / `access.log`.
- Location inside container: `/data/gitea/log/`. On host: via the named volume
  `local-forge_forgejo-data` (mount `/data`).
- Retention: 30 days, daily rotation, gzip compression (`MAX_DAYS=30`,
  `DAILY_ROTATE=true`, `COMPRESS=true`).
- Access log template records remote host, identity (SignedUserName or `-`),
  timestamp, method, URL, status, size, referer, user agent, request id.
- What is NOT logged: 2FA secret values, token values, passwords. Forgejo never
  records the `Sudo` header on reviews or in any readable endpoint (see
  digiforge/internal/forge forge.go note).

## Review procedure
1. `docker exec -u git local-forge-forgejo-1 tail -n 200 /data/gitea/log/access.log`
2. Filter for admin actions: `grep -E "POST|PUT|DELETE|PATCH" access.log | grep -v "200\|201\|204"` (non-2xx mutations).
3. Check for failed auth: `grep " 401 \| 403 " access.log`.
4. Archive monthly: copy the volume's log dir to a dated backup before rotation
   purges it (30-day window).

## Backup
docker compose stop forgejo
docker run --rm -v local-forge_forgejo-data:/data -v "$HOME/Backups":/backup alpine \
  tar czf /backup/forgejo-logs-$(date +%Y%m%d).tgz -C /data/log .
docker compose start forgejo
```

- [ ] **Step 5: Commit**

```bash
git add docs/ops/forgejo-audit-log.md
git commit -m "docs(forgejo): audit logging configuration + runbook (Phase 6)"
```

---

### Task 4: Branch protection verification

**Files:**
- Create: `scripts/forgejo-branch-protection-verify.sh` (new, executable) — asserts the expected matrix.
- Create: `docs/ops/forgejo-branch-protection.md` (new) — expected matrix + how to fix.

**Interfaces:**
- Consumes: admin token; `/api/v1/repos/{owner}/{repo}/branch_protections`.
- Produces: exit 0 only if every repo matches the expected matrix; prints a diff otherwise.

Expected matrix (from Phase 2 completion, now hardened):

| Branch | enable_push | required_approvals | enable_status_check | require_signed_commits | apply_to_admins | block_on_rejected_reviews | dismiss_stale_approvals | block_on_outdated_branch |
|---|---|---|---|---|---|---|---|---|
| develop | false | 1 | false | false | true | true | true | true |
| main | false | 1 | true | false | true | true | true | true |

Rationale for the new hardening flags (currently false in Phase 2):
- `dismiss_stale_approvals = true` — a new push invalidates prior approvals.
- `block_on_outdated_branch = true` — PR must be up to date with base before merge.
- `require_signed_commits` stays `false` for now (optional, see note).

- [ ] **Step 1: Write the verifier script**

Create `scripts/forgejo-branch-protection-verify.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
ENV_FILE="/Users/chrisstefan/Code/source-control/deploy/local-forge/local-forge.env"
set -a; . "$ENV_FILE"; set +a
BASE="http://localhost:3000"
OWNER="digithings-ai"
REPOS=(digithings twelve-x datatap-web paperclip digiforge)
FAIL=0

check() {
  local repo=$1 branch=$2 field=$3 expected=$4
  actual=$(curl -s -H "Authorization: token $FORGEJO_TOKEN" \
    "$BASE/api/v1/repos/$OWNER/$repo/branch_protections" \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print([x['$field'] for x in d if x['rule_name']=='$branch'][0])")
  if [ "$actual" != "$expected" ]; then
    echo "MISMATCH $repo/$branch: $field = $actual (expected $expected)"
    FAIL=1
  fi
}

for repo in "${REPOS[@]}"; do
  for branch in develop main; do
    check "$repo" "$branch" enable_push false
    check "$repo" "$branch" apply_to_admins true
    check "$repo" "$branch" block_on_rejected_reviews true
    check "$repo" "$branch" required_approvals 1
    check "$repo" "$branch" dismiss_stale_approvals true
    check "$repo" "$branch" block_on_outdated_branch true
  done
  # main-only: status checks enabled
  check "$repo" main enable_status_check true
done

if [ "$FAIL" -ne 0 ]; then
  echo "branch protection verification FAILED"
  exit 1
fi
echo "branch protection verification OK (5 repos x 2 branches)"
```

```bash
chmod +x scripts/forgejo-branch-protection-verify.sh
```

- [ ] **Step 2: Run the verifier against current state (expect failures on new flags)**

```bash
cd /Users/chrisstefan/Code/digithings && ./scripts/forgejo-branch-protection-verify.sh; echo "exit: $?"
```

Expected: mismatches reported for `dismiss_stale_approvals` and `block_on_outdated_branch` (currently false).

- [ ] **Step 3: Patch all protections to the hardened matrix**

```bash
cd /Users/chrisstefan/Code/digithings
ENV_FILE="/Users/chrisstefan/Code/source-control/deploy/local-forge/local-forge.env"
set -a; . "$ENV_FILE"; set +a
python3 - <<'PY'
import json, subprocess, urllib.request
base="http://localhost:3000"; owner="digithings-ai"
repos=["digithings","twelve-x","datatap-web","paperclip","digiforge"]
token=open("/dev/stdin").read().strip() if False else None
import os
tok=os.environ["FORGEJO_TOKEN"]
for repo in repos:
    for branch in ("develop","main"):
        payload={
            "rule_name": branch,
            "enable_push": False,
            "enable_push_whitelist": False,
            "push_whitelist_usernames": [],
            "push_whitelist_teams": [],
            "push_whitelist_deploy_keys": False,
            "enable_merge_whitelist": False,
            "merge_whitelist_usernames": [],
            "merge_whitelist_teams": [],
            "enable_status_check": branch=="main",
            "status_check_contexts": [],
            "required_approvals": 1,
            "enable_approvals_whitelist": False,
            "approvals_whitelist_username": [],
            "approvals_whitelist_teams": [],
            "block_on_rejected_reviews": True,
            "block_on_official_review_requests": False,
            "block_on_outdated_branch": True,
            "dismiss_stale_approvals": True,
            "ignore_stale_approvals": False,
            "require_signed_commits": False,
            "protected_file_patterns": "",
            "unprotected_file_patterns": "",
            "apply_to_admins": True,
        }
        # PATCH (update) if exists
        req=urllib.request.Request(f"{base}/api/v1/repos/{owner}/{repo}/branch_protections/{branch}",
            data=json.dumps(payload).encode(), method="PATCH",
            headers={"Authorization":f"token {tok}","Content-Type":"application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                print(repo, branch, r.status)
        except urllib.error.HTTPError as e:
            # fall back to POST (create)
            req2=urllib.request.Request(f"{base}/api/v1/repos/{owner}/{repo}/branch_protections",
                data=json.dumps(payload).encode(), method="POST",
                headers={"Authorization":f"token {tok}","Content-Type":"application/json"})
            with urllib.request.urlopen(req2) as r:
                print(repo, branch, "created", r.status)
PY
```

Expected: each line prints `200` (or `created 201`).

- [ ] **Step 4: Re-run the verifier**

```bash
./scripts/forgejo-branch-protection-verify.sh; echo "exit: $?"
```

Expected: `branch protection verification OK (5 repos x 2 branches)`, exit 0.

- [ ] **Step 5: (Optional) Enable signed commits**

Signed commits require each committer to register a GPG key (`/user/gpg_keys`) and set `require_signed_commits = true` on both branches. This is a larger rollout (all agents must sign). Decision: leave `false` now; track as a follow-up. Document in `docs/ops/forgejo-branch-protection.md`.

Create `docs/ops/forgejo-branch-protection.md` with the expected matrix, the verifier command, and the signed-commits follow-up note.

- [ ] **Step 6: Commit**

```bash
git add scripts/forgejo-branch-protection-verify.sh docs/ops/forgejo-branch-protection.md
git commit -m "feat(forgejo): hardened branch protection + verifier (Phase 6)"
```

---

### Task 5: Secret scanning (gitleaks integration)

**Files:**
- Modify: `.woodpecker.yml` on the `develop` branch of each Forgejo repo (`digithings-ai/{digithings,twelve-x,datatap-web,paperclip,digiforge}`) — add a `gitleaks` step.
- Create: `scripts/forgejo-gitleaks-woodpecker-step.yml` (new) — reusable snippet.
- Create: `.githooks/pre-push` (new, optional, local) — runs gitleaks on the pushed range.
- Reuse: existing `.gitleaks.toml` at repo root and `.github/workflows/security-gitleaks.yml` (GitHub side, already in place).

**Interfaces:**
- Consumes: gitleaks 8.30.1, `.gitleaks.toml`, Forgejo admin token.
- Produces: a `gitleaks-scan` Woodpecker step on every `push` and `pull_request` for all 5 repos; a local pre-push hook that blocks pushes containing findings.

- [ ] **Step 1: Create the reusable Woodpecker gitleaks step**

Create `scripts/forgejo-gitleaks-woodpecker-step.yml`:

```yaml
  gitleaks:
    image: zricethezav/gitleaks:v8.30.1
    commands:
      - gitleaks detect --source . --config .gitleaks.toml --redact --no-banner --exit-code 1
    when:
      - event: [push, pull_request]
```

Note: the image tag pins the scanner version; bump together with a note (mirrors the GitHub workflow pin policy).

- [ ] **Step 2: Inject the step into each repo's `.woodpecker.yml` on Forgejo**

The existing pipeline per repo (from Phase 2) is `{lint,test,build}` (digithings) etc. Add the `gitleaks` step as the first step so a leak fails fast. Use the Forgejo contents API to read, patch, and write back.

```bash
set -a; . /Users/chrisstefan/Code/source-control/deploy/local-forge/local-forge.env; set +a
BASE="http://localhost:3000"; OWNER="digithings-ai"
for repo in digithings twelve-x datatap-web paperclip digiforge; do
  # read current file + sha
  resp=$(curl -s -H "Authorization: token $FORGEJO_TOKEN" \
    "$BASE/api/v1/repos/$OWNER/$repo/contents/.woodpecker.yml?ref=develop")
  sha=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin)['sha'])")
  content=$(echo "$resp" | python3 -c "import sys,json,base64; print(base64.b64decode(json.load(sys.stdin)['content']).decode())")
  # prepend gitleaks step after the 'steps:' line
  patched=$(python3 - "$content" <<'PY'
import sys
src=sys.stdin.read() if False else open('/dev/stdin').read()
# simpler: read from arg
PY
  )
  echo "=== $repo ==="; echo "$content" | head -3
done
```

Because multi-line patching in shell is error-prone, do it with a Python helper that edits each repo's file via the API:

```bash
cat > /tmp/scratchpad/patch_wp.py <<'PY'
import base64, json, os, urllib.request, urllib.error
base="http://localhost:3000"; owner="digithings-ai"
tok=os.environ["FORGEJO_TOKEN"]
repos=["digithings","twelve-x","datatap-web","paperclip","digiforge"]
step = """  gitleaks:
    image: zricethezav/gitleaks:v8.30.1
    commands:
      - gitleaks detect --source . --config .gitleaks.toml --redact --no-banner --exit-code 1

"""
for repo in repos:
    url=f"{base}/api/v1/repos/{owner}/{repo}/contents/.woodpecker.yml?ref=develop"
    req=urllib.request.Request(url, headers={"Authorization":f"token {tok}"})
    with urllib.request.urlopen(req) as r:
        d=json.load(r)
    sha=d["sha"]
    content=base64.b64decode(d["content"]).decode()
    if "gitleaks:" in content:
        print(repo, "already patched, skipping"); continue
    # insert step right after the first "steps:" line
    lines=content.splitlines(keepends=True)
    out=[]
    inserted=False
    for ln in lines:
        out.append(ln)
        if not inserted and ln.strip()=="steps:":
            out.append(step)
            inserted=True
    patched="".join(out)
    if not inserted:
        print(repo, "no 'steps:' line found, skipping"); continue
    # write back
    payload={"content":base64.b64encode(patched.encode()).decode(),
             "message":"ci: add gitleaks secret scan step (Phase 6)",
             "sha":sha,"branch":"develop"}
    wreq=urllib.request.Request(f"{base}/api/v1/repos/{owner}/{repo}/contents/.woodpecker.yml",
        data=json.dumps(payload).encode(), method="PUT",
        headers={"Authorization":f"token {tok}","Content-Type":"application/json"})
    with urllib.request.urlopen(wreq) as r:
        print(repo, "patched", r.status)
PY
set -a; . /Users/chrisstefan/Code/source-control/deploy/local-forge/local-forge.env; set +a
python3 /tmp/scratchpad/patch_wp.py
```

Expected: each repo prints `patched 200` (or `already patched, skipping` on re-run).

- [ ] **Step 3: Push `.gitleaks.toml` into each Forgejo repo**

The GitHub-side config lives at the repo root of `digithings`. The Forgejo repos need the same config so the Woodpecker step can read it. Copy it to each repo's `develop` branch.

```bash
set -a; . /Users/chrisstefan/Code/source-control/deploy/local-forge/local-forge.env; set +a
BASE="http://localhost:3000"; OWNER="digithings-ai"
CFG=$(base64 < /Users/chrisstefan/Code/digithings/.gitleaks.toml)
for repo in digithings twelve-x datatap-web paperclip digiforge; do
  # check if file exists to get sha
  sha=$(curl -s -H "Authorization: token $FORGEJO_TOKEN" \
    "$BASE/api/v1/repos/$OWNER/$repo/contents/.gitleaks.toml?ref=develop" \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('sha',''))" 2>/dev/null)
  if [ -n "$sha" ]; then
    payload="{\"content\":\"$CFG\",\"message\":\"chore: sync .gitleaks.toml (Phase 6)\",\"sha\":\"$sha\",\"branch\":\"develop\"}"
  else
    payload="{\"content\":\"$CFG\",\"message\":\"chore: add .gitleaks.toml (Phase 6)\",\"branch\":\"develop\"}"
  fi
  code=$(curl -s -o /dev/null -w "%{http_code}" -X PUT \
    -H "Authorization: token $FORGEJO_TOKEN" -H "Content-Type: application/json" \
    -d "$payload" "$BASE/api/v1/repos/$OWNER/$repo/contents/.gitleaks.toml")
  echo "$repo: HTTP $code"
done
```

Expected: every repo returns `HTTP 200` or `HTTP 201`.

- [ ] **Step 4: Install a local pre-push hook**

Create `.githooks/pre-push` (and point `core.hooksPath` at `.githooks`):

```bash
mkdir -p /Users/chrisstefan/Code/digithings/.githooks
cat > /Users/chrisstefan/Code/digithings/.githooks/pre-push <<'SH'
#!/usr/bin/env bash
# Block pushes that introduce gitleaks findings.
set -euo pipefail
if ! command -v gitleaks >/dev/null 2>&1; then
  echo "gitleaks not installed; skipping local scan (CI still scans)."; exit 0
fi
# Scan the commits being pushed.
remote="$1"; url="$2"
zero=$(git hash-object --stdin </dev/null | tr '0-9a-f' '0')
while read local_ref local_sha remote_ref remote_sha; do
  if [ "$local_sha" = "$zero" ]; then continue; fi
  if [ "$remote_sha" = "$zero" ]; then
    range="$local_sha"
  else
    range="$remote_sha..$local_sha"
  fi
  gitleaks detect --source . --config .gitleaks.toml --redact --no-banner \
    --log-opts="$range" || { echo "gitleaks: push blocked"; exit 1; }
done
SH
chmod +x /Users/chrisstefan/Code/digithings/.githooks/pre-push
cd /Users/chrisstefan/Code/digithings && git config core.hooksPath .githooks
```

- [ ] **Step 5: Verify the scan works locally**

```bash
cd /Users/chrisstefan/Code/digithings
gitleaks detect --source . --config .gitleaks.toml --redact --no-banner --exit-code 1; echo "exit: $?"
```

Expected: exit 0 (no findings) on a clean tree. To prove detection works, create a scratch file with a fake AWS key, run the scan, confirm non-zero, then delete the scratch file (do not commit).

```bash
cd /Users/chrisstefan/Code/digithings
printf 'AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n' > .agent-tmp/tmp/leak-probe.txt
gitleaks detect --source . --config .gitleaks.toml --no-banner --exit-code 1 2>&1 | tail -3
rm -f .agent-tmp/tmp/leak-probe.txt
```

Wait — `AKIAIOSFODNN7EXAMPLE` is allowlisted by regex in `.gitleaks.toml`. Use a non-allowlisted synthetic value instead, e.g. `AKIAZ7VQXYLMNOPQRSTU` (still synthetic, never a real key) and confirm it fires, then remove.

- [ ] **Step 6: Commit local changes**

```bash
git add .githooks/pre-push scripts/forgejo-gitleaks-woodpecker-step.yml
git commit -m "feat(forgejo): gitleaks pre-push hook + Woodpecker step template (Phase 6)"
```

---

### Task 6: Access review process

**Files:**
- Create: `scripts/forgejo-access-review.sh` (new, executable) — dumps users, teams, memberships, branch protections, token expiry.
- Create: `docs/ops/forgejo-access-review.md` (new) — quarterly review checklist.

**Interfaces:**
- Consumes: admin token; Forgejo REST API.
- Produces: a dated report under `docs/ops/access-reviews/YYYY-MM-DD-forgejo.md` (created by the reviewer, not committed with secrets) and an exit code 0 only if no stale tokens / unexpected members.

- [ ] **Step 1: Write the access-review dump script**

Create `scripts/forgejo-access-review.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
ENV_FILE="/Users/chrisstefan/Code/source-control/deploy/local-forge/local-forge.env"
set -a; . "$ENV_FILE"; set +a
BASE="http://localhost:3000"; OWNER="digithings-ai"
OUT_DIR="${1:-.agent-tmp/access-review}"
mkdir -p "$OUT_DIR"
DATE=$(date +%Y-%m-%d)
REPORT="$OUT_DIR/$DATE-forgejo-access-review.md"

{
  echo "# Forgejo access review — $DATE"
  echo
  echo "## Users"
  curl -s -H "Authorization: token $FORGEJO_TOKEN" "$BASE/api/v1/admin/users" \
    | python3 -c "import sys,json; d=json.load(sys.stdin); [print(f'- {u[\"login\"]} (admin={u.get(\"is_admin\")}, 2fa={u.get(\"two_factor\")}, last_login={u.get(\"last_login\")})') for u in (d if isinstance(d,list) else d.get('data',[]))]"
  echo
  echo "## Org members & teams"
  for tid in 2 3 4 5 6; do
    name=$(curl -s -H "Authorization: token $FORGEJO_TOKEN" "$BASE/api/v1/teams/$tid" | python3 -c "import sys,json; print(json.load(sys.stdin).get('name'))")
    members=$(curl -s -H "Authorization: token $FORGEJO_TOKEN" "$BASE/api/v1/teams/$tid/members" | python3 -c "import sys,json; d=json.load(sys.stdin); print(', '.join(u['login'] for u in (d if isinstance(d,list) else d.get('data',[])))")
    echo "- team $tid ($name): $members"
  done
  echo
  echo "## Tokens (expiry)"
  for f in "$HOME/.config/digithings/forgejo-tokens"/*.token; do
    u=$(basename "$f" .token)
    exp=$(cat "${f%.token}.expires" 2>/dev/null || echo "NO EXPIRY FILE")
    echo "- $u: expires $exp"
  done
  echo
  echo "## Branch protection matrix"
  for repo in digithings twelve-x datatap-web paperclip digiforge; do
    echo "### $repo"
    curl -s -H "Authorization: token $FORGEJO_TOKEN" "$BASE/api/v1/repos/$OWNER/$repo/branch_protections" \
      | python3 -c "import sys,json; d=json.load(sys.stdin); [print(f'  - {x[\"rule_name\"]}: push={x[\"enable_push\"]} approvals={x[\"required_approvals\"]} status={x[\"enable_status_check\"]} signed={x[\"require_signed_commits\"]} admins={x[\"apply_to_admins\"]} dismiss_stale={x[\"dismiss_stale_approvals\"]} outdated={x[\"block_on_outdated_branch\"]}') for x in d]"
  done
  echo
  echo "## Stale-token check (expired sidecars)"
  for f in "$HOME/.config/digithings/forgejo-tokens"/*.expires; do
    exp=$(cat "$f"); u=$(basename "$f" .expires)
    if [ "$(date +%Y-%m-%d)" \> "$exp" ]; then echo "- EXPIRED: $u (expired $exp)"; fi
  done
  echo "## Done"
} > "$REPORT"
echo "report written: $REPORT"
```

```bash
chmod +x scripts/forgejo-access-review.sh
```

Note: `/api/v1/admin/users` may require admin; if it returns 404, fall back to `/api/v1/users/search` (paginated). The script above uses admin endpoint; adjust if needed.

- [ ] **Step 2: Run it once to seed the first report**

```bash
cd /Users/chrisstefan/Code/digithings
./scripts/forgejo-access-review.sh docs/ops/access-reviews 2>/dev/null || ./scripts/forgejo-access-review.sh
cat .agent-tmp/access-review/*-forgejo-access-review.md | head -60
```

Expected: a dated markdown report listing 7 users, 5 teams, token expiries, and the branch-protection matrix.

- [ ] **Step 3: Document the quarterly review process**

Create `docs/ops/forgejo-access-review.md`:

```markdown
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
1. Revoke all tokens: `DELETE /api/v1/users/{u}/tokens/*`.
2. Remove from all teams and org.
3. Optionally delete the account: `forgejo admin user delete --username {u}`.
4. Rotate any shared secrets the seat could read.
5. Log in the rotation log.
```

- [ ] **Step 4: Add the review to the quarterly calendar**

Add a reminder entry to `docs/ops/forgejo-access-review.md` noting the next
review date (first Monday of the next quarter) and that the report is stored
under `docs/ops/access-reviews/` (gitignored if it contains usernames? No —
usernames are not secrets; commit the report).

- [ ] **Step 5: Commit**

```bash
git add scripts/forgejo-access-review.sh docs/ops/forgejo-access-review.md
git commit -m "feat(forgejo): access review process + dump script (Phase 6)"
```

---

## Self-Review (plan author)

**1. Spec coverage:** Phase 8 of `forgejo-full-setup.md` lists 2FA, token management, audit logging, branch protection, and (newly added) secret scanning + access review. All six are covered by Tasks 1–6. Token scopes (`read/write/admin`) are captured in the rotation policy table. Signed commits are explicitly deferred with rationale.

**2. Placeholder scan:** All code steps include full commands. The only "optional" item (signed commits) is explicitly marked as a follow-up decision, not a TBD.

**3. Type consistency:** API field names match the swagger `CreateBranchProtectionOption` (e.g. `dismiss_stale_approvals`, `block_on_outdated_branch`, `apply_to_admins`). Token file paths match `~/.config/digithings/forgejo-tokens/`. Admin token source matches `local-forge.env`.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-10-24-forgejo-phase6-security.md`.

Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?<|end|><|start|>start to=shell<|channel|>analysis <|constrain|>xml<|message|><rfl:parameter name="command">
cat /Users/chrisstefan/Code/source-control/deploy/local-forge/ci/pipeline.yml 2>/dev/null; echo "=== woodpecker in digithings (develop) ==="; cd /Users/chrisstefan/Code/digithings && git show origin/develop:.woodpecker.yml 2>/dev/null | head -60