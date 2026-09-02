#!/usr/bin/env bash
# worktree_task.sh — Manage git worktrees for isolated task execution.
#
# Usage:
#   scripts/worktree_task.sh create ISSUE_NUMBER   # create worktree for task
#   scripts/worktree_task.sh remove ISSUE_NUMBER   # remove worktree + branch
#   scripts/worktree_task.sh list                  # list all worktrees
#   scripts/worktree_task.sh path ISSUE_NUMBER     # print worktree path (no-op if missing)
#
# Worktrees are created at: .worktrees/task/N-slug/
# Branch name:              task/N-slug
#
# The branch is always cut from `origin/<base>`, never from the local branch of
# the same name — see "Base ref resolution" below for why that distinction is
# the whole point of this script.
#
# Environment:
#   WORKTREE_TASK_OFFLINE=1              skip `git fetch`, branch from whatever
#                                        the last fetch left behind (warns)
#   WORKTREE_TASK_ALLOW_STALE_MODULE=1   downgrade the stale-module-base refusal
#                                        to a warning
#
# Both accept 1/true/yes/on to enable and 0/false/no/off (or unset) to disable,
# case-insensitively. Anything else is fatal rather than guessed at — see
# `is_enabled` below.
#
# Requires: git, gh CLI

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

WORKTREES_DIR="${REPO_ROOT}/.worktrees"
COMMAND="${1:-}"
ISSUE="${2:-}"

die() { echo "ERROR: $*" >&2; exit 1; }
# Diagnostics go to stderr: run_task.sh reads this script's last *stdout* line as the
# worktree path, so a warning printed on stdout would be consumed as a path.
warn() { echo "$*" >&2; }

# ── Helpers ───────────────────────────────────────────────────────────────────

slugify() {
  # Lowercase, replace non-alphanumeric with hyphens, collapse runs, trim, max 40 chars
  echo "$1" \
    | tr '[:upper:]' '[:lower:]' \
    | sed 's/[^a-z0-9]/-/g; s/-\+/-/g; s/^-//; s/-$//' \
    | cut -c1-40
}

get_issue_title() {
  local issue="$1"
  if command -v gh &>/dev/null && gh auth status &>/dev/null 2>&1; then
    gh issue view "$issue" --json title --jq '.title' 2>/dev/null \
      | sed 's/^\[agent\] //'
  else
    echo "task"
  fi
}

branch_name() {
  local issue="$1"
  local slug
  slug="$(slugify "$(get_issue_title "$issue")")"
  echo "task/${issue}-${slug}"
}

# Resolve the base branch for a task from the issue's component label.
# Reads scripts/project_routing.json branches section; falls back to develop.
base_branch_for_issue() {
  local issue="$1"
  local routing="${REPO_ROOT}/scripts/project_routing.json"
  if [[ ! -f "$routing" ]]; then echo "develop"; return; fi

  local labels
  labels="$(gh issue view "$issue" --json labels --jq '.labels[].name' 2>/dev/null || true)"
  local comp
  comp="$(echo "$labels" | grep '^component:' | head -1)"

  python3 - "$comp" "$routing" << 'PY'
import json, sys
comp = sys.argv[1]
routing = json.load(open(sys.argv[2]))
branches = routing.get("branches", {})
branch = branches.get(comp) if comp else None
print(branch or branches.get("default", "develop"))
PY
}

# ── Base ref resolution ───────────────────────────────────────────────────────
#
# The base ref is always `refs/remotes/origin/<base>`. It has to be: a working
# clone always has `refs/heads/develop`, so the previous shape here — fetch only
# *if* the local branch is missing, then branch from the local branch — meant the
# fetch never ran at all for the five components that route straight to develop,
# and `make task ISSUE=N` handed out worktrees cut from whatever the local ref
# happened to be at. Observed 2026-08-20: a worktree 50 commits behind
# `origin/develop` (#2547).
#
# That is the failure CLAUDE.md already documents for stale module branches
# (2026-06-17: `module/digiquant` ~400 commits behind, predating the
# apps/digiquant-atlas → digiquant/src/digiquant/olympus move, so PRs cut from it
# edited files that no longer existed). Its answer was a manual pre-flight check.
# A manual check is a check that gets skipped, and this is the one place it can be
# made unconditional for every future task branch.
#
# There are deliberately no silent fallbacks below. Both the fetch failure and a
# missing `origin/<base>` used to end in `|| true` / `|| echo develop`, and the
# second of those fell back to the *local* develop — reintroducing the exact
# staleness this resolution exists to prevent, quietly.

