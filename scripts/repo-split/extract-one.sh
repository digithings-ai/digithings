#!/usr/bin/env bash
# extract-one.sh — history-preserving extraction of ONE repo into a THROWAWAY clone.
# Dry runs only: DEST must be inside $PAPERCLIP_RUN_SCRATCH_DIR (or /tmp). Never pushes.
# Usage: extract-one.sh <r1..r7> <SRC_REPO_DIR> <DEST_DIR> [REF]
# Report (stdout + <DEST>.report.tsv): commits, files, worktree bytes, git bytes, gitleaks findings.
set -u
REPO_ID="${1:?usage: extract-one.sh <r1..r7> <SRC> <DEST> [REF]}"
SRC="${2:?usage: extract-one.sh <r1..r7> <SRC> <DEST> [REF]}"
DEST="${3:?usage: extract-one.sh <r1..r7> <SRC> <DEST> [REF]}"
REF="${4:-github/develop}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ML="$HERE/move-lists"
case "$REPO_ID" in r1|r2|r3|r4|r5|r6|r7) ;; *) echo "bad repo id: $REPO_ID" >&2; exit 2;; esac
case "$DEST" in "$PAPERCLIP_RUN_SCRATCH_DIR"*|/tmp/*) ;; *) echo "refusing DEST outside scratch/tmp: $DEST" >&2; exit 2;; esac
command -v git-filter-repo >/dev/null || { echo "git-filter-repo missing" >&2; exit 2; }
command -v gitleaks >/dev/null || { echo "gitleaks missing" >&2; exit 2; }
[ -e "$DEST" ] && { echo "refusing: DEST exists: $DEST" >&2; exit 2; }
ARGS=()
while IFS= read -r p; do
  case "$p" in ''|'#'*) continue;; esac
  ARGS+=(--path "$p")
done < "$ML/$REPO_ID.paths"
[ "${#ARGS[@]}" -gt 0 ] || { echo "empty move list: $REPO_ID" >&2; exit 2; }
SHA=$(git -C "$SRC" rev-parse --verify "$REF^{commit}" 2>/dev/null) || { echo "bad REF: $REF" >&2; exit 2; }
echo "cloning $SRC @ $SHA -> $DEST (local hardlinks, full history) ..."
git clone -q "$SRC" "$DEST" 2>&1 | tail -2  # local: hardlinks, source untouched; filter-repo only reads shared objects
git -C "$DEST" checkout -q "$SHA" || { echo "checkout $SHA failed" >&2; exit 1; }
echo "filter-repo keep-pass: ${#ARGS[@]} path args ..."
git -C "$DEST" filter-repo --force "${ARGS[@]}" >/dev/null 2>"$DEST.filter-repo.log" || { tail -5 "$DEST.filter-repo.log"; exit 1; }
if [ -f "$ML/$REPO_ID.drop" ]; then
  DARGS=()
  while IFS= read -r p; do
    case "$p" in ''|'#'*) continue;; esac
    DARGS+=(--path "$p")
  done < "$ML/$REPO_ID.drop"
  if [ "${#DARGS[@]}" -gt 0 ]; then
    echo "filter-repo drop-pass: ${#DARGS[@]} path args ..."
    git -C "$DEST" filter-repo --force "${DARGS[@]}" --invert >/dev/null 2>>"$DEST.filter-repo.log" || { tail -5 "$DEST.filter-repo.log"; exit 1; }
  fi
fi
COMMITS=$(git -C "$DEST" rev-list --count HEAD)
FILES=$(git -C "$DEST" ls-files | wc -l | tr -d ' ')
WT_BYTES=$(du -sk "$DEST" | cut -f1)
GIT_BYTES=$(du -sk "$DEST/.git" | cut -f1)
if gitleaks detect --source "$DEST" --report-format json --report-path "$DEST.gitleaks.json" --exit-code 0 >/dev/null 2>"$DEST.gitleaks.log"; then
  LEAKS=$(python3 -c "import json;print(len(json.load(open('$DEST.gitleaks.json'))))" 2>/dev/null || echo ?) 
else
  LEAKS=$(python3 -c "import json;print(len(json.load(open('$DEST.gitleaks.json'))))" 2>/dev/null || echo ?)
fi
printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$REPO_ID" "$COMMITS" "$FILES" "$WT_BYTES" "$GIT_BYTES" "$LEAKS" | tee "$DEST.report.tsv"
echo "report: $DEST.report.tsv"
