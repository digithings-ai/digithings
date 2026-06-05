#!/usr/bin/env bash
# Shared helpers for Claude Code hooks.
# Hooks receive a JSON payload on stdin and must exit:
#   0 — allow
#   2 — block (stderr shown to the model)
#   other non-zero — non-blocking error

set -euo pipefail

# Resolve project root: env override > git toplevel > script-relative fallback
PROJECT_ROOT="${DIGI_PROJECT_ROOT:-}"
if [[ -z "$PROJECT_ROOT" ]]; then
  PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
fi
if [[ -z "$PROJECT_ROOT" ]]; then
  # Script lives at scripts/claude-hooks/ — two levels up is repo root
  PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../" && pwd)"
fi

# Read stdin once and cache it so multiple Python calls don't consume it twice.
_HOOK_INPUT="$(cat)"

# Prefer setup-python's ``python`` on CI over distro ``python3`` (shlex API parity).
hook_python() {
  if [[ -n "${HOOK_PYTHON:-}" ]]; then
    printf '%s\n' "$HOOK_PYTHON"
    return
  fi
  if command -v python >/dev/null 2>&1; then
    command -v python
    return
  fi
  command -v python3
}

HOOK_PY="$(hook_python)"

# Extract a field from the tool_input JSON. Usage: hook_field file_path
hook_field() {
  local key="$1"
  printf '%s' "$_HOOK_INPUT" | "$HOOK_PY" -c "
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
  printf '%s' "$_HOOK_INPUT" | "$HOOK_PY" -c "
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
