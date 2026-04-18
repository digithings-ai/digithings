#!/usr/bin/env bash
# commit_helper.sh — Conventional commit helper for DigiThings.
#
# Validates and applies commits in the format:
#   type(component): description
#
# Usage:
#   scripts/commit_helper.sh "feat(digigraph): add new workflow step"
#   scripts/commit_helper.sh          # interactive mode
#   make commit MSG="fix(digisearch): correct query filter"
#
# Valid types:    feat fix refactor test docs chore style perf
# Valid components: digigraph digiquant digisearch digismith digiclaw
#                   digibase digikey digichat website config root

set -euo pipefail

VALID_TYPES=(feat fix refactor test docs chore style perf)
VALID_COMPONENTS=(digigraph digiquant digisearch digismith digiclaw digibase digikey digichat website config root)
COAUTHOR="Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"

# ── Helpers ────────────────────────────────────────────────────────────────────

in_array() {
  local needle="$1"; shift
  for item in "$@"; do [[ "$item" == "$needle" ]] && return 0; done
  return 1
}

validate_message() {
  local msg="$1"
  local pattern='^([a-z]+)\(([a-z]+)\): .{3,}'

  if ! [[ "$msg" =~ $pattern ]]; then
    echo "ERROR: Commit message must match: type(component): description"
    echo "       Got: $msg"
    echo ""
    echo "  Valid types:      ${VALID_TYPES[*]}"
    echo "  Valid components: ${VALID_COMPONENTS[*]}"
    echo ""
    echo "  Example: feat(digigraph): add new MCP tool for backtest triggers"
    return 1
  fi

  local type="${BASH_REMATCH[1]}"
  local component="${BASH_REMATCH[2]}"

  if ! in_array "$type" "${VALID_TYPES[@]}"; then
    echo "ERROR: Unknown commit type '$type'"
    echo "  Valid types: ${VALID_TYPES[*]}"
    return 1
  fi

  if ! in_array "$component" "${VALID_COMPONENTS[@]}"; then
    echo "ERROR: Unknown component '$component'"
    echo "  Valid components: ${VALID_COMPONENTS[*]}"
    return 1
  fi

  return 0
}

do_commit() {
  local msg="$1"
  git commit -m "$msg" -m "" -m "$COAUTHOR"
  echo ""
  echo "  committed: $msg"
}

# ── Interactive mode ──────────────────────────────────────────────────────────

interactive_mode() {
  echo "── DigiThings Commit Helper ─────────────────────────────────────────"
  echo ""

  echo "Type (${VALID_TYPES[*]}):"
  read -r commit_type
  if ! in_array "$commit_type" "${VALID_TYPES[@]}"; then
    echo "ERROR: Invalid type '$commit_type'" >&2; exit 1
  fi

  echo "Component (${VALID_COMPONENTS[*]}):"
  read -r commit_component
  if ! in_array "$commit_component" "${VALID_COMPONENTS[@]}"; then
    echo "ERROR: Invalid component '$commit_component'" >&2; exit 1
  fi

  echo "Description (imperative, present tense, ≥3 chars):"
  read -r commit_desc
  if [[ ${#commit_desc} -lt 3 ]]; then
    echo "ERROR: Description too short" >&2; exit 1
  fi

  local msg="${commit_type}(${commit_component}): ${commit_desc}"
  echo ""
  echo "  Message: $msg"
  echo "  Co-author: $COAUTHOR"
  echo ""
  read -r -p "Commit? [y/N] " confirm
  if [[ "$confirm" =~ ^[Yy]$ ]]; then
    do_commit "$msg"
  else
    echo "Aborted."
    exit 1
  fi
}

# ── Main ──────────────────────────────────────────────────────────────────────

if [[ $# -eq 0 ]]; then
  interactive_mode
  exit 0
fi

MSG="$1"
if ! validate_message "$MSG"; then
  exit 1
fi

do_commit "$MSG"
