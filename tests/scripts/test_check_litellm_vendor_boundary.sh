#!/usr/bin/env bash
# Regression suite for scripts/check_litellm_vendor_boundary.sh (DIG-1780).
#
# Runs against a scratch fixture repo so the live tree is never mutated. The cases
# that matter are the ones a real PR would hit: someone re-pins the vendor image in a
# compose file, in a workflow, or in prose, and someone bumps the litellm version in
# only one of the three places it is written down.
#
# Usage: bash tests/scripts/test_check_litellm_vendor_boundary.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC_SCRIPT="$REPO_ROOT/scripts/check_litellm_vendor_boundary.sh"
VERIFIER="$REPO_ROOT/scripts/verify_litellm_no_enterprise.py"

pass=0
fail=0

_ok() { pass=$((pass + 1)); }
_bad() {
  echo "FAIL: $1"
  fail=$((fail + 1))
}

assert_ok() {
  local name="$1"
  shift
  if "$@"; then _ok; else
    _bad "$name"
  fi
}

assert_fail() {
  local name="$1"
  shift
  if ! "$@"; then _ok; else
    _bad "$name (expected failure)"
  fi
}

assert_contains() {
  local name="$1" haystack="$2" needle="$3"
  if [[ "$haystack" == *"$needle"* ]]; then _ok; else
    _bad "$name (missing '$needle')"
    echo "  got: $haystack"
  fi
}

FIXTURE="$(mktemp -d)"
trap 'rm -rf "$FIXTURE"' EXIT

# The forbidden references are assembled from parts, never written literally. This suite
# is a tracked file that the gate itself scans, so a literal here would leave the gate
# permanently red against its own regression suite — and exempting the suite from the
# gate would open the door to a real violation hiding in the file that is least likely
# to be read. Name the vendor, not the pull command.
VENDOR_VENDOR="berriai"
VENDOR_PKG="litellm"
VENDOR_HOST_VENDOR="docker.litellm.ai"
VENDOR_IMG="$VENDOR_HOST_VENDOR/$VENDOR_VENDOR/$VENDOR_PKG:main-stable"
VENDOR_GHCR_IMG="ghcr.io/$VENDOR_VENDOR/$VENDOR_PKG:main-latest"

mkdir -p "$FIXTURE/scripts" "$FIXTURE/.github/workflows" "$FIXTURE/docs"

# Mirror the production script so ROOT resolves to the fixture.
cp "$SRC_SCRIPT" "$FIXTURE/scripts/check_litellm_vendor_boundary.sh"
chmod +x "$FIXTURE/scripts/check_litellm_vendor_boundary.sh"
SCRIPT="$FIXTURE/scripts/check_litellm_vendor_boundary.sh"

# The gate reads `git ls-files` for its compose list, so the fixture must be a repo.
git -C "$FIXTURE" init -q
git -C "$FIXTURE" config user.email gate@example.invalid
git -C "$FIXTURE" config user.name gate

# A minimal compliant tree: the Dockerfile pin, a compose file on the exact tag, and
# the two source-fetch exceptions with their real host.
cat >"$FIXTURE/Dockerfile.litellm" <<'EOF'
FROM python:3.12-slim
ARG LITELLM_VERSION=1.72.6
EOF

cat >"$FIXTURE/docker-compose.yml" <<'EOF'
services:
  litellm:
    build:
      context: .
      dockerfile: Dockerfile.litellm
    image: digi-litellm:1.72.6
EOF

mkdir -p "$FIXTURE/docs/plans"
cat >"$FIXTURE/scripts/provider_review_bootstrap.py" <<'EOF'
X = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices.json"
EOF

git -C "$FIXTURE" add -A >/dev/null 2>&1
git -C "$FIXTURE" commit -qm fixture >/dev/null 2>&1

run_gate() {
  bash "$SCRIPT" 2>&1
}

# ── 1. Missing ripgrep fails closed ──────────────────────────────────────────
EMPTY_BIN="$FIXTURE/empty-bin"; mkdir -p "$EMPTY_BIN"
for cmd in dirname pwd sed grep git; do
  src="$(command -v "$cmd" || true)"
  [[ -n "$src" ]] && ln -s "$src" "$EMPTY_BIN/$cmd"
done
set +e
out="$(env -i PATH="$EMPTY_BIN" HOME="$HOME" /bin/bash "$SCRIPT" 2>&1)"
rc=$?
set -e
assert_fail "missing rg exits non-zero" test "$rc" -eq 0
assert_contains "missing rg emits actionable error" "$out" "ripgrep not found"

