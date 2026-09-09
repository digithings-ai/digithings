#!/usr/bin/env bash
# Regression for #2557 — release-please branches admitted into the taxonomy.
#
# Before #2557, `release-please--branches--<target>--components--<component>`
# refs were pushed by release-please-*.yml but rejected by the client pre-push
# hook, so a maintainer could not push a follow-up fix (e.g. lockfile resync)
# onto the bot's branch without `--no-verify`. The hook regex and the mirrored
# github-rulesets JSON now admit the pattern for the two configured targets
# (develop, module/*).
#
# These tests pin the regex itself (allow / deny matrix) and the hook↔ruleset
# sync. They do not need a real temp-repo fixture: taxonomy rejection happens
# before the live-trading scan, and allow cases are pure bash `[[ =~ ]]`.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HOOK="$REPO_ROOT/scripts/hooks/pre-push.sh"
RULESET="$REPO_ROOT/scripts/github-rulesets/01-branch-naming.json"

pass=0
fail=0

assert_match() {
  local name="$1" branch="$2" expect="$3"  # expect: 0=match, 1=no-match
  if [[ "$branch" =~ $branch_regex ]]; then
    got=0
  else
    got=1
  fi
  if [[ "$got" -eq "$expect" ]]; then
    echo "PASS: $name ($branch)"
    pass=$((pass + 1))
  else
    echo "FAIL: $name ($branch) — expected exit-like $expect, got $got" >&2
    fail=$((fail + 1))
  fi
}

# Load CONTRIBUTOR_HANDLES + branch_regex the same way the hook does.
# shellcheck disable=SC1090
CONTRIBUTOR_HANDLES="$(
  sed -n "s/^CONTRIBUTOR_HANDLES='\\(.*\\)'$/\\1/p" "$HOOK" | head -1
)"
if [[ -z "$CONTRIBUTOR_HANDLES" ]]; then
  echo "FAIL: could not extract CONTRIBUTOR_HANDLES from $HOOK" >&2
  exit 1
fi
branch_regex="$(
  # Evaluate the assignment with CONTRIBUTOR_HANDLES already set (the hook
  # interpolates the handles into the regex at definition time).
  CONTRIBUTOR_HANDLES="$CONTRIBUTOR_HANDLES" bash -c '
    source /dev/null
    eval "$(grep -E "^branch_regex=" "'"$HOOK"'")"
    printf "%s" "$branch_regex"
  '
)"
if [[ -z "$branch_regex" ]]; then
  echo "FAIL: could not extract branch_regex from $HOOK" >&2
  exit 1
fi

echo "== #2557 allow: configured release-please targets =="
assert_match "digichat on develop" \
  "release-please--branches--develop--components--digichat" 0
assert_match "digiskills on module/*" \
  "release-please--branches--module/digiskills--components--digiskills" 0
assert_match "hyphenated component on develop" \
  "release-please--branches--develop--components--digi-chat" 0

echo "== #2557 deny: targets / shapes the bot must not invent =="
assert_match "main is not a release-please target" \
  "release-please--branches--main--components--digichat" 1
assert_match "arbitrary feature branch is not a target" \
  "release-please--branches--feature/foo--components--x" 1
assert_match "uppercase component rejected" \
  "release-please--branches--develop--components--DigiChat" 1
assert_match "missing components segment" \
  "release-please--branches--develop--digichat" 1
assert_match "truncated prefix only" \
  "release-please--branches--develop" 1
assert_match "empty component" \
  "release-please--branches--develop--components--" 1

echo "== sync: github-rulesets pattern carries the same release-please arm =="
ruleset_pattern="$(
  python3 -c '
import json, sys
path = sys.argv[1]
data = json.load(open(path, encoding="utf-8"))
pat = data["rules"][0]["parameters"]["pattern"]
print(pat)
' "$RULESET"
)"
rp_arm='release-please--branches--(develop|module/[a-z0-9-]+)--components--[a-z0-9-]+'
if [[ "$branch_regex" == *"$rp_arm"* ]]; then
  echo "PASS: hook branch_regex contains release-please arm"
  pass=$((pass + 1))
else
  echo "FAIL: hook branch_regex missing release-please arm: $branch_regex" >&2
  fail=$((fail + 1))
fi
if [[ "$ruleset_pattern" == *"$rp_arm"* ]]; then
  echo "PASS: ruleset pattern contains release-please arm"
  pass=$((pass + 1))
else
  echo "FAIL: ruleset pattern missing release-please arm: $ruleset_pattern" >&2
  fail=$((fail + 1))
fi

# Ruleset excludes main|develop (handled separately); hook includes them. Strip
# those arms and compare the shared taxonomy body so the two cannot drift.
# The hook wraps CONTRIBUTOR_HANDLES in `(…)` for alternation; the ruleset
# inlines a bare handle. Collapse `(handle)` → `handle` before comparing —
# both forms match the same names; only the release-please / bot / task arms
# must stay byte-identical.
normalize_handles() {
  # Collapse single-alternative groups that are just a contributor handle.
  sed -E 's/\(([a-z0-9]+)\)\//\1\//g'
}
hook_body="$branch_regex"
hook_body="${hook_body#^(}"
hook_body="${hook_body%)\$}"
hook_shared="$(printf '%s' "${hook_body#main|develop|}" | normalize_handles)"
ruleset_body="$ruleset_pattern"
ruleset_body="${ruleset_body#^(}"
ruleset_body="${ruleset_body%)\$}"
ruleset_shared="$(printf '%s' "$ruleset_body" | normalize_handles)"
if [[ "$hook_shared" == "$ruleset_shared" ]]; then
  echo "PASS: hook and ruleset share the same taxonomy body"
  pass=$((pass + 1))
else
  echo "FAIL: hook/ruleset taxonomy drift" >&2
  echo "  hook shared:    $hook_shared" >&2
  echo "  ruleset body:   $ruleset_shared" >&2
  fail=$((fail + 1))
fi

echo "== structural: refusal help text names the release-please pattern =="
if grep -q 'release-please--branches--<target>--components--<component>' "$HOOK"; then
  echo "PASS: pre-push help text documents release-please pattern"
  pass=$((pass + 1))
else
  echo "FAIL: pre-push help text missing release-please pattern" >&2
  fail=$((fail + 1))
fi

echo
echo "Summary: $pass passed, $fail failed"
if [[ "$fail" -ne 0 ]]; then
  exit 1
fi
