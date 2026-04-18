#!/usr/bin/env bash
# fetch_task.sh — Fetch a GitHub Issue spec for agent consumption.
#
# Usage:
#   scripts/fetch_task.sh ISSUE_NUMBER
#   scripts/fetch_task.sh 42
#
# Output: title on first line, then full body (markdown).
# Requires: gh CLI + gh auth login

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

ISSUE="${1:-}"

if [[ -z "$ISSUE" ]]; then
  echo "Usage: scripts/fetch_task.sh ISSUE_NUMBER" >&2
  exit 1
fi

# Strip leading # if provided
ISSUE="${ISSUE#\#}"

if ! command -v gh &>/dev/null; then
  echo "ERROR: gh CLI not found. Install: https://cli.github.com" >&2
  exit 1
fi

# Fetch issue metadata
DATA="$(gh issue view "$ISSUE" --json number,title,body,labels,url,state)"

python3 - <<PYEOF
import json, sys

data = json.loads('''${DATA}''')

number = data['number']
title  = data['title'].removeprefix('[agent] ').strip()
body   = data.get('body', '').strip()
url    = data['url']
state  = data['state']

comp = ''
risk = ''
for lbl in data.get('labels', []):
    name = lbl['name']
    if name.startswith('component:'):
        comp = name.split(':', 1)[1]
    elif name.startswith('risk:'):
        risk = name.split(':', 1)[1]

print(f"=== Task #{number}: {title} ===")
print(f"URL:       {url}")
print(f"State:     {state}")
print(f"Component: {comp or '(not set)'}")
print(f"Risk:      {risk or '(not set)'}")
print()
print(body)
PYEOF
