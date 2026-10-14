#!/usr/bin/env bash
# extract-all.sh — run extract-one.sh for R6,R7,R1,R2,R3,R5,R4 (plan migration order,
# repo-split.md section 5 step 2) from SRC into per-repo throwaway clones under OUT_BASE.
# Each extraction is independent (fresh full clone). Writes OUT_BASE/report.tsv.
# Usage: extract-all.sh <SRC_REPO_DIR> <OUT_BASE> [REF]
set -u
SRC="${1:?usage: extract-all.sh <SRC> <OUT_BASE> [REF]}"
OUT="${2:?usage: extract-all.sh <SRC> <OUT_BASE> [REF]}"
REF="${3:-github/develop}"
HERE="$(cd "$(dirname "$0")" && pwd)"
case "$OUT" in "$PAPERCLIP_RUN_SCRATCH_DIR"*|/tmp/*) ;; *) echo "refusing OUT outside scratch/tmp" >&2; exit 2;; esac
/bin/mkdir -p "$OUT"
printf 'repo\tcommits\tfiles\tworktree_kb\tgit_kb\tgitleaks_hits\n' > "$OUT/report.tsv"
for r in r6 r7 r1 r2 r3 r5 r4; do
  "$HERE/extract-one.sh" "$r" "$SRC" "$OUT/$r" "$REF" || { echo "FAILED: $r" >&2; exit 1; }
  cat "$OUT/$r.report.tsv" >> "$OUT/report.tsv"
done
column -t -s "$(printf '\t')" "$OUT/report.tsv"
