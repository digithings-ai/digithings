#!/usr/bin/env bash
# Regression for scripts/hooks/pre-push.sh after #2468 / #2483.
#
# #2468 — deletions are exempt from the branch-name taxonomy (zero-sha local),
#         so out-of-taxonomy refs (bot/stub-tsv-*, garbage) stay deletable;
#         main deletions still require ALLOW_MAIN_PUSH=1.
#
# #2483 — live-trading co-sign actually gates:
#         • only a non-blank Human-Approved-By trailer clears the scan
#         • Co-Authored-By (bots or humans) does not
#         • is_zero_sha is width-agnostic (40 and 64 zeros)
#         • unresolvable diff base / failed diff refuse rather than skip
#         • sensitive-path grep is not -q (pipefail + SIGPIPE false negative)
#
# Usage: bash tests/scripts/test_pre_push_hook.sh
# CI: pytest wrapper tests/scripts/test_pre_push_hook.py under ruff-and-scripts.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HOOK="$REPO_ROOT/scripts/hooks/pre-push.sh"
ORIGIN_URL='https://github.com/digithings-ai/digithings.git'
ZERO40='0000000000000000000000000000000000000000'
ZERO64='0000000000000000000000000000000000000000000000000000000000000000'
# Fake non-zero shas — safe only on paths that never call git (deletion /
# taxonomy / URL). Live-trading and fail-closed cases use the fixture repo.
OLD_SHA='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
NEW_SHA='bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'

pass=0
fail=0

_fixture_root() {
  local base="${RUNNER_TEMP:-${TMPDIR:-/var/tmp}}"
  mktemp -d "${base%/}/pre-push-fixture.XXXXXX"
}

# ── Fixture: real repo so merge-base / diff / log / trailers work ────────────
FIXTURE="$(_fixture_root)"
BARE="$(_fixture_root)/origin.git"
cleanup() {
  rm -rf "$FIXTURE" "$(dirname "$BARE")"
}
trap cleanup EXIT

git init -q --bare "$BARE"
git clone -q "$BARE" "$FIXTURE" 2>/dev/null
cd "$FIXTURE"
git config user.email "pre-push-test@example.com"
git config user.name "pre-push-test"
# Keep `origin` pointed at the local bare so merge-base / fetch work.
# The digithings URL is only passed as the hook's $2 (allowlist check) —
# never as the actual remote, or fixture setup would push to GitHub.
# Seed develop so merge-base and remote tracking ref exist.
git checkout -q -b develop
mkdir -p digiquant/src/digiquant/dashboard
echo 'seed' > digiquant/src/digiquant/dashboard/README.md
git add -A
git commit -q -m "seed develop"
# Bare has no default branch yet — push and set HEAD.
git push -q origin develop
git -C "$BARE" symbolic-ref HEAD refs/heads/develop
# Fetch so origin/develop resolves locally (hook merge-base target).
git fetch -q origin develop:refs/remotes/origin/develop

cd "$REPO_ROOT"

run_hook() {
  # Args: cwd url stdin_line [ENV=VAL...]
  local cwd="$1"
  local url="$2"
  local stdin_line="$3"
  shift 3
  set +e
  (
    cd "$cwd"
    printf '%s\n' "$stdin_line" | env -u ALLOW_MAIN_PUSH -u ALLOW_DEVELOP_PUSH "$@" \
      bash "$HOOK" origin "$url"
  ) >/dev/null 2>&1
  local rc=$?
  set -e
  return "$rc"
}

assert_exit() {
  local want="$1"
  local desc="$2"
  local cwd="$3"
  local url="$4"
  local line="$5"
  shift 5
  local rc=0
  run_hook "$cwd" "$url" "$line" "$@" || rc=$?
  if [[ "$rc" -eq "$want" ]]; then
    echo "PASS [exit $want] $desc"
    pass=$((pass + 1))
  else
    echo "FAIL [exit $want] $desc  (got $rc)"
    fail=$((fail + 1))
  fi
}

