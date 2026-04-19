#!/usr/bin/env bash
# worktree_task.sh — Manage git worktrees for isolated task execution.
#
# Usage:
#   scripts/worktree_task.sh create ISSUE_NUMBER   # create worktree for task
#   scripts/worktree_task.sh remove ISSUE_NUMBER   # remove worktree + branch
#   scripts/worktree_task.sh list                  # list all worktrees
#   scripts/worktree_task.sh path ISSUE_NUMBER     # print worktree path (no-op if missing)
#
# Worktrees are created at: .worktrees/task-N-slug/
# Branch name:              task-N-slug
#
# Requires: git, gh CLI

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

WORKTREES_DIR="${REPO_ROOT}/.worktrees"
COMMAND="${1:-}"
ISSUE="${2:-}"

die() { echo "ERROR: $*" >&2; exit 1; }

# ── Helpers ───────────────────────────────────────────────────────────────────

slugify() {
  # Lowercase, replace non-alphanumeric with hyphens, collapse runs, trim, max 40 chars
  echo "$1" \
    | tr '[:upper:]' '[:lower:]' \
    | sed 's/[^a-z0-9]/-/g; s/-\+/-/g; s/^-//; s/-$//' \
    | cut -c1-40
}

get_issue_title() {
  local issue="$1"
  if command -v gh &>/dev/null && gh auth status &>/dev/null 2>&1; then
    gh issue view "$issue" --json title --jq '.title' 2>/dev/null \
      | sed 's/^\[agent\] //'
  else
    echo "task"
  fi
}

branch_name() {
  local issue="$1"
  local slug
  slug="$(slugify "$(get_issue_title "$issue")")"
  echo "task/${issue}-${slug}"
}

# Resolve the base branch for a task from the issue's component label.
# Reads scripts/project_routing.json branches section; falls back to develop.
base_branch_for_issue() {
  local issue="$1"
  local routing="${REPO_ROOT}/scripts/project_routing.json"
  if [[ ! -f "$routing" ]]; then echo "develop"; return; fi

  local labels
  labels="$(gh issue view "$issue" --json labels --jq '.labels[].name' 2>/dev/null || true)"
  local comp
  comp="$(echo "$labels" | grep '^component:' | head -1)"

  python3 - "$comp" "$routing" << 'PY'
import json, sys
comp = sys.argv[1]
routing = json.load(open(sys.argv[2]))
branches = routing.get("branches", {})
branch = branches.get(comp) if comp else None
print(branch or branches.get("default", "develop"))
PY
}

worktree_path() {
  local branch="$1"
  echo "${WORKTREES_DIR}/${branch}"
}

# ── Commands ──────────────────────────────────────────────────────────────────

cmd_create() {
  [[ -z "$ISSUE" ]] && die "Usage: worktree_task.sh create ISSUE_NUMBER"

  local branch
  branch="$(branch_name "$ISSUE")"
  local wt_path
  wt_path="$(worktree_path "$branch")"

  # Idempotent — no-op if already exists
  if [[ -d "$wt_path" ]]; then
    echo "Worktree already exists: $wt_path"
    echo "$wt_path"
    return 0
  fi

  # Resolve base branch from issue component label (module/* or develop)
  local base
  base="$(base_branch_for_issue "$ISSUE")"

  # Ensure base branch exists locally (fetch from origin if needed)
  if ! git show-ref --verify --quiet "refs/heads/${base}"; then
    git fetch origin "${base}:${base}" 2>/dev/null || true
  fi
  local base_ref
  base_ref="$(git show-ref --verify --quiet "refs/heads/${base}" && echo "${base}" || echo "develop")"

  echo "Base branch: ${base_ref}"
  mkdir -p "$WORKTREES_DIR"

  # Create branch from base if it doesn't exist; otherwise reuse
  if git show-ref --verify --quiet "refs/heads/${branch}"; then
    git worktree add "$wt_path" "$branch"
  else
    git worktree add -b "$branch" "$wt_path" "$base_ref"
  fi

  echo "Worktree created: $wt_path"
  echo "Branch: $branch"
  echo "$wt_path"
}

cmd_remove() {
  [[ -z "$ISSUE" ]] && die "Usage: worktree_task.sh remove ISSUE_NUMBER"

  local branch
  branch="$(branch_name "$ISSUE")"
  local wt_path
  wt_path="$(worktree_path "$branch")"

  if [[ ! -d "$wt_path" ]]; then
    echo "Worktree not found (already removed?): $wt_path"
    return 0
  fi

  git worktree remove "$wt_path" --force
  echo "Worktree removed: $wt_path"

  # Remove branch only if it was already merged; skip silently if not
  if git branch --merged | grep -q "^  ${branch}$"; then
    git branch -d "$branch"
    echo "Branch deleted: $branch"
  else
    echo "Branch kept (not merged): $branch"
    echo "Delete manually when ready: git branch -d $branch"
  fi
}

cmd_list() {
  git worktree list
}

cmd_path() {
  [[ -z "$ISSUE" ]] && die "Usage: worktree_task.sh path ISSUE_NUMBER"
  local branch
  branch="$(branch_name "$ISSUE")"
  worktree_path "$branch"
}

# ── Dispatch ──────────────────────────────────────────────────────────────────

case "$COMMAND" in
  create) cmd_create ;;
  remove) cmd_remove ;;
  list)   cmd_list   ;;
  path)   cmd_path   ;;
  "")     die "Usage: worktree_task.sh create|remove|list|path [ISSUE_NUMBER]" ;;
  *)      die "Unknown command: $COMMAND. Valid: create, remove, list, path" ;;
esac
