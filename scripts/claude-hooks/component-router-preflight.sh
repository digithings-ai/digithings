#!/usr/bin/env bash
# Non-blocking preflight: warn on the first edit to a component whose AGENTS.md
# has not yet been read in this session. Exit 0 always; writes to stderr only.

source "$(dirname "$0")/_lib.sh"

# ── Extract target path ────────────────────────────────────────────────────────
path="$(hook_field file_path)"
notebook="$(hook_field notebook_path)"
target="${path:-$notebook}"
[ -z "$target" ] && exit 0

# ── Resolve path relative to project root ─────────────────────────────────────
# Strip absolute project root prefix to get the repo-relative path.
if [[ "$target" == "$PROJECT_ROOT/"* ]]; then
  rel="${target#$PROJECT_ROOT/}"
else
  rel="$target"
fi

# ── Map repo-relative path to a component ─────────────────────────────────────
# Known components with AGENTS.md files.
components=(
  digigraph
  digiquant
  digisearch
  digichat
  digikey
  digismith
  digiclaw
  digibase
)

component=""
for c in "${components[@]}"; do
  if [[ "$rel" == "$c/"* ]]; then
    component="$c"
    break
  fi
done

# Not a component file — nothing to check.
[ -z "$component" ] && exit 0

# ── Session-scoped marker directory ───────────────────────────────────────────
# Use session_id from the hook payload if available; otherwise fall back to a
# hash of PROJECT_ROOT so parallel sessions don't collide.
session_id="$(printf '%s' "$_HOOK_INPUT" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get('session_id', ''))
except Exception:
    print('')
" 2>/dev/null)"

if [ -z "$session_id" ]; then
  # Stable fallback: PID-based so at minimum it's per-process.
  session_id="pid-$$"
fi

marker_dir="/tmp/digi-component-preflight-${session_id}"
mkdir -p "$marker_dir"
marker_file="${marker_dir}/${component}"

# ── Warn on first edit to this component ──────────────────────────────────────
if [ ! -f "$marker_file" ]; then
  agents_doc="${PROJECT_ROOT}/${component}/AGENTS.md"
  echo "note: first edit to '${component}/' in this session — consider reading ${component}/AGENTS.md before proceeding." >&2
  if [ -f "$agents_doc" ]; then
    echo "      Path: ${agents_doc}" >&2
  fi
  touch "$marker_file"
fi

exit 0
