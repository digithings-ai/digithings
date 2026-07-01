#!/usr/bin/env bash
# digidev commit_helper.sh — validated conventional commit
# Usage: scripts/commit_helper.sh "type(component): description (#N)"
set -euo pipefail

MSG=${1:-}

if [[ -z "$MSG" ]]; then
  echo "Usage: make commit MSG=\"type(scope): description (#N)\""
  echo ""
  echo "Types: feat | fix | refactor | docs | test | chore | perf | ci"
  echo "Example: make commit MSG=\"feat(api): add /healthz endpoint (#42)\""
  exit 1
fi

# ── Validate conventional commit format ───────────────────────────────────────
PATTERN='^(feat|fix|refactor|docs|test|chore|perf|ci|build|style|revert)(\([a-zA-Z0-9_/-]+\))?!?:\s+.{10,}'
if ! echo "$MSG" | grep -Eq "$PATTERN"; then
  echo ""
  echo "Error: commit message does not match conventional commit format."
  echo ""
  echo "  Expected:  type(scope): description  (min 10 chars after colon)"
  echo "  Got:       $MSG"
  echo ""
  echo "  Types: feat | fix | refactor | docs | test | chore | perf | ci"
  echo "  Scope: component name, optional"
  echo "  Example: feat(api): add /healthz endpoint (#42)"
  echo ""
  exit 1
fi

# ── Warn if no staged files ───────────────────────────────────────────────────
STAGED=$(git diff --cached --name-only)
if [[ -z "$STAGED" ]]; then
  echo ""
  echo "Warning: no staged changes. Stage files with 'git add <files>' first."
  echo "Run 'git status' to see what's available."
  echo ""
  exit 1
fi

# ── Check score gate ──────────────────────────────────────────────────────────
if [[ ! -f ".score-last.json" ]]; then
  echo ""
  echo "Warning: no score recorded for this diff."
  echo "Run 'make score' to verify quality gate before committing."
  echo ""
  echo "Proceeding anyway... (run 'make score' if this is not intentional)"
  echo ""
fi

# ── Commit ────────────────────────────────────────────────────────────────────
git commit -m "$MSG"
echo ""
echo "✓ Committed: $MSG"
echo ""
echo "Next: make pr  (or continue implementing)"
