#!/usr/bin/env bash
# Verify the current Forgejo branch-protection matrix (localhost:3000).
#
# The matrix is the one documented in docs/ops/forgejo-branch-protection.md.
# It is deliberately not uniform: main is strict, the integration branch is
# lighter. A missing rule is a failure, not a crash.
set -euo pipefail

ENV_FILE="${LOCAL_FORGE_ENV:-$HOME/Code/source-control/deploy/local-forge/local-forge.env}"
if [ ! -f "$ENV_FILE" ]; then
  echo "branch-protection-verify: env file not found: $ENV_FILE" >&2
  echo "Set LOCAL_FORGE_ENV to the Forgejo env file." >&2
  exit 1
fi
set -a; . "$ENV_FILE"; set +a

BASE="${FORGEJO_URL:-http://localhost:3000}"
OWNER="${FORGEJO_REPO_ORG:-digithings-ai}"

python3 - "$BASE" "$FORGEJO_TOKEN" "$OWNER" <<'PY'
import json
import sys
import urllib.error
import urllib.request

base, token, owner = sys.argv[1:4]
headers = {"Authorization": "token " + token}

# repo, branch, enable_push, required_approvals, enable_status_check,
# require_signed_commits, apply_to_admins, block_on_rejected_reviews,
# dismiss_stale_approvals, block_on_outdated_branch
MATRIX = [
    ("digithings", "main", False, 1, True, False, True, True, True, True),
    ("digithings", "develop", False, 1, False, False, True, True, False, False),
    ("twelve-x", "main", False, 1, True, False, True, True, True, True),
    ("twelve-x", "develop", False, 1, False, False, True, True, False, False),
    ("datatap-web", "main", False, 1, False, False, True, True, False, False),
    ("paperclip", "main", False, 1, True, False, True, True, True, True),
    ("paperclip", "master", False, 1, False, False, True, True, False, False),
    ("digiforge", "main", False, 1, True, False, True, True, True, True),
    ("digiforge", "develop", False, 1, False, False, True, True, False, False),
]

FIELDS = (
    "enable_push",
    "required_approvals",
    "enable_status_check",
    "require_signed_commits",
    "apply_to_admins",
    "block_on_rejected_reviews",
    "dismiss_stale_approvals",
    "block_on_outdated_branch",
)

rules: dict[tuple[str, str], dict] = {}
failures = 0
for repo in sorted({row[0] for row in MATRIX}):
    url = f"{base}/api/v1/repos/{owner}/{repo}/branch_protections"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        print(f"MISSING {repo}: cannot read protections (HTTP {exc.code})")
        failures += 1
        continue
    except Exception as exc:  # noqa: BLE001 - report, do not crash
        print(f"MISSING {repo}: cannot read protections ({exc})")
        failures += 1
        continue
    for rule in data:
        rules[(repo, rule["rule_name"])] = rule

for repo, branch, *expected in MATRIX:
    rule = rules.get((repo, branch))
    if rule is None:
        print(f"MISSING {repo}/{branch}: no protection rule")
        failures += 1
        continue
    for field, want in zip(FIELDS, expected):
        got = rule.get(field)
        if got != want:
            print(f"MISMATCH {repo}/{branch}: {field} = {got!r} (expected {want!r})")
            failures += 1
    if rule.get("enable_status_check") and not rule.get("status_check_contexts"):
        print(f"GAP {repo}/{branch}: status checks enabled with no required context")

if failures:
    print(f"branch protection verification FAILED ({failures} mismatch(es))")
    raise SystemExit(1)

print(f"branch protection verification OK ({len(MATRIX)} rules across 5 repos)")
print("Known gaps are documented in docs/ops/forgejo-branch-protection.md")
PY
