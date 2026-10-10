#!/usr/bin/env bash
# Proves the OCC rollout's allowed-diff guard can actually fail, and that it
# fails for the right reason (DIG-2779).
#
# The guard lives inside scripts/occ_invite_key_rollout.sh step 2/7, behind a
# wrangler preflight and a `Type ROLLOUT` confirmation. Running the real script
# to exercise it would mean a Cloudflare identity check and a live prompt, so
# this suite lifts the step-2 block out of the file and drives it on its own.
# The block is re-extracted from the script for every case, so a case can never
# pass against a stale copy.
#
# Counsel's condition (DIG-1474, 9 Oct) is that the put NARROWS the OCC tenant
# to the help corpus. That is stricter than "changes at most the token", and the
# difference is what most of these cases exist to pin:
#
#   1. narrowing works            -> the happy path still runs
#   2. added backend block        -> the path union sees an ADDED key. The old
#                                    guard enumerated `paths(scalars)` on the
#                                    current registry only, so a brand-new
#                                    backend.digisearchIndex was invisible and
#                                    the run reported a clean one-field change.
#   3. a third field moves        -> refused, naming the field (R10 / routing)
#   4. corpus already narrowed    -> refused. Rotating the key alone is NOT a
#                                    compliant rollout.
#   5. token already current      -> refused. A paste that changed nothing here
#                                    is not a rollout.
#   6. tickets corpus re-added    -> refused by name, before the diff check
#
# Cases 2, 3, 4 and 6 are the ones a green run cannot substitute for.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE/.."

SCRIPT="scripts/occ_invite_key_rollout.sh"
NEW_KEY="2222bbbb3333cccc4444dddd5555eeee6666ffff7777aaaa8888bbbb9999"
KEY2="111122223333444455556666777788889999aaaabbbbccccddddeeeeffff0000"
HOST="occ.digithings.ai"
BLOCK=""
rc=0
fails=0

# The real registry shape, minus the secrets: one OCC entry whose retrieval
# corpus still names both corpora, one first-party entry, and the mcp.servers
# entry the script must carry across verbatim.
registry() { # <token> <index>
  printf '{"%s":{"token":"%s","backend":{"digisearchIndex":"%s"},"mcp":{"servers":[{"id":"zammad"}]},"gateMode":"turn_limited"},"digithings.ai":{"token":"first-party-token","gateMode":"ungated"}}' \
    "$HOST" "$1" "$2"
}

extract_block() {
  awk '/^# -+ build the JSON --$/{f=1} f&&/^# -+ fingerprint --$/{f=0} f' "$SCRIPT"
}

# run_block <block-file> <current-json> <new-key> ; echoes the runner's output,
# returns its exit code. The knobs the real script fixes are fixed here too, so
# a case cannot pass by exporting a different corpus.
run_block() { # <block-file> <current-json> <new-key>
  BLOCK_FILE="$1" CURRENT_JSON="$2" NEW_KEY="$3" \
  bash -c '
    set -euo pipefail
    OCC_HOST='"$HOST"'
    OCC_HELP_INDEX="occ_help"
    OCC_FORBIDDEN_INDEX="occ_tickets"
    say()  { printf "=== %s\n" "$*" >&2; }
    fail() { printf "\nFATAL: %s\n" "$*" >&2; exit 1; }
    eval "$(cat "$BLOCK_FILE")"
  ' 2>&1
}

# mutate_block <out-file> <from> <to> : rewrite the step-2 block with an exact
# string substitution. python, not sed: the block is shell holding jq, and the
# anchors carry `$`, `[`, `|`, `.` and quotes — enough for a hand-escaped sed
# pattern to silently match nothing and hand a clean run.
mutate_block() { # <out-file> <from> <to>
  extract_block > "$HERE/.occ_block.src"
  BLOCK_SRC="$HERE/.occ_block.src" OUT="$1" python3 - "$2" "$3" <<'PYMUT' || return 1
import os, sys
s = open(os.environ["BLOCK_SRC"]).read()
frm, to = sys.argv[1], sys.argv[2]
n = s.count(frm)
if n != 1:
    sys.stderr.write("anchor occurs %d times\n" % n); sys.exit(1)
out = s.replace(frm, to)
if out == s:
    sys.stderr.write("rewrite was a no-op\n"); sys.exit(1)
open(os.environ["OUT"], "w").write(out)
PYMUT
}

