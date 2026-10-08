#!/usr/bin/env bash
#
# DIG-2366: prove reapply.sh / apply.sh / verify.sh / rollback.sh actually
# catch the states they claim to catch.
#
# A green run of the tools on good input proves nothing unless the bad inputs
# also fail. This script drives each tool against a CLONE of the install tree
# (DIG2366_CLI_ROOT), never the live one, and asserts the exit code.
#
# Cases:
#   1  already patched          -> reapply exits 0, verify passes
#   2  baseline, missing patch  -> reapply exits 0 and says safe, apply then verify
#   3  anchor drift             -> reapply exits 3, nothing applied
#   4  silent third-party edit  -> reapply exits 4, nothing applied
#   5  pinned version replaced  -> reapply exits 3 without --allow-version-drift
#   6  tampered SHA256SUMS      -> every tool refuses before doing anything
#   7  rollback restores bytes  -> live shas equal baseline again
#   8  verify.sh state modes    -> "not applied" is a state, not a failure; a
#                                 half-applied tree IS a failure and is named
#
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HP="$HERE/.."
CLONE_ROOT="$HERE/../rehearsal/selftest-store/cli"
SRC_DIST="$HOME/.paperclip/cli/installs/npm/2026.1001.0/node_modules/@paperclipai/server/dist"
DST_DIST="$CLONE_ROOT/installs/npm/2026.1001.0/node_modules/@paperclipai/server/dist"

PASS=0
FAIL=0
check() { # check <label> <expected-rc> <actual-rc>
    if [ "$2" = "$3" ]; then
        printf '  \033[32mok\033[0m    %-52s rc=%s\n' "$1" "$3"; PASS=$((PASS + 1))
    else
        printf '  \033[31mFAIL\033[0m  %-52s want rc=%s got rc=%s\n' "$1" "$2" "$3"; FAIL=$((FAIL + 1))
    fi
}

reset_clone() {
    rm -rf "$CLONE_ROOT"
    mkdir -p "$CLONE_ROOT/installs/npm/2026.1001.0/node_modules/@paperclipai/server"
    # a real writable copy, never a symlink to the live tree
    cp -Rc "$SRC_DIST" "$DST_DIST"
    ln -s "installs/npm/2026.1001.0" "$CLONE_ROOT/current"
    cat >"$CLONE_ROOT/install.json" <<JSON
{"schemaVersion":1,"source":"npm","version":"2026.1001.0","channel":"pinned","payloadPath":"$CLONE_ROOT/installs/npm/2026.1001.0","previous":[]}
JSON
}

sha()      { shasum -a 256 "$1" | awk '{print $1}'; }
sha_of()   { shasum -a 256 "$DST_DIST/$1" | awk '{print $1}'; }
want_sha() { awk -v k="$1/$2" '$2 == k {print $1}' "$HP/SHA256SUMS"; }

run_reapply() { DIG2366_CLI_ROOT="$CLONE_ROOT" "$HP/reapply.sh" "$@" >"$HERE/selftest-last.log" 2>&1; }
live_untouched() {
    local rel
    for rel in services/documents.js routes/issues.js; do
        [ "$(sha_of "$rel")" = "$(want_sha baseline "$rel")" ] || return 1
    done
    return 0
}

printf '\n=== DIG-2366 tool self-test (all cases run on a clone) ===\n'

# ------------------------------------------------------------------ case 1 & 2
printf '\n-- case 1: install already carries the patch\n'
reset_clone
cp "$HP/patched/services/documents.js" "$DST_DIST/services/documents.js"
cp "$HP/patched/routes/issues.js"      "$DST_DIST/routes/issues.js"
set +e; run_reapply; rc=$?; set -e
check "reapply: already applied" 0 "$rc"
grep -q "already carry the patch" "$HERE/selftest-last.log" && printf '  \033[32mok\033[0m    and says so\n' || printf '  \033[31mFAIL\033[0m  but did not say so\n'

printf '\n-- case 2: install is at baseline, patch missing\n'
reset_clone
set +e; run_reapply; rc=$?; set -e
check "reapply: safe to reapply" 0 "$rc"
grep -q "re-derives to the reviewed bytes exactly" "$HERE/selftest-last.log" && printf '  \033[32mok\033[0m    and proves the re-derivation\n' || printf '  \033[31mFAIL\033[0m  but did not prove the re-derivation\n'
set +e; DIG2366_CLI_ROOT="$CLONE_ROOT" "$HP/apply.sh" >"$HERE/selftest-apply.log" 2>&1; rc=$?; set -e
check "apply: lands the patch" 0 "$rc"
set +e; DIG2366_CLI_ROOT="$CLONE_ROOT" "$HP/verify.sh" >"$HERE/selftest-verify.log" 2>&1; rc=$?; set -e
check "verify: passes on patched bytes" 0 "$rc"

