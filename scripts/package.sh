#!/usr/bin/env bash
# Bundle Digi for distribution (one-click packaging). Phase 3.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
DATE=$(date +%Y%m%d)
OUT="digi-bundle-${DATE}.tar.gz"
echo "Creating $OUT from $ROOT"
tar --exclude='.git' --exclude='.venv' --exclude='.env' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='.pytest_cache' --exclude='*.egg-info' --exclude='node_modules' \
    --exclude='digiquant/results' --exclude='digi-bundle-*.tar.gz' \
    -czf "$OUT" .
echo "Done: $OUT"
