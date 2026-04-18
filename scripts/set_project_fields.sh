#!/usr/bin/env bash
# set_project_fields.sh — bulk-set Phase/Area/Kind/Priority on DigiThings GitHub Project items.
#
# Usage:
#   scripts/set_project_fields.sh [--tsv PATH] [--owner OWNER] [--project NUM]
#
# Defaults: owner=digithings-ai, project=1, tsv=scripts/project_fields.tsv
#
# TSV format (tab-separated, header required, empty cell = leave field unchanged):
#
#   issue<TAB>phase<TAB>area<TAB>kind<TAB>priority
#   2<TAB>Phase 2 — Hardening<TAB>Cross-cutting<TAB>Epic<TAB>P0
#   3<TAB>Phase 2 — Hardening<TAB>Cross-cutting<TAB>Epic<TAB>P0
#
# Field/option names must match the Project's configuration exactly (em-dash, etc.).
# Re-runs are idempotent — rows can be added/edited and the script rerun safely.

set -euo pipefail

OWNER="digithings-ai"
PROJECT=1
TSV="scripts/project_fields.tsv"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tsv) TSV="$2"; shift 2 ;;
    --owner) OWNER="$2"; shift 2 ;;
    --project) PROJECT="$2"; shift 2 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

[[ -f "$TSV" ]] || { echo "TSV not found: $TSV" >&2; exit 1; }
command -v jq >/dev/null || { echo "jq required" >&2; exit 1; }
command -v gh >/dev/null || { echo "gh required" >&2; exit 1; }

echo "Fetching project metadata..."
PROJECT_ID=$(gh project view "$PROJECT" --owner "$OWNER" --format json | jq -r .id)
FIELDS_JSON=$(gh project field-list "$PROJECT" --owner "$OWNER" --format json --limit 50)

# Field-id lookups
field_id() { echo "$FIELDS_JSON" | jq -r --arg n "$1" '.fields[] | select(.name==$n) | .id'; }
option_id() {
  echo "$FIELDS_JSON" | jq -r --arg f "$1" --arg o "$2" \
    '.fields[] | select(.name==$f) | .options[] | select(.name==$o) | .id'
}

PHASE_FID=$(field_id Phase)
AREA_FID=$(field_id Area)
KIND_FID=$(field_id Kind)
PRIO_FID=$(field_id Priority)

for f in "$PHASE_FID" "$AREA_FID" "$KIND_FID" "$PRIO_FID"; do
  [[ -n "$f" ]] || { echo "Missing one of Phase/Area/Kind/Priority fields on Project" >&2; exit 1; }
done

echo "Fetching project items..."
ITEMS_JSON=$(gh project item-list "$PROJECT" --owner "$OWNER" --format json --limit 500)

item_id_for_issue() {
  echo "$ITEMS_JSON" | jq -r --argjson n "$1" \
    '.items[] | select(.content.number == $n) | .id' | head -1
}

set_field() {
  local item_id="$1" field_id="$2" opt_id="$3"
  gh project item-edit \
    --id "$item_id" \
    --project-id "$PROJECT_ID" \
    --field-id "$field_id" \
    --single-select-option-id "$opt_id" \
    > /dev/null
}

apply_row() {
  local issue="$1" phase="$2" area="$3" kind="$4" prio="$5"
  local item_id
  item_id=$(item_id_for_issue "$issue")
  if [[ -z "$item_id" ]]; then
    echo "  skip #$issue — not on the Project" >&2
    return
  fi

  local changed=()
  if [[ -n "$phase" ]]; then
    local oid; oid=$(option_id Phase "$phase")
    [[ -z "$oid" ]] && { echo "  #$issue: unknown Phase '$phase'" >&2; } || { set_field "$item_id" "$PHASE_FID" "$oid"; changed+=("Phase"); }
  fi
  if [[ -n "$area" ]]; then
    local oid; oid=$(option_id Area "$area")
    [[ -z "$oid" ]] && { echo "  #$issue: unknown Area '$area'" >&2; } || { set_field "$item_id" "$AREA_FID" "$oid"; changed+=("Area"); }
  fi
  if [[ -n "$kind" ]]; then
    local oid; oid=$(option_id Kind "$kind")
    [[ -z "$oid" ]] && { echo "  #$issue: unknown Kind '$kind'" >&2; } || { set_field "$item_id" "$KIND_FID" "$oid"; changed+=("Kind"); }
  fi
  if [[ -n "$prio" ]]; then
    local oid; oid=$(option_id Priority "$prio")
    [[ -z "$oid" ]] && { echo "  #$issue: unknown Priority '$prio'" >&2; } || { set_field "$item_id" "$PRIO_FID" "$oid"; changed+=("Priority"); }
  fi
  echo "  #$issue ← ${changed[*]:-(no changes)}"
}

echo "Applying $(( $(wc -l < "$TSV") - 1 )) rows from $TSV"
tail -n +2 "$TSV" | while IFS=$'\t' read -r issue phase area kind prio; do
  [[ -z "${issue// }" ]] && continue
  [[ "$issue" =~ ^# ]] && continue
  apply_row "$issue" "${phase:-}" "${area:-}" "${kind:-}" "${prio:-}"
done

echo "Done. View: https://github.com/orgs/$OWNER/projects/$PROJECT"
