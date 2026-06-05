#!/usr/bin/env bash
# Tests for scripts/claude-hooks/protected-path-bash-guard.sh
# Usage: bash tests/scripts/test_protected_path_bash_guard.sh
# Exits non-zero and prints a summary if any assertions fail.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

pass=0
fail=0

# ── Fixture: a minimal git repo on a non-task branch (develop) ───────────────
FAKE_ROOT="$(mktemp -d)"
TASK_ROOT="$(mktemp -d)"
cp -r "$REPO_ROOT/scripts/claude-hooks" "$FAKE_ROOT/"
cd "$FAKE_ROOT"
git init -q
git config user.email "test@example.com"
git config user.name "test"
git checkout -b develop 2>/dev/null || true
git commit --allow-empty -m "init" 2>/dev/null || true
cd "$REPO_ROOT"

# ── Fixture: a minimal git repo on a task branch ─────────────────────────────
cp -r "$REPO_ROOT/scripts/claude-hooks" "$TASK_ROOT/"
cd "$TASK_ROOT"
git init -q
git config user.email "test@example.com"
git config user.name "test"
git checkout -b task/256-test 2>/dev/null || true
git commit --allow-empty -m "init" 2>/dev/null || true
cd "$REPO_ROOT"

cleanup() {
  rm -rf "$FAKE_ROOT" "$TASK_ROOT"
}
trap cleanup EXIT

# ── Helpers ───────────────────────────────────────────────────────────────────

# run_guard_in ROOT CMD [ENV=VAL...]  — returns the guard exit code
# Extra KEY=VAL pairs are exported into the guard's environment.
run_guard_in() {
  local root="$1"
  local cmd="$2"
  shift 2
  local json rc=0
  json="$(python3 -c "
import json, sys
cmd = sys.argv[1]
print(json.dumps({'tool_name': 'Bash', 'tool_input': {'command': cmd}}))
" "$cmd")"
  # Default DIGI_ALLOW_PROTECTED=0 so GHA org env cannot weaken denied cases; "$@" may override.
  set +e
  printf '%s' "$json" \
    | env -u DIGI_ALLOW_PROTECTED DIGI_ALLOW_PROTECTED=0 DIGI_PROJECT_ROOT="$root" "$@" \
        bash "$root/claude-hooks/protected-path-bash-guard.sh" 2>/dev/null
  rc=$?
  set -e
  return $rc
}

assert_denied() {
  local desc="$1"
  local cmd="$2"
  local root="${3:-$FAKE_ROOT}"
  local rc=0
  run_guard_in "$root" "$cmd" || rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "PASS [denied]  $desc"
    pass=$((pass + 1))
  else
    echo "FAIL [denied]  $desc  (expected non-zero, got 0)"
    fail=$((fail + 1))
  fi
}

assert_allowed() {
  local desc="$1"
  local cmd="$2"
  local root="${3:-$FAKE_ROOT}"
  local extra="${4:-}"
  local rc=0
  if [ -n "$extra" ]; then
    run_guard_in "$root" "$cmd" "$extra" || rc=$?
  else
    run_guard_in "$root" "$cmd" || rc=$?
  fi
  if [ "$rc" -eq 0 ]; then
    echo "PASS [allowed] $desc"
    pass=$((pass + 1))
  else
    echo "FAIL [allowed] $desc  (expected 0, got $rc)"
    fail=$((fail + 1))
  fi
}

# ── DENY cases (non-task branch) ──────────────────────────────────────────────

# Output redirects into .github/workflows/
assert_denied "cat > .github/workflows/ci.yml (relative)" \
  "cat > .github/workflows/ci.yml"

assert_denied "cat >> .github/workflows/ci.yml (append)" \
  "cat >> .github/workflows/ci.yml"

assert_denied "echo x > $FAKE_ROOT/.github/workflows/ci.yml (absolute)" \
  "echo x > $FAKE_ROOT/.github/workflows/ci.yml"

# SECURITY.md
assert_denied "echo x > SECURITY.md" \
  "echo x > SECURITY.md"

# docs/scoring/
assert_denied "cat > docs/scoring/rubric.md" \
  "cat > docs/scoring/rubric.md"