# Build a REAL tip that touches no live-trading path, on an in-taxonomy branch
# forked from develop. Real shas matter here: a synthetic sha makes the hook fail
# closed in the diff-base scan, which would make a develop-guard test exit 1 for
# the wrong reason and pass before any guard exists.
make_clean_tip() {
  local branch="task/530-guard-fixture"
  cd "$FIXTURE"
  git checkout -q -B "$branch" develop
  mkdir -p docs/ops
  echo "guard-fixture-$(date +%s%N)-$RANDOM" > docs/ops/guard-fixture.md
  git add -A
  git commit -q -m "530 fixture: clean tip touching no live-trading path"
  local tip
  tip="$(git rev-parse HEAD)"
  cd "$REPO_ROOT"
  printf '%s' "$tip"
}

# Assert the hook's refusal text carries a specific substring. The wording is
# load-bearing: an unexplained refusal is the fastest thing an agent under
# pressure "solves" with --no-verify, which is worse than the accident.
run_hook_out() {
  local cwd="$1"
  local url="$2"
  local stdin_line="$3"
  shift 3
  (
    cd "$cwd"
    printf '%s\n' "$stdin_line" | env -u ALLOW_MAIN_PUSH -u ALLOW_DEVELOP_PUSH "$@" \
      bash "$HOOK" origin "$url"
  ) 2>&1 || true
}

assert_refusal_mentions() {
  local desc="$1"
  local needle="$2"
  local line="$3"
  shift 3
  local out
  out="$(run_hook_out "$FIXTURE" "$ORIGIN_URL" "$line" "$@")"
  if [[ "$out" == *"$needle"* ]]; then
    echo "PASS [wording] $desc"
    pass=$((pass + 1))
  else
    echo "FAIL [wording] $desc  (refusal text lacks: $needle)"
    fail=$((fail + 1))
  fi
}

# Build a tip that changes a live-trading path; commit message via stdin (heredoc).
# Avoids shell angle-bracket hazards in trailer email addresses.
# Prints the new tip sha on stdout. Branch name is task/2483-cosign-tmp.
make_live_tip() {
  local branch="task/2483-cosign-tmp"
  cd "$FIXTURE"
  git checkout -q -B "$branch" develop
  # Match the shipped live-trading regex: digiquant/.../live/
  mkdir -p digiquant/src/digiquant/live
  # Unique content so successive tips always produce a non-empty diff.
  echo "order-$(date +%s%N)-$RANDOM" > digiquant/src/digiquant/live/place_order.py
  git add -A
  # Message on stdin — caller feeds a heredoc. Avoids -m + <email> quoting.
  git commit -q -F -
  local tip
  tip="$(git rev-parse HEAD)"
  cd "$REPO_ROOT"
  printf '%s' "$tip"
}

# Non-sensitive tip (taxonomy + scan both green without a trailer).
make_safe_tip() {
  local branch="task/2483-safe-tmp"
  cd "$FIXTURE"
  git checkout -q -B "$branch" develop
  echo "safe-$RANDOM" > digiquant/src/digiquant/dashboard/note.txt
  git add -A
  git commit -q -m "chore: non-sensitive change"
  local tip
  tip="$(git rev-parse HEAD)"
  cd "$REPO_ROOT"
  printf '%s' "$tip"
}

develop_sha() {
  git -C "$FIXTURE" rev-parse develop
}

# ── #2468: deletions exempt from taxonomy (fake SHAs OK — no git calls) ─────
assert_exit 0 "delete out-of-taxonomy branch (garbage/nonsense)" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/garbage/nonsense $ZERO40 refs/heads/garbage/nonsense $OLD_SHA"

assert_exit 0 "delete bot/stub-tsv branch (the stranded-ref case)" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/bot/stub-tsv-9999 $ZERO40 refs/heads/bot/stub-tsv-9999 $OLD_SHA"

assert_exit 0 "delete in-taxonomy task branch" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/task/1-legit $ZERO40 refs/heads/task/1-legit $OLD_SHA"

# ── #2483: is_zero_sha width-agnostic (sha256-width deletion) ────────────────
assert_exit 0 "delete out-of-taxonomy with 64-zero sha (sha256)" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/garbage/sha256 $ZERO64 refs/heads/garbage/sha256 $OLD_SHA"

# ── main guard still covers deletions ───────────────────────────────────────
assert_exit 1 "delete main without ALLOW_MAIN_PUSH" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/main $ZERO40 refs/heads/main $OLD_SHA"

