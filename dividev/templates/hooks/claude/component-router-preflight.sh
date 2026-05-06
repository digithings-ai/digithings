#!/usr/bin/env bash
# Non-blocking reminder to read a component's AGENTS.md before editing files
# inside that component directory.
#
# Fires on Edit/Write/NotebookEdit. If the target path belongs to a known
# component and that component's AGENTS.md hasn't been read this session,
# emits a warning to stderr and exits 0 (never blocks).
source "$(dirname "$0")/_lib.sh"

path="$(hook_field file_path)"
notebook="$(hook_field notebook_path)"
target="${path:-$notebook}"
[ -z "$target" ] && exit 0

case "$target" in
  /*) abs="$target" ;;
  *)  abs="$PROJECT_ROOT/$target" ;;
esac

# Known component directories — edit this list to match your project.
# The installer writes the component names from dividev.yml here.
components="{{COMPONENTS_SPACE}}"

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

[ -z "$component" ] && exit 0

agents_doc="$PROJECT_ROOT/$component/AGENTS.md"

transcript="$(_HOOK_INPUT_TRANSCRIPT="$(printf '%s' "$_HOOK_INPUT" | python3 -c "
import json, sys
try:
    print(json.load(sys.stdin).get('transcript_path', ''))
except Exception:
    print('')
")"
echo "$_HOOK_INPUT_TRANSCRIPT")"

if [ -n "$transcript" ] && [ -f "$transcript" ]; then
  if python3 -c "
import json, sys

path = sys.argv[1]
with open(sys.argv[2], encoding='utf-8') as fh:
    for line in fh:
        try:
            msg = json.loads(line)
        except Exception:
            continue
        if msg.get('type') == 'tool_use' and msg.get('name') == 'Read':
            fp = (msg.get('input') or {}).get('file_path', '')
            if path in fp or fp in path:
                sys.exit(0)
sys.exit(1)
" "$agents_doc" "$transcript" 2>/dev/null; then
    exit 0
  fi
fi

echo "component-router: editing '$component/' but '$component/AGENTS.md' has not been read this session." >&2
echo "  Read it first: Read $agents_doc" >&2
echo "  It contains the pre-flight checklist, rules, and test command for this component." >&2

exit 0
