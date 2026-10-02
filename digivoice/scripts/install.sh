#!/usr/bin/env bash
# One-command digivoice install from a git checkout.
#
#   bash digivoice/scripts/install.sh [--skip-models]
#
# Wires: editable CLI + ~/.hammerspoon/digivoice symlink + models dir
# (+ optional ggml-base.en.bin fetch).
#
# CLI: prefers `uv tool install -e` (no pre-activated venv). Falls back to
# `uv pip install -e` only inside an active or repo `.venv`, then plain pip.
#
# SAFETY — never rsync this checkout's hammerspoon/ over
#   ~/Library/Application Support/digivoice/hammerspoon
# That unguarded copy wiped the #4965 banner tip. The Python installer only
# symlinks ~/.hammerspoon/digivoice and SHA-guards any App Support copy
# (refuses unless dest/.digivoice-tip matches DIGIVOICE_TIP_SHA).
#
# Two-step if uv/pip is missing: install uv (https://docs.astral.sh/uv/), then
# re-run this script. Mac proof path: uv tool install -e ./digivoice, then
# digivoice install --fetch-models.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if ! git -C "$ROOT" rev-parse HEAD >/dev/null 2>&1; then
  echo "digivoice install: not a git checkout; cannot record tip SHA" >&2
  exit 1
fi

DIGIVOICE_TIP_SHA="$(git -C "$ROOT" rev-parse HEAD)"
export DIGIVOICE_TIP_SHA
export DIGIVOICE_HAMMERSPOON_SOURCE="$ROOT/digivoice/hammerspoon"

APP_SUPPORT_HS="${HOME}/Library/Application Support/digivoice/hammerspoon"
if [[ -d "$APP_SUPPORT_HS" && ! -L "$APP_SUPPORT_HS" ]]; then
  echo "digivoice install: Application Support hammerspoon copy present at:"
  echo "  $APP_SUPPORT_HS"
  echo "Leaving it alone (no rsync). Live adapter = ~/.hammerspoon/digivoice symlink."
fi

SKIP_MODELS=0
for arg in "$@"; do
  case "$arg" in
    --skip-models) SKIP_MODELS=1 ;;
    -h|--help)
      echo "usage: bash digivoice/scripts/install.sh [--skip-models]"
      echo "tip SHA is recorded via git rev-parse HEAD ($DIGIVOICE_TIP_SHA)."
      exit 0
      ;;
  esac
done

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
  echo "Two-step: install uv from https://docs.astral.sh/uv/ then re-run this script." >&2
  return 2
}

install_editable_cli

FETCH=(--fetch-models)
if [[ "$SKIP_MODELS" -eq 1 ]]; then
  FETCH=()
fi

if command -v digivoice >/dev/null 2>&1; then
  digivoice install "${FETCH[@]}"
else
  PYTHONPATH="$ROOT/digivoice/src" python3 -m digivoice install "${FETCH[@]}"
fi

echo "tip SHA: $DIGIVOICE_TIP_SHA"
echo "Smoke: digivoice doctor && digivoice reload && digivoice banner show"
echo "Quit teardown: TUI Quit (not closing Terminal). Uninstall: digivoice uninstall"
echo "Reinstall: bash digivoice/scripts/install.sh"