# -------------------------------------------------------------------- case 3
printf '\n-- case 3: upstream moved, the anchors no longer hold\n'
reset_clone
# insert two lines above the documents.js import block so every line number shifts
python3 - "$DST_DIST/services/documents.js" <<'PY'
import sys, pathlib
p = pathlib.Path(sys.argv[1]); t = p.read_text()
t = t.replace('import { isSystemIssueDocumentKey, issueDocumentKeySchema }',
              '// upstream added a comment\n// and another one\nimport { isSystemIssueDocumentKey, issueDocumentKeySchema }', 1)
p.write_text(t)
assert 'upstream added a comment' in t, "case 3 mutation did not apply"
PY
DRIFT_SHA=$(sha_of services/documents.js)
if [ "$DRIFT_SHA" = "$(want_sha baseline services/documents.js)" ]; then
    printf '  \033[31mFAIL\033[0m  the case 3 mutation did not change the file\n'; FAIL=$((FAIL + 1))
else
    printf '  \033[32mok\033[0m    the case 3 mutation really changed the file\n'
fi
set +e; run_reapply; rc=$?; set -e
check "reapply: anchor drift refuses" 3 "$rc"
grep -q "anchor drift" "$HERE/selftest-last.log" && printf '  \033[32mok\033[0m    and names the reason\n' || printf '  \033[31mFAIL\033[0m  but did not name the reason\n'
[ "$(sha_of services/documents.js)" = "$DRIFT_SHA" ] && printf '  \033[32mok\033[0m    and wrote nothing to the install tree\n' || printf '  \033[31mFAIL\033[0m  AND MODIFIED THE INSTALL TREE\n'

# -------------------------------------------------------------------- case 4
printf '\n-- case 4: a third party edited the file, anchors still line up\n'
reset_clone
# Append AFTER the anchor at line 9014, so the anchor the patch is written
# against still holds exactly, the builder succeeds, and the result differs from
# the reviewed bytes. That is the only shape that exercises verdict 4.
BEFORE=$(shasum -a 256 "$DST_DIST/routes/issues.js" | awk '{print $1}')
printf '\n// a third party appended this line\n' >> "$DST_DIST/routes/issues.js"
AFTER=$(shasum -a 256 "$DST_DIST/routes/issues.js" | awk '{print $1}')
if [ "$BEFORE" = "$AFTER" ]; then
    printf '  \033[31mFAIL\033[0m  the case 4 mutation did not change the file at all\n'
    FAIL=$((FAIL + 1))
else
    printf '  \033[32mok\033[0m    the case 4 mutation really changed the file\n'
fi
set +e; run_reapply; rc=$?; set -e
check "reapply: differing re-derivation refuses" 4 "$rc"
grep -q "means something different now" "$HERE/selftest-last.log" && printf '  \033[32mok\033[0m    and says a human must re-read the diff\n' || printf '  \033[31mFAIL\033[0m  but did not flag the drift\n'

# -------------------------------------------------------------------- case 5
printf '\n-- case 5: the pinned install was replaced by an update\n'
reset_clone
python3 - "$CLONE_ROOT/install.json" <<'PY'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1]); d = json.loads(p.read_text())
d["version"] = "2026.1005.0"
d["payloadPath"] = d["payloadPath"].replace("2026.1001.0", "2026.1005.0")
p.write_text(json.dumps(d))
PY
set +e; run_reapply; rc=$?; set -e
check "reapply: version drift refuses" 3 "$rc"
grep -q "NOTHING WAS APPLIED" "$HERE/selftest-last.log" && printf '  \033[32mok\033[0m    and says nothing was applied\n' || printf '  \033[31mFAIL\033[0m  but did not say nothing was applied\n'

# -------------------------------------------------------------------- case 6
printf '\n-- case 6: SHA256SUMS no longer describes the files on disk\n'
reset_clone
cp "$HP/SHA256SUMS" "$HERE/SHA256SUMS.orig"
cp "$HP/patched/routes/issues.js" "$HP/patched/routes/issues.js.selftest"
printf '\n' >> "$HP/patched/routes/issues.js"
if [ "$(sha "$HP/patched/routes/issues.js")" = "$(want_sha patched routes/issues.js)" ]; then
    printf '  \033[31mFAIL\033[0m  the case 6 tamper did not change the file\n'; FAIL=$((FAIL + 1))
else
    printf '  \033[32mok\033[0m    the case 6 tamper really changed the file\n'
