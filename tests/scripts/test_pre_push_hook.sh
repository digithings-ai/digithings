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
# DIG-1122 — execution-workspace branches (DIG-<n>-<title-slug>, the shape the
#         Paperclip harness checks out) are in the taxonomy, while the
#         near-misses that a loose prefix match would also admit are not.
#
# DIG-4898 — rescue/<issue>-<date>, the branch kit/bin/dt-worktree-rescue pushes
#         before it retires a worktree, is in the taxonomy: uppercase issue key
#         and collision suffix included, so the helper's first name is legal.
#
# DIG-1589 — duplicate-work guard (resume-before-create):
#         • a new branch rebuilding >=3 unmerged patch-ids on another unmerged
#           origin/* branch is refused, and the refusal names the sibling, its
#           tip and the overlap count
#         • an overlap of 1 or 2 is allowed (two parallel leaves share a patch)
#         • RESUME_FROM=<sibling> and RESTART_REASON both permit the push
#         • patches already merged into develop never trip the guard
#         • re-pushing an unmerged branch at its own tip is not a self-refusal
#         • an update to a branch the remote already holds is never refused, even
#           when it still overlaps a sibling: the guard is about creation, and an
#           update signal that is never read refuses ordinary follow-up work
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
# The checker is copied in before the seed commit, not after: the hook resolves
# it from the git toplevel (an installed hook is a copy under .git/hooks and
# cannot find it via $0), and committing it into develop first means every
# fixture branch built off develop already carries it — otherwise the copy would
# land as one extra shared patch and skew every overlap count below.
mkdir -p scripts
cp "$REPO_ROOT/scripts/branch_restart_check.py" scripts/branch_restart_check.py
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

# Same invocation as run_hook, but keeps stderr so the refusal *text* can be
# asserted, not just the exit status. run_hook discards it, which cannot tell
# "refused for the right reason" from "refused for an unrelated one".
capture_hook() {
  local cwd="$1"
  local url="$2"
  local stdin_line="$3"
  shift 3
  (
    cd "$cwd"
    printf '%s\n' "$stdin_line" | env -u ALLOW_MAIN_PUSH -u ALLOW_DEVELOP_PUSH "$@" \
      bash "$HOOK" origin "$url"
  ) 2>&1
}

# Refusal must carry the evidence the operator needs to act: which sibling, at
# which tip, and how many patch-ids overlap. A bare "duplicate work" line would
# send the reader back to git by hand — the whole point is that the hook did it.
assert_refusal_names() {
  local desc="$1"
  local want_branch="$2"
  local want_tip="$3"
  local want_count="$4"
  local cwd="$5"
  local url="$6"
  local line="$7"
  shift 7
  local out rc=0
  # `|| rc=$?` must sit *outside* the command substitution: inside `$( )` it
  # would assign in the subshell and the parent would always read rc 0, so every
  # refusal would look like a pass.
  out="$(capture_hook "$cwd" "$url" "$line" "$@")" || rc=$?
  if [ "$rc" -ne 1 ]; then
    echo "FAIL [refusal] $desc  (expected exit 1, got $rc)"
    fail=$((fail + 1))
    return
  fi
  if ! grep -qF "$want_branch" <<<"$out" \
    || ! grep -qF "$want_tip" <<<"$out" \
    || ! grep -qF "shares $want_count of them" <<<"$out"; then
    echo "FAIL [refusal] $desc  (missing sibling/tip/count in the message)"
    echo "$out" | sed 's/^/      | /'
    fail=$((fail + 1))
    return
  fi
  echo "PASS [refusal] $desc"
  pass=$((pass + 1))
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

# Same invocation as run_hook, but keeps stdout+stderr so the refusal *text*
# can be asserted. The wording is load-bearing: an unexplained refusal is the
# fastest thing an agent under pressure "solves" with --no-verify, which is
# worse than the accident it prevents.
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

# ── DIG-1122: execution-workspace branches DIG-<n>-<title-slug> ──────────────
# Paperclip checks out execution workspaces on `DIG-<n>-<title-slug>`, which
# matched no taxonomy arm: every commit made there was unpushable by
# construction. Uses real shas so the acceptance case also clears the scan.
DIG_WS='DIG-47-digithings-cron-twelve-x-dispatch-counts-do-not-match-the-cron-duplicate-dispatches-and-silent-gaps'
assert_exit 0 "execution-workspace branch DIG-<n>-<slug> accepted" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/$DIG_WS $SAFE_TIP refs/heads/$DIG_WS $DEV_SHA"

# The narrowness cases matter as much as the acceptance one: a regex written as
# a bare `DIG[a-z-]*` prefix would accept all three of these.
assert_exit 1 "DIG-noNumber-slug refused (number required)" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/DIG-noNumber-slug $SAFE_TIP refs/heads/DIG-noNumber-slug $DEV_SHA"

assert_exit 1 "DIGITHINGS/x refused (no digit after DIG)" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/DIGITHINGS/x $SAFE_TIP refs/heads/DIGITHINGS/x $DEV_SHA"

assert_exit 1 "DIG/47-slug refused (slash namespace is not the harness shape)" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/DIG/47-slug $SAFE_TIP refs/heads/DIG/47-slug $DEV_SHA"

assert_exit 1 "DIG-47-refused-with-no-slug (slug required)" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/DIG-47- $SAFE_TIP refs/heads/DIG-47- $DEV_SHA"

assert_exit 1 "DIG-47-SLUG refused (slug is lowercase only)" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/DIG-47-SLUG $SAFE_TIP refs/heads/DIG-47-SLUG $DEV_SHA"

# ── DIG-4898: rescue/<issue>-<date> — the branch the rescue helper pushes ────
# `kit/bin/dt-worktree-rescue` pushes `rescue/<issue>-<date>` when it retires a
# worktree that still holds work. With no arm, the push was refused, the helper
# exited 2 and the worktree stayed — so this is run through the real hook, not
# just the regex, because the refusal is the outcome the helper reads.
RESCUE_BRANCH='rescue/DIG-4898-2026-10-21'
assert_exit 0 "rescue/<issue>-<date> accepted (uppercase issue key)" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/$RESCUE_BRANCH $SAFE_TIP refs/heads/$RESCUE_BRANCH $DEV_SHA"

# The helper adds `-2`/`-3` when the name is already taken, so the arm has to
# take a suffix as well — a rescue that collides must not be the one that fails.
RESCUE_SUFFIXED='rescue/DIG-4898-2026-10-21-2'
assert_exit 0 "rescue/<issue>-<date>-2 accepted (collision suffix)" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/$RESCUE_SUFFIXED $SAFE_TIP refs/heads/$RESCUE_SUFFIXED $DEV_SHA"

# The near-misses: the arm admits a rescue branch, not the word "rescue".
assert_exit 1 "rescue/ with no name refused" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/rescue/ $SAFE_TIP refs/heads/rescue/ $DEV_SHA"

assert_exit 1 "rescue/ nested further than one segment refused" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/rescue/DIG-4898/2026-10-21 $SAFE_TIP refs/heads/rescue/DIG-4898/2026-10-21 $DEV_SHA"

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

# ── an update push is still scanned for live paths ───────────────────────────
# The duplicate-work arm treats an update as not-refusable, and it must not have
# done that by skipping the rest of the hook. The base sha below is real — the
# branch is genuinely pushed — so this is an update rather than a create wearing
# a sha the remote does not hold.
LIVE_UPD_BASE="$(make_live_tip <<'EOF'
feat: touch live path

Human-Approved-By: A Human
EOF
)"
git -C "$FIXTURE" push -q origin task/2483-cosign-tmp