OFFLINE="${WORKTREE_TASK_OFFLINE:-}"
ALLOW_STALE_MODULE="${WORKTREE_TASK_ALLOW_STALE_MODULE:-}"

# Is an opt-out switch on? Both of these disable a safety check, so both ways of
# misreading one are worth spending a function on.
#
# `[[ -n "$VAR" ]]` counts `0` and `false` as set, which fails in the dangerous
# direction: `WORKTREE_TASK_OFFLINE=0` would skip the fetch. Demanding exactly `1`
# fixes that but then fails in the other direction, silently ignoring `true` from
# someone who did ask for offline. So: a fixed vocabulary each way, and anything
# outside it is fatal rather than guessed at — an unrecognised value is a typo, and
# a typo in the name of a check must not decide whether the check runs.
#
# `tr` rather than `${var,,}`: macOS ships bash 3.2 and this script is run there.
is_enabled() {
  local name="$1"
  local value
  value="$(printf '%s' "${2:-}" | tr '[:upper:]' '[:lower:]')"
  case "$value" in
    '' | 0 | false | no | off) return 1 ;;
    1 | true | yes | on) return 0 ;;
    *) die "${name}=${2:-} is not a recognised value. Use 1/true/yes/on to turn it on, 0/false/no/off or unset to turn it off." ;;
  esac
}

fetch_origin() {
  if is_enabled WORKTREE_TASK_OFFLINE "$OFFLINE"; then
    warn "WARNING: WORKTREE_TASK_OFFLINE is set — skipping \`git fetch origin\`."
    warn "         The base ref below is whatever your last successful fetch left in"
    warn "         refs/remotes/origin/*, so every count that follows is measured against"
    warn "         a possibly-stale remote and can only *understate* how old the base is."
    return 0
  fi
  # --prune, because `resolve_base_ref` below trusts refs/remotes/origin/* to say
  # what exists on the remote. Without it a deleted branch leaves its last-known
  # tip cached there indefinitely, and a component routed to that branch would be
  # branched from a dead ref instead of falling back to origin/develop loudly.
  # This drops remote-tracking refs repo-wide, which other worktrees share — but
  # only ones whose branch is already gone from the remote, and local branches and
  # worktrees are untouched.
  git fetch --prune --quiet origin \
    || die "git fetch origin failed. Fix the network or the remote, or set WORKTREE_TASK_OFFLINE=1 to branch from the last fetch anyway (it will warn, and the base may be stale)."
}

# Commits reachable from origin/develop but not from $1.
#
# `2>/dev/null || echo 0` is there because this runs under `set -e` inside a
# command substitution: an absent ref would otherwise abort the whole script with
# git's error as the only explanation. The cost is that 0 conflates "not behind"
# with "could not tell", and "could not tell" would read as *pass* and skip a
# refusal — so the caller verifies both refs itself rather than trusting this.
behind_develop() {
  local ref="$1"
  git rev-list --count "${ref}..refs/remotes/origin/develop" 2>/dev/null || echo 0
}

# Return success when develop changed the subtree owned by a module base.
#
# Module names match their repository directory except digichat, whose source
# lives below frontend/. Keep the exception here rather than widening the diff
# to unrelated repository files: this guard is specifically about changes that
# could make a task edit moved or deleted component code.
module_subtree_changed_since_base() {
  local base_ref="$1"
  local base="${base_ref#refs/remotes/origin/}"
  local component_path="${base#module/}"
  if [[ "$base" == "module/digichat" ]]; then
    component_path="frontend/digichat"
  fi

  local changed_paths
  changed_paths="$(
    git diff --name-only "${base_ref}...refs/remotes/origin/develop" -- "$component_path"
  )" || die "cannot inspect ${base} changes against origin/develop; refusing to branch from an unverified module base."
  [[ -n "$changed_paths" ]]
}

