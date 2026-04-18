#!/usr/bin/env bash
# Shared helpers for Claude Code hooks.
# Hooks receive a JSON payload on stdin and must exit:
#   0 — allow
#   2 — block (stderr shown to the model)
#   other non-zero — non-blocking error

set -euo pipefail

PROJECT_ROOT="${DIGI_PROJECT_ROOT:-/Users/chrisstefan/Code/digithings}"

# Read stdin once and cache it so multiple python3 calls don't consume it twice.
_HOOK_INPUT="$(cat)"

# Extract a field from the tool_input JSON. Usage: hook_field file_path
hook_field() {
  local key="$1"
  printf '%s' "$_HOOK_INPUT" | python3 -c "
import json, sys
try:
    payload = json.load(sys.stdin)
except Exception:
    sys.exit(0)
ti = payload.get('tool_input') or {}
val = ti.get('$key', '')
if isinstance(val, (dict, list)):
    import json as _j
    print(_j.dumps(val))
else:
    print(val)
"
}

# Extract the tool name from the hook payload.
hook_tool() {
  printf '%s' "$_HOOK_INPUT" | python3 -c "
import json, sys
try:
    print(json.load(sys.stdin).get('tool_name', ''))
except Exception:
    print('')
"
}

deny() {
  echo "guardrail: $*" >&2
  exit 2
}
