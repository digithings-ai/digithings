#!/usr/bin/env bash
# set-branch-protection.sh — Configure required status checks on `develop`.
#
# main is deliberately NOT supported here — its gate is a single dedicated
# check ("Every commit reaching main was reviewed", from ci-review-coverage.yml)
# set up as a one-off `gh api` call, not by this script. See docs/BRANCH_PROTECTION.md
# § On main. Passing --branch main is refused rather than silently applying
# develop's contexts and clobbering it — before #2469 this script's payload was
# already develop-specific, so pointing it at main would have overwritten main's
# one check with develop's three.
#
# Usage:
#   bash scripts/set-branch-protection.sh [--dry-run]
#
# Options:
#   --dry-run         Print the payload without calling the GitHub API
#
# Required status checks configured (verified live and applied 2026-08-19, #2469):
#   - "Required checks passed"     — ci.yml aggregator job, fans in every
#                                    path-gated component job
#   - "doc-links + agents-init"    — ci-docs.yml (unconditional on pull_request
#                                    since fd6de617f)
#   - "mypy — digibase + digikey"  — ci-type-check.yml (unconditional on
#                                    pull_request since fd6de617f)
#
# Prerequisites:
#   - gh CLI installed and authenticated (gh auth login)

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
      sed -n '2,/^$/p' "$0" | sed '$d; s/^# \?//'
      exit 0
      ;;
    *) echo "ERROR: Unknown argument: $1" >&2; exit 1 ;;
  esac
done

if [[ "$BRANCH" != "develop" ]]; then
  echo "ERROR: this script only supports 'develop'. main's protection is a" >&2
  echo "one-off gh api call (see docs/BRANCH_PROTECTION.md § On main) — do not" >&2
  echo "point this script at it, its contexts are develop-specific." >&2
  exit 1
fi

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
# required_pull_request_reviews=null  — not "0 approvals": null means no pull
#                                       request is required on develop at all.
#                                       main differs — it sends an object with
#                                       required_approving_review_count: 0, which
#                                       *does* require a PR. Verified live
#                                       2026-08-19; revisit as the team grows.
# restrictions=null                   — no push restrictions beyond the checks above.
PAYLOAD=$(cat <<'EOF'
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "Required checks passed",
      "doc-links + agents-init",
      "mypy — digibase + digikey"
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