assert_exit 0 "delete main with ALLOW_MAIN_PUSH=1" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/main $ZERO40 refs/heads/main $OLD_SHA" \
  ALLOW_MAIN_PUSH=1

# ── develop guard (DIG-530) ─────────────────────────────────────────────────
# develop carries required_pull_request_reviews: null (BRANCHING.md:51), so there
# is no server-side PR gate on it and this hook is the only guard. bffce04d9
# reached develop with no PR and no review because develop is inside branch_regex
# and the per-ref opt-in existed only for main.
DEVELOP_SHA="$(git -C "$FIXTURE" rev-parse develop)"
CLEAN_TIP="$(make_clean_tip)"
DEVELOP_PUSH_LINE="refs/heads/task/530-guard-fixture $CLEAN_TIP refs/heads/develop $DEVELOP_SHA"

assert_exit 1 "push develop without ALLOW_DEVELOP_PUSH" \
  "$FIXTURE" "$ORIGIN_URL" \
  "$DEVELOP_PUSH_LINE"

assert_exit 0 "push develop with ALLOW_DEVELOP_PUSH=1" \
  "$FIXTURE" "$ORIGIN_URL" \
  "$DEVELOP_PUSH_LINE" \
  ALLOW_DEVELOP_PUSH=1

# Deletions mirror the existing main coverage exactly.
assert_exit 1 "delete develop without ALLOW_DEVELOP_PUSH" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/develop $ZERO40 refs/heads/develop $OLD_SHA"

assert_exit 0 "delete develop with ALLOW_DEVELOP_PUSH=1" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/develop $ZERO40 refs/heads/develop $OLD_SHA" \
  ALLOW_DEVELOP_PUSH=1

# The refusal must name the cause and hand over the corrective command. A bare
# "refusing to push to develop" reads as an unexplained failure, and the fastest
# way an agent under pressure resolves one is --no-verify.
assert_refusal_mentions "develop refusal names the corrective command" \
  "set-upstream-to" \
  "$DEVELOP_PUSH_LINE"

assert_refusal_mentions "develop refusal names the opt-in" \
  "ALLOW_DEVELOP_PUSH" \
  "$DEVELOP_PUSH_LINE"

# ── creation / update still enforce taxonomy (fake SHA — fails before scan) ─
assert_exit 1 "push new out-of-taxonomy branch" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/garbage/nonsense $NEW_SHA refs/heads/garbage/nonsense $ZERO40"

# ── tags exempt from branch-name check; zero remote → merge-base path ───────
# Use a real tip so fail-closed does not fire after taxonomy exemption.
SAFE_TIP="$(make_safe_tip)"
DEV_SHA="$(develop_sha)"
assert_exit 0 "push tag (not refs/heads/*) with real tip" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/tags/v9.9.9 $SAFE_TIP refs/tags/v9.9.9 $ZERO40"

# ── remote URL allowlist ─────────────────────────────────────────────────────
assert_exit 1 "disallowed remote URL" \
  "$FIXTURE" "https://evil.example/digithings.git" \
  "refs/heads/task/1-legit $SAFE_TIP refs/heads/task/1-legit $ZERO40"

ORIGIN_MIRROR_URL='https://origin.cursor.com/chrizefan/digithings.git'
ORIGIN_LOCAL_URL='https://origin.cursor.com/chrizefan/digithings.git/local'
assert_exit 0 "promotion branch to Origin mirror URL" \
  "$FIXTURE" "$ORIGIN_MIRROR_URL" \
  "refs/heads/task/2483-safe $SAFE_TIP refs/heads/task/2483-safe $DEV_SHA"
assert_exit 1 "origin/* draft toward GitHub" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/origin/draft $SAFE_TIP refs/heads/origin/draft $ZERO40"
assert_exit 0 "origin/* draft toward Origin-only endpoint" \
  "$FIXTURE" "$ORIGIN_LOCAL_URL" \
  "refs/heads/origin/draft $SAFE_TIP refs/heads/origin/draft $ZERO40"
assert_exit 1 "promotion branch toward Origin-only endpoint" \
  "$FIXTURE" "$ORIGIN_LOCAL_URL" \
  "refs/heads/task/1-legit $SAFE_TIP refs/heads/task/1-legit $ZERO40"

