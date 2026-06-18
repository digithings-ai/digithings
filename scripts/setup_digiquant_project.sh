#!/usr/bin/env bash
# setup_digiquant_project.sh — One-shot setup for the digiQuant GitHub Project.
#
# Creates the project and adds the same five custom fields as Project #1:
#   Phase, Area, Kind, Priority, Model
#
# Usage:
#   bash scripts/setup_digiquant_project.sh [--org ORG]
#
# After running, set the project number as a GitHub Actions variable:
#   gh variable set DIGI_QUANT_PROJECT_NUMBER --org digithings-ai --body <N>
#
# Requires: gh CLI + org-level project write access

set -euo pipefail

ORG="digithings-ai"
TITLE="digiQuant"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --org) ORG="$2"; shift 2 ;;
    -h|--help) sed -n '2,15p' "$0" | sed 's/^# \?//'; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

if ! command -v gh &>/dev/null; then
  echo "ERROR: gh CLI not found." >&2; exit 1
fi
if ! gh auth status &>/dev/null; then
  echo "ERROR: Not authenticated. Run: gh auth login" >&2; exit 1
fi

echo "Creating project '${TITLE}' under org '${ORG}'..."
PROJECT_JSON=$(gh project create --owner "$ORG" --title "$TITLE" --format json)
PROJECT_NUMBER=$(echo "$PROJECT_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['number'])")
echo "Created project #${PROJECT_NUMBER}"

add_field() {
  local name="$1"; shift
  local opts_csv
  opts_csv=$(IFS=','; echo "$*")
  echo -n "  Adding field '${name}'..."
  gh project field-create "$PROJECT_NUMBER" --owner "$ORG" --name "$name" \
    --data-type SINGLE_SELECT --single-select-options "$opts_csv" > /dev/null
  echo " done."
}

add_field "Phase" \
  "Phase 2 — Hardening" \
  "Phase 3 — Domain unification" \
  "Phase 4 — Atlas on DigiGraph" \
  "Phase 5 — Atlas tiering" \
  "SITAAS pilot"

add_field "Area" \
  "Cross-cutting" \
  "DigiGraph" \
  "DigiQuant" \
  "DigiSearch" \
  "DigiSmith" \
  "DigiKey" \
  "DigiChat" \
  "DigiBase" \
  "DigiClaw" \
  "Website" \
  "SITAAS" \
  "Docs" \
  "Atlas"

add_field "Kind" \
  "Epic" \
  "Feature" \
  "Task" \
  "Bug" \
  "Chore" \
  "Research"

add_field "Priority" \
  "P0" \
  "P1" \
  "P2" \
  "P3"

add_field "Model" \
  "sonnet" \
  "opus"

echo ""
echo "Setup complete. Project URL: https://github.com/orgs/${ORG}/projects/${PROJECT_NUMBER}"
echo ""
echo "Next step — store the project number as a GitHub Actions variable:"
echo "  gh variable set DIGI_QUANT_PROJECT_NUMBER --repo <org/repo> --body ${PROJECT_NUMBER}"
echo "  (Use --org ${ORG} instead if you have org admin access)"
echo ""
echo "Or export locally:"
echo "  export DIGI_QUANT_PROJECT_NUMBER=${PROJECT_NUMBER}"
