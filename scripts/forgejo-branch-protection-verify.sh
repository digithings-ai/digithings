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
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(str([x['$field'] for x in d if x['rule_name']=='$branch'][0]).lower())")
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
