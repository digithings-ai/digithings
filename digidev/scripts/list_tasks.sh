#!/usr/bin/env bash
# digidev list_tasks.sh — list open agent-task issues
# Usage: scripts/list_tasks.sh [--component <name>]
set -euo pipefail

COMPONENT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --component) COMPONENT="$2"; shift 2 ;;
    *) shift ;;
  esac
done

# Detect issue tracker
ISSUE_TRACKER="github"
if [[ -f "agents.yml" ]]; then
  ISSUE_TRACKER=$(python3 -c "
import re
try:
    import yaml
    cfg = yaml.safe_load(open('agents.yml'))
    print(cfg.get('issue_tracker', 'github'))
except ImportError:
    txt = open('agents.yml').read()
    m = re.search(r'issue_tracker:\s*(\S+)', txt)
    print(m.group(1) if m else 'github')
" 2>/dev/null || echo "github")
fi

echo ""
echo "Open agent-task issues${COMPONENT:+ — component: $COMPONENT}"
echo ""

case "$ISSUE_TRACKER" in
  jira)
    echo "Issue tracker: Jira"
    if ! command -v curl &>/dev/null || [[ -z "${JIRA_BASE_URL:-}" || -z "${JIRA_EMAIL:-}" || -z "${JIRA_API_TOKEN:-}" ]]; then
      echo "  Set JIRA_BASE_URL, JIRA_EMAIL, and JIRA_API_TOKEN to list Jira issues."
      echo "  Or open: ${JIRA_BASE_URL:-your-jira-instance}/issues/?filter=agent-task"
      exit 0
    fi
    JQL="project = ${JIRA_PROJECT:-} AND labels = agent-task AND status != Done"
    [[ -n "$COMPONENT" ]] && JQL="$JQL AND labels = component:$COMPONENT"
    curl -s -u "${JIRA_EMAIL}:${JIRA_API_TOKEN}" \
      "${JIRA_BASE_URL}/rest/api/2/search?jql=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$JQL")&fields=summary,status,labels&maxResults=50" \
      | python3 -c "
import sys, json
d = json.load(sys.stdin)
for issue in d.get('issues', []):
    key = issue['key']
    title = issue['fields']['summary']
    status = issue['fields']['status']['name']
    print(f'  {key}  {title}  [{status}]')
"
    ;;
  linear)
    echo "Issue tracker: Linear"
    if command -v linear &>/dev/null; then
      linear issue list --filter "label:agent-task" 2>/dev/null || true
    else
      echo "  Install the Linear CLI or use the Linear MCP server to list issues."
      echo "  See: digidev/integrations/linear/README.md"
    fi
    ;;
  *)
    # GitHub Issues
    if ! command -v gh &>/dev/null; then
      echo "Error: gh CLI required. Install: https://cli.github.com/"
      exit 1
    fi

    LABELS="agent-task"
    [[ -n "$COMPONENT" ]] && LABELS="${LABELS},component:${COMPONENT}"

    gh issue list \
      --label "$LABELS" \
      --state open \
      --json number,title,labels,assignees,updatedAt \
      --jq '
        .[] |
        "  #\(.number)  \(.title)\n" +
        "    labels:   \([.labels[].name] | join(", "))\n" +
        "    assignee: \(if .assignees | length > 0 then [.assignees[].login] | join(", ") else "unassigned" end)\n" +
        "    updated:  \(.updatedAt[:10])\n"
      ' 2>/dev/null \
      || gh issue list --label "agent-task" --state open
    ;;
esac
echo ""
