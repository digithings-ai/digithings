#!/usr/bin/env bash
# Non-blocking warning when editing on main or the default integration branch.
# Exit 0 always; writes to stderr so the reminder surfaces in the transcript.
source "$(dirname "$0")/_lib.sh"

path="$(hook_field file_path)"
notebook="$(hook_field notebook_path)"
target="${path:-$notebook}"
[ -z "$target" ] && exit 0

branch="$(git -C "$PROJECT_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '')"

case "$branch" in
  {{MAIN_BRANCH}}|{{DEFAULT_BRANCH}})
    echo "note: editing '$target' on branch '$branch'. Prefer a task branch (task/N-slug) or feature branch for non-trivial changes." >&2
    ;;
esac
exit 0
