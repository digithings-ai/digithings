#!/usr/bin/env bash
# run_task.sh — Execute a digithings backlog task end-to-end in an isolated worktree.
#
# Usage:
#   scripts/run_task.sh ISSUE_NUMBER
#   scripts/run_task.sh 42
#   scripts/run_task.sh 42 --dry-run    # print pipeline steps without executing
#
# Pipeline:
#   1. Fetch task spec from GitHub Issue
#   2. Create git worktree (.worktrees/task/N-slug/)
#   3. Print spec + pause for agent to implement
#   4. Run component unit tests
#   5. Commit with conventional message
#   6. Push branch to origin
#   7. Open PR
#   8. Remove worktree
#
# Requires: gh CLI, git, python3

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

ISSUE="${1:-}"
DRY_RUN=false

# ── Parse args ────────────────────────────────────────────────────────────────
shift || true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=true; shift ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

[[ -z "$ISSUE" ]] && { echo "Usage: scripts/run_task.sh ISSUE_NUMBER [--dry-run]" >&2; exit 1; }
ISSUE="${ISSUE#\#}"

die() { echo "ERROR: $*" >&2; exit 1; }

header() { echo ""; echo "════════════════════════════════════════════════════════════"; echo "$*"; echo "════════════════════════════════════════════════════════════"; }
step()   { echo ""; echo "── $* ──"; }

# Track worktree path so the trap can clean up on any exit.
WORKTREE_PATH=""
_cleanup() {
  if [[ -n "$WORKTREE_PATH" ]] && [[ -d "$WORKTREE_PATH" ]]; then
    echo "" >&2
    echo "── Cleanup: removing worktree $WORKTREE_PATH ──" >&2
    cd "$REPO_ROOT"
    scripts/worktree_task.sh remove "$ISSUE" 2>/dev/null || true
  fi
}
trap _cleanup EXIT

if $DRY_RUN; then
  echo ""
  echo "[DRY RUN] Task pipeline for issue #${ISSUE}:"
  echo "  Step 1  scripts/fetch_task.sh ${ISSUE}"
  echo "  Step 2  scripts/worktree_task.sh create ${ISSUE}"
  echo "  Step 3  [PAUSE] Agent implements in worktree"
  echo "  Step 4  pytest -m unit -k {component} -v --tb=short"
  echo "  Step 5  make commit MSG='feat({component}): {title} (#{issue})'"
  echo "  Step 6  git push origin task/${ISSUE}-{slug}"
  echo "  Step 7  make pr"
  echo "  Step 8  scripts/worktree_task.sh remove ${ISSUE}"
  echo ""
  exit 0
fi

# ── Prerequisites ─────────────────────────────────────────────────────────────
for cmd in gh git python3; do
  command -v "$cmd" &>/dev/null || die "$cmd not found in PATH"
done
gh auth status &>/dev/null || die "gh CLI not authenticated. Run: gh auth login"

# ── Step 1: Fetch task spec ───────────────────────────────────────────────────
header "Task #${ISSUE}"

step "Fetching spec from GitHub"
SPEC="$(scripts/fetch_task.sh "$ISSUE")"
echo "$SPEC"

# Extract component and title from spec output
COMPONENT="$(echo "$SPEC" | grep '^Component:' | awk '{print $2}')"
TITLE_RAW="$(echo "$SPEC" | head -1 | sed "s/=== Task #${ISSUE}: //; s/ ===//")"

# ── Step 2: Create worktree ───────────────────────────────────────────────────
step "Creating worktree"
WORKTREE_PATH="$(scripts/worktree_task.sh create "$ISSUE" | tail -1)"
BRANCH="$(git -C "$WORKTREE_PATH" branch --show-current)"

echo "Worktree: $WORKTREE_PATH"
echo "Branch:   $BRANCH"

# ── Step 3: Pause for implementation ──────────────────────────────────────────
echo ""
echo "┌─────────────────────────────────────────────────────────────────────┐"
echo "│  AGENT: Implement the task in the worktree below.                  │"
echo "│                                                                     │"
echo "│  Path:  ${WORKTREE_PATH}"
echo "│                                                                     │"
echo "│  Checklist:                                                         │"
echo "│  1. Read ${COMPONENT:-{component}}/AGENTS.md (pre-flight checklist)           │"
echo "│  2. Read ${COMPONENT:-{component}}/ARCHITECTURE.md (module map, extension)    │"
echo "│  3. Implement, run component tests incrementally                    │"
echo "│  4. Stage all changes (git add) before pressing Enter               │"
echo "│                                                                     │"
echo "│  When done: press Enter to continue the pipeline.                  │"
echo "└─────────────────────────────────────────────────────────────────────┘"
echo ""
read -rp "Press Enter when implementation is complete and changes are staged... "

# ── Step 4: Run component tests ───────────────────────────────────────────────
step "Running component tests"
cd "$WORKTREE_PATH"

if [[ -n "$COMPONENT" ]] && [[ "$COMPONENT" != "(not" ]]; then
  TEST_CMD="pytest -m unit -k ${COMPONENT} -v --tb=short"
else
  TEST_CMD="pytest -m unit -v --tb=short"
fi

echo "Command: $TEST_CMD"
if ! eval "$TEST_CMD"; then
  echo ""
  echo "⚠  Tests failed. Fix failures in the worktree and re-run manually:"
  echo "   cd $WORKTREE_PATH && $TEST_CMD"
  echo ""
  read -rp "Press Enter when tests pass to continue, or Ctrl+C to abort... "
  eval "$TEST_CMD" || die "Tests still failing. Aborting pipeline."
fi

# ── Step 5: Commit ────────────────────────────────────────────────────────────
step "Committing"
cd "$WORKTREE_PATH"

# Build commit message
COMP_PART="${COMPONENT:-root}"
COMMIT_MSG="feat(${COMP_PART}): ${TITLE_RAW} (#${ISSUE})"

echo "Commit message: $COMMIT_MSG"
bash "${REPO_ROOT}/scripts/commit_helper.sh" "$COMMIT_MSG"

# ── Step 6: Push ──────────────────────────────────────────────────────────────
step "Pushing branch"
cd "$WORKTREE_PATH"
git push origin "$BRANCH" --set-upstream

# ── Step 7: Open PR ───────────────────────────────────────────────────────────
step "Opening PR"
cd "$WORKTREE_PATH"
PR_URL="$(bash "${REPO_ROOT}/scripts/create_pr.sh" 2>&1 | tail -1)"

# ── Step 8: Cleanup (handled by EXIT trap) ────────────────────────────────────
# Trap calls scripts/worktree_task.sh remove on any exit path.

# ── Done ──────────────────────────────────────────────────────────────────────
header "Done"
echo "Task #${ISSUE}: ${TITLE_RAW}"
echo "PR: ${PR_URL}"
echo ""
echo "Next steps:"
echo "  - Update docs/agent-backlog/INDEX.md status to 'in_progress'"
echo "  - After PR merge: update INDEX.md status to 'done'"