# ── non-sensitive in-taxonomy push allowed without trailer ───────────────────
assert_exit 0 "non-sensitive task branch update (no trailer needed)" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/task/2483-safe $SAFE_TIP refs/heads/task/2483-safe $DEV_SHA"

# ── #2483: live-trading co-sign matrix ───────────────────────────────────────
LIVE_BLOCKED="$(make_live_tip <<'EOF'
feat: touch live path

Co-Authored-By: github-actions[bot] <41898282+github-actions[bot]@users.noreply.github.com>
EOF
)"
assert_exit 1 "live path + Co-Authored-By bot does not clear gate" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/task/2483-cosign $LIVE_BLOCKED refs/heads/task/2483-cosign $DEV_SHA"

LIVE_DEPENDABOT="$(make_live_tip <<'EOF'
feat: touch live path

Co-Authored-By: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>
EOF
)"
assert_exit 1 "live path + Co-Authored-By dependabot does not clear gate" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/task/2483-cosign $LIVE_DEPENDABOT refs/heads/task/2483-cosign $DEV_SHA"

LIVE_CLAUDE="$(make_live_tip <<'EOF'
feat: touch live path

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
assert_exit 1 "live path + Co-Authored-By Claude does not clear gate" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/task/2483-cosign $LIVE_CLAUDE refs/heads/task/2483-cosign $DEV_SHA"

LIVE_HUMAN_CO="$(make_live_tip <<'EOF'
feat: touch live path

Co-Authored-By: Chris Stefan <chris@example.com>
EOF
)"
assert_exit 1 "live path + Co-Authored-By human does not clear gate" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/task/2483-cosign $LIVE_HUMAN_CO refs/heads/task/2483-cosign $DEV_SHA"

LIVE_TYPO="$(make_live_tip <<'EOF'
feat: touch live path

Human-Approved-Byte: not a trailer
EOF
)"
assert_exit 1 "live path + Human-Approved-Byte typo does not clear gate" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/task/2483-cosign $LIVE_TYPO refs/heads/task/2483-cosign $DEV_SHA"

LIVE_BARE="$(make_live_tip <<'EOF'
feat: touch live path

Human-Approved-By:
EOF
)"
assert_exit 1 "live path + bare Human-Approved-By: does not clear gate" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/task/2483-cosign $LIVE_BARE refs/heads/task/2483-cosign $DEV_SHA"

LIVE_BODY="$(make_live_tip <<'EOF'
feat: document the gate

Mention Human-Approved-By: Someone in the body, not as a trailer.

Signed-off-by: pre-push-test <pre-push-test@example.com>
EOF
)"
assert_exit 1 "live path + Human-Approved-By only in body prose does not clear gate" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/task/2483-cosign $LIVE_BODY refs/heads/task/2483-cosign $DEV_SHA"

LIVE_OK="$(make_live_tip <<'EOF'
feat: touch live path

Human-Approved-By: A Human
EOF
)"
assert_exit 0 "live path + Human-Approved-By: value clears gate" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/task/2483-cosign $LIVE_OK refs/heads/task/2483-cosign $DEV_SHA"

# New-branch push (zero remote sha) still scans via merge-base with origin/develop.
assert_exit 0 "new-branch live tip with Human-Approved-By (zero remote sha)" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/task/2483-new $LIVE_OK refs/heads/task/2483-new $ZERO40"

assert_exit 1 "new-branch live tip without trailer (zero remote sha)" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/task/2483-new $LIVE_BLOCKED refs/heads/task/2483-new $ZERO40"

# ── #2483: fail-closed when no diff base ─────────────────────────────────────
cd "$FIXTURE"
git checkout -q --orphan orphan-unrelated
git rm -rfq . >/dev/null 2>&1 || true
echo orphan > orphan.txt
git add -A
git commit -q -m "orphan root"
ORPHAN_TIP="$(git rev-parse HEAD)"
git checkout -q develop
cd "$REPO_ROOT"
assert_exit 1 "orphan tip with no merge-base refuses unscanned" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/task/2483-orphan $ORPHAN_TIP refs/heads/task/2483-orphan $ZERO40"

# ── structural guards ────────────────────────────────────────────────────────
if grep -nE 'is_zero_sha\(\)' "$HOOK" >/dev/null \
  && grep -nE '\[\[ "\$1" =~ \^0\+\$ \]\]' "$HOOK" >/dev/null; then
  echo "PASS [structure] is_zero_sha matches ^0+\$ (width-agnostic)"
  pass=$((pass + 1))