# Built on top rather than by make_live_tip, which resets its branch to develop
# and would leave the new tip a sibling of the pushed base instead of a child.
git -C "$FIXTURE" checkout -q task/2483-cosign-tmp
echo "order-update-$RANDOM" > "$FIXTURE/digiquant/src/digiquant/live/place_order.py"
git -C "$FIXTURE" add -A
git -C "$FIXTURE" commit -q -F - <<'EOF'
feat: touch a live path on an update push

Co-Authored-By: github-actions[bot] <41898282+github-actions[bot]@users.noreply.github.com>
EOF
LIVE_UPD_TIP="$(git -C "$FIXTURE" rev-parse HEAD)"
assert_exit 1 "an update push to a live path without the trailer still refuses" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/task/2483-cosign-tmp $LIVE_UPD_TIP refs/heads/task/2483-cosign-tmp $LIVE_UPD_BASE"

echo "order-update-signed-$RANDOM" > "$FIXTURE/digiquant/src/digiquant/live/place_order.py"
git -C "$FIXTURE" add -A
git -C "$FIXTURE" commit -q -F - <<'EOF'
feat: touch a live path on an update push, signed off

Human-Approved-By: A Human
EOF
LIVE_UPD_SIGNED="$(git -C "$FIXTURE" rev-parse HEAD)"
assert_exit 0 "an update push to a live path with the trailer is allowed" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/task/2483-cosign-tmp $LIVE_UPD_SIGNED refs/heads/task/2483-cosign-tmp $LIVE_UPD_BASE"

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

# ── DIG-1589: duplicate-work guard (resume before create) ────────────────────
# The guard asks git whether the candidate's unmerged patch-ids already exist on
# another unmerged origin/* branch. Building that fixture needs two branches off
# one base holding the same patches, which is exactly what a cherry-pick
# produces: same diff, same patch-id, different commit sha. Content is prefixed
# per branch so two fixtures never share a patch-id by accident — that would
# silently turn the merged-into-develop case below into the refusal case.
cd "$FIXTURE"

SHARED_COMMITS=()
make_shared_patches() {
  local prefix="$1"
  local count="$2"
  local branch="$3"
  git checkout -q -B "$branch" develop
  SHARED_COMMITS=()
  local i
  for ((i = 1; i <= count; i++)); do
    echo "${prefix}-$i" > "digiquant/src/digiquant/dashboard/${prefix}-$i.txt"
    git add -A
    git commit -q -m "feat(dashboard): ${prefix} change $i"
    SHARED_COMMITS+=("$(git rev-parse HEAD)")
  done
}

