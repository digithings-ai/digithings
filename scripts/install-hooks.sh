#!/usr/bin/env bash
# Install the pre-push hook into this clone's shared hooks directory.
#
# Two things this has to get right, both learned the hard way:
#
#   1. Hooks live in the *common* git dir, which every linked worktree shares.
#      Inside a worktree `.git` is a file, not a directory, so the literal path
#      `.git/hooks/pre-push` fails outright with "Not a directory" — and since
#      `make task` creates worktrees, that was most of the clones in play.
#
#   2. Because that one installed hook is shared by every worktree, installing
#      whatever the *working tree* happens to have checked out lets a session
#      parked on a task branch silently downgrade the hook for all of them.
#      Three different versions were found live at once this way. So the source
#      defaults to a known-good ref rather than to the working tree.
#
# Override with HOOKS_REF=<ref>, or HOOKS_REF=WORKTREE to install the
# uncommitted local copy when you are developing the hook itself.
set -euo pipefail

ref="${HOOKS_REF:-origin/develop}"
src_path="scripts/hooks/pre-push.sh"

cd "$(git rev-parse --show-toplevel)"
hooks_dir="$(cd "$(git rev-parse --git-common-dir)" && pwd)/hooks"
mkdir -p "$hooks_dir"

# Stage inside the destination dir so the final mv is atomic: a failed read or a
# syntax error can never leave a truncated hook behind, and a hook that is
# half-written is a hook that silently stops guarding.
tmp="$(mktemp "$hooks_dir/.pre-push.XXXXXX")"
trap 'rm -f "$tmp"' EXIT

if [ "$ref" = "WORKTREE" ]; then
  if [ ! -f "$src_path" ]; then
    echo "install-hooks: $src_path not found in the working tree." >&2
    exit 1
  fi
  cat "$src_path" >"$tmp"
  source_desc="working tree (uncommitted)"
else
  if ! git cat-file -e "$ref:$src_path" 2>/dev/null; then
    echo "install-hooks: cannot read $src_path at '$ref'." >&2
    echo "  Run 'git fetch origin' first, or set HOOKS_REF=WORKTREE to install the local copy." >&2
    exit 1
  fi
  git show "$ref:$src_path" >"$tmp"
  source_desc="$ref"
fi

if ! bash -n "$tmp" 2>/dev/null; then
  echo "install-hooks: refusing to install — $src_path at $source_desc is not valid bash." >&2
  exit 1
fi

chmod 755 "$tmp"
mv "$tmp" "$hooks_dir/pre-push"
trap - EXIT

echo "installed: $hooks_dir/pre-push"
echo "  source:  $src_path @ $source_desc"
echo "  blob:    $(git hash-object "$hooks_dir/pre-push")"
