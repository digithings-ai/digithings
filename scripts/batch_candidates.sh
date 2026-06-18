#!/usr/bin/env bash
# batch_candidates.sh — group open agent-task issues by phase+area for parallel execution.
#
# Usage:
#   bash scripts/batch_candidates.sh
#   bash scripts/batch_candidates.sh --phase "Phase 3 — Domain unification"
#   bash scripts/batch_candidates.sh --area DigiGraph
#   bash scripts/batch_candidates.sh --phase "Phase 2 — Hardening" --area Cross-cutting

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TSV="$SCRIPT_DIR/project_fields.tsv"

# ── Argument parsing ──────────────────────────────────────────────────────────
FILTER_PHASE=""
FILTER_AREA=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --phase)
      FILTER_PHASE="$2"
      shift 2
      ;;
    --area)
      FILTER_AREA="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      echo "Usage: $0 [--phase <phase>] [--area <area>]" >&2
      exit 1
      ;;
  esac
done

# ── Dependency checks ─────────────────────────────────────────────────────────
if ! command -v gh &>/dev/null; then
  echo "ERROR: gh CLI not found. Install from https://cli.github.com/" >&2
  exit 1
fi

if [[ ! -f "$TSV" ]]; then
  echo "WARNING: $TSV not found — phase/area/kind data unavailable. Exiting." >&2
  exit 0
fi

if ! command -v python3 &>/dev/null; then
  echo "ERROR: python3 not found." >&2
  exit 1
fi

# ── Fetch open agent-task issues ─────────────────────────────────────────────
ISSUES_JSON=$(gh issue list \
  --label agent-task \
  --state open \
  --limit 500 \
  --json number,title,body,labels 2>/dev/null) || {
  echo "ERROR: gh issue list failed. Are you authenticated? Run: gh auth login" >&2
  exit 1
}

# Write JSON to a temp file so Python can read it cleanly
TMPFILE=$(mktemp /tmp/batch_candidates_XXXXXX.json)
trap 'rm -f "$TMPFILE"' EXIT
printf '%s' "$ISSUES_JSON" > "$TMPFILE"

# ── Python join + grouping logic ──────────────────────────────────────────────
# Pass args explicitly so the heredoc is single-quoted (no shell interpolation).
python3 - "$TSV" "$FILTER_PHASE" "$FILTER_AREA" "$TMPFILE" <<'PYEOF'
import sys
import csv
import json
import re

tsv_path, filter_phase, filter_area, issues_file = sys.argv[1:]


def load_tsv(path):
    """Return {issue_number: row_dict} from the project_fields TSV."""
    rows = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            try:
                rows[int(row["issue"])] = row
            except (ValueError, KeyError):
                continue
    return rows


def has_cross_refs(issue, other_numbers):
    """Return True if issue body references any other issue in the same group."""
    refs = {int(m) for m in re.findall(r"#(\d+)", issue["body"])}
    return bool(refs & other_numbers)


def group_label(group_issues, group_numbers):
    """Return batchability label: 'batchable' or 'review before batching'."""
    if len(group_issues) > 4:
        return "review before batching"
    if any(i["model"] == "opus" for i in group_issues):
        return "review before batching"
    for issue in group_issues:
        if has_cross_refs(issue, group_numbers - {issue["number"]}):
            return "review before batching"
    return "batchable"


tsv_rows = load_tsv(tsv_path)

with open(issues_file, encoding="utf-8") as f:
    issues = json.load(f)

if not issues:
    print("No open agent-task issues found.")
    sys.exit(0)

enriched = []
skipped = 0
for issue in issues:
    num = issue["number"]
    if num not in tsv_rows:
        skipped += 1
        continue
    row = tsv_rows[num]
    phase = row.get("phase", "Unknown")
    area = row.get("area", "Unknown")
    # model column is optional; default to sonnet when absent or blank
    model = (row.get("model") or "sonnet").strip() or "sonnet"

    if filter_phase and phase != filter_phase:
        continue
    if filter_area and area != filter_area:
        continue

    enriched.append({
        "number": num,
        "title": issue["title"],
        "body": issue.get("body") or "",
        "phase": phase,
        "area": area,
        "model": model,
    })

if skipped > 0:
    print(f"(Note: {skipped} open agent-task issue(s) had no TSV entry and were skipped)", file=sys.stderr)

if not enriched:
    print("No matching issues after filters.")
    sys.exit(0)

groups = {}
for issue in enriched:
    groups.setdefault((issue["phase"], issue["area"]), []).append(issue)

group_numbers = {key: {i["number"] for i in lst} for key, lst in groups.items()}

total_issues = 0
for key in sorted(groups.keys()):
    phase, area = key
    group_issues = groups[key]
    nums = group_numbers[key]
    n = len(group_issues)
    label = group_label(group_issues, nums)

    print(f"=== {phase} / {area} ({n} issue{'s' if n != 1 else ''} — {label}) ===")
    for issue in sorted(group_issues, key=lambda x: x["number"]):
        print(f"  #{issue['number']:<4} [{issue['model']}]  {issue['title']}")
    print()
    total_issues += n

total_groups = len(groups)
print(
    f"{total_issues} open agent-task issue{'s' if total_issues != 1 else ''} "
    f"across {total_groups} group{'s' if total_groups != 1 else ''}"
)
PYEOF
