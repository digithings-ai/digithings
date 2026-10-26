#!/usr/bin/env bash
# Dump a Forgejo access review report (read-only).
#
#   scripts/forgejo-access-review.sh [output-dir]
#
# Default output: .agent-tmp/access-review/YYYY-MM-DD-forgejo-access-review.md
set -euo pipefail

ENV_FILE="${LOCAL_FORGE_ENV:-$HOME/Code/source-control/deploy/local-forge/local-forge.env}"
if [ ! -f "$ENV_FILE" ]; then
  echo "forgejo-access-review: env file not found: $ENV_FILE" >&2
  echo "Set LOCAL_FORGE_ENV to the Forgejo env file." >&2
  exit 1
fi
set -a; . "$ENV_FILE"; set +a

BASE="${FORGEJO_URL:-http://localhost:3000}"
CONTAINER="${FORGEJO_CONTAINER:-local-forge-forgejo-1}"
OWNER="${FORGEJO_REPO_ORG:-digithings-ai}"
OUT_DIR="${1:-.agent-tmp/access-review}"
mkdir -p "$OUT_DIR"
DATE=$(date +%Y-%m-%d)
REPORT="$OUT_DIR/$DATE-forgejo-access-review.md"

python3 - "$BASE" "$FORGEJO_TOKEN" "$OWNER" "$HOME" "$DATE" "$CONTAINER" <<'PY' > "$REPORT"
import glob
import json
import os
import subprocess
import sys
import urllib.request

base, tok, owner, home, date, container = sys.argv[1:7]

def api(path):
    req = urllib.request.Request(base + path, headers={"Authorization": f"token {tok}"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)

print(f"# Forgejo access review — {date}")
print()
print("## Users")
for u in api("/api/v1/admin/users"):
    print(f"- {u['login']} (admin={u.get('is_admin')}, last_login={u.get('last_login')})")
print()
print("## 2FA status (CLI)")
print("```")
try:
    print(subprocess.check_output(
        ["docker", "exec", "-u", "git", container, "forgejo", "admin", "user", "list"],
        text=True, stderr=subprocess.STDOUT).strip())
except (OSError, subprocess.CalledProcessError) as exc:
    print(f"unavailable: {exc}")
print("```")
print()
print("## Org members & teams")
for team in api(f"/api/v1/orgs/{owner}/teams"):
    members = api(f"/api/v1/teams/{team['id']}/members")
    xs = members if isinstance(members, list) else members.get("data", [])
    print(f"- {team.get('name')}: {', '.join(u['login'] for u in xs)}")
print()
print("## Tokens (expiry)")
for f in sorted(glob.glob(os.path.join(home, ".config/digithings/forgejo-tokens/*.token"))):
    u = os.path.basename(f).replace(".token", "")
    exp_path = f.replace(".token", ".expires")
    exp = open(exp_path).read().strip() if os.path.exists(exp_path) else "NO EXPIRY FILE"
    print(f"- {u}: expires {exp}")
print()
print("## Branch protection matrix")
for repo in ["digithings", "twelve-x", "datatap-web", "paperclip", "digiforge"]:
    print(f"### {repo}")
    try:
        rules = api(f"/api/v1/repos/{owner}/{repo}/branch_protections")
    except Exception as exc:  # report, do not abort the whole report
        print(f"  - unreadable: {exc}")
        continue
    for x in rules:
        print(
            f"  - {x['rule_name']}: push={str(x['enable_push']).lower()} "
            f"approvals={x['required_approvals']} "
            f"status={str(x['enable_status_check']).lower()} "
            f"signed={str(x['require_signed_commits']).lower()} "
            f"admins={str(x['apply_to_admins']).lower()} "
            f"dismiss_stale={str(x['dismiss_stale_approvals']).lower()} "
            f"outdated={str(x['block_on_outdated_branch']).lower()}"
        )
print()
print("## Stale-token check (expired sidecars)")
today = date
for f in sorted(glob.glob(os.path.join(home, ".config/digithings/forgejo-tokens/*.expires"))):
    exp = open(f).read().strip()
    u = os.path.basename(f).replace(".expires", "")
    if today > exp:
        print(f"- EXPIRED: {u} (expired {exp})")
print("## Done")
PY

echo "report written: $REPORT"