else
  echo "FAIL [structure] is_zero_sha must match ^0+\$"
  fail=$((fail + 1))
fi

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

# Co-Authored-By must not appear as an acceptance arm (the #2483 bug).
# Comments may quote the old pattern; only non-comment lines count.
if awk '
  /^[[:space:]]*#/ { next }
  /Co-Authored-By/ { found=1 }
  END { exit found ? 0 : 1 }
' "$HOOK"; then
  echo "FAIL [structure] Co-Authored-By must not be an acceptance arm"
  fail=$((fail + 1))
else
  echo "PASS [structure] no Co-Authored-By acceptance arm"
  pass=$((pass + 1))
fi

# Trailer parse must use git's trailer formatter, not a body-line regex.
if grep -nE 'trailers:key=Human-Approved-By' "$HOOK" >/dev/null; then
  echo "PASS [structure] Human-Approved-By via %(trailers:key=...)"
  pass=$((pass + 1))
else
  echo "FAIL [structure] must parse Human-Approved-By via git trailers"
  fail=$((fail + 1))
fi

# Sensitive-path grep must not use -q (pipefail SIGPIPE false negative).
if awk '
  /live_trading\|execute_trade\|place_order/ { hit=1; line=$0 }
  END {
    if (!hit) exit 1
    if (line ~ /grep -[^ ]*q/ || line ~ /grep -q/) exit 2
    exit 0
  }
' "$HOOK"; then
  echo "PASS [structure] live-trading grep is not -q"
  pass=$((pass + 1))
else
  rc=$?
  if [[ "$rc" -eq 2 ]]; then
    echo "FAIL [structure] live-trading grep must not use -q under pipefail"
  else
    echo "FAIL [structure] live-trading path grep not found"
  fi
  fail=$((fail + 1))
fi

# ── DIG-530 structural pins ─────────────────────────────────────────────────
# develop must STAY inside branch_regex. The fix is the per-ref opt-in, not
# deleting develop from the taxonomy: a taxonomy failure refuses for the wrong
# reason and offers no ALLOW_DEVELOP_PUSH escape hatch.
if grep -E '^branch_regex=' "$HOOK" | grep -q 'develop'; then
  echo "PASS [structure] develop stays in branch_regex (per-ref opt-in, not taxonomy)"
  pass=$((pass + 1))
else
  echo "FAIL [structure] develop must remain in branch_regex; refuse via ALLOW_DEVELOP_PUSH instead"
  fail=$((fail + 1))
fi

# The hook's own header comment is the first thing anyone reads when the guard
# surprises them. An undocumented ALLOW_DEVELOP_PUSH is an unusable escape hatch.
if sed -n '1,20p' "$HOOK" | grep -q 'ALLOW_DEVELOP_PUSH'; then
  echo "PASS [structure] hook header documents ALLOW_DEVELOP_PUSH"
  pass=$((pass + 1))
else
  echo "FAIL [structure] hook header comment must document ALLOW_DEVELOP_PUSH"
  fail=$((fail + 1))
fi

# Docs pin, not a hook assertion: BRANCHING.md's ALLOW_MAIN_PUSH prose (lines 55
# and 219) goes stale the moment this guard exists, and nothing else notices.
if grep -q 'ALLOW_DEVELOP_PUSH' "$REPO_ROOT/BRANCHING.md"; then
  echo "PASS [docs] BRANCHING.md documents ALLOW_DEVELOP_PUSH"
  pass=$((pass + 1))
else
  echo "FAIL [docs] BRANCHING.md ALLOW_MAIN_PUSH prose must gain ALLOW_DEVELOP_PUSH"
  fail=$((fail + 1))
fi

# Fail-closed: empty base must set failed, not continue silently past the scan.
if grep -nE 'cannot determine a diff base' "$HOOK" >/dev/null; then
  echo "PASS [structure] empty diff base refuses the push"
  pass=$((pass + 1))
else
  echo "FAIL [structure] empty diff base must refuse, not skip"
  fail=$((fail + 1))
fi

echo "pre-push hook: $pass passed, $fail failed"
[[ "$fail" -eq 0 ]]
