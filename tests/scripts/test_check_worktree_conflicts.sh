#!/usr/bin/env bash
# Regression suite for scripts/check-worktree-conflicts.sh (#2485 pipefail drain +
# nested `.worktrees/task/N-slug/` discovery after #2569).
#
# Usage: bash tests/scripts/test_check_worktree_conflicts.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/check-worktree-conflicts.sh"

pass=0
fail=0

assert_ok() {
  local name="$1"
  shift
  if "$@"; then
    pass=$((pass + 1))
  else
    echo "FAIL: $name"
    fail=$((fail + 1))
  fi
}

assert_fail() {
  local name="$1"
  shift
  if ! "$@"; then
    pass=$((pass + 1))
  else
    echo "FAIL: $name (expected failure)"
    fail=$((fail + 1))
  fi
}

assert_eq() {
  local name="$1"
  local got="$2"
  local want="$3"
  if [[ "$got" == "$want" ]]; then
    pass=$((pass + 1))
  else
    echo "FAIL: $name (got='$got' want='$want')"
    fail=$((fail + 1))
  fi
}

contains() {
  local haystack="$1"
  local needle="$2"
  [[ "$haystack" == *"$needle"* ]]
}

# ── Source guard: issue-body grep must drain stdin (no -q) ────────────────────
# Under pipefail, `writer | grep -q` exits 141 once the body is large enough and
# an `if` reads that as "no match" (#2485). Pin the production shape, not just a
# toy repro — a rewrite that reintroduces -q must fail here even if every
# runtime case below happens to use a short stub body.
assert_ok "issue-body grep drains stdin (no -q)" \
  grep -nF 'echo "$text" | grep -i "$comp" >/dev/null' "$SCRIPT" >/dev/null
assert_fail "issue-body grep must not use grep -q/-iq on \$text" \
  grep -nE 'echo "\$text" \| grep -[a-z]*q' "$SCRIPT" >/dev/null
# The basename self-skip used to be grep -q; it is now a [[ ]] prefix match.
assert_fail "self-skip must not rely on grep -q for task basename" \
  grep -nF 'grep -q "^task-${ISSUE}-"' "$SCRIPT" >/dev/null

# ── Pure pipefail repro of the #2485 defect class ─────────────────────────────
# Measured ~56KB on GNU grep 3.11 for the -q inversion; 70KB stays above that.
_pipefail_large_body_match() {
  local text
  text="$(python3 -c 'print("padding-" * 10000 + " digigraph ")')"
  set -o pipefail
  if echo "$text" | grep -i digigraph >/dev/null; then
    return 0
  fi
  return 1
}
assert_ok "large body still matches when grep drains stdin" _pipefail_large_body_match

_pipefail_large_body_quiet_inverts() {
  local text rc
  text="$(python3 -c 'print("padding-" * 10000 + " digigraph ")')"
  set +e
  set -o pipefail
  echo "$text" | grep -iq digigraph >/dev/null
  rc=$?
  set -e
  # 141 = SIGPIPE from the writer when -q exits early; treat that (or any
  # non-zero) as the inverted/broken outcome we must not ship.
  [[ "$rc" -ne 0 ]]
}
# Document the defect class still exists for -q; skip if this grep never SIGPIPEs
# (some builds drain anyway). A zero here means the environment cannot reproduce
# the inversion — do not fail the suite on that alone.
if _pipefail_large_body_quiet_inverts; then
  pass=$((pass + 1))
  echo "ok: grep -q + large stdin still inverts under pipefail on this host"
else
  pass=$((pass + 1))
  echo "note: grep -q did not invert on this host; drain pin above still stands"
fi

# ── Hermetic scratch repo for nested / flat worktree discovery ────────────────
SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/wt-conflicts.XXXXXX")"
cleanup() { rm -rf "$SCRATCH"; }
trap cleanup EXIT

ORIGIN="$SCRATCH/origin.git"
WORK="$SCRATCH/work"
mkdir -p "$ORIGIN" "$WORK"

git init --bare --quiet "$ORIGIN"
git -C "$ORIGIN" symbolic-ref HEAD refs/heads/develop

git clone --quiet "$ORIGIN" "$WORK"
git -C "$WORK" config user.email "test@example.com"
git -C "$WORK" config user.name "test"
# Hermetic: never pick up a developer signing key / template.
git -C "$WORK" config commit.gpgsign false
git -C "$WORK" checkout -b develop --quiet
mkdir -p "$WORK/digigraph/src" "$WORK/digiquant/src" "$WORK/scripts"
echo "base" >"$WORK/digigraph/src/base.py"
echo "base" >"$WORK/digiquant/src/base.py"
cp "$SCRIPT" "$WORK/scripts/check-worktree-conflicts.sh"
chmod +x "$WORK/scripts/check-worktree-conflicts.sh"
git -C "$WORK" add .
git -C "$WORK" commit --quiet -m "init"
git -C "$WORK" push --quiet origin develop

# Stub gh: auth ok + issue view returns a body that names digigraph (and for the
# large-body case, pads past the SIGPIPE threshold).
install_gh_stub() {
  local bin_dir="$1"
  local body_mode="${2:-short}"
  mkdir -p "$bin_dir"
  cat >"$bin_dir/gh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
case "\$*" in
  *"auth status"*) exit 0 ;;
  *"issue view"*)
    if [[ "$body_mode" == large ]]; then
      python3 -c 'import json; print(json.dumps({"title":"fix digigraph","body":("x"*70000)+" digigraph overlap"}))'
    else
      printf '%s\n' '{"title":"fix digigraph handler","body":"touches digigraph/**"}'
    fi
    ;;
  *)
    echo "gh stub: unexpected: \$*" >&2
    exit 1
    ;;
