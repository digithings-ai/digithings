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
# Project-field flags (optional — if omitted, fields are left unset on Project #1):
#   --phase PHASE      Phase name, e.g. "Phase 2 — Hardening"
#   --area AREA        Area name, e.g. "Cross-cutting"
#   --kind KIND        Kind: Epic, Feature, Task, Bug, Chore, Research
#   --priority PRI     Priority: P0, P1, P2, P3
#   --model MODEL      Model: sonnet (default) | opus (for high-risk tasks)
#
# When --phase/--area/--kind/--priority are provided:
#   - A row is appended to scripts/project_fields.tsv automatically.
#   - scripts/set_project_fields.sh is called to set the fields live on Project #1.
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

# Project-field defaults (empty = not provided)
PHASE=""
AREA=""
KIND=""
PRIORITY=""
MODEL="sonnet"

VALID_COMPONENTS="digigraph digiquant digisearch digismith digiclaw digibase digikey digichat website root"
VALID_TYPES="feat fix refactor docs test chore style perf"
VALID_RISKS="low med high"
VALID_PHASES="Phase 2 — Hardening|Phase 3 — Domain unification|SITAAS pilot|Phase 4 — Atlas on DigiGraph|Phase 5 — Atlas tiering"
VALID_AREAS="Cross-cutting|DigiGraph|DigiQuant|DigiSearch|DigiSmith|DigiKey|DigiChat|DigiBase|DigiClaw|Website|SITAAS|Docs|Atlas"
VALID_KINDS="Epic Feature Task Bug Chore Research"
VALID_PRIORITIES="P0 P1 P2 P3"
VALID_MODELS="sonnet opus"

# ── Helpers ───────────────────────────────────────────────────────────────────
die() { echo "ERROR: $*" >&2; exit 1; }

contains() {
  local item="$1"; shift
  for x in "$@"; do [[ "$x" == "$item" ]] && return 0; done
  return 1
}

contains_pipe() {
  local item="$1" list="$2"
  [[ "|$list|" == *"|$item|"* ]]
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
    --phase)     PHASE="$2";     shift 2 ;;
    --area)      AREA="$2";      shift 2 ;;
    --kind)      KIND="$2";      shift 2 ;;
    --priority)  PRIORITY="$2";  shift 2 ;;
    --model)     MODEL="$2";     shift 2 ;;
    -h|--help)
      sed -n '2,29p' "$0" | sed 's/^# \?//'
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

  # Project-field prompts
  echo ""
  echo "=== Project Fields (optional — press Enter to skip) ==="
  echo "Phase (${VALID_PHASES//|/, }):"
  read -r PHASE
  echo "Area (${VALID_AREAS//|/, }):"
  read -r AREA
  echo "Kind (${VALID_KINDS// /, }):"
  read -r KIND
  echo "Priority (${VALID_PRIORITIES// /, }):"
  read -r PRIORITY
  echo "Model (sonnet/opus) [sonnet]:"
  read -r _MODEL
  MODEL="${_MODEL:-sonnet}"
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
if [[ -n "$KIND" ]]; then
  # shellcheck disable=SC2086
  contains "$KIND" $VALID_KINDS || \
    die "Invalid kind '$KIND'. Valid: ${VALID_KINDS}"
fi
if [[ -n "$PRIORITY" ]]; then
  # shellcheck disable=SC2086
  contains "$PRIORITY" $VALID_PRIORITIES || \
    die "Invalid priority '$PRIORITY'. Valid: ${VALID_PRIORITIES}"
fi
if [[ -n "$PHASE" ]]; then
  contains_pipe "$PHASE" "$VALID_PHASES" || \
    die "Invalid phase '${PHASE}'. Valid: ${VALID_PHASES//|/ | }"
fi
if [[ -n "$AREA" ]]; then
  contains_pipe "$AREA" "$VALID_AREAS" || \
    die "Invalid area '${AREA}'. Valid: ${VALID_AREAS//|/ | }"
fi
# shellcheck disable=SC2086
contains "$MODEL" $VALID_MODELS || \
  die "Invalid model '${MODEL}'. Valid: ${VALID_MODELS}"

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
  [[ -n "$PHASE" ]]    && echo "  Phase:     ${PHASE}"
  [[ -n "$AREA" ]]     && echo "  Area:      ${AREA}"
  [[ -n "$KIND" ]]     && echo "  Kind:      ${KIND}"
  [[ -n "$PRIORITY" ]] && echo "  Priority:  ${PRIORITY}"
  echo "  Model:     ${MODEL}"
  [[ -n "$BODY" ]]     && echo "  Body:      (${#BODY} chars)"
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
if gh project item-add "$PROJECT_NUMBER" --owner "$PROJECT_OWNER" --url "$ISSUE_URL" >/dev/null 2>&1; then
  echo "Added to Project ${PROJECT_OWNER}/${PROJECT_NUMBER}" >&2
else
  echo "WARN: could not auto-add ${ISSUE_URL} to Project ${PROJECT_OWNER}/${PROJECT_NUMBER} — add manually with: gh project item-add ${PROJECT_NUMBER} --owner ${PROJECT_OWNER} --url ${ISSUE_URL}" >&2
fi

# ── Append TSV row + set live Project fields (if project fields provided) ──────
_HAS_FIELDS=false
[[ -n "$PHASE" || -n "$AREA" || -n "$KIND" || -n "$PRIORITY" ]] && _HAS_FIELDS=true

if $_HAS_FIELDS; then
  # Parse issue number from URL: .../issues/42 → 42
  ISSUE_NUMBER="${ISSUE_URL##*/}"

  if [[ -n "$ISSUE_NUMBER" ]]; then
    TSV="scripts/project_fields.tsv"

    # Append row if not already present
    if ! grep -q "^${ISSUE_NUMBER}	" "$TSV" 2>/dev/null; then
      printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$ISSUE_NUMBER" "${PHASE}" "${AREA}" "${KIND}" "${PRIORITY}" "${MODEL}" \
        >> "$TSV"
      echo "Appended TSV row for #${ISSUE_NUMBER} → ${TSV}" >&2
    else
      echo "TSV row for #${ISSUE_NUMBER} already exists — skipping append." >&2
    fi

    # Set Project fields live
    if [[ -f "scripts/set_project_fields.sh" ]]; then
      echo "Setting Project fields for #${ISSUE_NUMBER}..." >&2
      bash scripts/set_project_fields.sh \
        --owner "$PROJECT_OWNER" \
        --project "$PROJECT_NUMBER" \
        --tsv "$TSV" 2>&1 | grep "#${ISSUE_NUMBER}" >&2 || true
    fi
  else
    echo "WARN: could not parse issue number from URL '${ISSUE_URL}' — TSV not updated." >&2
  fi
fi
