#!/usr/bin/env bash
# extract-one.sh — history-preserving extraction of ONE repo into a THROWAWAY clone.
# Dry runs only: DEST must be inside $PAPERCLIP_RUN_SCRATCH_DIR (or /tmp). Never pushes.
# Usage: extract-one.sh <rN> <SRC_REPO_DIR> <DEST_DIR> [REF]  (rN = any id with a move-lists/<id>.paths file; r7 held)
# Report (stdout + <DEST>.report.tsv): commits, files, content bytes, history bytes (floor), gitleaks findings.
set -u
REPO_ID="${1:?usage: extract-one.sh <rN> <SRC> <DEST> [REF]}"
SRC="${2:?usage: extract-one.sh <rN> <SRC> <DEST> [REF]}"
DEST="${3:?usage: extract-one.sh <rN> <SRC> <DEST> [REF]}"
REF="${4:-github/develop}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ML="$HERE/move-lists"
[ -f "$ML/$REPO_ID.paths" ] || { echo "no move list: $REPO_ID (r7 is on HOLD)" >&2; exit 2; }
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
# Sizes are LOGICAL bytes (immune to hardlinks/promisor packs): CONTENT_BYTES = HEAD blobs;
# HIST_BYTES = reachable objects present locally (a floor; missing lazy blobs are skipped).
# Isolate one branch: filter-repo rewrites every ref, keeping all objects alive.
# A real split carries a single branch, so drop everything else, then repack.
TIP=$(git -C "$DEST" rev-parse HEAD)
git -C "$DEST" for-each-ref --format='delete %(refname) %(objectname)' | git -C "$DEST" update-ref --stdin 2>/dev/null || true
git -C "$DEST" update-ref refs/heads/extracted "$TIP"
git -C "$DEST" symbolic-ref HEAD refs/heads/extracted
git -C "$DEST" remote remove origin 2>/dev/null || true
git -C "$DEST" repack -a -d -f -q 2>/dev/null || true
git -C "$DEST" prune --expire=now 2>/dev/null || true
git -C "$DEST" gc --prune=now --quiet 2>/dev/null || true

COMMITS=$(git -C "$DEST" rev-list --count HEAD)
FILES=$(git -C "$DEST" ls-files | wc -l | tr -d ' ')
CONTENT_BYTES=$(git -C "$DEST" ls-files -s | python3 -c "import sys,subprocess; blobs=[l.split()[1] for l in sys.stdin]; out=subprocess.run(['git','cat-file','--batch-check=%(objectsize)'],input=''.join(b+'\n' for b in blobs),capture_output=True,text=True,cwd='$DEST'.replace(chr(39),'')); print(sum(int(x) for x in out.stdout.split() if x.isdigit()))")
HIST_BYTES=$(git -C "$DEST" rev-list --objects --all | git -C "$DEST" cat-file --batch-check='%(objectsize)' | python3 -c "import sys;print(sum(int(x) for x in sys.stdin.read().split() if x.isdigit()))")
if gitleaks detect --source "$DEST" --report-format json --report-path "$DEST.gitleaks.json" --exit-code 0 >/dev/null 2>"$DEST.gitleaks.log"; then
  LEAKS=$(python3 -c "import json;print(len(json.load(open('$DEST.gitleaks.json'))))" 2>/dev/null || echo ?) 
else
  LEAKS=$(python3 -c "import json;print(len(json.load(open('$DEST.gitleaks.json'))))" 2>/dev/null || echo ?)
fi
printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$REPO_ID" "$COMMITS" "$FILES" "$CONTENT_BYTES" "$HIST_BYTES" "$LEAKS" | tee "$DEST.report.tsv"
echo "report: $DEST.report.tsv"
