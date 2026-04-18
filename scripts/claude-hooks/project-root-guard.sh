#!/usr/bin/env bash
# Block Write/Edit/NotebookEdit outside the project root.
# Exceptions: the approved plan-file dir under ~/.claude/plans/, and /tmp scratch.
source "$(dirname "$0")/_lib.sh"

path="$(hook_field file_path)"
notebook="$(hook_field notebook_path)"
target="${path:-$notebook}"

# Empty target — let other hooks or the tool itself decide.
[ -z "$target" ] && exit 0

# Resolve to absolute path if relative (Claude usually passes absolute).
case "$target" in
  /*) abs="$target" ;;
  *)  abs="$PROJECT_ROOT/$target" ;;
esac

# Allowed prefixes.
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

deny "write target '$abs' is outside the digithings project root ($PROJECT_ROOT). \
File mutations must stay inside the project. Allowed exceptions: ~/.claude/plans, /tmp."
