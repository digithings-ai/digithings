#!/usr/bin/env bash
# Block Write/Edit/NotebookEdit outside the project root.
# Exceptions: the approved plan-file dir under ~/.claude/plans/, Claude Code's
# per-project persistent memory under ~/.claude/projects/*/memory/, and /tmp scratch.
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

# PROJECT_ROOT follows the hook's cwd, so a mid-session `cd` between the main
# tree and a linked worktree re-roots the guard. The session's original project
# dir (CLAUDE_PROJECT_DIR, pinned by Claude Code for hooks) and the main repo
# behind the current checkout (MAIN_REPO_ROOT) both stay in-project.
if [ -n "${CLAUDE_PROJECT_DIR:-}" ]; then
  allowed_prefixes+=("$CLAUDE_PROJECT_DIR/")
fi
MAIN_REPO_ROOT="$(main_repo_root)"
if [ -n "$MAIN_REPO_ROOT" ]; then
  allowed_prefixes+=("$MAIN_REPO_ROOT/")
fi

for p in "${allowed_prefixes[@]}"; do
  case "$abs" in
    "$p"*) exit 0 ;;
  esac
done

# Claude Code's harness-designated per-project persistent memory. The
# project-slug dir name is a harness implementation detail, so any project's
# memory dir under ~/.claude/projects/ counts.
case "$abs" in
  "$HOME"/.claude/projects/*/memory/*) exit 0 ;;
esac

deny "write target '$abs' is outside the digithings project root ($PROJECT_ROOT). \
File mutations must stay inside the project. Allowed exceptions: ~/.claude/plans, \
~/.claude/projects/<project>/memory, /tmp."
