#!/usr/bin/env bash
# digidev create_issue.sh — create a structured agent-task issue
# Usage: scripts/create_issue.sh
set -euo pipefail

# ── Read config ───────────────────────────────────────────────────────────────
ISSUE_TRACKER="github"
COMPONENTS=""
if [[ -f "agents.yml" ]]; then
  eval "$(python3 - <<'PY'
import re
try:
    import yaml
    cfg = yaml.safe_load(open("agents.yml"))
    tracker = cfg.get("issue_tracker", "github")
    comps = cfg.get("components", [])
    names = [c.get("name", c) if isinstance(c, dict) else str(c) for c in (comps if isinstance(comps, list) else [])]
    print(f"ISSUE_TRACKER='{tracker}'")
    print(f"COMPONENTS='{' '.join(names)}'")
except ImportError:
    txt = open("agents.yml").read()
    m = re.search(r"issue_tracker:\s*(\S+)", txt)
    print(f"ISSUE_TRACKER='{m.group(1) if m else 'github'}'")
    names = re.findall(r"^\s+- name:\s*(\S+)", txt, re.MULTILINE)
    print(f"COMPONENTS='{' '.join(names)}'")
PY
)"
fi

# ── Collect fields interactively ──────────────────────────────────────────────
echo ""
echo "Create a new agent-task issue"
echo ""

read -rp "Title: " TITLE
[[ -z "$TITLE" ]] && { echo "Title required."; exit 1; }

echo ""
echo "Execution tier:"
echo "  1) copilot  — housekeeping, clear-rule tasks (auto-assigned)"
echo "  2) cursor   — clear-spec, single-component (auto-assigned)"
echo "  3) claude   — judgment, cross-module, sensitive (local only)"
read -rp "Tier [1/2/3]: " TIER_CHOICE
case "$TIER_CHOICE" in
  1) TIER="copilot" ;;
  3) TIER="claude"  ;;
  *) TIER="cursor"  ;;
esac

echo ""
echo "Risk level:"
echo "  1) low   — no user data, no auth, no live systems"
echo "  2) med   — touches shared state or external APIs"
echo "  3) high  — auth, secrets, live-trading, cross-service"
read -rp "Risk [1/2/3]: " RISK_CHOICE
case "$RISK_CHOICE" in
  1) RISK="low"  ;;
  3) RISK="high" ;;
  *) RISK="med"  ;;
esac

echo ""
if [[ -n "$COMPONENTS" ]]; then
  echo "Components: $COMPONENTS"
  read -rp "Component (or leave blank): " COMPONENT
else
  read -rp "Component name: " COMPONENT
fi

echo ""
read -rp "Goal (one sentence): " GOAL

echo ""
echo "Acceptance criteria (one per line, empty line to finish):"
CRITERIA=""
while true; do
  read -rp "  - " LINE
  [[ -z "$LINE" ]] && break
  CRITERIA="${CRITERIA}- [ ] ${LINE}\n"
done
CRITERIA="${CRITERIA}- [ ] Tests pass for changed code"

# ── Create issue ──────────────────────────────────────────────────────────────
BODY=$(printf "### Goal\n%s\n\n### Acceptance criteria\n%b\n\n### Execution tier\n%s\n\n### Risk\n%s\n" \
  "$GOAL" "$CRITERIA" "$TIER" "$RISK")

case "$ISSUE_TRACKER" in
  jira)
    echo ""
    echo "Creating Jira issue..."
    if [[ -z "${JIRA_BASE_URL:-}" || -z "${JIRA_EMAIL:-}" || -z "${JIRA_API_TOKEN:-}" ]]; then
      echo "Error: set JIRA_BASE_URL, JIRA_EMAIL, and JIRA_API_TOKEN."
      exit 1
    fi
    PAYLOAD=$(python3 -c "
import json, sys
print(json.dumps({
    'fields': {
        'project': {'key': '${JIRA_PROJECT:-}'},
        'summary': sys.argv[1],
        'description': sys.argv[2],
        'issuetype': {'name': 'Task'},
        'labels': ['agent-task', 'exec:${TIER}', 'risk:${RISK}']
    }
}))" "$TITLE" "$BODY")
    curl -s -X POST \
      -u "${JIRA_EMAIL}:${JIRA_API_TOKEN}" \
      -H "Content-Type: application/json" \
      -d "$PAYLOAD" \
      "${JIRA_BASE_URL}/rest/api/2/issue" \
      | python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"Created: {d.get('key','?')} — {d.get('self','?')}\")"
    ;;
  linear)
    echo ""
    echo "Creating Linear issue..."
    if command -v linear &>/dev/null; then
      linear issue create --title "$TITLE" --description "$BODY" \
        --label "agent-task,exec:${TIER}" 2>/dev/null \
        || echo "Linear CLI error — use the Linear MCP server or web UI."
    else
      echo "Install the Linear CLI or use the Linear MCP to create this issue:"
      echo "  Title: $TITLE"
      echo "  Labels: agent-task, exec:${TIER}, risk:${RISK}"
      echo "  Body:"
      echo "$BODY"
    fi
    ;;
  *)
    # GitHub Issues
    if ! command -v gh &>/dev/null; then
      echo "Error: gh CLI required. Install: https://cli.github.com/"
      exit 1
    fi
    LABELS="agent-task,exec:${TIER},risk:${RISK}"
    [[ -n "$COMPONENT" ]] && LABELS="${LABELS},component:${COMPONENT}"

    ISSUE_URL=$(gh issue create \
      --title "[agent] $TITLE" \
      --body "$BODY" \
      --label "$LABELS" 2>/dev/null)
    echo ""
    echo "✓ Created: $ISSUE_URL"
    echo ""
    echo "  exec:$TIER  →  $(
      case "$TIER" in
        copilot) echo "Copilot will be auto-assigned via GitHub Actions." ;;
        cursor)  echo "Open in Cursor and start with the task command." ;;
        claude)  echo "Run: make task ISSUE=<number>" ;;
      esac)"
    ;;
esac
echo ""
