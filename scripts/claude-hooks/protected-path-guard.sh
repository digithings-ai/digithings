#!/usr/bin/env bash
# Block edits to protected paths unless we're on a properly-named branch
# (task/N-slug or the repo's feat|fix|docs|chore taxonomy) or the caller
# explicitly sets DIGI_ALLOW_PROTECTED=1 (must be human-set, not agent-set).
# Issue traceability is still enforced separately by the "Require Fixes #N" CI
# gate — this hook only gates *which branch shape* may touch these paths.
source "$(dirname "$0")/_lib.sh"

path="$(hook_field file_path)"
notebook="$(hook_field notebook_path)"
target="${path:-$notebook}"
[ -z "$target" ] && exit 0

# Human override (intentionally not documented to agents).
if [ "${DIGI_ALLOW_PROTECTED:-0}" = "1" ]; then
  exit 0
fi

# Protected path patterns (glob-style, matched against absolute path).
protected=(
  "$PROJECT_ROOT/SECURITY.md"
  "$PROJECT_ROOT/.github/workflows/"
  "$PROJECT_ROOT/docs/scoring/"
  "$PROJECT_ROOT/config/litellm.yaml"
  "$PROJECT_ROOT/projects/"
)

# Live-trading path regex (matches root agents.yml human_gates).
live_trading_regex='(live_trading|execute_trade|place_order|/live[/.])'

# Branch check — agent-task branches (task-N-*) are allowed for protected edits
# except live-trading, which is never allowed without DIGI_ALLOW_PROTECTED=1.
branch="$(git -C "$PROJECT_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '')"

case "$target" in
  *$PROJECT_ROOT/projects/*)
    deny "projects/ is confidential — never edit via agent." ;;
esac

if [[ "$target" =~ $live_trading_regex ]]; then
  deny "edit to live-trading path '$target' is blocked. \
Live-trading code requires explicit human approval; set DIGI_ALLOW_PROTECTED=1 in a human session."
fi

for p in "${protected[@]}"; do
  case "$target" in
    "$p"*)
      if [[ ! "$branch" =~ ^(task/[0-9]+-|feat/|fix/|docs/|chore/) ]]; then
        deny "'$target' is protected. Edits allowed only from a properly-named branch (task/N-slug, feat/, fix/, docs/, chore/) or with explicit human approval. Current branch: '$branch'."
      fi
      ;;
  esac
done

exit 0
