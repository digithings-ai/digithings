#!/usr/bin/env bash
# Auto-format files after Claude edits: ruff for Python, ESLint for TS/JS.
# Silently skips if the formatter is not installed.
source "$(dirname "$0")/_lib.sh"

file="$(hook_field file_path)"
[ -z "$file" ] && exit 0

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
    cd "$PROJECT_ROOT"
    npx eslint --fix "$file" --quiet 2>/dev/null || true
    ;;
esac

exit 0