# config/litellm.yaml
assert_denied "cat > config/litellm.yaml" \
  "cat > config/litellm.yaml"

# projects/ (confidential — always blocked, even on task branch)
assert_denied "cat > projects/secret.md (non-task)" \
  "cat > projects/secret.md"
assert_denied "cat > projects/secret.md (task branch — still denied)" \
  "cat > projects/secret.md" "$TASK_ROOT"

# tee into protected path
assert_denied "echo x | tee .github/workflows/ci.yml" \
  "echo x | tee .github/workflows/ci.yml"

assert_denied "echo x | tee -a .github/workflows/ci.yml" \
  "echo x | tee -a .github/workflows/ci.yml"

# sed -i on protected path
assert_denied "sed -i 's/a/b/' .github/workflows/ci.yml" \
  "sed -i 's/a/b/' .github/workflows/ci.yml"

# mv to protected path (file target)
assert_denied "mv /tmp/ci.yml .github/workflows/ci.yml" \
  "mv /tmp/ci.yml .github/workflows/ci.yml"

# mv to protected directory (no filename — normpath strips trailing slash)
assert_denied "mv /tmp/ci.yml .github/workflows" \
  "mv /tmp/ci.yml .github/workflows"

# cp to protected path (file target)
assert_denied "cp /tmp/ci.yml .github/workflows/ci.yml" \
  "cp /tmp/ci.yml .github/workflows/ci.yml"

# BSD sed -i '' (Darwin in-place form) — empty backup suffix must not fool the parser
assert_denied "sed -i '' 's/a/b/' .github/workflows/ci.yml" \
  "sed -i '' 's/a/b/' .github/workflows/ci.yml"

# Live-trading path — block even on task/* branch
assert_denied "cat > live_trading/order.py (non-task)" \
  "cat > live_trading/order.py"
assert_denied "cat > live_trading/order.py (task branch — still denied)" \
  "cat > live_trading/order.py" "$TASK_ROOT"
assert_denied "cat > src/execute_trade.py" \
  "cat > src/execute_trade.py"

# ── ALLOW cases ───────────────────────────────────────────────────────────────

# /tmp/ writes are always safe
assert_allowed "cat > /tmp/scratch.txt" \
  "cat > /tmp/scratch.txt"

# Read from protected path (no write)
assert_allowed "cat .github/workflows/ci.yml | grep name" \
  "cat .github/workflows/ci.yml | grep name"

# Input redirect (not a write)
assert_allowed "python3 script.py < .github/workflows/ci.yml" \
  "python3 script.py < .github/workflows/ci.yml"

# Comparison operator in shell test (not a redirect)
assert_allowed "if [ \$x -gt 0 ]; then echo ok; fi" \
  'if [ $x -gt 0 ]; then echo ok; fi'

# Quoted > inside grep (not a redirect)
assert_allowed 'grep ">" .github/workflows/ci.yml' \
  'grep ">" .github/workflows/ci.yml'

# Pipe to non-file destination
assert_allowed "curl -s http://example.com | jq '.'" \
  "curl -s http://example.com | jq '.'"

# Write to /tmp/
assert_allowed "echo x > /tmp/output.txt" \
  "echo x > /tmp/output.txt"

# Write outside PROJECT_ROOT
assert_allowed "echo x > /var/log/app.log" \
  "echo x > /var/log/app.log"

# tee to /tmp/
assert_allowed "echo x | tee /tmp/debug.log" \
  "echo x | tee /tmp/debug.log"

# Task branch allows protected writes (non-live-trading)
assert_allowed "cat > .github/workflows/ci.yml on task branch (allowed)" \
  "cat > .github/workflows/ci.yml" "$TASK_ROOT"

# DIGI_ALLOW_PROTECTED=1 override
assert_allowed "DIGI_ALLOW_PROTECTED=1 overrides deny" \
  "cat > .github/workflows/ci.yml" "$FAKE_ROOT" "DIGI_ALLOW_PROTECTED=1"

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "Results: $pass passed, $fail failed."
if [ "$fail" -gt 0 ]; then
  exit 1
fi
exit 0
