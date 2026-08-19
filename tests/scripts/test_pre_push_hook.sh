#!/usr/bin/env bash
# Regression for scripts/hooks/pre-push.sh after #2468 / #2463.
#
# Until that fix, the branch-name taxonomy check ran *before* the zero-sha
# deletion skip, so `git push origin --delete bot/stub-tsv-<N>` (and any
# out-of-taxonomy ref) failed client-side with a name error and stranded the
# branch on origin. Deletions must be exempt from the taxonomy; `main`
# deletions still require ALLOW_MAIN_PUSH=1; creation/update still enforce
# the name regex (including the new bot/<slug> pattern).
#
# Usage: bash tests/scripts/test_pre_push_hook.sh
# Wired into CI via .github/workflows/ci.yml (ruff-and-scripts).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HOOK="$REPO_ROOT/scripts/hooks/pre-push.sh"
ORIGIN_URL='https://github.com/digithings-ai/digithings.git'
ZERO='0000000000000000000000000000000000000000'
# Fake non-zero shas — the hook does not resolve them on the deletion path.
OLD_SHA='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
NEW_SHA='bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'

pass=0
fail=0

run_hook() {
  local url="$1"
  local stdin_line="$2"
  shift 2
  # Extra KEY=VAL pairs (e.g. ALLOW_MAIN_PUSH=1) are applied via env.
  set +e
  printf '%s\n' "$stdin_line" | env -u ALLOW_MAIN_PUSH "$@" \
    bash "$HOOK" origin "$url" >/dev/null 2>&1
  local rc=$?
  set -e
  return "$rc"
}

assert_exit() {
  local want="$1"
  local desc="$2"
  local url="$3"
  local line="$4"
  shift 4
  local rc=0
  run_hook "$url" "$line" "$@" || rc=$?
  if [[ "$rc" -eq "$want" ]]; then
    echo "PASS [exit $want] $desc"
    pass=$((pass + 1))
  else
    echo "FAIL [exit $want] $desc  (got $rc)"
    fail=$((fail + 1))
  fi
}

# ── #2468: deletions exempt from taxonomy ───────────────────────────────────
# The bug: taxonomy ran first and exit 1'd before the zero-sha continue.
assert_exit 0 "delete out-of-taxonomy branch (garbage/nonsense)" "$ORIGIN_URL" \
  "refs/heads/garbage/nonsense $ZERO refs/heads/garbage/nonsense $OLD_SHA"

assert_exit 0 "delete bot/stub-tsv branch (the stranded-ref case)" "$ORIGIN_URL" \
  "refs/heads/bot/stub-tsv-9999 $ZERO refs/heads/bot/stub-tsv-9999 $OLD_SHA"

assert_exit 0 "delete in-taxonomy task branch" "$ORIGIN_URL" \
  "refs/heads/task/1-legit $ZERO refs/heads/task/1-legit $OLD_SHA"

# ── main guard still covers deletions ───────────────────────────────────────
assert_exit 1 "delete main without ALLOW_MAIN_PUSH" "$ORIGIN_URL" \
  "refs/heads/main $ZERO refs/heads/main $OLD_SHA"

assert_exit 0 "delete main with ALLOW_MAIN_PUSH=1" "$ORIGIN_URL" \
  "refs/heads/main $ZERO refs/heads/main $OLD_SHA" \
  ALLOW_MAIN_PUSH=1

# ── creation / update still enforce taxonomy ─────────────────────────────────
assert_exit 1 "push new out-of-taxonomy branch" "$ORIGIN_URL" \
  "refs/heads/garbage/nonsense $NEW_SHA refs/heads/garbage/nonsense $ZERO"

assert_exit 0 "push new task/<N>-slug branch" "$ORIGIN_URL" \
  "refs/heads/task/2463-legit $NEW_SHA refs/heads/task/2463-legit $ZERO"

assert_exit 0 "push new bot/<slug> branch (taxonomy addition)" "$ORIGIN_URL" \
  "refs/heads/bot/stub-tsv-2459 $NEW_SHA refs/heads/bot/stub-tsv-2459 $ZERO"

assert_exit 0 "update existing develop tip (in-taxonomy)" "$ORIGIN_URL" \
  "refs/heads/develop $NEW_SHA refs/heads/develop $OLD_SHA"

# ── tags exempt from branch-name check ──────────────────────────────────────
assert_exit 0 "push tag (not refs/heads/*)" "$ORIGIN_URL" \
  "refs/tags/v9.9.9 $NEW_SHA refs/tags/v9.9.9 $ZERO"

# ── remote URL allowlist ─────────────────────────────────────────────────────
assert_exit 1 "disallowed remote URL" \
  "https://evil.example/digithings.git" \
  "refs/heads/task/1-legit $NEW_SHA refs/heads/task/1-legit $ZERO"

# ── structural guards against reintroducing the bug ──────────────────────────
# is_deletion must be set from zero_sha *before* the taxonomy check, and the
# taxonomy gate must be gated on is_deletion == 0.
if grep -nE 'is_deletion=0' "$HOOK" >/dev/null \
  && awk '
      /is_deletion=0/ { del_set=NR }
      /is_deletion.*-eq 0/ && /refs\/heads/ { tax_gate=NR }
      END { exit !(del_set && tax_gate && del_set < tax_gate) }
    ' "$HOOK"; then
  echo "PASS [structure] is_deletion set before taxonomy gate"
  pass=$((pass + 1))
else
  echo "FAIL [structure] is_deletion must be computed before the taxonomy gate"
  fail=$((fail + 1))
fi

if grep -nE 'bot/\[a-z0-9-\]\+' "$HOOK" >/dev/null; then
  echo "PASS [structure] bot/<slug> present in branch_regex"
  pass=$((pass + 1))
else
  echo "FAIL [structure] branch_regex missing bot/[a-z0-9-]+"
  fail=$((fail + 1))
fi

echo "pre-push hook: $pass passed, $fail failed"
[[ "$fail" -eq 0 ]]
