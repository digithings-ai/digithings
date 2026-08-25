#!/usr/bin/env bash
# Regression for #2502 — install pre-push from a known-good ref, in any worktree.
#
# scripts/install-hooks.sh must:
#   • resolve the shared hooks dir (worktree-safe; honours core.hooksPath)
#   • default the source to a known-good ref, not the working tree
#   • refuse outside a git work tree (no silent ./hooks/ write)
#   • refuse a missing/unreachable ref without truncating a live hook
#   • refuse invalid bash (bash -n) without truncating a live hook
#   • stage via mktemp + mv so a failed read cannot leave a half-written hook
#
# Uses a real scratch repo (+ optional linked worktree). Never points origin at
# the real digithings URL.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
INSTALLER="$REPO_ROOT/scripts/install-hooks.sh"
HOOK_SRC="$REPO_ROOT/scripts/hooks/pre-push.sh"

pass=0
fail=0

# A developer's global config is not this suite's business.
export GIT_CONFIG_GLOBAL=/dev/null
export GIT_CONFIG_SYSTEM=/dev/null
export GIT_CONFIG_NOSYSTEM=1

assert_exit() {
  local expect="$1" name="$2"
  shift 2
  set +e
  out="$("$@" 2>&1)"
  rc=$?
  set -e
  if [[ "$rc" -eq "$expect" ]]; then
    echo "PASS: $name (rc=$rc)"
    pass=$((pass + 1))
  else
    echo "FAIL: $name — expected rc=$expect, got rc=$rc" >&2
    echo "$out" >&2
    fail=$((fail + 1))
  fi
}

assert_true() {
  local name="$1"
  shift
  if "$@"; then
    echo "PASS: $name"
    pass=$((pass + 1))
  else
    echo "FAIL: $name" >&2
    fail=$((fail + 1))
  fi
}

FIXTURE_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/install-hooks.XXXXXX")"
cleanup() {
  # Linked worktrees must be removed before the main repo dir.
  if [[ -n "${WORKTREE_DIR:-}" && -d "$WORKTREE_DIR" ]]; then
    git -C "$REPO_DIR" worktree remove --force "$WORKTREE_DIR" 2>/dev/null || rm -rf "$WORKTREE_DIR"
  fi
  rm -rf "$FIXTURE_ROOT"
}
trap cleanup EXIT

REPO_DIR="$FIXTURE_ROOT/repo"
mkdir -p "$REPO_DIR"
git -C "$REPO_DIR" init -q
git -C "$REPO_DIR" config user.email "test@example.com"
git -C "$REPO_DIR" config user.name "test"
# Seed the known-good path the installer reads from a ref.
mkdir -p "$REPO_DIR/scripts/hooks"
cp "$HOOK_SRC" "$REPO_DIR/scripts/hooks/pre-push.sh"
git -C "$REPO_DIR" add scripts/hooks/pre-push.sh
git -C "$REPO_DIR" commit -q -m "seed hook"
git -C "$REPO_DIR" branch -M develop
# Simulate origin/develop as the default HOOKS_REF.
git -C "$REPO_DIR" remote add origin "$REPO_DIR"
git -C "$REPO_DIR" update-ref refs/remotes/origin/develop refs/heads/develop

echo "== refuse outside a git work tree =="
NON_REPO="$FIXTURE_ROOT/not-a-repo"
mkdir -p "$NON_REPO"
assert_exit 1 "outside repo exits 1" \
  env -C "$NON_REPO" bash "$INSTALLER"
assert_true "outside repo did not create ./hooks/" \
  test ! -e "$NON_REPO/hooks"

echo "== default install from origin/develop =="
assert_exit 0 "default install succeeds" \
  env -C "$REPO_DIR" bash "$INSTALLER"
INSTALLED="$REPO_DIR/.git/hooks/pre-push"
assert_true "hook landed in shared .git/hooks" test -x "$INSTALLED"
before_hash="$(git hash-object "$INSTALLED")"

echo "== bad HOOKS_REF leaves the live hook untouched =="
assert_exit 1 "missing ref fails closed" \
  env -C "$REPO_DIR" HOOKS_REF=refs/heads/does-not-exist bash "$INSTALLER"
assert_true "live hook unchanged after missing-ref refuse" \
  test "$(git hash-object "$INSTALLED")" = "$before_hash"

echo "== invalid bash (WORKTREE) leaves the live hook untouched =="
# Corrupt the working-tree copy only; origin/develop still has good bash.
printf 'if then\n' >"$REPO_DIR/scripts/hooks/pre-push.sh"
assert_exit 1 "invalid bash refuses install" \
  env -C "$REPO_DIR" HOOKS_REF=WORKTREE bash "$INSTALLER"
assert_true "live hook unchanged after bash -n refuse" \
  test "$(git hash-object "$INSTALLED")" = "$before_hash"
# Restore a valid working-tree copy for later WORKTREE cases.
cp "$HOOK_SRC" "$REPO_DIR/scripts/hooks/pre-push.sh"

echo "== WORKTREE override installs the working-tree copy =="
# Fingerprint the working-tree file so we can tell it apart from origin.
echo "# coverage-fingerprint-$(date +%s)" >>"$REPO_DIR/scripts/hooks/pre-push.sh"
assert_exit 0 "WORKTREE install succeeds" \
  env -C "$REPO_DIR" HOOKS_REF=WORKTREE bash "$INSTALLER"
assert_true "WORKTREE install matches working-tree blob" \
  test "$(git hash-object "$INSTALLED")" = "$(git hash-object "$REPO_DIR/scripts/hooks/pre-push.sh")"

echo "== core.hooksPath is honoured =="
CUSTOM_HOOKS="$FIXTURE_ROOT/custom-hooks"
git -C "$REPO_DIR" config core.hooksPath "$CUSTOM_HOOKS"
# Reinstall default from origin/develop into the custom path.
assert_exit 0 "install into core.hooksPath" \
  env -C "$REPO_DIR" HOOKS_REF=origin/develop bash "$INSTALLER"
assert_true "hook landed under core.hooksPath" test -x "$CUSTOM_HOOKS/pre-push"
git -C "$REPO_DIR" config --unset core.hooksPath

echo "== linked worktree installs into the common hooks dir =="
WORKTREE_DIR="$FIXTURE_ROOT/linked"
git -C "$REPO_DIR" worktree add -q -b chore/install-hooks-wt "$WORKTREE_DIR" develop
# Reset installed hook so we can see the worktree install land in common dir.
rm -f "$REPO_DIR/.git/hooks/pre-push"
assert_exit 0 "install from linked worktree" \
  env -C "$WORKTREE_DIR" HOOKS_REF=origin/develop bash "$INSTALLER"
assert_true "linked worktree wrote common .git/hooks/pre-push" \
  test -x "$REPO_DIR/.git/hooks/pre-push"
assert_true "linked worktree has no private hooks dir" \
  test ! -e "$WORKTREE_DIR/.git/hooks"

echo
echo "Summary: $pass passed, $fail failed"
if [[ "$fail" -ne 0 ]]; then
  exit 1
fi
