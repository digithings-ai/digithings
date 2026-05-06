#!/usr/bin/env bash
# digidev run_task.sh — create an isolated git worktree for a backlog issue
# Usage: scripts/run_task.sh <issue-number>
set -euo pipefail

ISSUE=${1:-}
[[ -z "$ISSUE" ]] && { echo "Usage: make task ISSUE=<number>"; exit 1; }

# ── Require gh CLI ────────────────────────────────────────────────────────────
if ! command -v gh &>/dev/null; then
  echo "Error: gh CLI is required. Install: https://cli.github.com/"
  exit 1
fi

# ── Check for Jira/Linear mode (fallback: GitHub Issues) ─────────────────────
ISSUE_TRACKER="github"
if [[ -f "agents.yml" ]]; then
  ISSUE_TRACKER=$(python3 -c "
import re, sys
try:
    import yaml
    cfg = yaml.safe_load(open('agents.yml'))
    print(cfg.get('issue_tracker', 'github'))
except ImportError:
    txt = open('agents.yml').read()
    m = re.search(r'issue_tracker:\s*(\S+)', txt)
    print(m.group(1) if m else 'github')
" 2>/dev/null || echo "github")
fi

# ── Get issue title ───────────────────────────────────────────────────────────
echo "→ Fetching issue #${ISSUE}..."

case "$ISSUE_TRACKER" in
  jira)
    # Jira MCP or JIRA_BASE_URL + token
    JIRA_URL=${JIRA_BASE_URL:-}
    if [[ -z "$JIRA_URL" ]]; then
      echo "Error: set JIRA_BASE_URL for Jira issue lookup."
      TITLE="task"
    else
      TITLE=$(curl -s -u "${JIRA_EMAIL}:${JIRA_API_TOKEN}" \
        "${JIRA_URL}/rest/api/2/issue/${ISSUE}" 2>/dev/null \
        | python3 -c "import sys,json,re; d=json.load(sys.stdin); t=d['fields']['summary'].lower(); print(re.sub(r'[^a-z0-9]+','-',t)[:40].strip('-'))" 2>/dev/null || echo "task")
    fi
    ;;
  linear)
    TITLE="task"  # Linear CLI or MCP; fall through to manual if unavailable
    ;;
  *)
    # GitHub Issues
    ISSUE_JSON=$(gh issue view "$ISSUE" --json title,labels 2>/dev/null) || {
      echo "Error: issue #${ISSUE} not found or gh not authenticated (run: gh auth login)."
      exit 1
    }
    TITLE=$(echo "$ISSUE_JSON" \
      | python3 -c "
import sys, json, re
d = json.load(sys.stdin)
t = d['title'].lower()
print(re.sub(r'[^a-z0-9]+', '-', t)[:40].strip('-'))
" 2>/dev/null || echo "task")
    ;;
esac

BRANCH="task/${ISSUE}-${TITLE}"
WORKTREE_DIR=".worktrees/task-${ISSUE}-${TITLE}"

echo "→ Branch:   $BRANCH"
echo "→ Worktree: $WORKTREE_DIR"

# ── Check for existing worktree ───────────────────────────────────────────────
if git worktree list | grep -qF "$BRANCH"; then
  echo ""
  echo "→ Worktree already exists."
  EXISTING=$(git worktree list --porcelain \
    | awk '/^worktree /{wt=$2} /^branch .*'"$BRANCH"'/{print wt}')
  echo ""
  echo "  cd ${EXISTING:-$WORKTREE_DIR}"
  exit 0
fi

# ── Determine base branch ─────────────────────────────────────────────────────
DEFAULT_BRANCH=$(python3 -c "
import re
try:
    import yaml
    cfg = yaml.safe_load(open('agents.yml'))
    print(cfg.get('default_branch', 'develop'))
except Exception:
    try:
        txt = open('agents.yml').read()
        m = re.search(r'default_branch:\s*(\S+)', txt)
        print(m.group(1) if m else 'develop')
    except Exception:
        print('develop')
" 2>/dev/null || echo "develop")

# Determine component-specific module branch (if it exists)
# agents.yml components list is used to detect if a module/* branch exists
COMPONENT_BRANCH=""
if [[ "$ISSUE_TRACKER" == "github" ]]; then
  COMPONENT=$(echo "${ISSUE_JSON:-}" \
    | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    labels = [l['name'] for l in d.get('labels', []) if l['name'].startswith('component:')]
    print(labels[0].replace('component:', '') if labels else '')
except Exception:
    print('')
" 2>/dev/null || echo "")
  if [[ -n "$COMPONENT" ]]; then
    MODULE_BRANCH="module/${COMPONENT}"
    if git show-ref --verify --quiet "refs/heads/${MODULE_BRANCH}" 2>/dev/null || \
       git show-ref --verify --quiet "refs/remotes/origin/${MODULE_BRANCH}" 2>/dev/null; then
      COMPONENT_BRANCH="$MODULE_BRANCH"
    fi
  fi
fi

BASE_BRANCH="${COMPONENT_BRANCH:-$DEFAULT_BRANCH}"

# ── Fetch and create worktree ─────────────────────────────────────────────────
echo "→ Base: $BASE_BRANCH"
echo "→ Fetching..."
git fetch origin "$BASE_BRANCH" 2>/dev/null || true

mkdir -p .worktrees

git worktree add "$WORKTREE_DIR" -b "$BRANCH" "origin/$BASE_BRANCH" 2>/dev/null \
  || git worktree add "$WORKTREE_DIR" -b "$BRANCH" "$BASE_BRANCH" 2>/dev/null \
  || {
    echo "Error: could not create worktree from '${BASE_BRANCH}'."
    echo "Check that '${BASE_BRANCH}' exists locally or on origin."
    exit 1
  }

# ── Print instructions ────────────────────────────────────────────────────────
echo ""
echo "✓ Worktree ready."
echo ""
echo "  cd $WORKTREE_DIR"
echo ""
echo "Next steps:"
echo "  1. Read {component}/AGENTS.md for pre-flight rules"
echo "  2. Run baseline tests to confirm clean state"
echo "  3. Implement acceptance criteria from issue #${ISSUE}"
echo "  4. make score SCORES=\"security=?,quality=?,optimization=?,accuracy=?\""
echo "  5. make commit MSG=\"feat(component): short description (#${ISSUE})\""
echo "  6. make pr"
echo ""
