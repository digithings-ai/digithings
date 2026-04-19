#!/usr/bin/env bash
# component-router-preflight.sh — Non-blocking reminder to read a component's
# AGENTS.md before editing files inside that component directory.
#
# Fires on Edit/Write/NotebookEdit. If the target path belongs to a known
# component and that component's AGENTS.md does not appear in the recent
# transcript, emits a warning to stderr and exits 0 (never blocks).
#
# Hook payload schema (Claude Code PreToolUse):
#   { "tool_name": "...", "tool_input": { "file_path": "...", ... },
#     "transcript_path": "/path/to/transcript.jsonl" }

source "$(dirname "$0")/_lib.sh"

# ── 1. Resolve target path ─────────────────────────────────────────────────────
path="$(hook_field file_path)"
notebook="$(hook_field notebook_path)"
target="${path:-$notebook}"
[ -z "$target" ] && exit 0

case "$target" in
  /*) abs="$target" ;;
  *)  abs="$PROJECT_ROOT/$target" ;;
esac

# ── 2. Map target to a component ───────────────────────────────────────────────
# Known top-level component directories.
components="digigraph digiquant digisearch digismith digiclaw digibase digikey digichat"

component=""
for comp in $components; do
  comp_prefix="$PROJECT_ROOT/$comp/"
  case "$abs" in
    "$comp_prefix"*)
      component="$comp"
      break
      ;;
  esac
done

# Not inside any component — nothing to check.
[ -z "$component" ] && exit 0

agents_doc="$PROJECT_ROOT/$component/AGENTS.md"

# ── 3. Check recent transcript for a Read of this component's AGENTS.md ────────
transcript="$(_HOOK_INPUT_TRANSCRIPT="$(printf '%s' "$_HOOK_INPUT" | python3 -c "
import json, sys
try:
    print(json.load(sys.stdin).get('transcript_path', ''))
except Exception:
    print('')
")"
echo "$_HOOK_INPUT_TRANSCRIPT")"

if [ -n "$transcript" ] && [ -f "$transcript" ]; then
  # Look for a Read tool call referencing the component's AGENTS.md anywhere
  # in the transcript (simple substring match is sufficient for a warning).
  if python3 -c "
import json, sys

path = sys.argv[1]
with open(sys.argv[2], encoding='utf-8') as fh:
    for line in fh:
        try:
            msg = json.loads(line)
        except Exception:
            continue
        # Look in tool_use messages for Read calls that reference the agents doc.
        if msg.get('type') == 'tool_use' and msg.get('name') == 'Read':
            fp = (msg.get('input') or {}).get('file_path', '')
            if path in fp or fp in path:
                sys.exit(0)   # found it — silent
sys.exit(1)  # not found
" "$agents_doc" "$transcript" 2>/dev/null; then
    exit 0  # AGENTS.md was read — no warning needed
  fi
fi

# ── 4. Emit warning (never block) ──────────────────────────────────────────────
echo "component-router: editing '$component/' but '$component/AGENTS.md' has not been read this session." >&2
echo "  Read it first: Read $agents_doc" >&2
echo "  It contains the pre-flight checklist, rules, and test command for this component." >&2

exit 0