esac
EOF
  chmod +x "$bin_dir/gh"
}

run_check() {
  local issue="$1"
  shift
  env -i \
    PATH="$SCRATCH/bin:/usr/bin:/bin" \
    HOME="$SCRATCH/home" \
    GIT_CONFIG_GLOBAL=/dev/null \
    GIT_CONFIG_SYSTEM=/dev/null \
    "$@" \
    bash "$WORK/scripts/check-worktree-conflicts.sh" "$issue"
}

mkdir -p "$SCRATCH/home"
install_gh_stub "$SCRATCH/bin" short

# No .worktrees yet — advisory must stay quiet and exit 0.
set +e
out="$(run_check 42)"
rc=$?
set -e
assert_eq "exit 0 with no worktrees dir" "$rc" "0"
assert_ok "reports nothing to compare" contains "$out" "No .worktrees/ directory"

# Nested worktree for another issue that edits digigraph — must WARN.
git -C "$WORK" branch task/99-other develop --quiet
mkdir -p "$WORK/.worktrees/task"
git -C "$WORK" worktree add --quiet "$WORK/.worktrees/task/99-other" task/99-other
echo "other" >>"$WORK/.worktrees/task/99-other/digigraph/src/base.py"
git -C "$WORK/.worktrees/task/99-other" add digigraph/src/base.py
git -C "$WORK/.worktrees/task/99-other" -c user.email=test@example.com -c user.name=test \
  commit --quiet -m "other digigraph change"

set +e
out="$(run_check 42)"
rc=$?
set -e
assert_eq "nested conflict check exits 0" "$rc" "0"
assert_ok "nested foreign worktree is discovered" contains "$out" "WARNING: Overlapping files"
assert_ok "names the overlapping digigraph file" contains "$out" "digigraph/src/base.py"
assert_ok "names the foreign worktree branch" contains "$out" "task/99-other"

# Self worktree for issue 42 editing the same component must be skipped.
git -C "$WORK" branch task/42-self develop --quiet
git -C "$WORK" worktree add --quiet "$WORK/.worktrees/task/42-self" task/42-self
echo "self" >>"$WORK/.worktrees/task/42-self/digigraph/src/base.py"
git -C "$WORK/.worktrees/task/42-self" add digigraph/src/base.py
git -C "$WORK/.worktrees/task/42-self" -c user.email=test@example.com -c user.name=test \
  commit --quiet -m "self digigraph change"

set +e
out="$(run_check 42)"
set -e
assert_ok "still warns about the foreign nested worktree" contains "$out" "task/99-other"
assert_fail "must not report the current issue worktree as a conflict" \
  contains "$out" "task/42-self"

# Legacy flat layout `.worktrees/task-77-legacy/` must still be scanned.
git -C "$WORK" branch task/77-legacy develop --quiet
git -C "$WORK" worktree add --quiet "$WORK/.worktrees/task-77-legacy" task/77-legacy
echo "legacy" >>"$WORK/.worktrees/task-77-legacy/digigraph/src/base.py"
git -C "$WORK/.worktrees/task-77-legacy" add digigraph/src/base.py
git -C "$WORK/.worktrees/task-77-legacy" -c user.email=test@example.com -c user.name=test \
  commit --quiet -m "legacy digigraph change"

set +e
out="$(run_check 42)"
set -e
assert_ok "legacy flat worktree is discovered" contains "$out" "task/77-legacy"
assert_ok "legacy path appears in warning" contains "$out" "task-77-legacy"

# digiquant-only change must not match a digigraph-inferred glob.
git -C "$WORK" branch task/88-quant develop --quiet
git -C "$WORK" worktree add --quiet "$WORK/.worktrees/task/88-quant" task/88-quant
echo "quant" >>"$WORK/.worktrees/task/88-quant/digiquant/src/base.py"
git -C "$WORK/.worktrees/task/88-quant" add digiquant/src/base.py
git -C "$WORK/.worktrees/task/88-quant" -c user.email=test@example.com -c user.name=test \
  commit --quiet -m "quant only"

set +e
out="$(run_check 42)"
set -e
assert_fail "digiquant-only foreign tree must not match digigraph glob" \
  contains "$out" "task/88-quant"

# Large issue body must still infer digigraph (end-to-end #2485 through the script).
install_gh_stub "$SCRATCH/bin" large
set +e
out="$(run_check 42)"
set -e
assert_ok "large issue body still infers digigraph glob" contains "$out" "digigraph/**"
assert_ok "large body still surfaces nested overlap" contains "$out" "task/99-other"

# Missing issue arg: usage on stderr, exit 0 (non-blocking advisory).
set +e
usage_out="$(env -i PATH="$SCRATCH/bin:/usr/bin:/bin" HOME="$SCRATCH/home" \
  bash "$WORK/scripts/check-worktree-conflicts.sh" 2>&1)"
usage_rc=$?
set -e
assert_eq "no-arg exits 0" "$usage_rc" "0"
assert_ok "no-arg prints usage" contains "$usage_out" "Usage:"

echo "check-worktree-conflicts: $pass passed, $fail failed"
[[ "$fail" -eq 0 ]]
