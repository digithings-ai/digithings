#!/usr/bin/env bash
# Block shell-redirect writes to protected paths from Bash tool calls.
# Intercepts: >, >>, tee, sed -i, mv, cp targeting protected paths.
# Keep protected paths in sync with protected-path-guard.sh.
source "$(dirname "$0")/_lib.sh"

cmd="$(hook_field command)"
[ -z "$cmd" ] && exit 0

if [ "${DIGIDEV_ALLOW_PROTECTED:-0}" = "1" ]; then
  exit 0
fi

protected=(
  {{PROTECTED_PATHS_BASH}}
)

always_block_regex='{{LIVE_TRADING_REGEX}}'

# Fast pre-check: skip Python parse for commands with no write-implying tokens.
case "$cmd" in
  *">"*|*" tee "*|*"|tee "*|*"tee "*|*"sed -i"*|*" mv "*|*" cp "*|"mv "*|"cp "*) ;;
  *) exit 0 ;;
esac

write_targets="$(BASH_GUARD_CMD="$cmd" BASH_GUARD_ROOT="$PROJECT_ROOT" \
  python3 -c "
import sys, os, shlex

raw = os.environ.get('BASH_GUARD_CMD', '')
project_root = os.environ.get('BASH_GUARD_ROOT', '')

if not raw:
    sys.exit(0)

try:
    lex = shlex.shlex(raw, posix=False, punctuation_chars=True)
    lex.whitespace = ' \t\r\n'
    tokens = list(lex)
except Exception:
    sys.exit(0)

def strip_quotes(s):
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('\"', \"'\"):
        return s[1:-1]
    return s

targets = []
i = 0
while i < len(tokens):
    tok = tokens[i]

    if tok in ('>', '>>', '&>', '>|') or (len(tok) > 1 and tok[-1] == '>' and tok[:-1].isdigit()):
        j = i + 1
        if j < len(tokens) and tokens[j] not in ('>', '>>', '|', '&', ';'):
            targets.append(strip_quotes(tokens[j]))
        i = j + 1
        continue

    if tok == 'tee':
        j = i + 1
        while j < len(tokens) and strip_quotes(tokens[j]).startswith('-'):
            j += 1
        if j < len(tokens) and tokens[j] not in ('|', ';', '&', '>', '>>'):
            targets.append(strip_quotes(tokens[j]))
        i = j + 1
        continue

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
                if j < len(tokens) and strip_quotes(tokens[j]) == '':
                    j += 1
                continue
            if saw_i and not script_seen and not st.startswith('-'):
                script_seen = True
                j += 1
                continue
            if saw_i and script_seen and not st.startswith('-'):
                targets.append(st)
                break
            j += 1
        i = j + 1
        continue

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

for t in targets:
    if not t or t.startswith('/dev/') or t.startswith('/proc/'):
        continue
    if os.path.isabs(t):
        resolved = os.path.normpath(t)
    else:
        resolved = os.path.normpath(os.path.join(project_root, t))
    print(resolved)
")"

[ -z "$write_targets" ] && exit 0

branch="$(git -C "$PROJECT_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '')"

while IFS= read -r target; do
  [ -z "$target" ] && continue

  case "$target" in
    /tmp/*) continue ;;
  esac

  case "$target" in
    "$PROJECT_ROOT"*) ;;
    *) continue ;;
  esac

  if [[ -n "$always_block_regex" ]] && [[ "$target" =~ $always_block_regex ]]; then
    deny "Bash write to sensitive path '$target' is blocked. \
This path requires explicit human approval; set ${ALLOW_VAR}=1 in a human session."
  fi

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
