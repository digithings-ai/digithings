#!/usr/bin/env bash
# Block shell-redirect writes to protected paths from Bash tool calls.
# Intercepts: >, >>, tee, sed -i, mv, cp targeting protected paths.
# Keep protected paths / branch logic in sync with protected-path-guard.sh.
source "$(dirname "$0")/_lib.sh"

cmd="$(hook_field command)"
[ -z "$cmd" ] && exit 0

# Human override (intentionally not documented to agents).
# REM-127 test harness sets DIGI_FORCE_GUARD_TEST=1 so org-wide DIGI_ALLOW_PROTECTED
# cannot weaken deny-path assertions on GHA runners.
if [ "${DIGI_FORCE_GUARD_TEST:-0}" != "1" ] && [ "${DIGI_ALLOW_PROTECTED:-0}" = "1" ]; then
  exit 0
fi

# Protected path patterns — keep in sync with protected-path-guard.sh.
# No trailing slash: normpath strips it, so comparisons use "$p"|"$p/"* below.
protected=(
  "$PROJECT_ROOT/SECURITY.md"
  "$PROJECT_ROOT/.github/workflows"
  "$PROJECT_ROOT/docs/scoring"
  "$PROJECT_ROOT/config/litellm.yaml"
  "$PROJECT_ROOT/projects"
)

# Live-trading path regex (always block, even on task/* branches).
live_trading_regex='(live_trading|execute_trade|place_order|/live[/.])'

# Fast pre-check: skip the Python parse for commands with no write-implying tokens.
# This avoids spawning python3 on every git/pytest/ruff invocation.
case "$cmd" in
  *">"*|*" tee "*|*"|tee "*|*"tee "*|*"sed -i"*|*" mv "*|*" cp "*|"mv "*|"cp "*) ;;
  *) exit 0 ;;
esac

# Extract write-target paths from the Bash command using Python's shlex tokenizer.
# posix=False keeps quoted characters intact (e.g. grep ">" is NOT a redirect).
# The command is passed via env var to avoid stdin conflicts with _lib.sh's cache.
# Returns one resolved absolute path per line; empty output = no write targets found.
write_targets="$(BASH_GUARD_CMD="$cmd" BASH_GUARD_ROOT="$PROJECT_ROOT" \
  "$HOOK_PY" -c "
import sys, os, shlex

raw = os.environ.get('BASH_GUARD_CMD', '')
project_root = os.environ.get('BASH_GUARD_ROOT', '')

if not raw:
    sys.exit(0)

try:
    lex = shlex.shlex(raw, posix=False, punctuation_chars=True)
    lex.whitespace = ' \t\r\n'
    tokens = list(lex)
except Exception as exc:
    import sys
    print(f'bash-guard parse error: {exc!r}', file=sys.stderr)
    sys.exit(0)

def strip_quotes(s):
    '''Remove a single layer of matching outer quotes from a token.'''
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('\"', \"'\"):
        return s[1:-1]
    return s

targets = []
i = 0
while i < len(tokens):
    tok = tokens[i]

    # Output redirects: > >> &> >|  and fd redirects like 2>
    if tok in ('>', '>>', '&>', '>|') or (len(tok) > 1 and tok[-1] == '>' and tok[:-1].isdigit()):
        j = i + 1
        if j < len(tokens) and tokens[j] not in ('>', '>>', '|', '&', ';'):
            targets.append(strip_quotes(tokens[j]))
        i = j + 1
        continue

    # tee [-a] [--] path ...
    if tok == 'tee':
        j = i + 1
        while j < len(tokens) and strip_quotes(tokens[j]).startswith('-'):
            j += 1
        if j < len(tokens) and tokens[j] not in ('|', ';', '&', '>', '>>'):
            targets.append(strip_quotes(tokens[j]))
        i = j + 1
        continue

    # sed -i [SCRIPT] file  (any -i / -ibak form)
    if tok == 'sed':
        j = i + 1
        saw_i = False
        script_seen = False
        while j < len(tokens):
            t = tokens[j]
            if t in (';', '&', '|'):
                break
            st = strip_quotes(t)
            if st.startswith('-') and 'i' in st:
                saw_i = True
                j += 1
                # BSD sed -i '' — empty-quoted token is the backup suffix, not the script
                if j < len(tokens) and strip_quotes(tokens[j]) == '':
                    j += 1
                continue
            if saw_i and not script_seen and not st.startswith('-'):
                script_seen = True  # This token is the sed script expression
                j += 1
                continue
            if saw_i and script_seen and not st.startswith('-'):
                targets.append(st)  # This is the file argument
                break
            j += 1
        i = j + 1
        continue

    # mv src dest  /  cp src dest — last positional arg is the destination
    if tok in ('mv', 'cp'):
        j = i + 1
        args = []
        while j < len(tokens) and tokens[j] not in (';', '&', '|'):
            st = strip_quotes(tokens[j])
            if not st.startswith('-'):
                args.append(st)
            j += 1
        if args:
            targets.append(args[-1])
        i = j + 1
        continue

    i += 1

# Resolve each target to an absolute path.
for t in targets:
    if not t or t.startswith('/dev/') or t.startswith('/proc/'):
        continue
    if os.path.isabs(t):
        resolved = os.path.normpath(t)
    else:
        resolved = os.path.normpath(os.path.join(project_root, t))
    print(resolved)
")"

# If no write targets detected, nothing to guard.
[ -z "$write_targets" ] && exit 0

# Branch check deferred until here — only needed when write targets exist.
branch="$(git -C "$PROJECT_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '')"

# Evaluate each write target against protected paths.
while IFS= read -r target; do
  [ -z "$target" ] && continue

  # Always allow writes to /tmp/.
  case "$target" in
    /tmp/*) continue ;;
  esac

  # Always allow writes outside PROJECT_ROOT.
  case "$target" in
    "$PROJECT_ROOT"*) ;;
    *) continue ;;
  esac

  # confidential projects/ dir — always block (exact dir or any file inside).
  case "$target" in
    "$PROJECT_ROOT/projects"|"$PROJECT_ROOT/projects/"*)
      deny "projects/ is confidential — Bash writes to '$target' are blocked." ;;
  esac

  # Live-trading paths — always block (even on task/* branches).
  if [[ "$target" =~ $live_trading_regex ]]; then
    deny "Bash write to live-trading path '$target' is blocked. \
Live-trading code requires explicit human approval; set DIGI_ALLOW_PROTECTED=1 in a human session."
  fi

  # Protected paths — block unless on a task branch.
  # Match exact directory target ("$p") and any path inside ("$p/"*).
  for p in "${protected[@]}"; do
    case "$target" in
      "$p"|"$p/"*)
        if [[ ! "$branch" =~ ^task/[0-9]+- ]]; then
          deny "Bash write to protected path '$target' is blocked. \
Writes allowed only from a task branch (task/N-slug) or with explicit human approval. Current branch: '$branch'."
        fi
        ;;
    esac
  done

done <<< "$write_targets"

exit 0