pass() { printf 'PASS  %s\n' "$1"; }
fail_case() { printf 'FAIL  %s\n' "$1"; rc=1; fails=$((fails+1)); }

echo "== the guard under test (extracted from $SCRIPT) =="
extract_block > /dev/null || fail_case "could not extract the step-2 block"
nb="$(extract_block | grep -c . || true)"
echo "   step-2 block: ${nb} non-blank lines"
if [ "$nb" -lt 40 ]; then
  fail_case "step-2 block looks truncated (${nb} lines); the extraction markers moved"
else
  pass "step-2 block extracted (${nb} lines)"
fi

# ---------------------------------------------------------------------------
echo
echo "CASE 1: narrowing occ_help,occ_tickets -> occ_help must still run"
extract_block > "$HERE/.occ_block.bak"
out="$(run_block "$HERE/.occ_block.bak" "$(registry old-occ-token occ_help,occ_tickets)" "$NEW_KEY")"
if printf '%s' "$out" | grep -q 'exactly two fields will change'; then
  pass "case 1 — the rollout reports both fields and proceeds"
else
  fail_case "case 1 — expected the two-field summary; got:"; printf '%s\n' "$out" | sed 's/^/    /'
fi

# ---------------------------------------------------------------------------
echo
echo "CASE 2: the OCC entry has no backend block at all (an ADDED key)"
out="$(run_block "$HERE/.occ_block.bak" '{"occ.digithings.ai":{"token":"old-occ-token","mcp":{"servers":[{"id":"zammad"}]}},"digithings.ai":{"token":"t"}}' "$NEW_KEY")"
if printf '%s' "$out" | grep -q 'exactly two fields will change'; then
  pass "case 2 — an added backend.digisearchIndex is seen, not silently ignored"
else
  fail_case "case 2 — the path union missed an added key; got:"; printf '%s\n' "$out" | sed 's/^/    /'
fi

# ---------------------------------------------------------------------------
echo
echo "CASE 3: a third field moves in the same put -> must be refused by name"
mutate_block "$HERE/.occ_block.bak" \
  '| .[$h].backend.digisearchIndex = $i' \
  '| .[$h].backend.digisearchIndex = $i | .[$h].gateMode = "ungated"' \
  || fail_case "case 3 — could not apply the third-field mutation"
out="$(run_block "$HERE/.occ_block.bak" "$(registry old-occ-token occ_help,occ_tickets)" "$NEW_KEY")"
if printf '%s' "$out" | grep -q 'FATAL' && printf '%s' "$out" | grep -q 'gateMode'; then
  pass "case 3 — a third field is refused and named"
else
  fail_case "case 3 — expected a FATAL naming gateMode; got:"; printf '%s\n' "$out" | sed 's/^/    /'
fi

# ---------------------------------------------------------------------------
echo
echo "CASE 4: the corpus is ALREADY narrowed -> the token-only run is not compliant"
extract_block > "$HERE/.occ_block.bak"
out="$(run_block "$HERE/.occ_block.bak" "$(registry old-occ-token occ_help)" "$NEW_KEY")"
if printf '%s' "$out" | grep -q 'backend.digisearchIndex did not change'; then
  pass "case 4 — a run that narrows nothing is refused (Counsel's both-fields rule)"
else
  fail_case "case 4 — a token-only run was allowed to look compliant; got:"; printf '%s\n' "$out" | sed 's/^/    /'
fi