rebuild_from() {
  # New branch off develop replaying the first <n> shared patches.
  local branch="$1"
  local n="$2"
  local base="${3:-develop}"
  local i
  git checkout -q -B "$branch" "$base"
  for ((i = 0; i < n; i++)); do
    git cherry-pick -x "${SHARED_COMMITS[$i]}" >/dev/null 2>&1
  done
  git rev-parse HEAD
}

# ── a sibling with 3 unmerged patches, pushed so origin/<branch> exists ──────
make_shared_patches shared 3 task/1589-sibling
git push -q origin task/1589-sibling
git fetch -q origin
SIBLING_TIP="$(git rev-parse HEAD)"
SIBLING_TIP_SHORT="$(git rev-parse --short=8 HEAD)"

REBUILD_TIP="$(rebuild_from task/1589-rebuild 3)"
REBUILD_LINE="refs/heads/task/1589-rebuild $REBUILD_TIP refs/heads/task/1589-rebuild $ZERO40"

assert_exit 1 "rebuild of 3 unmerged patch-ids on an unmerged sibling is refused" \
  "$FIXTURE" "$ORIGIN_URL" "$REBUILD_LINE"

assert_refusal_names "refusal names the sibling, its tip and the overlap count" \
  "origin/task/1589-sibling" "$SIBLING_TIP_SHORT" 3 \
  "$FIXTURE" "$ORIGIN_URL" "$REBUILD_LINE"

# ── re-pushing an unmerged branch at its own tip is not a self-refusal ───────
# Without the self-exclusion the candidate overlaps *itself* on origin/ 100% and
# no agent could ever push a second commit to an unmerged branch.
assert_exit 0 "re-push of an unmerged branch at its own tip is allowed" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/task/1589-sibling $SIBLING_TIP refs/heads/task/1589-sibling $SIBLING_TIP"

# ── an update to an already-pushed, already-overlapping branch is allowed ────
# The guard refuses *creation*. Once the remote holds the ref, the branch keeps
# overlapping the same siblings at every later commit, so a sibling check on an
# update push refuses ordinary follow-up work — with the stranded branches this
# repo carries, that is most pushes. This is the reviewer's reproduction: two
# pushed branches sharing 3 patch-ids, then one unrelated commit on top of one
# of them, pushed as an ordinary update.
#
# A second patch family keeps this fixture's branches from becoming siblings of
# the shared/ cases: one stray shared patch-id here would turn the RESUME_FROM
# and merged cases below into accidental refusals.
SAVED_SHARED=("${SHARED_COMMITS[@]}")
make_shared_patches follow 3 task/1589-followup
git push -q origin task/1589-followup
git fetch -q origin
FOLLOW_TIP="$(rebuild_from task/1589-followup-rebuild 3)"
git push -q origin task/1589-followup-rebuild
git fetch -q origin
echo "follow-up note" > digiquant/src/digiquant/dashboard/followup-note.txt
git add -A
git commit -q -m "docs(dashboard): unrelated follow-up note on an existing branch"
FOLLOW_UPDATE_TIP="$(git rev-parse HEAD)"
SHARED_COMMITS=("${SAVED_SHARED[@]}")

assert_exit 0 "update push to an already-pushed, already-overlapping branch is allowed" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/task/1589-followup-rebuild $FOLLOW_UPDATE_TIP refs/heads/task/1589-followup-rebuild $FOLLOW_TIP"

# ── 1 and 2 shared patches is parallel work, not a rebuild ───────────────────
REBUILD_ONE_TIP="$(rebuild_from task/1589-rebuild-one 1)"
assert_exit 0 "overlap of 1 patch-id does not refuse" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/task/1589-rebuild-one $REBUILD_ONE_TIP refs/heads/task/1589-rebuild-one $ZERO40"

REBUILD_TWO_TIP="$(rebuild_from task/1589-rebuild-two 2)"
assert_exit 0 "overlap of 2 patch-ids does not refuse" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/task/1589-rebuild-two $REBUILD_TWO_TIP refs/heads/task/1589-rebuild-two $ZERO40"

# ── RESUME_FROM=<sibling> excludes the sibling and permits the push ──────────
assert_exit 0 "RESUME_FROM=<sibling> permits the push" \
  "$FIXTURE" "$ORIGIN_URL" "$REBUILD_LINE" \
  RESUME_FROM=task/1589-sibling

# RESUME_FROM that names some *other* branch leaves the sibling in scope, so the
# refusal stands — the escape is not a blanket bypass.
assert_exit 1 "RESUME_FROM naming a different branch does not bypass" \
  "$FIXTURE" "$ORIGIN_URL" "$REBUILD_LINE" \
  RESUME_FROM=task/1589-unrelated

# ── RESTART_REASON in the tip commit message ─────────────────────────────────
RESTART_TIP="$(rebuild_from task/1589-restart 3)"
git commit -q --amend -F - <<'EOF'
feat(dashboard): shared change 3

RESTART_REASON: the sibling branch is stranded with no owner and no PR.
EOF
RESTART_TIP="$(git rev-parse HEAD)"
assert_exit 0 "RESTART_REASON in the tip commit message permits the push" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/task/1589-restart $RESTART_TIP refs/heads/task/1589-restart $ZERO40"

