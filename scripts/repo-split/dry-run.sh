#!/usr/bin/env bash
# dry-run.sh — validate every move-list path exists at REF. No clone, no rewrite.
# Usage: dry-run.sh [REF] [REPO_DIR]   (defaults: github/develop, .)
# Exit 1 on any missing path. Prints per-repo file counts.
set -u
REF="${1:-github/develop}"
REPO="${2:-.}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ML="$HERE/move-lists"
FAIL=0
for r in r1 r2 r3 r4 r5 r6 r7; do
  n=0; miss=0
  while IFS= read -r p; do
    case "$p" in ''|'#'*) continue;; esac
    if git -C "$REPO" ls-tree -r --name-only "$REF" -- "$p" 2>/dev/null | grep -q .; then
      n=$((n+1))
    else
      echo "MISSING $r: $p"; miss=$((miss+1)); FAIL=1
    fi
  done < "$ML/$r.paths"
  # count expanded files
  files=0
  while IFS= read -r p; do
    case "$p" in ''|'#'*) continue;; esac
    c=$(git -C "$REPO" ls-tree -r --name-only "$REF" -- "$p" 2>/dev/null | wc -l)
    files=$((files+c))
  done < "$ML/$r.paths"
  echo "$r: $n move-list entries ok, $miss missing, ~$files files"
done
# r5.drop entries must exist inside the kept tree (they are removed post-extraction)
while IFS= read -r p; do
  case "$p" in ''|'#'*) continue;; esac
  git -C "$REPO" ls-tree -r --name-only "$REF" -- "$p" 2>/dev/null | grep -q . || { echo "MISSING r5.drop: $p"; FAIL=1; }
done < "$ML/r5.drop"
[ "$FAIL" -eq 0 ] && echo "DRY-RUN OK at $REF" || { echo "DRY-RUN FAIL"; exit 1; }
