#!/usr/bin/env bash
# list_tasks.sh — List open agent-task GitHub Issues.
#
# Usage:
#   scripts/list_tasks.sh                         # all open agent-task issues
#   scripts/list_tasks.sh --component digisearch  # filter by component
#   scripts/list_tasks.sh --status closed         # show closed tasks
#   scripts/list_tasks.sh --json                  # machine-readable JSON
#
# Requires: gh CLI + gh auth login

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

COMPONENT=""
STATUS="open"
JSON_MODE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --component) COMPONENT="$2"; shift 2 ;;
    --status)    STATUS="$2";    shift 2 ;;
    --json)      JSON_MODE=true; shift   ;;
    -h|--help)
      sed -n '2,10p' "$0" | sed 's/^# \?//'
      exit 0
      ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

if ! command -v gh &>/dev/null; then
  echo "ERROR: gh CLI not found. Install: https://cli.github.com" >&2
  exit 1
fi

# Build label filter
LABEL="agent-task"
if [[ -n "$COMPONENT" ]]; then
  LABEL="${LABEL},component:${COMPONENT}"
fi

# Fetch issues as JSON
RAW="$(gh issue list \
  --label "$LABEL" \
  --state "$STATUS" \
  --json number,title,labels,url,createdAt \
  --limit 100)"

if $JSON_MODE; then
  echo "$RAW"
  exit 0
fi

# Parse and display as plain table
COUNT="$(echo "$RAW" | python3 -c "import json,sys; data=json.load(sys.stdin); print(len(data))")"

if [[ "$COUNT" == "0" ]]; then
  echo "No ${STATUS} agent-task issues found${COMPONENT:+ for component:${COMPONENT}}."
  exit 0
fi

echo ""
echo "Open agent tasks${COMPONENT:+ [${COMPONENT}]} (${COUNT}):"
echo "──────────────────────────────────────────────────────────────────────────"
printf "%-6s  %-14s  %-8s  %-42s  %s\n" "#" "COMPONENT" "RISK" "TITLE" "URL"
echo "──────────────────────────────────────────────────────────────────────────"

echo "$RAW" | python3 - <<'PYEOF'
import json, sys

data = json.load(sys.stdin)
for issue in data:
    num = f"#{issue['number']}"
    title = issue['title'].removeprefix('[agent] ').removeprefix('[agent]').strip()
    title = title[:42] + '…' if len(title) > 42 else title
    url = issue['url']

    comp = ''
    risk = ''
    for lbl in issue.get('labels', []):
        name = lbl['name']
        if name.startswith('component:'):
            comp = name.split(':', 1)[1]
        elif name.startswith('risk:'):
            risk = name.split(':', 1)[1]

    print(f"{num:<6}  {comp:<14}  {risk:<8}  {title:<42}  {url}")
PYEOF

echo ""
echo "Run 'make task ISSUE=N' to execute a task."
echo "Run 'scripts/fetch_task.sh N' to read a task spec."