# ── RESTART_REASON in the push environment, and echoed back into the log ─────
out_rc=0
env_out="$(capture_hook "$FIXTURE" "$ORIGIN_URL" "$REBUILD_LINE" \
  RESTART_REASON="hand-rolled baseline, no sibling to resume from")" || out_rc=$?
if [ "$out_rc" -eq 0 ] && grep -qF "hand-rolled baseline" <<<"$env_out"; then
  echo "PASS [exit 0] RESTART_REASON in the push env permits and is echoed back"
  pass=$((pass + 1))
else
  echo "FAIL [exit 0] RESTART_REASON in the push env permits and is echoed back (rc=$out_rc)"
  echo "$env_out" | sed 's/^/      | /'
  fail=$((fail + 1))
fi

# ── overlap with work already merged into develop never refuses ──────────────
# Two independent reasons, which is why this is safe: the merged branch is no
# longer an unmerged sibling, and `git cherry` reports those patches as already
# upstream so they are not in the candidate's unmerged set at all.
MERGED_TIP="$(rebuild_from task/1589-merged-rebuild 3)"
git checkout -q develop
git merge -q --no-ff -m "merge: fold the sibling into develop" task/1589-sibling
git push -q origin develop
git fetch -q origin develop:refs/remotes/origin/develop
# A zero remote sha, not develop's: this branch was never pushed, so this is a
# creation push. Naming a real sha here would make it an update push, which the
# guard skips before it looks at siblings — and this case would then pass for
# the wrong reason and stop testing the merged-sibling filter at all.
assert_exit 0 "overlap with a branch already merged into develop does not refuse" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/task/1589-merged-rebuild $MERGED_TIP refs/heads/task/1589-merged-rebuild $ZERO40"

# ── a protected branch is never treated as a sibling ─────────────────────────
# Zero remote sha again, for the same reason: if this were an update push the
# guard would allow it before consulting the sibling list, and dropping
# `module/` from PROTECTED_BRANCH_PREFIXES would go unnoticed.
make_shared_patches mod 3 module/dashboard
git push -q origin module/dashboard
git fetch -q origin
git checkout -q -B task/1589-mod-rebuild develop
for sha in "${SHARED_COMMITS[@]}"; do
  git cherry-pick -x "$sha" >/dev/null 2>&1
done
MOD_REBUILD_TIP="$(git rev-parse HEAD)"
assert_exit 0 "a protected module/* branch is not a duplicate-work sibling" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/task/1589-mod-rebuild $MOD_REBUILD_TIP refs/heads/task/1589-mod-rebuild $ZERO40"

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

# DIG-1122: the execution-workspace arm, with its digit required, plus a help
# line that names it. A refusal message that omits the shape the harness
# actually produces is what made this look like a config error, not a policy gap.
# Comments may quote the pattern (the rationale above the regex does), so only
# non-comment lines count — same lesson as the Co-Authored-By guard below.
if awk '
  /^[[:space:]]*#/ { next }
  /branch_regex=/ && /DIG-\[0-9\]\+/ { found=1 }
  END { exit found ? 0 : 1 }
' "$HOOK"; then
  echo "PASS [structure] DIG-<n>-<slug> present in branch_regex"
  pass=$((pass + 1))
else
  echo "FAIL [structure] branch_regex missing DIG-[0-9]+-[a-z0-9-]+"
  fail=$((fail + 1))
fi

if awk '
  /^[[:space:]]*#/ { next }
  /echo .*DIG-<n>-<slug>/ { found=1 }
  END { exit found ? 0 : 1 }
' "$HOOK"; then
  echo "PASS [structure] help text lists DIG-<n>-<slug>"
  pass=$((pass + 1))
else
  echo "FAIL [structure] Allowed-patterns help must list DIG-<n>-<slug>"
  fail=$((fail + 1))
fi

# DIG-4898: same two properties for the rescue arm — present in the regex, and
# named in the help. The uppercase character class is the load-bearing part: a
# lowercase-only arm leaves the conventional name refused, which is the bug the
# ticket is about.
if awk '
  /^[[:space:]]*#/ { next }
  /branch_regex=/ && /rescue\/\[A-Za-z0-9-\]\+/ { found=1 }
  END { exit found ? 0 : 1 }
' "$HOOK"; then
  echo "PASS [structure] rescue/<issue>-<date> present in branch_regex (uppercase allowed)"
  pass=$((pass + 1))
else
  echo "FAIL [structure] branch_regex missing rescue/[A-Za-z0-9-]+"
  fail=$((fail + 1))
fi

if awk '
  /^[[:space:]]*#/ { next }
  /echo .*rescue\/<issue>-<date>/ { found=1 }
  END { exit found ? 0 : 1 }
' "$HOOK"; then
  echo "PASS [structure] help text lists rescue/<issue>-<date>"
  pass=$((pass + 1))
else
  echo "FAIL [structure] Allowed-patterns help must list rescue/<issue>-<date>"
  fail=$((fail + 1))
fi

# BRANCHING.md carries the no-blanket-push rule; the regex without it is the
# destructive half of this change. Match the rule heading, not the word
# "blanket" anywhere in the file.
if grep -qF 'DIG-<n>-<slug>' "$REPO_ROOT/BRANCHING.md" \
  && grep -qF 'never blanket-push' "$REPO_ROOT/BRANCHING.md"; then
  echo "PASS [structure] BRANCHING.md documents the execution-workspace branch"
  pass=$((pass + 1))
