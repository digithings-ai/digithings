#!/usr/bin/env bash
# create_issue.sh — Create a GitHub Issue for the DigiThings agent backlog.
#
# Usage:
#   scripts/create_issue.sh --component COMP --type TYPE --title "..." [options]
#   scripts/create_issue.sh   (interactive mode — prompts for inputs)
#
# Options:
#   --component COMP   Component name (digigraph, digisearch, etc.)
#   --type TYPE        Change type: feat, fix, refactor, docs, test, chore
#   --title "..."      Issue title (will be prefixed with [agent] if not already)
#   --body "..."       Issue body (markdown); reads from stdin if omitted
#   --risk LEVEL       Risk level: low, med, high (default: low)
#   --draft            Skip confirmation prompt
#
# Requires: gh CLI + gh auth login
# Output: issue URL on success

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# ── Defaults ──────────────────────────────────────────────────────────────────
COMPONENT=""
TYPE=""
TITLE=""
BODY=""
RISK="low"
DRAFT=false

VALID_COMPONENTS="digigraph digiquant digisearch digismith digiclaw digibase digikey digichat website root"
VALID_TYPES="feat fix refactor docs test chore style perf"
VALID_RISKS="low med high"

# ── Helpers ───────────────────────────────────────────────────────────────────
die() { echo "ERROR: $*" >&2; exit 1; }

contains() {
  local item="$1"; shift
  for x in "$@"; do [[ "$x" == "$item" ]] && return 0; done
  return 1
}

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --component) COMPONENT="$2"; shift 2 ;;
    --type)      TYPE="$2";      shift 2 ;;
    --title)     TITLE="$2";     shift 2 ;;
    --body)      BODY="$2";      shift 2 ;;
    --risk)      RISK="$2";      shift 2 ;;
    --draft)     DRAFT=true;     shift   ;;
    -h|--help)
      sed -n '2,20p' "$0" | sed 's/^# \?//'
      exit 0
      ;;
    *) die "Unknown option: $1" ;;
  esac
done

# ── Prerequisite check ────────────────────────────────────────────────────────
if ! command -v gh &>/dev/null; then
  die "gh CLI not found. Install: https://cli.github.com"
fi
if ! gh auth status &>/dev/null; then
  die "Not authenticated. Run: gh auth login"
fi

# ── Interactive mode (no required args) ───────────────────────────────────────
if [[ -z "$COMPONENT" && -z "$TITLE" ]]; then
  echo "=== New Agent Task ==="

  echo "Component (${VALID_COMPONENTS// /, }):"
  read -r COMPONENT

  echo "Type (${VALID_TYPES// /, }):"
  read -r TYPE

  echo "Title (short description):"
  read -r TITLE

  echo "Risk level (low/med/high) [low]:"
  read -r _RISK
  RISK="${_RISK:-low}"

  echo "Body (paste markdown, end with a line containing only EOF):"
  BODY=""
  while IFS= read -r line; do
    [[ "$line" == "EOF" ]] && break
    BODY="${BODY}${line}\n"
  done
fi

# ── Validation ────────────────────────────────────────────────────────────────
[[ -z "$COMPONENT" ]] && die "--component is required"
[[ -z "$TITLE" ]]     && die "--title is required"

# shellcheck disable=SC2086
contains "$COMPONENT" $VALID_COMPONENTS || \
  die "Invalid component '$COMPONENT'. Valid: ${VALID_COMPONENTS}"
# shellcheck disable=SC2086
contains "$RISK" $VALID_RISKS || \
  die "Invalid risk '$RISK'. Valid: ${VALID_RISKS}"
if [[ -n "$TYPE" ]]; then
  # shellcheck disable=SC2086
  contains "$TYPE" $VALID_TYPES || \
    die "Invalid type '$TYPE'. Valid: ${VALID_TYPES}"
fi

# ── Normalize title ───────────────────────────────────────────────────────────
# Strip leading [agent] if user added it; we'll add our own prefix
TITLE="${TITLE#\[agent\] }"
TITLE="${TITLE#\[agent\]}"

# ── Body: read from stdin if not provided ─────────────────────────────────────
if [[ -z "$BODY" ]] && ! $DRAFT; then
  if [[ ! -t 0 ]]; then
    # Piped input
    BODY="$(cat)"
  fi
fi

# ── Build labels ──────────────────────────────────────────────────────────────
LABELS="agent-task,component:${COMPONENT},risk:${RISK}"

# ── Confirmation ──────────────────────────────────────────────────────────────
if ! $DRAFT; then
  echo ""
  echo "Creating issue:"
  echo "  Title:     [agent] ${TITLE}"
  echo "  Labels:    ${LABELS}"
  echo "  Component: ${COMPONENT}"
  echo "  Risk:      ${RISK}"
  [[ -n "$BODY" ]] && echo "  Body:      (${#BODY} chars)"
  echo ""
  read -rp "Proceed? [Y/n] " confirm
  [[ "${confirm:-Y}" =~ ^[Yy]$ ]] || { echo "Cancelled."; exit 0; }
fi

# ── Create the issue ──────────────────────────────────────────────────────────
CREATE_ARGS=(
  --title "[agent] ${TITLE}"
  --label "$LABELS"
)

if [[ -n "$BODY" ]]; then
  CREATE_ARGS+=(--body "$BODY")
else
  CREATE_ARGS+=(--body "$(printf '## Goal\n\n_To be filled in._\n\n## Acceptance Criteria\n\n- [ ] \n\n## Documentation to Update\n\n- [ ] %s/ARCHITECTURE.md\n' "$COMPONENT")")
fi

ISSUE_URL="$(gh issue create "${CREATE_ARGS[@]}")"
echo "$ISSUE_URL"

# ── Add to GitHub Project #1 (org: digithings-ai) ─────────────────────────────
# Keeps the backlog single-pane; idempotent — re-adding an existing item is a no-op.
PROJECT_OWNER="${DIGI_PROJECT_OWNER:-digithings-ai}"
PROJECT_NUMBER="${DIGI_PROJECT_NUMBER:-1}"
if [[ -n "$ISSUE_URL" ]]; then
  if gh project item-add "$PROJECT_NUMBER" --owner "$PROJECT_OWNER" --url "$ISSUE_URL" >/dev/null 2>&1; then
    echo "Added to Project ${PROJECT_OWNER}/${PROJECT_NUMBER}" >&2
  else
    echo "WARN: could not auto-add ${ISSUE_URL} to Project ${PROJECT_OWNER}/${PROJECT_NUMBER} — add manually with: gh project item-add ${PROJECT_NUMBER} --owner ${PROJECT_OWNER} --url ${ISSUE_URL}" >&2
  fi
fi
