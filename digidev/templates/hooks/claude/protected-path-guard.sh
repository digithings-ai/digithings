#!/usr/bin/env bash
# Block edits to protected paths unless we're on a task/* branch or the
# caller explicitly sets DIGIDEV_ALLOW_PROTECTED=1 (must be human-set).
source "$(dirname "$0")/_lib.sh"

path="$(hook_field file_path)"
notebook="$(hook_field notebook_path)"
target="${path:-$notebook}"
[ -z "$target" ] && exit 0

# Human override — set DIGIDEV_ALLOW_PROTECTED=1 in a human session to bypass.
# Using a fixed name avoids bash variable-name issues with hyphenated project names.
if [ "${DIGIDEV_ALLOW_PROTECTED:-0}" = "1" ]; then
  exit 0
fi

# Protected path patterns — edit to match your project's sensitive areas.
protected=(
  {{PROTECTED_PATHS_BASH}}
)

# Paths that are ALWAYS blocked (even on task branches).
# Adjust this regex to match your project's most sensitive code.
always_block_regex='{{LIVE_TRADING_REGEX}}'

branch="$(git -C "$PROJECT_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '')"

if [[ -n "$always_block_regex" ]] && [[ "$target" =~ $always_block_regex ]]; then
  deny "edit to sensitive path '$target' is blocked. \
This path requires explicit human approval; set DIGIDEV_ALLOW_PROTECTED=1 in a human session."
fi

for p in "${protected[@]}"; do
  p_clean="${p%/}"
  case "$target" in
    "$p_clean"|"$p_clean/"*)
      if [[ ! "$branch" =~ ^task/[0-9]+- ]]; then
        deny "'$target' is protected. Edits allowed only from a task branch (task/N-slug) or with explicit human approval. Current branch: '$branch'."
      fi
      ;;
  esac
done

exit 0
