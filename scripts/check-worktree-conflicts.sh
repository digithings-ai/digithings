#!/usr/bin/env bash
# check-worktree-conflicts.sh — Detect file-glob overlaps across active worktrees.
#
# Usage:
#   scripts/check-worktree-conflicts.sh ISSUE_NUMBER
#
# Reads the GitHub issue title/body to infer a component glob (e.g. "digigraph/**"),
# then checks each active .worktrees/* branch to see if any changed files overlap.
# Prints a warning table when overlaps are found. Always exits 0 (warning only, not blocking).
#
# Requires: git (gh CLI optional — gracefully skips when unavailable)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

ISSUE="${1:-}"
[[ -z "$ISSUE" ]] && { echo "Usage: scripts/check-worktree-conflicts.sh ISSUE_NUMBER" >&2; exit 0; }
ISSUE="${ISSUE#\#}"

WORKTREES_DIR="${REPO_ROOT}/.worktrees"

COMPONENTS="digigraph digiquant digisearch digismith digiclaw digibase digikey digichat"

# ── Helpers ───────────────────────────────────────────────────────────────────

header() { echo ""; echo "── $* ──"; }

# Infer component glob from issue metadata
infer_globs() {
  local issue="$1"
  local text=""

  if command -v gh &>/dev/null && gh auth status &>/dev/null; then
    text="$(gh issue view "$issue" --json title,body --jq '.title + " " + .body' 2>/dev/null || true)"
  fi

  local matched=""
  for comp in $COMPONENTS; do
    if echo "$text" | grep -qi "$comp"; then
      matched="${matched} ${comp}/**"
    fi
  done

  matched="${matched# }"

  if [[ -z "$matched" ]]; then
    echo "**"  # Broad fallback — no component inferred
  else
    echo "$matched"
  fi
}

matches_any_glob() {
  local file="$1"
  shift
  local glob
  for glob in "$@"; do
    # Strip trailing /** and treat as prefix check
    local prefix="${glob%/**}"
    if [[ "$glob" == "**" ]] || [[ "$file" == "$prefix"/* ]] || [[ "$file" == "$prefix" ]]; then
      return 0
    fi
  done
  return 1
}

# ── Main ──────────────────────────────────────────────────────────────────────

header "Worktree conflict check for issue #${ISSUE}"

# Fetch latest origin/develop so diffs are not stale
git fetch origin develop --quiet 2>/dev/null || true

# Infer globs from issue metadata
GLOBS_STR="$(infer_globs "$ISSUE")"
# Disable glob expansion before splitting GLOBS_STR so "digigraph/**" is not expanded
set -f
# shellcheck disable=SC2206
GLOBS=($GLOBS_STR)
set +f

echo "Issue:  #${ISSUE}"
echo "Globs:  ${GLOBS[*]}"

# No worktrees directory — nothing to check
if [[ ! -d "$WORKTREES_DIR" ]]; then
  echo "No .worktrees/ directory found — nothing to compare."
  echo ""
  exit 0
fi

FOUND_CONFLICT=false
CONFLICT_ROWS=""

for wt_dir in "$WORKTREES_DIR"/*/; do
  [[ -d "$wt_dir" ]] || continue

  # Skip the worktree for *this* issue (task-N-* pattern)
  wt_name="$(basename "$wt_dir")"
  if echo "$wt_name" | grep -q "^task-${ISSUE}-"; then
    continue
  fi

  # Get the branch name from the worktree
  wt_branch="$(git -C "$wt_dir" branch --show-current 2>/dev/null || echo "(detached)")"
  [[ -z "$wt_branch" ]] && wt_branch="(detached)"

  # Get changed files in this worktree vs origin/develop
  changed_files="$(git -C "$wt_dir" diff origin/develop...HEAD --name-only 2>/dev/null || true)"
  [[ -z "$changed_files" ]] && continue

  wt_rows=""
  while IFS= read -r file; do
    [[ -z "$file" ]] && continue
    if matches_any_glob "$file" "${GLOBS[@]}"; then
      wt_rows="${wt_rows}  ${file}"$'\n'
    fi
  done <<< "$changed_files"

  if [[ -n "$wt_rows" ]]; then
    FOUND_CONFLICT=true
    CONFLICT_ROWS="${CONFLICT_ROWS}WORKTREE: ${wt_branch} (${wt_dir})"$'\n'
    CONFLICT_ROWS="${CONFLICT_ROWS}${wt_rows}"$'\n'
  fi
done

if $FOUND_CONFLICT; then
  echo ""
  echo "WARNING: Overlapping files detected in active worktrees"
  echo "────────────────────────────────────────────────────────"
  echo "$CONFLICT_ROWS"
  echo "You may be editing files that another parallel task is already touching."
  echo "Coordinate with the other task or proceed with caution."
else
  echo "No overlapping files found across active worktrees."
fi

echo ""
exit 0