# ---------------------------------------------------------------------------
echo
echo "CASE 5: the pasted registry already holds the new key -> nothing rotated"
extract_block > "$HERE/.occ_block.bak"
out="$(run_block "$HERE/.occ_block.bak" "$(registry "$NEW_KEY" occ_help,occ_tickets)" "$NEW_KEY")"
if printf '%s' "$out" | grep -q 'occ.digithings.ai.token did not change'; then
  pass "case 5 — a no-op token rotation is refused"
else
  fail_case "case 5 — a no-op rotation was allowed; got:"; printf '%s\n' "$out" | sed 's/^/    /'
fi

# ---------------------------------------------------------------------------
echo
echo "CASE 6: the tickets corpus rides along in the put -> refused by name"
mutate_block "$HERE/.occ_block.bak" \
  '| .[$h].backend.digisearchIndex = $i' \
  '| .[$h].backend.digisearchIndex = "$i,occ_tickets"' \
  || fail_case "case 6 — could not apply the re-added-corpus mutation"
out="$(run_block "$HERE/.occ_block.bak" "$(registry old-occ-token occ_help,occ_tickets)" "$NEW_KEY")"
if printf '%s' "$out" | grep -q 'occ_tickets'; then
  pass "case 6 — the customer-PII corpus is named in the refusal"
else
  fail_case "case 6 — a re-added tickets corpus was not named; got:"; printf '%s\n' "$out" | sed 's/^/    /'
fi

# ---------------------------------------------------------------------------
echo
echo "== MUTANTS: each guard clause must be able to fail =="

mutate() { # <label> <from> <to> <input-json> <string-must-appear-in-the-mutant-output>
  local label="$1" from="$2" to="$3" input="$4" expect="$5" out
  mutate_block "$HERE/.occ_block.mut" "$from" "$to" \
    || { fail_case "mutant $label — anchor was not unique or the rewrite was a no-op"; return; }
  out="$(run_block "$HERE/.occ_block.mut" "$input" "$NEW_KEY")"
  if printf '%s' "$out" | grep -q "$expect"; then
    fail_case "mutant $label SURVIVED — its scenario still reports compliant"
  else
    pass "mutant $label killed — reverting the clause turns a clean case red"
  fi
}

# The whole point of the union: revert it to the pre-DIG-2779 single-sided walk
# and the ADDED-key case stops being protected, because the key the union finds
# is one `paths(scalars)` on the current registry cannot see.
ADDED_KEY_REGISTRY='{"occ.digithings.ai":{"token":"old-occ-token","mcp":{"servers":[{"id":"zammad"}]}},"digithings.ai":{"token":"t"}}'
mutate "union-to-single-sided" \
  '(($cur | [paths(scalars)]) + ($new[0] | [paths(scalars)]) | unique_by(.)) as $all' \
  '$cur | paths(scalars) as $all' \
  "$ADDED_KEY_REGISTRY" \
  'backend.digisearchIndex did not change'


mutate "drop the both-fields rule for the corpus" \
  'grep -qx "$INDEX_PATH" <<<"$CHANGED_KEYS"' \
  ':' \
  "$(registry old-occ-token occ_help)" \
  'backend.digisearchIndex did not change'

mutate "drop the both-fields rule for the token" \
  'grep -qx "$TOKEN_PATH" <<<"$CHANGED_KEYS"' \
  ':' \
  "$(registry "$NEW_KEY" occ_help,occ_tickets)" \
  'occ.digithings.ai.token did not change'

# ---------------------------------------------------------------------------
rm -f "$HERE/.occ_block.bak" "$HERE/.occ_block.mut" "$HERE/.occ_block.src"
echo
echo "==================================================================="
if [ "$rc" -eq 0 ]; then
  echo "SCOPE GUARD SUITE PASSED: the allowed diff is exactly {token, backend.digisearchIndex},"
  echo "both are required, and an added key is no longer invisible."
else
  echo "SCOPE GUARD SUITE FAILED: $fails check(s)"
fi
exit "$rc"