else
  echo "FAIL [structure] BRANCHING.md must document DIG-<n>-<slug> and the no-blanket-push rule"
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

# Fail-closed: empty base must set failed, not continue silently past the scan.
if grep -nE 'cannot determine a diff base' "$HOOK" >/dev/null; then
  echo "PASS [structure] empty diff base refuses the push"
  pass=$((pass + 1))
else
  echo "FAIL [structure] empty diff base must refuse, not skip"
  fail=$((fail + 1))
fi

# DIG-1589: the threshold is a named constant with its rationale attached. A
# bare literal in the comparison is how it silently became 1 and turned every
# pair of parallel leaves into a refusal.
if awk '
  /^[[:space:]]*#/ { if (!seen) last_comment = last_comment "\n" $0; next }
  /^MIN_UNMERGED_PATCH_OVERLAP[[:space:]]*=/ { seen = 1; next }
  { last_comment = "" }
  END { exit seen ? 0 : 1 }
' "$REPO_ROOT/scripts/branch_restart_check.py" \
  && grep -qE '^MIN_UNMERGED_PATCH_OVERLAP = 3$' "$REPO_ROOT/scripts/branch_restart_check.py"; then
  echo "PASS [structure] MIN_UNMERGED_PATCH_OVERLAP = 3 is a named constant"
  pass=$((pass + 1))
else
  echo "FAIL [structure] branch_restart_check.py must define MIN_UNMERGED_PATCH_OVERLAP = 3"
  fail=$((fail + 1))
fi

if grep -qF 'threshold is 3 and not 1' "$REPO_ROOT/scripts/branch_restart_check.py"; then
  echo "PASS [structure] the 3-not-1 rationale sits with the constant"
  pass=$((pass + 1))
else
  echo "FAIL [structure] the 'threshold is 3 and not 1' rationale is missing"
  fail=$((fail + 1))
fi

# The hook must call the checker rather than re-deriving the logic in bash.
if grep -qF 'branch_restart_check.py' "$HOOK"; then
  echo "PASS [structure] hook delegates to branch_restart_check.py"
  pass=$((pass + 1))
else
  echo "FAIL [structure] hook must invoke scripts/branch_restart_check.py"
  fail=$((fail + 1))
fi

# The guard must run on branch pushes only. Tags and notes pushed from an
# unmerged commit are not a second attempt at the work, and deletions have no
# branch left to judge — so the arm is gated on refs/heads and not on deletions.
if awk '
  /^[[:space:]]*#/ { next }
  /is_deletion.*-eq 0/ && /refs\/heads/ { gate = NR }
  /branch_restart_check\.py/ && !gate { early = NR }
  END { exit (gate && !early) ? 0 : 1 }
' "$HOOK"; then
  echo "PASS [structure] duplicate-work arm is gated on refs/heads"
  pass=$((pass + 1))
else
  echo "FAIL [structure] duplicate-work arm must be gated on refs/heads"
  fail=$((fail + 1))
fi

# The same arm must tell the checker whether this push creates the ref. git
# reports a ref the remote does not have as an all-zero sha, so that is the
# creation signal — and the hook already computes it for the diff base. Reading
# it in the arm, not somewhere else, is the difference between refusing a
# rebuild and refusing every follow-up commit to an unmerged branch.
# DIG-1579 scoping: three arms in this hook now share the same gate line,
# `is_deletion -eq 0 && refs/heads/*` (taxonomy, duplicate-work, branch-age).
# This guard took the LAST such line in the file, so the branch-age arm, which
# has no `is_zero_sha "$remote_sha"`, reset `signal` to 0 and failed a
# duplicate-work arm that never moved. Restrict the scan to the region at and
# above the branch_restart_check.py anchor, which is where that arm ends. The
# property under test is unchanged; only the window is.
if awk '
  /^[[:space:]]*#/ { next }
  /branch_restart_check\.py/ && !anchor { anchor = NR }
  /is_deletion.*-eq 0/ && /refs\/heads/ && !anchor { gate = NR; signal = 0 }
  /is_zero_sha "\$remote_sha"/ && gate && !signal && !anchor { signal = NR }
  END { exit (gate && anchor && signal && signal > gate && signal < anchor) ? 0 : 1 }
' "$HOOK"; then
  echo "PASS [structure] duplicate-work arm passes the create-vs-update signal"
  pass=$((pass + 1))
else
  echo "FAIL [structure] duplicate-work arm must read is_zero_sha \"\$remote_sha\" before the checker"
  fail=$((fail + 1))
fi

# ── DIG-1579: branch-age warning (warns, never blocks) ────────────────────────
# policy § 6, item 3. The hook delegates to scripts/branch_age_warning.py, pointed at
# the working copy through the same override the duplicate-work arm honours, so
# the seed commit every branch above was built from stays untouched and the
# overlap counts earlier in this suite remain comparable.
AGE_HELPER="$REPO_ROOT/scripts/branch_age_warning.py"
cd "$FIXTURE"

