#!/usr/bin/env bash
#
# DIG-2366 reapply check.
#
# The hotpatch lives in the paperclip install directory, and `paperclipai
# update` (or any reinstall) rewrites installs/npm/<version> from the tarball,
# which silently deletes the patched bytes. This script is the tripwire for
# that. It NEVER writes to the install directory. It only answers one
# question: is the patch still reapplicable to the bytes that are installed
# right now?
#
# Three outcomes, all safe:
#   0  already applied, or reapplicable — run apply.sh
#   3  anchor drift: the installed file no longer has the lines this patch
#      was written against. Nothing was applied. The patch must be re-derived
#      and re-reviewed by a human; it will not be applied blind.
#   4  the patch re-derives cleanly but produces DIFFERENT bytes than the
#      reviewed patch. Something else changed under it. Nothing was applied.
#
set -euo pipefail
# shellcheck source=lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

ALLOW_DRIFT=0
while [ $# -gt 0 ]; do
    case "$1" in
        --allow-version-drift) ALLOW_DRIFT=1; shift ;;
        -h|--help) sed -n '3,20p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) bad "unknown argument: $1"; exit 2 ;;
    esac
done

INSTALL_DIR="${INSTALL_DIR}"
DIST="$INSTALL_DIR/node_modules/@paperclipai/server/dist"

log "reapply check for the DIG-2366 hotpatch"
log "  install dir : $INSTALL_DIR"
log "  live dist   : $DIST"

# The recorded digests must still describe the files on disk before any of the
# words below mean anything.
assert_shas_recorded

# ---------------------------------------------------------------- 1. version
VERSION="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["version"])' "$INSTALL_JSON" 2>/dev/null || echo unknown)"
if [ "$VERSION" != "$PINNED_VERSION" ]; then
    if [ "$ALLOW_DRIFT" = 1 ]; then
        bad "WARNING: installed version is $VERSION, the patch was built against $PINNED_VERSION"
        bad "WARNING: continuing because --allow-version-drift was passed; a drift verdict is expected"
    else
        bad "installed version is $VERSION, not the pinned $PINNED_VERSION"
        bad "the pinned install was replaced. Re-run with --allow-version-drift to see"
        bad "whether the patch still applies to the new bytes. NOTHING WAS APPLIED."
        exit 3
    fi
fi

# ------------------------------------------------------- 2. classify live bytes
declare -a STATE=()
NEEDS=0
for rel in "${FILES[@]}"; do
    live="$(sha "$DIST/$rel")"
    if [ "$live" = "$(expected_sha patched "$rel")" ]; then
        STATE+=("patched"); log "  $rel  PATCHED  ($live)"
    elif [ "$live" = "$(expected_sha baseline "$rel")" ]; then
        STATE+=("baseline"); NEEDS=$((NEEDS + 1))
        log "  $rel  BASELINE ($live)  <- patch is missing"
    else
        STATE+=("unknown"); NEEDS=$((NEEDS + 1))
        log "  $rel  UNKNOWN  ($live)  <- not the baseline, not the patch"
    fi
done

if [ "$NEEDS" = 0 ]; then
    ok "both files already carry the patch. Nothing to do."
    exit 0
fi

# ------------------------------------------- 3. re-derive against installed bytes
# Scratch copies only. baseline/ and patched/ are the reviewed artefacts and are
# never written to by this script.
SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/dig2366-reapply.XXXXXX")"
trap 'rm -rf "$SCRATCH"' EXIT
mkdir -p "$SCRATCH/baseline" "$SCRATCH/patched"
for rel in "${FILES[@]}"; do
    mkdir -p "$SCRATCH/baseline/$(dirname "$rel")"
    cp "$DIST/$rel" "$SCRATCH/baseline/$rel"
done

log "re-deriving the patch against the installed bytes (anchors are checked, not assumed)"
set +e
DIG2366_BASELINE="$SCRATCH/baseline" DIG2366_PATCHED="$SCRATCH/patched" \
    python3 "$HP_DIR/tools/build-patched.py" >"$SCRATCH/build.log" 2>&1
BUILD_RC=$?
set -e
if [ "$BUILD_RC" != 0 ]; then
    bad "anchor drift — the patch no longer applies to the installed bytes"
    sed -n '1,12p' "$SCRATCH/build.log" | sed 's/^/    /'
    bad "NOTHING WAS APPLIED. This hotpatch must be re-derived against the new"
    bad "version and re-reviewed before it goes anywhere near the install dir."
    exit 3
fi

# ------------------------------------------------ 4. does it mean the same thing?
DRIFT=0
for rel in "${FILES[@]}"; do
    fresh="$(sha "$SCRATCH/patched/$rel")"
    reviewed="$(expected_sha patched "$rel")"
    if [ "$fresh" = "$reviewed" ]; then
        ok "  $rel  re-derives to the reviewed bytes exactly ($fresh)"
    else
        bad "  $rel  re-derives to $fresh but the reviewed patch is $reviewed"
        DRIFT=1
    fi
done

if [ "$DRIFT" = 1 ]; then
    bad "the patch re-applies cleanly but means something different now"
    bad "NOTHING WAS APPLIED. A human must re-read the diff before this is used."
    exit 4
fi

ok "the patch still applies cleanly to the installed bytes and produces the"
ok "reviewed result. To land it:"
printf '\n    %s/apply.sh && %s/verify.sh\n\n' "$HP_DIR" "$HP_DIR"
log "reapply.sh never writes to the install directory. apply.sh does."