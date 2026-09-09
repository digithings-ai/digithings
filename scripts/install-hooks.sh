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
#      parked on a task branch silently downgrade the hook for all of them:
#      whichever worktree installed last set the policy for every other one.
#      Four different candidate versions of this file were sitting across the
#      worktrees when that was found. So the source defaults to a known-good ref
#      rather than to the working tree.
#
# Override with HOOKS_REF=<ref>, or HOOKS_REF=WORKTREE to install the
# uncommitted local copy when you are developing the hook itself.
set -euo pipefail

ref="${HOOKS_REF:-origin/develop}"
src_path="scripts/hooks/pre-push.sh"

# Check these explicitly. `set -e` does NOT help here: when rev-parse fails it
# prints nothing, so `cd "$(git rev-parse ...)"` becomes `cd ""` — which succeeds
# as a no-op and leaves you silently operating on $PWD. Outside a repo that put a
# hook in ./hooks/, where git never looks, and still exited 0.
if ! toplevel="$(git rev-parse --show-toplevel 2>/dev/null)" || [ -z "$toplevel" ]; then
  echo "install-hooks: not inside a git work tree — nothing to install into." >&2
  echo "  Run this from a clone (after 'git init' if you are scaffolding a new repo)." >&2
  exit 1
fi
cd "$toplevel"

# `--git-path hooks` rather than `--git-common-dir`/hooks: it is the form that
# honours core.hooksPath, and it still resolves to the shared common dir from
# inside a linked worktree — which is the whole point of this script.
if ! hooks_path="$(git rev-parse --git-path hooks 2>/dev/null)" || [ -z "$hooks_path" ]; then
  echo "install-hooks: could not resolve this repository's hooks directory." >&2
  exit 1
fi

# Resolve the source *before* creating anything, so the run that correctly
# refuses does not leave a stray hooks/ directory behind for `git add .` to find.
if [ "$ref" = "WORKTREE" ]; then
  if [ ! -f "$src_path" ]; then
    echo "install-hooks: $src_path not found in the working tree." >&2
    exit 1
  fi
  source_desc="working tree (uncommitted)"
else
  # Let git's own stderr through: it distinguishes a stale remote from a
  # malformed ref from a ref that exists without this path, and swallowing it
  # made every one of those read as "run git fetch".
  if ! git cat-file -e "$ref:$src_path"; then
    echo "install-hooks: cannot read $src_path at '$ref' (see git's message above)." >&2
    echo "  If the ref is merely stale, 'git fetch origin' fixes it; to install the" >&2
    echo "  local copy instead, set HOOKS_REF=WORKTREE." >&2
    exit 1
  fi
  source_desc="$ref"
fi

mkdir -p "$hooks_path"
hooks_dir="$(cd "$hooks_path" && pwd)"

# Stage inside the destination dir so the final mv is atomic: a failed read or a
# syntax error can never leave a truncated hook behind, and a hook that is
# half-written is a hook that silently stops guarding.
tmp="$(mktemp "$hooks_dir/.pre-push.XXXXXX")"
trap 'rm -f "$tmp"' EXIT

if [ "$ref" = "WORKTREE" ]; then
  cat "$src_path" >"$tmp"
else
  git show "$ref:$src_path" >"$tmp"
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

# A WORKTREE install is an override, and overrides here are not durable: every
# worktree shares this one file, and `make agents-init` runs the *default*
# install on every invocation. So a concurrent session regenerating its agent
# surface silently puts origin/develop's copy back, and you find out when a push
# behaves unexpectedly. Say so at install time rather than let it surprise.
if [ "$ref" = "WORKTREE" ]; then
  cat >&2 <<EOF
  NOTE:    this is an override, and it is not durable. Every worktree shares
           this one hook, so the next plain 'make hooks-install' — or any
           'make agents-init', in any worktree — reinstalls origin/develop's
           copy over it. Re-run this command if that happens; to check which
           copy is live: git hash-object '$hooks_dir/pre-push'
EOF
fi
