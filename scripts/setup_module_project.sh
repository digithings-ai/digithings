#!/usr/bin/env bash
# setup_module_project.sh — Create a standard DigiThings module GitHub Project.
#
# Usage:
#   bash scripts/setup_module_project.sh --title "DigiChat" [--org ORG]
#
# Creates the project with standard fields (Phase, Area, Kind, Priority, Model)
# matching the rest of the DigiThings project boards.
#
# After running, register the project number:
#   gh variable set DIGI_<MODULE>_PROJECT_NUMBER --repo digithings-ai/digithings --body <N>
#   Also add the mapping to scripts/project_routing.json

set -euo pipefail

ORG="digithings-ai"
TITLE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --title) TITLE="$2"; shift 2 ;;
    --org)   ORG="$2";   shift 2 ;;
    -h|--help) sed -n '2,12p' "$0" | sed 's/^# \?//'; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

[[ -z "$TITLE" ]] && { echo "ERROR: --title is required" >&2; exit 1; }

command -v gh &>/dev/null || { echo "ERROR: gh CLI not found." >&2; exit 1; }
gh auth status &>/dev/null || { echo "ERROR: Not authenticated. Run: gh auth login" >&2; exit 1; }

echo "Creating project '${TITLE}' under org '${ORG}'..."
PROJECT_JSON=$(gh project create --owner "$ORG" --title "$TITLE" --format json)
PROJECT_NUMBER=$(echo "$PROJECT_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['number'])")
echo "Created project #${PROJECT_NUMBER}"

add_field() {
  local name="$1"; shift
  local opts_csv="$*"
  echo -n "  Adding field '${name}'..."
  gh project field-create "$PROJECT_NUMBER" --owner "$ORG" --name "$name" \
    --data-type SINGLE_SELECT --single-select-options "$opts_csv" > /dev/null
  echo " done."
}

add_field "Phase" \
  "Phase 2 — Hardening,Phase 3 — Domain unification,Phase 4 — Atlas on DigiGraph,Phase 5 — Atlas tiering,SITAAS pilot"
add_field "Area" \
  "Cross-cutting,DigiGraph,DigiQuant,DigiSearch,DigiSmith,DigiKey,DigiChat,DigiBase,DigiClaw,Website,SITAAS,Docs,Atlas"
add_field "Kind" \
  "Epic,Feature,Task,Bug,Chore,Research"
add_field "Priority" \
  "P0,P1,P2,P3"
add_field "Model" \
  "sonnet,opus"

echo ""
echo "Project URL: https://github.com/orgs/${ORG}/projects/${PROJECT_NUMBER}"
echo ""
echo "Next steps:"
echo "  1. Store the project number as a GitHub Actions variable:"
echo "     gh variable set DIGI_<MODULE>_PROJECT_NUMBER --repo digithings-ai/digithings --body ${PROJECT_NUMBER}"
echo "  2. Add the mapping to scripts/project_routing.json"
echo "     \"component:<module>\": ${PROJECT_NUMBER}"
