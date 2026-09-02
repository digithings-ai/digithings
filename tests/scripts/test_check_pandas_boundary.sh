#!/usr/bin/env bash
# Regression suite for scripts/check_pandas_boundary.sh (#3107 ripgrep fail-closed +
# allowlist enforcement). Runs against a scratch digiquant tree so the live tree
# is never mutated.
#
# Usage: bash tests/scripts/test_check_pandas_boundary.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC_SCRIPT="$REPO_ROOT/scripts/check_pandas_boundary.sh"

pass=0
fail=0

assert_ok() {
  local name="$1"
  shift
  if "$@"; then
    pass=$((pass + 1))
  else
    echo "FAIL: $name"
    fail=$((fail + 1))
  fi
}

assert_fail() {
  local name="$1"
  shift
  if ! "$@"; then
    pass=$((pass + 1))
  else
    echo "FAIL: $name (expected failure)"
    fail=$((fail + 1))
  fi
}

assert_contains() {
  local name="$1"
  local haystack="$2"
  local needle="$3"
  if [[ "$haystack" == *"$needle"* ]]; then
    pass=$((pass + 1))
  else
    echo "FAIL: $name (missing '$needle')"
    echo "  got: $haystack"
    fail=$((fail + 1))
  fi
}

FIXTURE="$(mktemp -d)"
cleanup() {
  rm -rf "$FIXTURE"
}
trap cleanup EXIT

mkdir -p "$FIXTURE/scripts" \
  "$FIXTURE/digiquant/src/digiquant" \
  "$FIXTURE/digiquant/src/digiquant/charts" \
  "$FIXTURE/digiquant/src/digiquant/strategies" \
  "$FIXTURE/digiquant/scripts/atlas" \
  "$FIXTURE/digiquant/sandbox/pandas_ta"

# Mirror the production script so ROOT resolves to the fixture.
cp "$SRC_SCRIPT" "$FIXTURE/scripts/check_pandas_boundary.sh"
chmod +x "$FIXTURE/scripts/check_pandas_boundary.sh"
SCRIPT="$FIXTURE/scripts/check_pandas_boundary.sh"

# Allowlisted paths (must match scripts/check_pandas_boundary.sh).
cat >"$FIXTURE/digiquant/src/digiquant/nautilus_runner.py" <<'PY'
import pandas as pd
PY
cat >"$FIXTURE/digiquant/src/digiquant/tearsheet.py" <<'PY'
from pandas import DataFrame
PY
# Non-allowlisted module — used for the violation case.
cat >"$FIXTURE/digiquant/src/digiquant/rogue_pandas.py" <<'PY'
# clean by default; violation tests overwrite
x = 1
PY

# ── 1. Missing ripgrep fails closed (#3107) ──────────────────────────────────
# Host images often ship /usr/bin/rg. Build a PATH with only the coreutils the
# gate needs so `command -v rg` fails without breaking `dirname`/`pwd`/`cd`.
EMPTY_BIN="$FIXTURE/empty-bin"; mkdir -p "$EMPTY_BIN"
for cmd in dirname pwd; do
  src="$(command -v "$cmd")"
  ln -s "$src" "$EMPTY_BIN/$cmd"
done
set +e
out="$(env -i PATH="$EMPTY_BIN" HOME="$HOME" /bin/bash "$SCRIPT" 2>&1)"
rc=$?
set -e
assert_fail "missing rg exits non-zero" test "$rc" -eq 0
assert_contains "missing rg emits actionable error" "$out" "ripgrep not found"

# ── 2. Clean tree (allowlisted imports only) passes ──────────────────────────
# Need real rg on PATH for remaining cases.
if ! command -v rg >/dev/null 2>&1; then
  echo "SKIP remaining cases: ripgrep not installed on this host"
  echo "pandas-boundary: $pass passed, $fail failed (partial)"
  exit "$fail"
fi

out="$(bash "$SCRIPT" 2>&1)" && rc=0 || rc=$?
assert_ok "clean allowlisted tree exits 0" test "$rc" -eq 0
assert_contains "clean tree prints OK" "$out" "pandas boundary OK"

# ── 3. Non-allowlisted import pandas fails ───────────────────────────────────
cat >"$FIXTURE/digiquant/src/digiquant/rogue_pandas.py" <<'PY'
import pandas as pd
PY
set +e
out="$(bash "$SCRIPT" 2>&1)"
rc=$?
set -e
assert_fail "rogue import pandas exits non-zero" test "$rc" -eq 0
assert_contains "rogue path listed" "$out" "digiquant/src/digiquant/rogue_pandas.py"

# ── 4. Non-allowlisted from pandas fails ─────────────────────────────────────
cat >"$FIXTURE/digiquant/src/digiquant/rogue_pandas.py" <<'PY'
from pandas import Series
PY
set +e
out="$(bash "$SCRIPT" 2>&1)"
rc=$?
set -e
assert_fail "rogue from pandas exits non-zero" test "$rc" -eq 0
assert_contains "from-pandas path listed" "$out" "rogue_pandas.py"

# ── 5. Inline / commented pandas does not trip the gate ──────────────────────
cat >"$FIXTURE/digiquant/src/digiquant/rogue_pandas.py" <<'PY'
# import pandas as pd
x = "from pandas import nowhere"
PY
out="$(bash "$SCRIPT" 2>&1)" && rc=0 || rc=$?
assert_ok "commented/string pandas is ignored" test "$rc" -eq 0

# ── 6. Live repo gate still green (integration smoke) ────────────────────────
out="$(bash "$SRC_SCRIPT" 2>&1)" && rc=0 || rc=$?
assert_ok "live digiquant tree passes pandas boundary" test "$rc" -eq 0
assert_contains "live tree OK banner" "$out" "pandas boundary OK"

echo "pandas-boundary: $pass passed, $fail failed"
exit "$fail"