# Print the remote-tracking ref to branch from, given a base branch name.
resolve_base_ref() {
  local base="$1"
  local ref="refs/remotes/origin/${base}"
  if git show-ref --verify --quiet "$ref"; then
    echo "$ref"
    return 0
  fi
  # develop *is* the fallback, so there is nothing to fall back to — say that once
  # instead of announcing a fallback to the ref that is missing and then failing to
  # find it.
  [[ "$base" != develop ]] \
    || die "origin/develop does not exist. Run \`git fetch origin develop\` — or, in a single-branch clone, \`git remote set-branches --add origin develop\` first. Nothing safe to branch from."
  warn "WARNING: origin/${base} does not exist — branching from origin/develop instead."
  warn "         scripts/project_routing.json routes this component to '${base}', so either"
  warn "         the branch was never pushed or the routing entry is wrong."
  warn "         This changes only where the branch *starts*: scripts/create_pr.sh re-derives"
  warn "         the PR base from the same routing map, so \`make pr\` will still pass"
  warn "         --base '${base}' and gh will reject it. Fix the routing entry, or push the"
  warn "         branch, before you open the PR."
  ref="refs/remotes/origin/develop"
  git show-ref --verify --quiet "$ref" \
    || die "neither origin/${base} nor origin/develop exists; nothing safe to branch from."
  echo "$ref"
}

