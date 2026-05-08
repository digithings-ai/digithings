#!/usr/bin/env bash
# Auto-format files after Claude edits: ruff for Python, ESLint for TS/JS.
source "$(dirname "$0")/_lib.sh"

file="$(hook_field file_path)"
[ -z "$file" ] && exit 0

# Resolve to absolute path so glob patterns and tool invocations are stable
# regardless of whether Claude passed a relative or absolute path.
[[ "$file" != /* ]] && file="$PROJECT_ROOT/$file"

case "$file" in
  *.py)
    ruff_bin="${PROJECT_ROOT}/.venv/bin/ruff"
    if command -v ruff &>/dev/null; then
      ruff format "$file" --quiet 2>/dev/null || true
    elif [ -x "$ruff_bin" ]; then
      "$ruff_bin" format "$file" --quiet 2>/dev/null || true
    fi
    ;;
  *.ts|*.tsx|*.js|*.jsx)
    if [[ "$file" == "$PROJECT_ROOT/frontend/digichat/"* ]]; then
      rel="${file#"$PROJECT_ROOT/frontend/digichat/"}"
      cd "$PROJECT_ROOT/frontend/digichat"
      npx eslint --fix "$rel" --quiet 2>/dev/null || true
    fi
    ;;
esac

exit 0
