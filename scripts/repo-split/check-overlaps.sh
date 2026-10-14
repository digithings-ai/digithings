#!/usr/bin/env bash
# check-overlaps.sh — expand every move-list path to a file list at REF and report
# files claimed by more than one repo. Known overlaps (overlaps-known.txt) are
# reported as KNOWN; anything else fails the run (exit 1).
# Usage: check-overlaps.sh [REF]   (default: github/develop)
set -u
REF="${1:-github/develop}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ML="$HERE/move-lists"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
drop_covers() { # <file> — true if file is under an r5.drop path
  local f="$1" d
  while IFS= read -r d; do
    case "$d" in ''|'#'*) continue;; esac
    case "$f" in "$d"|"$d"/*) return 0;; esac
  done < "$ML/r5.drop"
  return 1
}
expand() { # <repo> — write expanded file list to $TMP/<repo>.files
  local repo="$1"
  local out="$TMP/$repo.files"
  local p
  : > "$out"
  while IFS= read -r p; do
    case "$p" in ''|'#'*) continue;; esac
    git ls-tree -r --name-only "$REF" -- "$p" >> "$out" 2>/dev/null || true
  done < "$ML/$repo.paths"
  sort -u "$out" -o "$out"
}
for r in r1 r2 r3 r4 r5 r6 r7; do expand "$r"; done
# pairwise intersections
NEW=0
for a in r1 r2 r3 r4 r5 r6 r7; do
  for b in r1 r2 r3 r4 r5 r6 r7; do
    [ "$a" \< "$b" ] || continue
    comm -12 "$TMP/$a.files" "$TMP/$b.files" > "$TMP/ov-$a-$b.txt" || true
    while IFS= read -r f; do
      [ -n "$f" ] || continue
      if grep -qxF "$a $b $f" "$ML/overlaps-known.txt" 2>/dev/null || grep -qxF "$b $a $f" "$ML/overlaps-known.txt" 2>/dev/null; then
        echo "KNOWN overlap $a/$b: $f"
      elif [ "$a" = r5 ] && drop_covers "$f"; then
        echo "EXPECTED overlap $a/$b (removed by r5.drop second pass): $f"
      else
        echo "NEW overlap $a/$b: $f"
        NEW=$((NEW+1))
      fi
    done < "$TMP/ov-$a-$b.txt"
  done
done
for r in r1 r2 r3 r4 r5 r6 r7; do echo "files $r: $(wc -l < "$TMP/$r.files")"; done
if [ "$NEW" -gt 0 ]; then echo "FAIL: $NEW unlisted overlap(s)"; exit 1; fi
echo "OK: no unlisted overlaps"