fi
set +e; run_reapply; rc=$?; set -e
check "reapply: refuses on a tampered tree" 1 "$rc"
mv "$HP/patched/routes/issues.js.selftest" "$HP/patched/routes/issues.js"
if [ "$(sha "$HP/patched/routes/issues.js")" != "$(want_sha patched routes/issues.js)" ]; then
    printf '  \033[31mFAIL\033[0m  the tampered file was not restored byte for byte\n'; FAIL=$((FAIL + 1))
else
    printf '  \033[32mok\033[0m    the tampered file was restored byte for byte\n'
fi
set +e; run_reapply; rc=$?; set -e
check "reapply: passes again once restored" 0 "$rc"

# -------------------------------------------------------------------- case 7
printf '\n-- case 7: rollback restores the original bytes\n'
reset_clone
cp "$HP/patched/services/documents.js" "$DST_DIST/services/documents.js"
cp "$HP/patched/routes/issues.js"      "$DST_DIST/routes/issues.js"
set +e; DIG2366_CLI_ROOT="$CLONE_ROOT" "$HP/rollback.sh" >"$HERE/selftest-rollback.log" 2>&1; rc=$?; set -e
check "rollback: runs clean" 0 "$rc"
live_untouched && printf '  \033[32mok\033[0m    both files back to the baseline digest\n' || printf '  \033[31mFAIL\033[0m  files are NOT back to the baseline digest\n'

# -------------------------------------------------------------------- case 8
# verify.sh runs in three places in the window card - before apply, after
# apply, after rollback - so two of the three sanctioned states are "not
# applied". If verify treated that as a failure it would cry wolf in its own
# happy path. The state that genuinely must fail is a HALF-APPLIED tree: one
# file patched, one not. That is the mistake that would otherwise sail
# through a post-apply check.
printf '\n-- case 8: verify.sh state modes\n'
printf '  8a, "not applied" is a coherent state, not a failure\n'
reset_clone
set +e; DIG2366_CLI_ROOT="$CLONE_ROOT" "$HP/verify.sh" --expect baseline >"$HERE/selftest-verify-base.log" 2>&1; rc=$?; set -e
check "verify: baseline tree passes" 0 "$rc"
grep -q "state = baseline" "$HERE/selftest-verify-base.log" && printf '  \033[32mok\033[0m    and names the state\n' || printf '  \033[31mFAIL\033[0m  but did not name the state\n'

printf '  8b, a fully patched tree passes and can be gated on\n'
reset_clone
cp "$HP/patched/services/documents.js" "$DST_DIST/services/documents.js"
cp "$HP/patched/routes/issues.js"      "$DST_DIST/routes/issues.js"
set +e; DIG2366_CLI_ROOT="$CLONE_ROOT" "$HP/verify.sh" --expect patched >"$HERE/selftest-verify-patched.log" 2>&1; rc=$?; set -e
check "verify: patched tree passes" 0 "$rc"
grep -q "state = patched" "$HERE/selftest-verify-patched.log" && printf '  \033[32mok\033[0m    and names the state\n' || printf '  \033[31mFAIL\033[0m  but did not name the state\n'

printf '  8c, --expect gates: the same patched tree fails a baseline assertion\n'
set +e; DIG2366_CLI_ROOT="$CLONE_ROOT" "$HP/verify.sh" --expect baseline >"$HERE/selftest-verify-mismatch.log" 2>&1; rc=$?; set -e
check "verify: wrong --expect is refused" 1 "$rc"

printf '  8d, HALF-APPLIED: one file patched, one not. This must FAIL and be named.\n'
reset_clone
cp "$HP/patched/services/documents.js" "$DST_DIST/services/documents.js"
# routes/issues.js deliberately left at baseline
set +e; DIG2366_CLI_ROOT="$CLONE_ROOT" "$HP/verify.sh" >"$HERE/selftest-verify-half.log" 2>&1; rc=$?; set -e
check "verify: half-applied tree fails" 1 "$rc"
grep -q "HALF-APPLIED" "$HERE/selftest-verify-half.log" && printf '  \033[32mok\033[0m    and names the reason\n' || printf '  \033[31mFAIL\033[0m  but did not name the reason\n'

rm -f "$HERE/selftest-last.log" "$HERE/selftest-apply.log" "$HERE/selftest-verify.log" "$HERE/selftest-rollback.log" "$HERE/SHA256SUMS.orig" \
      "$HERE/selftest-verify-base.log" "$HERE/selftest-verify-patched.log" "$HERE/selftest-verify-mismatch.log" "$HERE/selftest-verify-half.log"
rm -rf "$CLONE_ROOT"

printf '\n=== self-test: %d passed, %d failed ===\n' "$PASS" "$FAIL"
[ "$FAIL" = 0 ]