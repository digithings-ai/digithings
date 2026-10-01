#!/usr/bin/env bash
# One-command digivoice install from a git checkout.
#
#   bash digivoice/scripts/install.sh [--skip-models]
#
# Wires: editable CLI (uv/pip) + ~/.hammerspoon/digivoice symlink + models dir
# (+ optional ggml-base.en.bin fetch).
#
# SAFETY — never rsync this checkout's hammerspoon/ over
#   ~/Library/Application Support/digivoice/hammerspoon
# That unguarded copy wiped the #4965 banner tip. The Python installer only
# symlinks ~/.hammerspoon/digivoice and SHA-guards any App Support copy
# (refuses unless dest/.digivoice-tip matches DIGIVOICE_TIP_SHA).
#
# Two-step if uv/pip is missing: install uv (https://docs.astral.sh/uv/), then
# re-run this script.

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

if command -v uv >/dev/null 2>&1; then
  uv pip install -e "$ROOT/digivoice"
elif command -v pip >/dev/null 2>&1; then
  pip install -e "$ROOT/digivoice"
else
  echo "digivoice install: uv or pip required." >&2
  echo "Two-step: install uv from https://docs.astral.sh/uv/ then re-run this script." >&2
  exit 2
fi

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