# A branch whose tip commit is `days` old, off develop so the duplicate-work
# guard sees a sibling-free branch. `GIT_*_DATE="@<epoch>"` is the portable
# spelling — it dates the committer as well as the author, which is the field
# `git log -1 --format=%ct` reads, so the age under test is the real one and not
# an author-date substitute. One new file per commit keeps every patch-id
# distinct, so a multi-commit fixture really reports N unmerged patches.
make_stale_tip() {
  local branch="$1"
  local days="$2"
  local commits="${3:-1}"
  local epoch i tip
  epoch="$(( $(date +%s) - days * 86400 ))"
  git -C "$FIXTURE" checkout -q -B "$branch" develop
  for ((i = 1; i <= commits; i++)); do
    echo "stale-$RANDOM-$i" > "$FIXTURE/digiquant/src/digiquant/dashboard/${branch##*/}-${i}.txt"
    git -C "$FIXTURE" add -A
    GIT_AUTHOR_DATE="@${epoch}" GIT_COMMITTER_DATE="@${epoch}" \
      git -C "$FIXTURE" commit -q -m "chore: stale change $i on ${branch}"
  done
  tip="$(git -C "$FIXTURE" rev-parse HEAD)"
  printf '%s' "$tip"
}

# The warning must carry the three things needed to act — how old, which tier,
# where the rule lives — and still let the push through. An exit status alone
# cannot tell "warned" from "refused for some other reason and printed text".
assert_warns() {
  local desc="$1"
  local url="$2"
  local line="$3"
  shift 3
  local out rc=0 missing=""
  out="$(capture_hook "$FIXTURE" "$url" "$line" "$@")" || rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "FAIL [warn] $desc  (expected exit 0, got $rc)"
    echo "$out" | sed 's/^/      | /'
    fail=$((fail + 1))
    return
  fi
  grep -qF 'last commit is' <<<"$out" || missing="$missing age"
  grep -qE 'tier T[0-9]' <<<"$out" || missing="$missing tier"
  grep -qF 'docs/ops/branch-hygiene-policy.md' <<<"$out" || missing="$missing policy"
  grep -qF 'Non-blocking' <<<"$out" || missing="$missing non-blocking-claim"
  if [ -n "$missing" ]; then
    echo "FAIL [warn] $desc  (missing:$missing)"
    echo "$out" | sed 's/^/      | /'
    fail=$((fail + 1))
    return
  fi
  echo "PASS [warn] $desc"
  pass=$((pass + 1))
}

# No age output at all — not merely "no line matching one wording", which a
# reworded warning would satisfy.
assert_silent() {
  local desc="$1"
  local url="$2"
  local line="$3"
  shift 3
  local out rc=0
  out="$(capture_hook "$FIXTURE" "$url" "$line" "$@")" || rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "FAIL [silent] $desc  (expected exit 0, got $rc)"
    echo "$out" | sed 's/^/      | /'
    fail=$((fail + 1))
    return
  fi
  if grep -qE 'last commit is|tier T[0-9]|branch-age' <<<"$out"; then
    echo "FAIL [silent] $desc  (age output printed on a branch that is not stale)"
    echo "$out" | sed 's/^/      | /'
    fail=$((fail + 1))
    return
  fi
  echo "PASS [silent] $desc"
  pass=$((pass + 1))
}

assert_no_taxonomy_error() {
  local desc="$1"
  local url="$2"
  local line="$3"
  shift 3
  local out rc=0
  out="$(capture_hook "$FIXTURE" "$url" "$line" "$@")" || rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "FAIL [delete] $desc  (expected exit 0, got $rc)"
    echo "$out" | sed 's/^/      | /'
    fail=$((fail + 1))
    return
  fi
  if grep -qi 'taxonomy' <<<"$out"; then
    echo "FAIL [delete] $desc  (a deletion raised the branch-name taxonomy)"
    echo "$out" | sed 's/^/      | /'
    fail=$((fail + 1))
    return
  fi
  echo "PASS [delete] $desc"
  pass=$((pass + 1))
}

# Every age case below points the hook at the working copy through
# BRANCH_AGE_WARNING_PATH, which capture_hook forwards to `env` as an assignment.

# ── a 14-day-old branch warns, and the push still succeeds ──────────────────
STALE_TIP="$(make_stale_tip fix/1579-stale-14d 14)"
assert_warns "stale branch warns with age, tier and policy link, and pushes" \
  "$ORIGIN_URL" \
  "refs/heads/fix/1579-stale-14d $STALE_TIP refs/heads/fix/1579-stale-14d $ZERO40" \
  BRANCH_AGE_WARNING_PATH="$AGE_HELPER"

# ── a fresh branch says nothing at all ──────────────────────────────────────
FRESH_TIP="$(make_safe_tip)"
assert_silent "fresh branch prints no age warning" \
  "$ORIGIN_URL" \
  "refs/heads/task/2483-safe-tmp $FRESH_TIP refs/heads/task/2483-safe-tmp $ZERO40" \
  BRANCH_AGE_WARNING_PATH="$AGE_HELPER"