# ── 2. Compliant fixture passes both checks ──────────────────────────────────
if ! command -v rg >/dev/null 2>&1; then
  echo "SKIP remaining cases: ripgrep not installed on this host"
  echo "litellm-boundary: $pass passed, $fail failed (partial)"
  exit "$fail"
fi

out="$(run_gate)" && rc=0 || rc=$?
assert_ok "compliant fixture exits 0" test "$rc" -eq 0
assert_contains "vendor boundary banner" "$out" "vendor image boundary OK"
assert_contains "pin banner" "$out" "litellm image pin OK"

# ── 3. Vendor image in a compose file fails ──────────────────────────────────
cat >"$FIXTURE/docker-compose.yml" <<EOF
services:
  litellm:
    image: $VENDOR_IMG
EOF
set +e
out="$(run_gate)"
rc=$?
set -e
assert_fail "vendor image in compose exits non-zero" test "$rc" -eq 0
assert_contains "compose violation names the file" "$out" "docker-compose.yml"
assert_contains "compose violation names the red line" "$out" "DIG-1780"

# ── 4. Vendor image in a workflow fails (--hidden matters) ───────────────────
cat >"$FIXTURE/docker-compose.yml" <<'EOF'
services:
  litellm:
    image: digi-litellm:1.72.6
EOF
cat >"$FIXTURE/.github/workflows/pin.yml" <<EOF
jobs:
  pin:
    steps:
      - run: docker pull $VENDOR_GHCR_IMG
EOF
git -C "$FIXTURE" add -A >/dev/null 2>&1
git -C "$FIXTURE" commit -qm wf >/dev/null 2>&1
set +e
out="$(run_gate)"
rc=$?
set -e
assert_fail "vendor image in a dotdir workflow exits non-zero" test "$rc" -eq 0
assert_contains "workflow violation is found under .github" "$out" ".github/workflows/pin.yml"
rm -f "$FIXTURE/.github/workflows/pin.yml"

