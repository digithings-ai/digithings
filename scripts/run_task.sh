#!/usr/bin/env bash
# run_task.sh — Execute a DigiThings backlog task end-to-end in an isolated worktree.
#
# Usage:
#   scripts/run_task.sh ISSUE_NUMBER
#   scripts/run_task.sh 42
#   scripts/run_task.sh 42 --dry-run    # print pipeline steps without executing
#
# Pipeline:
#   1. Fetch task spec from GitHub Issue
#   2. Create git worktree (.worktrees/task-N-slug/)
#   3. Print spec + pause for agent to implement
#   4. Run component unit tests
#   5. Self-score staged changes (4 dimensions)
#   6. Commit with conventional message
#   7. Push branch to origin
#   8. Open PR
#   9. Remove worktree
#
# Requires: gh CLI, git, python3 (venv or system with score.py deps)

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

if $DRY_RUN; then
  echo ""
  echo "[DRY RUN] Task pipeline for issue #${ISSUE}:"
  echo "  Step 1  scripts/fetch_task.sh ${ISSUE}"
  echo "  Step 2  scripts/worktree_task.sh create ${ISSUE}"
  echo "  Step 3  [PAUSE] Agent implements in worktree"
  echo "  Step 4  pytest -m unit -k {component} -v --tb=short"
  echo "  Step 5  make score (in worktree)"
  echo "  Step 6  make commit MSG='feat({component}): {title} (#{issue})'"
  echo "  Step 7  git push origin task-${ISSUE}-{slug}"
  echo "  Step 8  make pr"
  echo "  Step 9  scripts/worktree_task.sh remove ${ISSUE}"
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

# ── Step 5: Self-score ────────────────────────────────────────────────────────
step "Self-scoring staged changes"
cd "$WORKTREE_PATH"

SCORE_ATTEMPTS=0
while true; do
  SCORE_ATTEMPTS=$((SCORE_ATTEMPTS + 1))
  if python3 "${REPO_ROOT}/scripts/score.py" --staged; then
    echo "Score: PASS"
    break
  fi

  if [[ "$SCORE_ATTEMPTS" -ge 2 ]]; then
    echo ""
    echo "⚠  Score below threshold after ${SCORE_ATTEMPTS} attempts."
    echo "   Human review required before proceeding."
    read -rp "Press Enter to continue anyway (human approved), or Ctrl+C to abort... "
    break
  fi

  echo ""
  echo "Score failed (attempt $SCORE_ATTEMPTS/2). Fix the issues above and stage the fixes."
  read -rp "Press Enter to re-score... "
done

# ── Step 6: Commit ────────────────────────────────────────────────────────────
step "Committing"
cd "$WORKTREE_PATH"

# Build commit message
COMP_PART="${COMPONENT:-root}"
COMMIT_MSG="feat(${COMP_PART}): ${TITLE_RAW} (#${ISSUE})"

echo "Commit message: $COMMIT_MSG"
bash "${REPO_ROOT}/scripts/commit_helper.sh" "$COMMIT_MSG"

# ── Step 7: Push ──────────────────────────────────────────────────────────────
step "Pushing branch"
cd "$WORKTREE_PATH"
git push origin "$BRANCH" --set-upstream

# ── Step 8: Open PR ───────────────────────────────────────────────────────────
step "Opening PR"
cd "$WORKTREE_PATH"
PR_URL="$(bash "${REPO_ROOT}/scripts/create_pr.sh" 2>&1 | tail -1)"

# ── Step 9: Cleanup worktree ──────────────────────────────────────────────────
step "Cleaning up worktree"
cd "$REPO_ROOT"
scripts/worktree_task.sh remove "$ISSUE" || true

# ── Done ──────────────────────────────────────────────────────────────────────
header "Done"
echo "Task #${ISSUE}: ${TITLE_RAW}"
echo "PR: ${PR_URL}"
echo ""
echo "Next steps:"
echo "  - Update docs/agent-backlog/INDEX.md status to 'in_progress'"
echo "  - After PR merge: update INDEX.md status to 'done'"