# ── the 10-day boundary, tested either side of it ───────────────────────────
# 9 and 11 rather than 10: a commit dated exactly at the threshold is decided by
# the seconds between `date +%s` here and the hook's own `time.time()`, so the
# threshold case itself would be a coin toss.
NINE_TIP="$(make_stale_tip fix/1579-nine-days 9)"
assert_silent "a 9-day-old branch is below the threshold" \
  "$ORIGIN_URL" \
  "refs/heads/fix/1579-nine-days $NINE_TIP refs/heads/fix/1579-nine-days $ZERO40" \
  BRANCH_AGE_WARNING_PATH="$AGE_HELPER"

ELEVEN_TIP="$(make_stale_tip fix/1579-eleven-days 11)"
assert_warns "an 11-day-old branch is above the threshold" \
  "$ORIGIN_URL" \
  "refs/heads/fix/1579-eleven-days $ELEVEN_TIP refs/heads/fix/1579-eleven-days $ZERO40" \
  BRANCH_AGE_WARNING_PATH="$AGE_HELPER"

# ── § 5 exclusions stay silent even when ancient ────────────────────────────
MODULE_TIP="$(make_stale_tip module/1579-stale-module 90)"
assert_silent "a 90-day-old module/* branch is exempt (policy section 5)" \
  "$ORIGIN_URL" \
  "refs/heads/module/1579-stale-module $MODULE_TIP refs/heads/module/1579-stale-module $ZERO40" \
  BRANCH_AGE_WARNING_PATH="$AGE_HELPER"

# ── deleting a stale branch still succeeds, with no taxonomy error ───────────
# The branch is real on the fixture's own bare remote first, so this is the
# literal § 4 disposal shape and not a simulation of it.
STALE_DELETE_BRANCH='fix/1579-stale-delete'
STALE_DELETE_TIP="$(make_stale_tip "$STALE_DELETE_BRANCH" 40)"
git push -q origin "$STALE_DELETE_BRANCH"
assert_no_taxonomy_error "deleting a 40-day-old branch still succeeds (#2468 exemption intact)" \
  "$ORIGIN_URL" \
  "refs/heads/$STALE_DELETE_BRANCH $ZERO40 refs/heads/$STALE_DELETE_BRANCH $STALE_DELETE_TIP" \
  BRANCH_AGE_WARNING_PATH="$AGE_HELPER"
assert_silent "a deletion prints no age warning — the branch is on its way out" \
  "$ORIGIN_URL" \
  "refs/heads/$STALE_DELETE_BRANCH $ZERO40 refs/heads/$STALE_DELETE_BRANCH $STALE_DELETE_TIP" \
  BRANCH_AGE_WARNING_PATH="$AGE_HELPER"

# ── the warning must not turn a refusal into a pass ─────────────────────────
# `main` still needs ALLOW_MAIN_PUSH, and the age arm sits after that refusal,
# so a stale main push refuses exactly as it did before DIG-1579.
STALE_MAIN_TIP="$(make_stale_tip main 30)"
assert_exit 1 "stale push to main still refuses without ALLOW_MAIN_PUSH" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/main $STALE_MAIN_TIP refs/heads/main $ZERO40" \
  BRANCH_AGE_WARNING_PATH="$AGE_HELPER"
assert_exit 0 "stale push to main is allowed with ALLOW_MAIN_PUSH=1 and warns" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/main $STALE_MAIN_TIP refs/heads/main $ZERO40" \
  BRANCH_AGE_WARNING_PATH="$AGE_HELPER" ALLOW_MAIN_PUSH=1

# ── a missing helper is fail-open, not a refusal ────────────────────────────
# An installed hook is a copy under .git/hooks shared by every worktree and is
# installed from origin/develop, so "the helper is not there yet" is the normal
# state between a hook landing and the branch being pulled — not an error.
assert_exit 0 "a missing branch_age_warning.py does not block the push" \
  "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/fix/1579-stale-14d $STALE_TIP refs/heads/fix/1579-stale-14d $ZERO40" \
  BRANCH_AGE_WARNING_PATH=/nonexistent/branch_age_warning.py

MISSING_OUT="$(capture_hook "$FIXTURE" "$ORIGIN_URL" \
  "refs/heads/fix/1579-stale-14d $STALE_TIP refs/heads/fix/1579-stale-14d $ZERO40" \
  BRANCH_AGE_WARNING_PATH=/nonexistent/branch_age_warning.py)"
if grep -qF 'branch-age warning skipped' <<<"$MISSING_OUT"; then
  echo "PASS [warn] the missing helper is reported, not silent"
  pass=$((pass + 1))
else
  echo "FAIL [warn] a missing helper must say so rather than fail quietly"
  echo "$MISSING_OUT" | sed 's/^/      | /'
  fail=$((fail + 1))
fi

# ── the hook's default resolution finds the helper at the git toplevel ───────
# The cases above all used BRANCH_AGE_WARNING_PATH. This one relies on the
# lookup the hook performs on every real push, so the override cannot be the
# only thing that works.
cp "$AGE_HELPER" "$FIXTURE/scripts/branch_age_warning.py"
assert_warns "the helper is found at the git toplevel without an override" \
  "$ORIGIN_URL" \
  "refs/heads/fix/1579-stale-14d $STALE_TIP refs/heads/fix/1579-stale-14d $ZERO40"
