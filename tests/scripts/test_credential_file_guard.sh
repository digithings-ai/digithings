#!/usr/bin/env bash
# Canary + regression tests for the credential-file guard (DIG-1653).
#
# The canary in scope (d): a fake credential file is created in a throwaway git
# repo, an agent-style command tries to read it, and the captured output is
# asserted to contain neither the canary value nor the file's content. No real
# credential appears here — the value is generated per run.
#
# Usage: bash tests/scripts/test_credential_file_guard.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
GUARD_SH="$REPO_ROOT/scripts/claude-hooks/credential-file-guard.sh"
PATHS_PY="$REPO_ROOT/scripts/claude-hooks/credential_paths.py"
TRANSCRIPT_PY="$REPO_ROOT/scripts/check_transcript_secrets.py"
HOOK_PY="$(command -v python 2>/dev/null || command -v python3)"
# digitrace is a workspace package resolved by pytest.ini's pythonpath, not by an
# installed distribution, so PYTHONPATH has to mirror that here.
UV=(env "PYTHONPATH=$REPO_ROOT/digitrace/src" uv run --frozen --no-sync)

pass=0
fail=0

_fixture_root() {
  local base="${RUNNER_TEMP:-${TMPDIR:-/var/tmp}}"
  if [[ "$base" == /tmp || "$base" == /tmp/* ]]; then
    base="/var/tmp"
  fi
  mktemp -d "${base%/}/cred-guard-fixture.XXXXXX"
}

REPO_FIXTURE="$(_fixture_root)"
FAKE_HOME="$(_fixture_root)"
trap 'rm -rf "$REPO_FIXTURE" "$FAKE_HOME"' EXIT

# ── The canary credential ─────────────────────────────────────────────────────
# A fake OAuth-shaped config, deliberately shaped like the file that leaked:
#   [oauth_token]
#   refresh_token = "…"
# The value is generated here, so it exists only for the length of this run and
# is never a real credential.
CANARY_VALUE="$(openssl rand -hex 32)"
CANARY_DIR="$FAKE_HOME/Library/Preferences/.wrangler/config"
mkdir -p "$CANARY_DIR"
cat >"$CANARY_DIR/default.toml" <<EOF
[oauth_token]
access_token = "canary-access-not-a-secret"
refresh_token = "$CANARY_VALUE"
expires = "2026-10-07T00:00:00Z"
EOF

# A second canary under a different shape, so the guard is not just matching one
# filename: a PEM-shaped key in the same fixture home.
CANARY_PEM_VALUE="-----BEGIN PRIVATE KEY-----
MIIBOgIBAAJBAKj34GkxFhD90vcNLYLInFEX6Ppy1tPf9Cnzj4p4WGeKLs1Pt8Qu
KUpRKfFLfRYC9AIKjbJTWit+CqvjWYzvQwECAwEAAQJAIJLixBy2qpFoS4DSmoEm
o3qGy0t6z09AIJtH+5OeRV1be+N4cDYJKffGzDa88vQENZiRm0GRq6a+HPGQMd2k
TQIhAKMSvzIBnni7ot/OSie2TmJLY4SwTQAevXysE2RbFDYdAiEBCUEaRQnMnbp7
9mxDXDf6AU0cN/RPBjb9qSHDcWZHGzUCIG2Es59z8ugGrDY+pxLQnwfotadxd+Uy
v/Ow5T0q5gIJAiEAyS4RaI9YG8EWx/2w0T67ZUVAw8eOMB6BIUg0Xcu+3okCIBOs
5OiTDdMOw8SeCCjL4T5iMg==\n-----END PRIVATE KEY-----"
CANARY_PEM="$FAKE_HOME/.ssh/id_ed25519"
mkdir -p "$FAKE_HOME/.ssh"
printf '%s\n' "$CANARY_PEM_VALUE" >"$CANARY_PEM"

# ── Helpers ───────────────────────────────────────────────────────────────────

# run_guard <tool> <field> <value> [extra FIELD=VALUE ...] — returns exit code
run_guard() {
  local tool="$1" field="$2" value="$3"
  shift 3
  local json rc=0
  json="$("$HOOK_PY" -c "
import json, sys
print(json.dumps({'tool_name': sys.argv[1], 'tool_input': {sys.argv[2]: sys.argv[3]}}))
" "$tool" "$field" "$value")"
  local hook_in
  hook_in="$(mktemp)"
  printf '%s' "$json" >"$hook_in"
  set +e
  env -u DIGIDEV_ALLOW_CREDENTIAL_READ \
    PATH="${PATH:-/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin}" \
    HOME="${HOME:-/tmp}" \
    LANG="${LANG:-C.UTF-8}" \
    DIGI_FORCE_GUARD_TEST=1 \
    DIGIDEV_PROJECT_ROOT="$REPO_FIXTURE" \
    "$@" \
    bash "$GUARD_SH" <"$hook_in" 2>/dev/null
  rc=$?
  rm -f "$hook_in"
  set -e
  return $rc
}

assert_denied() {
  local desc="$1" tool="$2" field="$3" value="$4"
  local rc=0
  run_guard "$tool" "$field" "$value" || rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "PASS [denied]  $desc"
    pass=$((pass + 1))
  else
    echo "FAIL [denied]  $desc  (expected non-zero, got 0)"
    fail=$((fail + 1))
  fi
}

assert_allowed() {
  local desc="$1" tool="$2" field="$3" value="$4"
  shift 4
  local rc=0
  run_guard "$tool" "$field" "$value" "$@" || rc=$?
  if [ "$rc" -eq 0 ]; then
    echo "PASS [allowed] $desc"
    pass=$((pass + 1))
  else
    echo "FAIL [allowed] $desc  (expected 0, got $rc)"
    fail=$((fail + 1))
  fi
}

# ── (d) THE CANARY: the read is blocked and the value cannot reach output ─────

# Simulate the agent attempt end to end: if the guard allows the command, run it
# and capture stdout exactly as a run transcript would capture it.
canary_attempt() {
  local cmd="$1"
  local rc=0
  run_guard Bash command "$cmd" || rc=$?
  if [ "$rc" -eq 0 ]; then
    # Allowed: run it for real and capture whatever the transcript would hold.
    (cd "$REPO_FIXTURE" && HOME="$FAKE_HOME" eval "$cmd") 2>/dev/null || true
  else
    echo "guardrail: blocked"
  fi
}

canary_output="$(canary_attempt "cat $CANARY_DIR/default.toml")"

if printf '%s' "$canary_output" | grep -qF "$CANARY_VALUE"; then
  echo "FAIL [canary]  the canary value reached run output"
  fail=$((fail + 1))
else
  echo "PASS [canary]  the canary value never appears in run output"
  pass=$((pass + 1))
fi

canary_pem_output="$(canary_attempt "cat $CANARY_PEM")"
if printf '%s' "$canary_pem_output" | grep -qF "MIIBOgIBAAJBAKj34GkxFhD90v"; then
  echo "FAIL [canary]  the canary PEM body reached run output"
  fail=$((fail + 1))
else
  echo "PASS [canary]  the canary PEM body never appears in run output"
  pass=$((pass + 1))
fi

# The transcript audit agrees — the second layer, independent of the guard.
rc=0
printf '%s' "$canary_output" | "${UV[@]}" python "$TRANSCRIPT_PY" - >/dev/null 2>&1 || rc=$?
if [ "$rc" -eq 0 ]; then
  echo "PASS [canary]  transcript audit reports the captured output clean"
  pass=$((pass + 1))
else
  echo "FAIL [canary]  transcript audit flagged the captured output (exit $rc)"
  fail=$((fail + 1))
fi

# The audit must actually detect a real leak, or (d) proves nothing. Feed it the
# canary file directly.
if "${UV[@]}" python "$TRANSCRIPT_PY" "$CANARY_DIR/default.toml" >/dev/null 2>&1; then
  echo "FAIL [canary]  transcript audit MISSED the canary file"
  fail=$((fail + 1))
else
  echo "PASS [canary]  transcript audit detects the canary file"
  pass=$((pass + 1))
fi

# ── DENY: Read tool on credential paths ───────────────────────────────────────

assert_denied "Read the wrangler oauth config" Read file_path "$CANARY_DIR/default.toml"
assert_denied "Read ~/.wrangler/config/default.toml (tilde)" Read file_path "~/.wrangler/config/default.toml"
assert_denied "Read a .pem" Read file_path "/repo/server.pem"
assert_denied "Read an .key" Read file_path "/repo/tls.key"
assert_denied "Read .env" Read file_path "/repo/.env"
assert_denied "Read .env.local" Read file_path "/repo/.env.local"
assert_denied "Read .dev.vars" Read file_path "/repo/.dev.vars"
assert_denied "Read .netrc" Read file_path "$HOME/.netrc"
assert_denied "Read .npmrc" Read file_path "$HOME/.npmrc"
assert_denied "Read .aws/credentials" Read file_path "$HOME/.aws/credentials"
assert_denied "Read .git-credentials" Read file_path "$HOME/.git-credentials"
assert_denied "Read .docker/config.json" Read file_path "$HOME/.docker/config.json"
assert_denied "Read an ssh private key" Read file_path "$HOME/.ssh/id_ed25519"
assert_denied "Grep rooted at a credential dir" Grep path "$HOME/.aws"
assert_denied "Grep rooted at the wrangler config dir" Grep path "$CANARY_DIR"

# ── ALLOW: ordinary reads must not be blocked ─────────────────────────────────

assert_allowed "Read a .env.example template" Read file_path "$REPO_ROOT/.env.example"
assert_allowed "Read a docs .md" Read file_path "$REPO_ROOT/docs/ops/SECRETS_ROTATION.md"
assert_allowed "Read the credential-ownership sql migration" Read file_path \
  "$REPO_ROOT/digiquant/supabase/migrations/104_workspace_provider_credentials.sql"
assert_allowed "Read check_example_credentials.py" Read file_path \
  "$REPO_ROOT/scripts/check_example_credentials.py"
assert_allowed "Read a public key .pub" Read file_path "$HOME/.ssh/id_ed25519.pub"
assert_allowed "Read an unrelated source file" Read file_path "$REPO_ROOT/scripts/wrangler-auth.sh"

# ── DENY: Bash commands that would disclose a credential ──────────────────────

assert_denied "cat the wrangler config" Bash command "cat $CANARY_DIR/default.toml"
assert_denied "head the wrangler config" Bash command "head -5 $CANARY_DIR/default.toml"
assert_denied "grep inside .netrc" Bash command "grep -rn token $HOME/.netrc"
assert_denied "sed printing .aws/credentials" Bash command "sed -n '1,5p' $HOME/.aws/credentials"
assert_denied "python reading .dev.vars" Bash command \
  "python3 -c \"print(open('$HOME/.dev.vars').read())\""
assert_denied "cp a credential file out" Bash command "cp $CANARY_DIR/default.toml /tmp/exfil.toml"
assert_denied "cat a .pem via a relative path" Bash command "cat ./certs/server.pem"
assert_denied "cat .env from the repo root" Bash command "cat .env"
assert_denied "xargs cat over a credential glob" Bash command \
  "ls $HOME/.ssh | xargs cat"
assert_denied "command substitution hiding the path" Bash command \
  "echo \$(cat $HOME/.netrc)"
assert_denied "pipeline disclosing a credential" Bash command \
  "cat $CANARY_DIR/default.toml | head -1"

# ── DENY: reveal commands that name no credential path ────────────────────────

assert_denied "security find-generic-password -w" Bash command \
  "security find-generic-password -s digithings -w"
assert_denied "bws secret get" Bash command "bws secret get abc123"
assert_denied "bw get password" Bash command "bw get password my-secret"

# ── DENY: wrangler must go through the wrapper ────────────────────────────────

assert_denied "bare wrangler whoami" Bash command "npx wrangler whoami"
assert_denied "bare wrangler deploy" Bash command "npx wrangler deploy"
assert_denied "bare wrangler secret list" Bash command "npx wrangler secret list"

# ── ALLOW: the wrapper itself, and non-disclosing wrangler-adjacent commands ──

assert_allowed "the sanctioned wrapper" Bash command "scripts/wrangler-auth.sh whoami"
assert_allowed "the wrapper with a secret put" Bash command \
  "scripts/wrangler-auth.sh secret put MCP_EDGE_KEY"
assert_allowed "mkdir -p the wrangler config dir" Bash command "mkdir -p ~/.wrangler/config"
assert_allowed "rm a stale wrangler config" Bash command \
  "rm -f $CANARY_DIR/default.toml"
assert_allowed "ls the wrangler config dir" Bash command "ls -la $CANARY_DIR"
assert_allowed "git status" Bash command "git status"
assert_allowed "git log in the fixture repo" Bash command "git log --oneline -5"

# ── ALLOW: unrelated Bash commands are untouched ──────────────────────────────

assert_allowed "an unrelated cat" Bash command "cat $REPO_ROOT/Makefile"
assert_allowed "a shell test with >" Bash command 'if [ $x -gt 0 ]; then echo ok; fi'
assert_allowed "a quoted > inside grep" Bash command 'grep ">" Makefile'
assert_allowed "no command at all" Read file_path ""

# ── Value-shape audit unit checks ─────────────────────────────────────────────

_value_redactor="$(cd "$REPO_ROOT" && "${UV[@]}" python - "$CANARY_VALUE" <<'PY' 2>&1
import sys

from digitrace.redaction import detect_credential_value, redact_credentials

canary = sys.argv[1]

assert detect_credential_value(f'refresh_token = "{canary}"') == "secret-assignment"
assert detect_credential_value(
    "Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345"
) == "bearer-token"
assert detect_credential_value("api_key = sk-abc123def456789") == "secret-assignment"
assert detect_credential_value("nothing to see here") is None
assert detect_credential_value("") is None
assert "[REDACTED_CREDENTIAL]" in redact_credentials(f'refresh_token = "{canary}"')
# Placeholder-shaped values are not credentials — otherwise redacting a config
# template would destroy the thing you were trying to read.
assert redact_credentials("token: ***") == "token: ***"
assert detect_credential_value("password: changeme") is None
print("ok")
PY
)" || _value_redactor="failed"

if [ "$_value_redactor" = "ok" ]; then
  echo "PASS [values]  detect_credential_value / redact_credentials behave"
  pass=$((pass + 1))
else
  echo "FAIL [values]  detect_credential_value / redact_credentials: $_value_redactor"
  fail=$((fail + 1))
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "Results: $pass passed, $fail failed."
if [ "$fail" -gt 0 ]; then
  exit 1
fi
exit 0