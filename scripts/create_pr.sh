#!/usr/bin/env bash
# create_pr.sh — Create a pull request using the project PR template.
#
# Auto-derives title and component from the last commit message.
# Pre-fills the PR body from .github/PULL_REQUEST_TEMPLATE.md.
#
# Usage:
#   scripts/create_pr.sh
#   scripts/create_pr.sh --title "feat(digigraph): custom title"
#   scripts/create_pr.sh --draft
#   make pr
#
# Requires: gh CLI (https://cli.github.com)

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
TEMPLATE_FILE="$REPO_ROOT/.github/PULL_REQUEST_TEMPLATE.md"
DRAFT=false
CUSTOM_TITLE=""

# ── Parse args ────────────────────────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
  case "$1" in
    --title) CUSTOM_TITLE="$2"; shift 2 ;;
    --draft) DRAFT=true; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

# ── Validate prerequisites ────────────────────────────────────────────────────

if ! command -v gh &>/dev/null; then
  echo "ERROR: gh CLI not found. Install from https://cli.github.com" >&2
  exit 1
fi

if ! gh auth status &>/dev/null; then
  echo "ERROR: Not authenticated with gh. Run: gh auth login" >&2
  exit 1
fi

# ── Score gate (task/* branches only) ────────────────────────────────────────
# Enforce quality before the PR is opened rather than after via CI checkbox.
CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '')"
if [[ "$CURRENT_BRANCH" =~ ^task/ ]]; then
  if ! make -C "$REPO_ROOT" score 2>&1; then
    cat >&2 <<MSG

ERROR: make score failed — fix scoring violations before opening a PR.

Run /finish-task (Claude Code) or follow the score-and-fix skill to fix each
failing dimension, then re-run make pr.
MSG
    exit 1
  fi
fi

# ── Derive title from last commit ─────────────────────────────────────────────

LAST_COMMIT="$(git log -1 --format="%s")"
TITLE="${CUSTOM_TITLE:-$LAST_COMMIT}"

# Extract component from conventional commit format: type(component): ...
COMPONENT=""
if [[ "$LAST_COMMIT" =~ ^\w+\(([a-z]+)\): ]]; then
  COMPONENT="${BASH_REMATCH[1]}"
fi

# Extract type from conventional commit format
COMMIT_TYPE=""
if [[ "$LAST_COMMIT" =~ ^([a-z]+)\( ]]; then
  COMMIT_TYPE="${BASH_REMATCH[1]}"
fi

# ── Build PR body ─────────────────────────────────────────────────────────────

if [[ -f "$TEMPLATE_FILE" ]]; then
  BODY="$(cat "$TEMPLATE_FILE")"

  # Pre-check the detected component in the template checkboxes
  if [[ -n "$COMPONENT" ]]; then
    BODY="${BODY//- [ ] \`$COMPONENT\`/- [x] \`$COMPONENT\`}"
  fi

  # Pre-check the detected change type
  case "$COMMIT_TYPE" in
    feat)     BODY="${BODY//- [ ] Feature/- [x] Feature}" ;;
    fix)      BODY="${BODY//- [ ] Bug fix/- [x] Bug fix}" ;;
    refactor) BODY="${BODY//- [ ] Refactor/- [x] Refactor}" ;;
    test)     BODY="${BODY//- [ ] Tests/- [x] Tests}" ;;
    docs)     BODY="${BODY//- [ ] Documentation/- [x] Documentation}" ;;
    chore)    BODY="${BODY//- [ ] Chore/- [x] Chore}" ;;
  esac
else
  BODY="<!-- PR template not found at $TEMPLATE_FILE -->"
fi

# ── Create PR ─────────────────────────────────────────────────────────────────

echo "── Creating PR ──────────────────────────────────────────────────────"
echo "  Title:     $TITLE"
echo "  Component: ${COMPONENT:-unknown}"
echo "  Draft:     $DRAFT"
echo ""

DRAFT_FLAG=""
if [[ "$DRAFT" == "true" ]]; then
  DRAFT_FLAG="--draft"
fi

# Resolve base branch: module/* for module work, develop for cross-cutting
ROUTING_JSON="$REPO_ROOT/scripts/project_routing.json"
BASE_BRANCH="develop"
if [[ -n "$COMPONENT" && -f "$ROUTING_JSON" ]]; then
  RESOLVED="$(python3 -c "
import json, sys
routing = json.load(open('${ROUTING_JSON}'))
branches = routing.get('branches', {})
print(branches.get('component:${COMPONENT}', branches.get('default', 'develop')))
" 2>/dev/null || true)"
  [[ -n "$RESOLVED" ]] && BASE_BRANCH="$RESOLVED"
fi

echo "  Base:      $BASE_BRANCH"
echo ""

PR_URL="$(gh pr create \
  --title "$TITLE" \
  --body "$BODY" \
  --base "$BASE_BRANCH" \
  $DRAFT_FLAG \
  2>&1)"

echo "$PR_URL"
