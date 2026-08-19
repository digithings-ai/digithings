#!/usr/bin/env bash
# Regression for scripts/create_pr.sh COMPONENT extraction after #2433.
# macOS /bin/bash 3.2 does not support \w inside [[ =~ ]]; the portable
# [A-Za-z0-9_] class must keep matching so module/<component> base routing works.
# Usage: bash tests/scripts/test_create_pr_component_regex.sh
set -euo pipefail

pass=0
fail=0

assert_match() {
  local subject="$1"
  local expected="$2"
  local component=""
  # Keep in sync with scripts/create_pr.sh — do not reintroduce \w here.
  if [[ "$subject" =~ ^[A-Za-z0-9_]+\(([a-z]+)\): ]]; then
    component="${BASH_REMATCH[1]}"
  fi
  if [[ "$component" == "$expected" ]]; then
    pass=$((pass + 1))
  else
    echo "FAIL: subject='$subject' expected component='$expected' got='$component'"
    fail=$((fail + 1))
  fi
}

assert_no_match() {
  local subject="$1"
  local component=""
  if [[ "$subject" =~ ^[A-Za-z0-9_]+\(([a-z]+)\): ]]; then
    component="${BASH_REMATCH[1]}"
  fi
  if [[ -z "$component" ]]; then
    pass=$((pass + 1))
  else
    echo "FAIL: subject='$subject' expected no component, got='$component'"
    fail=$((fail + 1))
  fi
}

assert_match "fix(digiquant): preserve H8 requested targets" "digiquant"
assert_match "feat(digigraph): add tool gate" "digigraph"
assert_match "test(digichat): cover BYOK basePath" "digichat"
assert_match "chore(root): something" "root"
assert_no_match "fix: no component scope"
assert_no_match "fix(DigiQuant): wrong case"
assert_no_match "not a conventional commit"

# Guard against reintroducing \w in create_pr.sh (the #2433 regression).
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
if grep -nE '\[\[.*"\$LAST_COMMIT".*\\w' "$REPO_ROOT/scripts/create_pr.sh" >/dev/null; then
  echo "FAIL: scripts/create_pr.sh still uses \\\\w in LAST_COMMIT match"
  fail=$((fail + 1))
else
  pass=$((pass + 1))
fi

echo "create_pr component regex: $pass passed, $fail failed"
[[ "$fail" -eq 0 ]]
