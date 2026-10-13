#!/usr/bin/env bash
# DIG-2366: regenerate everything derived from baseline/, in one shot.
#
#   patched/{services/documents.js,routes/issues.js}   the patched bytes
#   SHA256SUMS                                         digest of each baseline/patched pair
#   DIG-2366.patch                                     the full production delta
#   DIG-2366.compact.patch                             the same delta, one screen
#
# baseline/ is READ ONLY here, always. It is the byte-for-byte copy of the live
# pinned bytes and the rollback target; nothing in this repo may rewrite it.
#
# Run this after any change to tools/build-patched.py so the artefacts and the
# digests move together in one commit. verify.sh, apply.sh, rollback.sh and
# reapply.sh all read SHA256SUMS, so a stale digest turns a correct tree into an
# UNKNOWN one.
set -euo pipefail

HP="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HP"

FILES=( services/documents.js routes/issues.js )

log() { printf '%s\n' "$*"; }

log "1/3 building patched/ from baseline/"
python3 tools/build-patched.py

log "2/3 SHA256SUMS"
: > SHA256SUMS
for rel in "${FILES[@]}"; do
  printf '%s  baseline/%s\n' "$(shasum -a 256 "baseline/$rel" | awk '{print $1}')" "$rel" >> SHA256SUMS
  printf '%s  patched/%s\n'  "$(shasum -a 256 "patched/$rel"  | awk '{print $1}')" "$rel" >> SHA256SUMS
done
sed 's/^/   /' SHA256SUMS

gen_patch() { # <outfile> <path-prefix>
  local out="$1" prefix="$2" rel
  : > "$out"
  for rel in "${FILES[@]}"; do
    diff -u --label "a/${prefix}${rel}" --label "b/${prefix}${rel}" \
      "baseline/$rel" "patched/$rel" >> "$out" || true
  done
}

log "3/3 patches"
gen_patch DIG-2366.patch         "node_modules/@paperclipai/server/dist/"
gen_patch DIG-2366.compact.patch ""
wc -l DIG-2366.patch DIG-2366.compact.patch | sed 's/^/   /'

log "done. Re-run rehearsal/ and verify.sh before committing."
