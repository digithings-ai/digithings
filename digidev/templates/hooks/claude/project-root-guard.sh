#!/usr/bin/env bash
# Block Write/Edit/NotebookEdit outside the project root.
# Exceptions: the approved plan-file dir under ~/.claude/plans/, and /tmp scratch.
source "$(dirname "$0")/_lib.sh"

path="$(hook_field file_path)"
notebook="$(hook_field notebook_path)"
target="${path:-$notebook}"

[ -z "$target" ] && exit 0

# Resolve to absolute, canonical path (handles ../ traversal).
abs="$(python3 -c "import os, sys; print(os.path.realpath(sys.argv[1]))" \
  "${target}" 2>/dev/null || true)"
if [ -z "$abs" ]; then
  # Fallback: non-existent target — normalise without resolving symlinks.
  case "$target" in
    /*) abs="$target" ;;
    *)  abs="$PROJECT_ROOT/$target" ;;
  esac
fi

allowed_prefixes=(
  "$PROJECT_ROOT/"
  "$HOME/.claude/plans/"
  "/tmp/"
  "/private/tmp/"
  "/var/folders/"
)

for p in "${allowed_prefixes[@]}"; do
  case "$abs" in
    "$p"*) exit 0 ;;
  esac
done

deny "write target '$abs' is outside the project root ($PROJECT_ROOT). \
File mutations must stay inside the project. Allowed exceptions: ~/.claude/plans, /tmp."