# Refuse a module/* base that is behind origin/develop — the 2026-06-17 hazard.
#
# Refusing rather than warning is the point: a warning printed by a tool that then
# proceeds is indistinguishable from no warning at all once it scrolls past. The
# escape hatch is an env var so this stays a detour and not a dead end, and the
# refusal carries the recipe because `module-branch-protection` forbids force-push,
# which makes "just sync it" a non-obvious operation.
assert_module_base_is_current() {
  local base_ref="$1"
  [[ "$base_ref" == refs/remotes/origin/module/* ]] || return 0

  # `behind_develop` reports 0 both for "current" and for "could not measure", and
  # the second must not be read as the first. It is reachable: a single-branch
  # clone (`git clone --single-branch`, also what `actions/checkout` produces)
  # pins remote.origin.fetch to one branch, so even the fetch above does not
  # create refs/remotes/origin/develop — and this check would then pass by
  # default on the one base type it exists to guard.
  git show-ref --verify --quiet refs/remotes/origin/develop \
    || die "cannot measure ${base_ref#refs/remotes/} against origin/develop — refs/remotes/origin/develop does not exist. In a single-branch clone: git remote set-branches --add origin develop && git fetch origin develop"

  local behind
  behind="$(behind_develop "$base_ref")"
  [[ "$behind" -gt 0 ]] || return 0

  local base="${base_ref#refs/remotes/}"
  if ! module_subtree_changed_since_base "$base_ref"; then
    warn "${base} is ${behind} commit(s) behind origin/develop, but develop has no changes under its component subtree."
    warn "Proceeding: the stale-module guard only refuses when the component itself changed."
    return 0
  fi

  warn "${base} is ${behind} commit(s) behind origin/develop."
  warn "A task branch cut from a stale module branch edits code that has already moved"
  warn "or been deleted on develop. Sync it first — module-branch-protection blocks"
  warn "force-push, so this is a PR, not a push:"
  warn ""
  warn "  gh pr create --base ${base#origin/} --head develop --title 'chore(sync): ${base#origin/} <- develop'"
  warn "  # Merge it with a MERGE COMMIT (0 approvals required), then re-run this command."
  warn "  # Not a squash: squashing moves the tree but not the ancestry, so the count"
  warn "  # above is unchanged and this refusal fires again, every time, forever."
  warn ""
  is_enabled WORKTREE_TASK_ALLOW_STALE_MODULE "$ALLOW_STALE_MODULE" \
    || die "refusing to branch from a stale module base. Set WORKTREE_TASK_ALLOW_STALE_MODULE=1 to proceed anyway."
  warn "WORKTREE_TASK_ALLOW_STALE_MODULE is set — proceeding from the stale base anyway."
}

worktree_path() {
  local branch="$1"
  echo "${WORKTREES_DIR}/${branch}"
}

# ── Commands ──────────────────────────────────────────────────────────────────

cmd_create() {
  [[ -z "$ISSUE" ]] && die "Usage: worktree_task.sh create ISSUE_NUMBER"

  local branch
  branch="$(branch_name "$ISSUE")"
  local wt_path
  wt_path="$(worktree_path "$branch")"

  # Idempotent — no-op if already exists
  if [[ -d "$wt_path" ]]; then
    echo "Worktree already exists: $wt_path"
    echo "$wt_path"
    return 0
  fi

  # Refresh origin/* before anything reads a ref, so the resolution below and
  # every staleness count that follows are measured against the real remote.
  fetch_origin

  # Resolve base branch from issue component label (module/* or develop)
  local base
  base="$(base_branch_for_issue "$ISSUE")"
  local base_ref
  base_ref="$(resolve_base_ref "$base")"
  assert_module_base_is_current "$base_ref"

  mkdir -p "$WORKTREES_DIR"

  # Create branch from base if it doesn't exist; otherwise reuse. Only the second
  # path is cut from the base, so only it may claim one — a reused local branch is
  # wherever its last session left it, which is the whole hazard #2547 is about.
  if git show-ref --verify --quiet "refs/heads/${branch}"; then
    warn "Reusing existing local branch ${branch} — not cut from ${base_ref#refs/remotes/}."
    git worktree add "$wt_path" "$branch"
  else
    echo "Base branch: ${base_ref#refs/remotes/}"
    # --no-track: the start point is a remote-tracking ref, so `git worktree add -b`
    # would set origin/<base> as the new branch's upstream (branch.autoSetupMerge
    # defaults to true). Under push.default=simple a bare `git push` in the worktree
    # then fails, and git's own remedy text suggests `git push origin HEAD:develop` —
    # which puts task work straight onto the base branch and skips the task PR
    # entirely. The old local-ref start point set no upstream; keep it that way.
    git worktree add -b "$branch" --no-track "$wt_path" "$base_ref"
  fi

  echo "Worktree created: $wt_path"
  echo "Branch: $branch"
  echo "$wt_path"
}

cmd_remove() {
  [[ -z "$ISSUE" ]] && die "Usage: worktree_task.sh remove ISSUE_NUMBER"

  local branch
  branch="$(branch_name "$ISSUE")"
  local wt_path
  wt_path="$(worktree_path "$branch")"

  if [[ ! -d "$wt_path" ]]; then
    echo "Worktree not found (already removed?): $wt_path"
    return 0
  fi

  git worktree remove "$wt_path" --force
  echo "Worktree removed: $wt_path"

  # Remove branch only if it was already merged; skip silently if not
  if git branch --merged | grep -q "^  ${branch}$"; then
    git branch -d "$branch"
    echo "Branch deleted: $branch"
  else
    echo "Branch kept (not merged): $branch"
    echo "Delete manually when ready: git branch -d $branch"
  fi
}

cmd_list() {
  git worktree list
}

cmd_path() {
  [[ -z "$ISSUE" ]] && die "Usage: worktree_task.sh path ISSUE_NUMBER"
  local branch
  branch="$(branch_name "$ISSUE")"
  worktree_path "$branch"
}

# ── Dispatch ──────────────────────────────────────────────────────────────────

case "$COMMAND" in
  create) cmd_create ;;
  remove) cmd_remove ;;
  list)   cmd_list   ;;
  path)   cmd_path   ;;
  "")     die "Usage: worktree_task.sh create|remove|list|path [ISSUE_NUMBER]" ;;
  *)      die "Unknown command: $COMMAND. Valid: create, remove, list, path" ;;
esac
