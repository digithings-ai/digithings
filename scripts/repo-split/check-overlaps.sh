#!/usr/bin/env bash
# check-overlaps.sh — expand every move-list to a file list at REF (minus that
# repo's .drop second-pass removals) and FAIL on any file claimed twice.
# No whitelist: each file has exactly one owner (rev-3 send-back).
# Usage: check-overlaps.sh [REF]   (default: github/develop)
set -u
REF="${1:-github/develop}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ML="$HERE/move-lists"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
REPOS=""
for f in "$ML"/r?.paths; do REPOS="$REPOS $(basename "$f" .paths)"; done
expand() { # <repo>
  local repo="$1"
  local out="$TMP/$repo.files"
  local p
  : > "$out"
  while IFS= read -r p; do
    case "$p" in ''|'#'*) continue;; esac
    git ls-tree -r --name-only "$REF" -- "$p" >> "$out" 2>/dev/null || true
  done < "$ML/$repo.paths"
  if [ -f "$ML/$repo.drop" ]; then
    while IFS= read -r p; do
      case "$p" in ''|'#'*) continue;; esac
      git ls-tree -r --name-only "$REF" -- "$p" >> "$TMP/$repo.dropfiles" 2>/dev/null || true
    done < "$ML/$repo.drop"
    sort -u "$TMP/$repo.dropfiles" -o "$TMP/$repo.dropfiles" 2>/dev/null || true
    sort -u "$out" -o "$out"
    comm -23 "$out" "$TMP/$repo.dropfiles" > "$out.net" || true
    mv "$out.net" "$out"
  else
    sort -u "$out" -o "$out"
  fi
}
for r in $REPOS; do expand "$r"; done
NEW=0
for a in $REPOS; do
  for b in $REPOS; do
    [ "$a" \< "$b" ] || continue
    comm -12 "$TMP/$a.files" "$TMP/$b.files" > "$TMP/ov-$a-$b.txt" || true
    while IFS= read -r f; do
      [ -n "$f" ] || continue
      echo "DOUBLE-CLAIM $a/$b: $f"
      NEW=$((NEW+1))
    done < "$TMP/ov-$a-$b.txt"
  done
done
for r in $REPOS; do echo "files $r (net of .drop): $(wc -l < "$TMP/$r.files")"; done
if [ "$NEW" -gt 0 ]; then echo "FAIL: $NEW double-claimed file(s)"; exit 1; fi
echo "OK: every file has exactly one owner"
