#!/usr/bin/env bash
# set-branch-protection.sh — Configure required status checks on a branch.
#
# Usage:
#   bash scripts/set-branch-protection.sh [--branch BRANCH] [--dry-run]
#
# Options:
#   --branch BRANCH   Branch to protect (default: develop)
#   --dry-run         Print the payload without calling the GitHub API
#
# Required status checks configured:
#   - "baseline / tests"  — the cross-module baseline suite (issue #291)
#   - "ruff-and-scripts"  — lint + script unit tests (job in ci.yml)
#   - "Require Fixes"  — every PR must trace to a backlog issue (pr-linkage.yml)
#
# Prerequisites:
#   - gh CLI installed and authenticated (gh auth login)
#   - Issue #291 (baseline CI suite) merged and green before running live

set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
BRANCH="develop"
DRY_RUN=false
REPO="digithings-ai/digithings"

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case $1 in
    --dry-run) DRY_RUN=true; shift ;;
    --branch)
      if [[ $# -lt 2 || "$2" == --* ]]; then
        echo "ERROR: --branch requires a value" >&2; exit 1
      fi
      BRANCH="$2"; shift 2 ;;
    -h|--help)
      sed -n '2,19p' "$0" | sed 's/^# \?//'
      exit 0
      ;;
    *) echo "ERROR: Unknown argument: $1" >&2; exit 1 ;;
  esac
done

# ── Prerequisite check ────────────────────────────────────────────────────────
if ! command -v gh &>/dev/null; then
  echo "ERROR: gh CLI not found. Install: https://cli.github.com" >&2
  exit 1
fi
if ! gh auth status &>/dev/null; then
  echo "ERROR: Not authenticated. Run: gh auth login" >&2
  exit 1
fi

# ── Build payload ─────────────────────────────────────────────────────────────
# required_status_checks.strict=true  — branch must be up-to-date before merge.
# contexts                            — these exact check names must pass.
# enforce_admins=false                — admins can bypass in emergencies (use sparingly).
# required_pull_request_reviews=null  — no mandatory review count for now; revisit
#                                       once the team grows.
# restrictions=null                   — no push restrictions beyond the checks above.
PAYLOAD=$(cat <<'EOF'
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "baseline / tests",
      "ruff-and-scripts",
      "Require Fixes"
    ]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": null,
  "restrictions": null
}
EOF
)

# ── Execute or dry-run ────────────────────────────────────────────────────────
if [[ "$DRY_RUN" == "true" ]]; then
  echo "DRY RUN: Would set protection on branch '$BRANCH' of $REPO with:"
  echo "$PAYLOAD"
else
  echo "Setting branch protection on '$BRANCH'..." >&2
  gh api "repos/$REPO/branches/$BRANCH/protection" \
    -X PUT \
    --input - <<< "$PAYLOAD"
  echo "Branch protection set on '$BRANCH'."
  echo ""
  echo "Verify with:"
  echo "  gh api repos/$REPO/branches/$BRANCH/protection | python3 -m json.tool"
fi
