#!/usr/bin/env bash
# Smoke test: verifies the exec:copilot → @Copilot assignment bridge works.
#
# Tier C: dispatch is handled by copilot-issue-dispatch.lock.yml (gh-aw).
#
# What it does:
#   1. Creates a scratch test issue labelled exec:copilot + priority:low
#   2. Waits for the gh-aw copilot-issue-dispatch workflow to fire and assign @Copilot
#   3. Confirms @Copilot is listed as an assignee
#   4. Closes the scratch issue (cleanup — GitHub issues can't be deleted via gh)
#
# Requirements:
#   - gh CLI authenticated to the digithings-ai org
#   - copilot-issue-dispatch.lock.yml deployed on the target branch (default: develop)
#   - Copilot coding agent enabled for the repo (Settings → Copilot → Coding agent)
#
# Usage:
#   ./scripts/agents/smoke_test_dispatch.sh [--repo ORG/REPO] [--timeout 120]
#
# Exit codes:
#   0  — @Copilot was assigned within the timeout (or quota exhausted + parked)
#   1  — timeout or unexpected state

set -euo pipefail

REPO="${REPO:-$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || echo "")}"
TIMEOUT=120   # seconds to wait for the workflow to run
POLL=10       # poll interval in seconds

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO="$2"; shift 2 ;;
    --timeout) TIMEOUT="$2"; shift 2 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

if [[ -z "$REPO" ]]; then
  echo "ERROR: could not detect repo. Set REPO env var or pass --repo ORG/REPO"
  exit 1
fi

echo "=== Tier 1 dispatch smoke test (Tier C: gh-aw copilot-issue-dispatch) ==="
echo "Repo:    $REPO"
echo "Timeout: ${TIMEOUT}s (poll every ${POLL}s)"
echo ""

# 1. Create scratch issue
TITLE="[smoke-test] copilot-issue-dispatch validation $(date +%Y%m%dT%H%M%S)"
echo "Creating test issue: $TITLE"
ISSUE_URL=$(gh issue create --repo "$REPO" \
  --title "$TITLE" \
  --label "exec:copilot,priority:low,component:root,complexity:S,risk:low" \
  --body "Automated smoke test for exec:copilot dispatch. Safe to close." \
  2>&1)
ISSUE_NUMBER=$(echo "$ISSUE_URL" | grep -oE '[0-9]+$')
echo "Created: $ISSUE_URL (#$ISSUE_NUMBER)"
echo ""

# Cleanup trap — always close the issue on exit
cleanup() {
  echo ""
  echo "Cleaning up: closing #$ISSUE_NUMBER"
  gh issue close "$ISSUE_NUMBER" --repo "$REPO" --comment "Smoke test complete — closing." 2>/dev/null || true
}
trap cleanup EXIT

# 2. Poll for assignment
echo "Waiting for copilot-issue-dispatch.lock.yml to fire..."
ELAPSED=0
RESULT="timeout"

while [[ $ELAPSED -lt $TIMEOUT ]]; do
  sleep $POLL
  ELAPSED=$((ELAPSED + POLL))

  # Fetch current assignees and labels
  STATE=$(gh issue view "$ISSUE_NUMBER" --repo "$REPO" \
    --json assignees,labels \
    --jq '{assignees: [.assignees[].login], labels: [.labels[].name]}')

  ASSIGNEES=$(echo "$STATE" | python3 -c "import json,sys; d=json.load(sys.stdin); print(' '.join(d['assignees']))")
  LABELS=$(echo "$STATE" | python3 -c "import json,sys; d=json.load(sys.stdin); print(' '.join(d['labels']))")

  echo "[${ELAPSED}s] assignees=(${ASSIGNEES:-none}) labels=${LABELS}"

  # Happy path: @Copilot assigned
  if echo "$ASSIGNEES" | grep -qiE "copilot|copilot-swe-agent"; then
    RESULT="assigned"
    break
  fi

  # Quota-exhausted path: pending:quota added (also counts as success — bridge fired)
  if echo "$LABELS" | grep -q "pending:quota"; then
    RESULT="parked"
    break
  fi

  # Escalated to Claude: exec:claude added
  if echo "$LABELS" | grep -q "exec:claude"; then
    RESULT="escalated_claude"
    break
  fi
done

echo ""
case "$RESULT" in
  assigned)
    echo "PASS: @Copilot assigned to #$ISSUE_NUMBER within ${ELAPSED}s"
    exit 0
    ;;
  parked)
    echo "PASS (quota exhausted): issue #$ISSUE_NUMBER parked with pending:quota — dispatch bridge fired correctly"
    exit 0
    ;;
  escalated_claude)
    echo "PASS (quota exhausted + escalated): issue #$ISSUE_NUMBER swapped to exec:claude — dispatch bridge fired correctly"
    exit 0
    ;;
  timeout)
    echo "FAIL: no assignment, pending:quota, or exec:claude label appeared within ${TIMEOUT}s"
    echo "Check: is copilot-issue-dispatch.lock.yml deployed? Is Copilot coding agent enabled?"
    echo "Workflow runs: https://github.com/${REPO}/actions/workflows/copilot-issue-dispatch.lock.yml"
    exit 1
    ;;
esac
