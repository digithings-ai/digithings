#!/usr/bin/env bash
# Proves scripts/verify_occ_invite_key.sh can report the closure bar as MET.
#
# DIG-1381 closes on check 2 ("correct key, no origin" -> slug=occ). No rollout
# has ever run, so that check has never been observed passing and nobody knows
# the script can distinguish a real key from a fake one. This drives it against a
# local fixture implementing the real hostTenantAuthorized rule, in four states:
#
#   1. Act B1, correct key   -> all 7 PASS, exit 0   (the bar, reached)
#   2. Act B1, wrong key     -> check 2 FAILs, exit 1  (the bar discriminates)
#   3. Act B2 simulated      -> checks 3+4 flip to denial, exit 0
#   4. Corpus leaked         -> check 7 FAILs, exit 1  (DIG-2779)
#
# Case 2 is the load-bearing one: without it, case 1 only shows the script can be
# green. It shows green MEANS the key matched.
#
# Case 4 exists for the same reason, about a different check. Check 7 asserts the
# retrieval corpus is not discoverable from the client projection. On a fixture
# that never leaks a corpus, that check passes for free, which is what a check
# that cannot fail looks like. FIXTURE_LEAK_CORPUS makes the fixture serialise
# backend.digisearchIndex — the regression check 7 exists to catch.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE/.."

KEY="a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90"   # throwaway
WRONG="0000000000000000000000000000000000000000000000000000000000000000"
PORT="${PORT:-8791}"
FIXT="scripts/occ_invite_key_fixture_server.mjs"
rc=0

run_verify() { # <label> <invite-key> <expect-check2> <expect-b2>
  local label="$1" ikey="$2" expect="$3" expect_b2="$4"
  echo
  echo "==================================================================="
  echo "CASE $label   (expecting check 2 to $expect)"
  echo "==================================================================="
  OCC_INVITE_KEY="$ikey" \
  PROBE_BASE="http://127.0.0.1:$PORT" \
  OCC_EMBED_HOST="https://occ.digithings.ai" \
  FIRST_PARTY_ORIGIN="https://digithings.ai" \
  WRONG_KEY="$WRONG" \
  EXPECT_B2="$expect_b2" \
  bash scripts/verify_occ_invite_key.sh
  local vrc=$?
  echo "-- verify exit code: $vrc"
  return $vrc
}

start_fixture() { # [extra env...]
  env "$@" FIXTURE_PORT="$PORT" node "$FIXT" 2>"$HERE/.fixture.err" &
  FIXTURE_PID=$!
  local i=0
  while [ $i -lt 50 ]; do
    if curl -fsS -o /dev/null "http://127.0.0.1:$PORT/api/embed/tenant-config" 2>/dev/null; then return 0; fi
    sleep 0.1; i=$((i+1))
  done
  echo "fixture never came up; stderr:"; cat "$HERE/.fixture.err"; return 1
}
stop_fixture() { kill "$FIXTURE_PID" 2>/dev/null; wait "$FIXTURE_PID" 2>/dev/null; rm -f "$HERE/.fixture.err"; }
trap stop_fixture EXIT

echo "== fixture says =="; FIXTURE_PORT=0 FIXTURE_OCC_TOKEN="$KEY" node "$FIXT" 2>&1 >/dev/null & sleep 0.4; kill %1 2>/dev/null; wait 2>/dev/null
echo
echo "### The fixture reads FIRST_PARTY_EMBED_HOSTS off disk; if occ.digithings.ai"
echo "### were off the real allowlist, case 1 could not pass."

start_fixture FIXTURE_OCC_TOKEN="$KEY" || exit 2
echo "-- fixture ready (Act B1: allowlist unchanged)"

run_verify "1: Act B1, correct key -> all 7 pass" "$KEY" "PASS" 0
c1=$?
if [ "$c1" -ne 0 ]; then echo "FAIL: expected exit 0 with the correct key, got $c1"; rc=1; fi
stop_fixture; trap - EXIT

start_fixture FIXTURE_OCC_TOKEN="$KEY" || exit 2
run_verify "2: Act B1, WRONG key -> check 2 must fail" "$WRONG" "FAIL" 0
c2=$?
if [ "$c2" -eq 0 ]; then echo "FAIL: check 2 passed with a wrong key — the bar does not discriminate"; rc=1; fi
stop_fixture; trap - EXIT

start_fixture FIXTURE_OCC_TOKEN="$KEY" FIXTURE_DROP_HOST="occ.digithings.ai" || exit 2
echo "-- fixture ready (Act B2 simulated: occ.digithings.ai dropped)"
run_verify "3: Act B2 simulated, correct key" "$KEY" "PASS" 1
c3=$?
if [ "$c3" -ne 0 ]; then echo "FAIL: post-B2 run with the correct key should be all-PASS, got $c3"; rc=1; fi
stop_fixture; trap - EXIT

start_fixture FIXTURE_OCC_TOKEN="$KEY" FIXTURE_LEAK_CORPUS="occ_help,occ_tickets" || exit 2
echo "-- fixture ready (regression: the projection serialises the corpus)"
run_verify "4: corpus leaked into the client projection" "$KEY" "PASS" 0
c4=$?
stop_fixture; trap - EXIT
if [ "$c4" -eq 0 ]; then
  echo "FAIL: check 7 passed while the fixture leaked backend.digisearchIndex — it cannot fail"
  rc=1
else
  echo "-- case 4 note: the run above must show a FAIL on 'retrieval corpus not exposed'"
fi

echo
echo "==================================================================="
[ "$rc" -eq 0 ] && echo "FIXTURE SUITE PASSED: the closure bar is reachable and discriminating." \
                || echo "FIXTURE SUITE FAILED"
exit "$rc"
