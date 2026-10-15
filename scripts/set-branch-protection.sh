#!/usr/bin/env bash
# set-branch-protection.sh — apply develop's required status checks.
#
# main is deliberately NOT supported here — its gate is a single dedicated
# check ("Every commit reaching main was reviewed", from ci-review-coverage.yml)
# set up as a one-off `gh api` call, not by this script. See docs/BRANCH_PROTECTION.md
# § On main. Passing --branch main is refused rather than silently applying
# develop's contexts and clobbering it — before #2469 this script's payload was
# already develop-specific, so pointing it at main would have overwritten main's
# one check with develop's three.
#
# ── WHAT OWNS WHAT (DIG-2223) ────────────────────────────────────────────────
#
# Two scripts could write develop's required contexts, and nothing coupled them:
#
#   * this file, carrying a hardcoded four-context payload (develop's three plus
#     `gitleaks-scan`), and
#   * `scripts/enable_branch_protection.py apply --check ...`, which is what
#     docs/BRANCH_PROTECTION.md documents.
#
# They disagreed. `gitleaks-scan` was required nowhere live and is declared
# `advisory` in .github/policy-checks.yml, yet running this script would have
# added it — a fourth gate, applied by hand, from a list no check consulted. So:
#
#   * `scripts/enable_branch_protection.py` is the ONLY script that PUTs branch
#     protection. It owns the preflight, the plan-blocked diagnosis, and the
#     union that stops a narrower apply from silently dropping a live gate.
#   * `.github/required-contexts.txt` is the single committed source of the
#     context SET. This file reads it and holds no list of its own, so there is
#     no second copy to drift.
#   * `scripts/check_required_policy_checks.py` EXECUTES this file
#     (`--print-contexts`) and fails on any difference from the snapshot. The
#     coupling is checked, not assumed — so re-adding a hardcoded context is a
#     red CI lane rather than a fourth gate applied a year from now.
#
# Adding a gate is therefore: edit the snapshot, declare it in
# .github/policy-checks.yml, prove its workflow reports on a docs-only PR, then
# run this. Not: edit a shell script.
#
# `gitleaks-scan` left this file on 2026-10-14. Its old PRE-APPLY NOTE warned that
# security-gitleaks.yml carried a workflow-level `paths-ignore: ["**.md",
# "docs/**"]`, and a workflow skipped that way reports no check run at all — so
# requiring it would have wedged every docs-only PR forever. PR #5318 (merged
# 2026-10-10) deleted that filter, so the hazard is gone; the inventory still
# calls the check `advisory` until DIG-1983's branch-protection write is
# sequenced. See docs/BRANCH_PROTECTION.md.
#
# Usage:
#   bash scripts/set-branch-protection.sh --print-contexts
#   bash scripts/set-branch-protection.sh --dry-run
#   bash scripts/set-branch-protection.sh [--replace-checks]
#
# Options:
#   --print-contexts   Print the contexts this script would apply, one per line,
#                      then exit. Reads no API and needs no gh auth, so the
#                      drift guard can execute it in CI.
#   --dry-run          Print the payload without calling the GitHub API.
#   --replace-checks   Write exactly the snapshot's contexts, dropping any the
#                      branch already requires. Off by default: the writer
#                      unions the live contexts instead, so a stale snapshot
#                      cannot quietly weaken the branch.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SNAPSHOT="$REPO_ROOT/.github/required-contexts.txt"
WRITER="$REPO_ROOT/scripts/enable_branch_protection.py"
REPO="digithings-ai/digithings"
BRANCH="develop"
PYTHON="${PYTHON:-python3}"

MODE="apply"
REPLACE_CHECKS=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --print-contexts) MODE="print-contexts"; shift ;;
    --dry-run)        MODE="dry-run"; shift ;;
    --replace-checks) REPLACE_CHECKS=true; shift ;;
    --branch)
      if [[ $# -lt 2 || "$2" == --* ]]; then
        echo "ERROR: --branch requires a value" >&2; exit 1
      fi
      BRANCH="$2"; shift 2 ;;
    -h|--help)
      sed -n '2,/^$/p' "$0" | sed '$d; s/^# \?//'
      exit 0
      ;;
    *) echo "ERROR: Unknown argument: $1" >&2; exit 1 ;;
  esac
done

if [[ "$BRANCH" != "develop" ]]; then
  echo "ERROR: this script only supports 'develop'. main's protection is a" >&2
  echo "one-off gh api call (see docs/BRANCH_PROTECTION.md § On main) — do not" >&2
  echo "point this script at it, its contexts are develop-specific." >&2
  exit 1
fi

if [[ ! -f "$SNAPSHOT" ]]; then
  echo "ERROR: $SNAPSHOT is missing." >&2
  echo "It is the single source of develop's required contexts; this script" >&2
  echo "deliberately holds no list of its own, so there is nothing to fall" >&2
  echo "back to. See the ownership note at the top of this file." >&2
  exit 1
fi

# The snapshot is prose plus a list. Comment lines are documentation, not gates.
CONTEXT_LINES="$(
  awk '
    { line = $0
      sub(/^[[:space:]]+/, "", line)
      sub(/[[:space:]]+$/, "", line) }
    line == "" || line ~ /^#/ { next }
    { print line }
  ' "$SNAPSHOT"
)"

if [[ -z "$CONTEXT_LINES" ]]; then
  echo "ERROR: $SNAPSHOT lists no required contexts." >&2
  exit 1
fi

CONTEXTS=()
while IFS= read -r ctx; do
  if [[ -n "$ctx" ]]; then
    CONTEXTS+=("$ctx")
  fi
done <<< "$CONTEXT_LINES"

if [[ "$MODE" == "print-contexts" ]]; then
  printf '%s\n' "${CONTEXTS[@]}"
  exit 0
fi

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "ERROR: $PYTHON not found." >&2
  exit 1
fi

# --dry-run prints the payload and calls nothing, so it must not demand a
# credential it will not use.
if [[ "$MODE" != "dry-run" ]]; then
  if ! command -v gh &>/dev/null; then
    echo "ERROR: gh CLI not found. Install: https://cli.github.com" >&2
    exit 1
  fi
  if ! gh auth status &>/dev/null; then
    echo "ERROR: Not authenticated. Run: gh auth login" >&2
    exit 1
  fi
fi

APPLY_ARGS=(apply --repo "$REPO" --branch "$BRANCH" --mode classic)
for ctx in "${CONTEXTS[@]}"; do
  APPLY_ARGS+=(--check "$ctx")
done
if [[ "$MODE" == "dry-run" ]]; then
  APPLY_ARGS+=(--dry-run)
fi
if [[ "$REPLACE_CHECKS" == "true" ]]; then
  APPLY_ARGS+=(--replace-checks)
fi

echo "Applying $REPO:$BRANCH required contexts, read from $SNAPSHOT:" >&2
printf '  - %s\n' "${CONTEXTS[@]}" >&2
exec "$PYTHON" "$WRITER" "${APPLY_ARGS[@]}"