# ── 5. Vendor reference in prose fails (AC requires an empty grep) ───────────
cat >"$FIXTURE/docs/policy.md" <<EOF
Run \`$VENDOR_IMG\` in production.
EOF
git -C "$FIXTURE" add -A >/dev/null 2>&1
git -C "$FIXTURE" commit -qm prose >/dev/null 2>&1
set +e
out="$(run_gate)"
rc=$?
set -e
assert_fail "vendor reference in prose exits non-zero" test "$rc" -eq 0
assert_contains "prose violation is reported" "$out" "docs/policy.md"
rm -f "$FIXTURE/docs/policy.md"

# ── 6. Source-fetch exception stays allowed, and cannot be abused ────────────
# 6a. The real exception path: a raw.githubusercontent.com fetch of the same repo.
mkdir -p "$FIXTURE/scripts/provider_review"
cat >"$FIXTURE/scripts/provider_review/bootstrap.py" <<'EOF'
X = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices.json"
EOF
git -C "$FIXTURE" add -A >/dev/null 2>&1
git -C "$FIXTURE" commit -qm srcexception >/dev/null 2>&1
out="$(run_gate)" && rc=0 || rc=$?
assert_ok "source fetch on the exception path is allowed" test "$rc" -eq 0

# 6b. An image pull in the same allowlisted file must NOT inherit the exemption.
cat >"$FIXTURE/scripts/provider_review/bootstrap.py" <<EOF
PRICING = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices.json"
IMAGE = "$VENDOR_GHCR_IMG"
EOF
git -C "$FIXTURE" add -A >/dev/null 2>&1
git -C "$FIXTURE" commit -qm abuse >/dev/null 2>&1
set +e
out="$(run_gate)"
rc=$?
set -e
assert_fail "image pull inside an allowlisted file still fails" test "$rc" -eq 0
assert_contains "abuse is attributed to the right file" "$out" "provider_review/bootstrap.py"

# ── 7. Moving tags fail; the exact pin passes ────────────────────────────────
cat >"$FIXTURE/scripts/provider_review/bootstrap.py" <<'EOF'
X = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices.json"
EOF
for tag in latest main-stable stable v1; do
  cat >"$FIXTURE/docker-compose.yml" <<EOF
services:
  litellm:
    image: ghcr.io/digithings-ai/litellm:$tag
EOF
  set +e
  out="$(run_gate)"
  rc=$?
  set -e
  assert_fail "moving tag '$tag' exits non-zero" test "$rc" -eq 0
done

# A digest pin is the strongest form and must pass.
cat >"$FIXTURE/docker-compose.yml" <<'EOF'
services:
  litellm:
    image: ghcr.io/digithings-ai/litellm@sha256:0000000000000000000000000000000000000000000000000000000000000000
EOF
set +e
out="$(run_gate)"
rc=$?
set -e
assert_ok "digest pin is accepted" test "$rc" -eq 0

# A ${VAR:-default} tag resolves to its default and must pass at the right version.
cat >"$FIXTURE/docker-compose.yml" <<'EOF'
services:
  litellm:
    image: ghcr.io/digithings-ai/litellm:${LITELLM_IMAGE_TAG:-1.72.6}
EOF
out="$(run_gate)" && rc=0 || rc=$?
assert_ok "\${VAR:-default} resolving to the pin is accepted" test "$rc" -eq 0

# …but a variable with no in-repo default is refused: nothing a reader can verify.
cat >"$FIXTURE/docker-compose.yml" <<'EOF'
services:
  litellm:
    image: ghcr.io/digithings-ai/litellm:${LITELLM_IMAGE_TAG}
EOF
set +e
out="$(run_gate)"
rc=$?
set -e
assert_fail "bare \${VAR} tag exits non-zero" test "$rc" -eq 0
assert_contains "bare variable names the remedy" "$out" "in-repo default"

# ── 8. Dockerfile/gate pin drift fails (the bump-one-of-three trap) ──────────
cat >"$FIXTURE/docker-compose.yml" <<'EOF'
services:
  litellm:
    image: digi-litellm:1.72.6
EOF
cat >"$FIXTURE/Dockerfile.litellm" <<'EOF'
FROM python:3.12-slim
ARG LITELLM_VERSION=1.99.0
EOF
git -C "$FIXTURE" add -A >/dev/null 2>&1
git -C "$FIXTURE" commit -qm drift >/dev/null 2>&1
set +e
out="$(run_gate)"
rc=$?
set -e
assert_fail "Dockerfile pin drift exits non-zero" test "$rc" -eq 0
assert_contains "drift names both versions" "$out" "1.99.0"
cat >"$FIXTURE/Dockerfile.litellm" <<'EOF'
FROM python:3.12-slim
ARG LITELLM_VERSION=1.72.6
EOF
git -C "$FIXTURE" add -A >/dev/null 2>&1
git -C "$FIXTURE" commit -qm undrift >/dev/null 2>&1

# ── 9. The image verifier rejects a planted enterprise/ directory ────────────
# Runs against the host interpreter: it must not need litellm installed to prove
# the enterprise check fires, so LITELLM_VERSION is left unset and a fake dist-info
# supplies the version.
if command -v python3 >/dev/null 2>&1; then
  FAKE_SITE="$FIXTURE/fake-site"
  mkdir -p "$FAKE_SITE/enterprise"
  cat >"$FAKE_SITE/enterprise/__init__.py" <<'EOF'
EOF
  mkdir -p "$FAKE_SITE/litellm-1.72.6.dist-info"
  cat >"$FAKE_SITE/litellm-1.72.6.dist-info/METADATA" <<'EOF'
Metadata-Version: 2.1
Name: litellm
Version: 1.72.6
EOF
  set +e
  out="$(PYTHONPATH="$FAKE_SITE" LITELLM_VERSION=1.72.6 python3 "$VERIFIER" 2>&1)"
  rc=$?
  set -e
  assert_fail "verifier rejects a planted enterprise/ directory" test "$rc" -eq 0
  assert_contains "verifier names the offending path" "$out" "enterprise-importable"

  # Remove the plant: the same tree must now pass.
  rm -rf "$FAKE_SITE/enterprise"
  out="$(PYTHONPATH="$FAKE_SITE" LITELLM_VERSION=1.72.6 python3 "$VERIFIER" 2>&1)" && rc=0 || rc=$?
  assert_ok "verifier passes a clean tree" test "$rc" -eq 0
  assert_contains "verifier OK banner names the version" "$out" "litellm==1.72.6"

  # A pin mismatch must fail — that is the "silent base drift" case.
  out="$(PYTHONPATH="$FAKE_SITE" LITELLM_VERSION=1.99.0 python3 "$VERIFIER" 2>&1)" && rc=0 || rc=$?
  assert_fail "verifier rejects a pin mismatch" test "$rc" -eq 0
  assert_contains "mismatch is reported as pin-mismatch" "$out" "pin-mismatch"
else
  echo "SKIP verifier cases: python3 not on PATH"
fi

# ── 10. Live repo gate is green (integration smoke) ──────────────────────────
out="$(bash "$SRC_SCRIPT" 2>&1)" && rc=0 || rc=$?
assert_ok "live tree passes the litellm boundary gate" test "$rc" -eq 0

echo "litellm-boundary: $pass passed, $fail failed"
exit "$fail"
