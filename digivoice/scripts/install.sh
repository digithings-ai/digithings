#!/usr/bin/env bash
# One-command digivoice install from a git checkout.
#
#   bash digivoice/scripts/install.sh [--auto]
#
# Installs the digivoice CLI as an editable package, then runs
# `digivoice install` (a wizard on a terminal; `--auto` installs the
# default local models with no prompts).
#
# CLI: prefers `uv tool install -e` (no pre-activated venv). Falls back to
# `uv pip install -e` inside an active or repo `.venv`, then plain pip.
#
# SAFETY: never rsync this checkout's hammerspoon/ over
#   ~/Library/Application Support/digivoice/hammerspoon
# This script leaves any existing copy there untouched; `digivoice update`
# refreshes the adapter.
#
# If uv/pip is missing: install uv (https://docs.astral.sh/uv/), then re-run.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

INSTALL_ARGS=()
for arg in "$@"; do
  case "$arg" in
    --auto) INSTALL_ARGS+=(--auto) ;;
    -h|--help)
      echo "usage: bash digivoice/scripts/install.sh [--auto]"
      exit 0
      ;;
    *)
      echo "digivoice install: unknown argument: $arg" >&2
      exit 2
      ;;
  esac
done

APP_SUPPORT_HS="${HOME}/Library/Application Support/digivoice/hammerspoon"
if [[ -d "$APP_SUPPORT_HS" && ! -L "$APP_SUPPORT_HS" ]]; then
  echo "digivoice install: Application Support hammerspoon copy present at:"
  echo "  $APP_SUPPORT_HS"
  echo "Leaving it alone (no rsync)."
fi

install_editable_cli() {
  local pkg="$ROOT/digivoice"
  if command -v uv >/dev/null 2>&1; then
    if uv tool install -e "$pkg"; then
      return 0
    fi
    echo "digivoice install: uv tool install failed; trying uv pip in a venv" >&2
    if [[ -z "${VIRTUAL_ENV:-}" ]]; then
      uv venv "$ROOT/.venv"
      # shellcheck disable=SC1091
      source "$ROOT/.venv/bin/activate"
    fi
    uv pip install -e "$pkg"
    return 0
  fi
  if command -v pip >/dev/null 2>&1; then
    pip install -e "$pkg"
    return 0
  fi
  echo "digivoice install: uv or pip required." >&2
  echo "Install uv from https://docs.astral.sh/uv/ then re-run this script." >&2
  return 2
}

install_editable_cli

if command -v digivoice >/dev/null 2>&1; then
  digivoice install ${INSTALL_ARGS[@]+"${INSTALL_ARGS[@]}"}
else
  PYTHONPATH="$ROOT/digivoice/src" python3 -m digivoice install ${INSTALL_ARGS[@]+"${INSTALL_ARGS[@]}"}
fi

echo "Smoke: digivoice doctor && digivoice reload && digivoice banner show"
echo "Reinstall: bash digivoice/scripts/install.sh"