rm -f "$FIXTURE/scripts/branch_age_warning.py"

# ── structure: the arm is a warning, wired like one ──────────────────────────
if grep -qF 'branch_age_warning.py' "$HOOK"; then
  echo "PASS [structure] hook delegates to branch_age_warning.py"
  pass=$((pass + 1))
else
  echo "FAIL [structure] hook must invoke scripts/branch_age_warning.py"
  fail=$((fail + 1))
fi

# Branch pushes only, and never a deletion — the same gate the duplicate-work arm
# uses, because both of those refs have nothing to warn about.
#
# This has to be a SOURCE-level assertion, and scoped to the branch-age arm
# alone. Two measured reasons, both from the M7 mutation (deleting the arm's own
# `is_deletion -eq 0`), which the behavioural deletion test cannot see:
#
#  1. The deletion exemption is enforced TWICE. The hook `continue`s on every
#     deletion at the "deletions have no commit range to scan" early exit, some
#     125 lines ABOVE this arm, so the arm is already unreachable before its own
#     gate is consulted. Dropping the gate leaves the push behaviour byte-for-byte
#     identical. Verified by running both revisions against a deletion with
#     BRANCH_AGE_WARNING_PYTHON pointed at an absent binary — the skip line is
#     loud when the arm IS reached, and both revisions print nothing. A control on
#     the same fixture, same hook, as a non-deletion, does print the skip line.
#  2. The previous version of this guard took the LAST `is_deletion -eq 0 &&
#     refs/heads` line in the whole file, and never confirmed that line belonged
#     to this arm. Three arms now share that gate shape, so under M7 the scan
#     silently re-bound to the duplicate-work arm at an earlier line — whose gate
#     is intact — and passed on a hook that had lost this arm's gate entirely.
#     Its `!early` half was dead in both revisions: the gate always precedes this
#     arm's own filename mention, so `early` was never set and could not fail.
#
# So: window the scan at this arm's own comment banner (unique in the file, read
# off disk and asserted), and require the gate to appear EXACTLY ONCE inside that
# window and ahead of the arm body. `n == 1` is what turns "some arm has this
# gate" into "this arm has this gate".
if awk '
  BEGIN { win = 0; n = 0; gate = 0; body = 0 }
  /DIG-1579: branch-age warning/ { win = 1; next }
  win && /^[[:space:]]*#/ { next }
  win && /branch_age_warning\.py/ && !body { body = NR }
  win && /is_deletion.*-eq 0/ && /refs\/heads/ { n++; gate = NR }
  END { exit (n == 1 && gate > 0 && body > 0 && gate < body) ? 0 : 1 }
' "$HOOK"; then
  echo "PASS [structure] branch-age arm is gated on refs/heads and not on deletions"
  pass=$((pass + 1))
else
  echo "FAIL [structure] branch-age arm must be gated on refs/heads and not on deletions"
  fail=$((fail + 1))
fi

# `|| true` on the invocation is what makes "never blocks" true of the wiring and
# not only of the module: the hook reads any non-zero exit as a deliberate
# block, so an un-editable `|| true` here would be the one path that can refuse.
# The statement is joined across its line continuations first — read one physical
# line and the guard matches the `age_checker=` assignment, never the call.
if awk '
  /\\$/ { pending = pending $0 " "; next }
  {
    line = pending $0; pending = ""
    if (line ~ /"\$age_checker" "\$local_sha"/) {
      anchor = NR
      if (line ~ /\|\|[[:space:]]*true/) ok = NR
    }
  }
  END { exit (anchor && ok) ? 0 : 1 }
' "$HOOK"; then
  echo "PASS [structure] the branch-age invocation is || true-ed"
  pass=$((pass + 1))
else
  echo "FAIL [structure] the branch-age invocation must be || true-ed so a crash cannot refuse"
  fail=$((fail + 1))
fi

# The threshold lives in the module as a named constant for the same reason
# MIN_UNMERGED_PATCH_OVERLAP does: a bare literal is how it became 1 and turned
# every pair of parallel leaves into a refusal.
if grep -qE '^STALE_AFTER_DAYS = 10$' "$AGE_HELPER" \
  && grep -qF 'section 6, item 3' "$AGE_HELPER"; then
  echo "PASS [structure] STALE_AFTER_DAYS = 10 is a named constant tied to the policy section"
  pass=$((pass + 1))
else
  echo "FAIL [structure] branch_age_warning.py must define STALE_AFTER_DAYS = 10 and cite section 6, item 3"
  fail=$((fail + 1))
fi

# The module must never reach the network: a pre-push hook that called out would
# be disabled with --no-verify, taking the live-trading co-sign gate down with it.
if grep -qE 'https?://|urllib|requests\.|urlopen|fetch\(' "$AGE_HELPER"; then
  echo "FAIL [structure] branch_age_warning.py must not call the network"
  fail=$((fail + 1))
else
  echo "PASS [structure] branch_age_warning.py makes no network call"
  pass=$((pass + 1))
fi

cd "$REPO_ROOT"

echo "pre-push hook: $pass passed, $fail failed"
[[ "$fail" -eq 0 ]]
