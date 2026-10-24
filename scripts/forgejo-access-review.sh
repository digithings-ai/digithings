#!/usr/bin/env bash
set -euo pipefail
ENV_FILE="/Users/chrisstefan/Code/source-control/deploy/local-forge/local-forge.env"
set -a; . "$ENV_FILE"; set +a
BASE="http://localhost:3000"; OWNER="digithings-ai"
OUT_DIR="${1:-.agent-tmp/access-review}"
mkdir -p "$OUT_DIR"
DATE=$(date +%Y-%m-%d)
REPORT="$OUT_DIR/$DATE-forgejo-access-review.md"

python3 - "$BASE" "$FORGEJO_TOKEN" "$OWNER" "$HOME" "$DATE" <<'PY' > "$REPORT"
import json, subprocess, sys, urllib.request
base, tok, owner, home, date = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
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
print(subprocess.check_output(["docker","exec","-u","git","local-forge-forgejo-1","forgejo","admin","user","list"], text=True).strip())
print("```")
print()
print("## Org members & teams")
for tid in [2,3,4,5,6]:
    team = api(f"/api/v1/teams/{tid}")
    members = api(f"/api/v1/teams/{tid}/members")
    xs = members if isinstance(members, list) else members.get("data", [])
    print(f"- team {tid} ({team.get('name')}): {', '.join(u['login'] for u in xs)}")
print()
print("## Tokens (expiry)")
import glob, os
for f in sorted(glob.glob(os.path.join(home, ".config/digithings/forgejo-tokens/*.token"))):
    u = os.path.basename(f).replace(".token","")
    exp_path = f.replace(".token",".expires")
    exp = open(exp_path).read().strip() if os.path.exists(exp_path) else "NO EXPIRY FILE"
    print(f"- {u}: expires {exp}")
print()
print("## Branch protection matrix")
for repo in ["digithings","twelve-x","datatap-web","paperclip","digiforge"]:
    print(f"### {repo}")
    for x in api(f"/api/v1/repos/{owner}/{repo}/branch_protections"):
        print(f"  - {x['rule_name']}: push={str(x['enable_push']).lower()} approvals={x['required_approvals']} status={str(x['enable_status_check']).lower()} signed={str(x['require_signed_commits']).lower()} admins={str(x['apply_to_admins']).lower()} dismiss_stale={str(x['dismiss_stale_approvals']).lower()} outdated={str(x['block_on_outdated_branch']).lower()}")
print()
print("## Stale-token check (expired sidecars)")
today = date
for f in sorted(glob.glob(os.path.join(home, ".config/digithings/forgejo-tokens/*.expires"))):
    exp = open(f).read().strip()
    u = os.path.basename(f).replace(".expires","")
    if today > exp:
        print(f"- EXPIRED: {u} (expired {exp})")
print("## Done")
PY
echo "report written: $REPORT"