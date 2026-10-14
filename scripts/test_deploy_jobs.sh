#!/usr/bin/env bash
# Proves the DIG-3697 deploy jobs:
#   - one entrypoint per Worker, matching workers.tsv
#   - git verify-tag against allowed_signers is mandatory
#   - an empty allowed_signers file refuses before verify-tag prints "Good"
#   - a dirty checkout or a HEAD that is not the tag is refused
#   - --live never reaches wrangler
#   - the only wrangler deploy invocation is --dry-run
#   - corpus-index has no source and does not call wrangler
#   - the OCC split does not put a secret or deploy
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
fails=0

fail() {
  echo "FAIL $*" >&2
  fails=$((fails + 1))
}

ok() { echo "ok   $*"; }

# --- source invariants -------------------------------------------------------

ids="stack digichat langfuse cron runner dashboard-api corpus-index digidata-api"
for id in $ids; do
  [ -x "scripts/deploy/${id}.sh" ] || fail "missing executable scripts/deploy/${id}.sh"
  grep -q -- "--job ${id} " "scripts/deploy/${id}.sh" || fail "${id}.sh does not pass --job ${id}"
done

tsv_ids="$(awk -F '\t' '$0 ~ /^#/ { next } NF { print $1 }' scripts/deploy/workers.tsv | tr '\n' ' ')"
for id in $ids; do
  case " $tsv_ids" in
    *" $id "*) ;;
    *) fail "workers.tsv missing $id" ;;
  esac
done
ok "eight job entrypoints match workers.tsv"

# Non-comment code must not put a secret or run a live wrangler deploy.
python3 - << 'PY' || fail "live deploy or secret put found in code"
import pathlib, sys
root = pathlib.Path("scripts")
files = list((root / "deploy").glob("*.sh")) + [
    root / "occ_invite_key_write.sh",
    root / "occ_invite_key_deploy.sh",
    root / "occ_invite_key_rollout.sh",
]
bad = []
for path in files:
    for n, line in enumerate(path.read_text().splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "secret put" in line:
            bad.append(f"{path}:{n}: secret put")
        if "wrangler deploy" in line and "--dry-run" not in line:
            bad.append(f"{path}:{n}: live wrangler deploy")
if bad:
    print("\n".join(bad), file=sys.stderr)
    sys.exit(1)
PY
ok "no live wrangler deploy and no secret put in code"

if grep -R -n --include='*.yml' -e 'buildkite' scripts/deploy >/dev/null 2>&1; then
  fail "scripts/deploy mentions buildkite"
fi
ok "deploy jobs are not a Buildkite pipeline"

# The committed signers file is comments only, so production refuses.
if grep -Eq '^[^#[:space:]]' scripts/deploy/allowed_signers; then
  fail "allowed_signers shipped with a key line"
fi
ok "allowed_signers ships with no keys"

# --- fixture repo ------------------------------------------------------------

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
KEY="$TMP/key"
ssh-keygen -t ed25519 -f "$KEY" -N "" -C "test-signer@digithings" -q
OTHER="$TMP/other"
ssh-keygen -t ed25519 -f "$OTHER" -N "" -C "other@digithings" -q
SIGNERS="$TMP/allowed_signers"
printf 'test-signer@digithings namespaces="git" %s\n' "$(cat "$KEY.pub")" > "$SIGNERS"
WRONG="$TMP/wrong_signers"
printf 'test-signer@digithings namespaces="git" %s\n' "$(cat "$OTHER.pub")" > "$WRONG"
STUB="$TMP/bin"
mkdir -p "$STUB"
LOG="$TMP/wrangler.log"
cat > "$STUB/wrangler" << 'EOF'
#!/bin/sh
printf '%s\n' "$*" >> "$WRANGLER_CALL_LOG"
exit 0
EOF
chmod 755 "$STUB/wrangler"

REPO="$TMP/repo"
git init -q "$REPO"
git -C "$REPO" config user.email "test-signer@digithings"
git -C "$REPO" config user.name "test-signer"
git -C "$REPO" config gpg.format ssh
git -C "$REPO" config user.signingkey "$KEY"
git -C "$REPO" config commit.gpgsign false
git -C "$REPO" config tag.gpgsign false
mkdir -p "$REPO/apps/digithings-stack-cloudflare"
printf 'name = "digithings-stack"\n' > "$REPO/apps/digithings-stack-cloudflare/wrangler.toml"
echo hello > "$REPO/f"
git -C "$REPO" add .
git -C "$REPO" commit -q -m "init"
git -C "$REPO" tag -s stack-v1.2.3 -m "release stack-v1.2.3"
git -C "$REPO" tag -s corpus-index-v1.0.0 -m "release corpus-index-v1.0.0"
git -C "$REPO" tag -a stack-v0.0.1 -m "unsigned annotated"

run_job() {
  PATH="$STUB:$PATH" WRANGLER_CALL_LOG="$LOG" \
    bash "$ROOT/scripts/deploy/run-job.sh" "$@"
}

# empty signers: refuse before "Good signature"
: > "$LOG"
out="$(run_job --job stack --tag stack-v1.2.3 --repo "$REPO" --allowed-signers "$ROOT/scripts/deploy/allowed_signers" 2>&1)" && rc=0 || rc=$?
if [ "$rc" -eq 0 ]; then fail "empty signers file was accepted"; else
  case "$out" in
    *"no keys"*) ;;
    *) fail "empty signers did not say no keys: $out" ;;
  esac
  case "$out" in
    *"Good signature"*) fail "empty signers printed Good signature" ;;
  esac
  [ ! -s "$LOG" ] || fail "empty signers called wrangler"
fi
ok "empty allowed_signers refuses before verify-tag"

# unsigned annotated tag
: > "$LOG"
out="$(run_job --job stack --tag stack-v0.0.1 --repo "$REPO" --allowed-signers "$SIGNERS" 2>&1)" && rc=0 || rc=$?
if [ "$rc" -eq 0 ]; then fail "unsigned tag was accepted"; fi
[ ! -s "$LOG" ] || fail "unsigned tag called wrangler"
ok "unsigned tag is refused"

# signed by a key that is not in the file
: > "$LOG"
out="$(run_job --job stack --tag stack-v1.2.3 --repo "$REPO" --allowed-signers "$WRONG" 2>&1)" && rc=0 || rc=$?
if [ "$rc" -eq 0 ]; then fail "wrong key was accepted"; fi
[ ! -s "$LOG" ] || fail "wrong key called wrangler"
ok "tag signed by an unlisted key is refused"

# wrong prefix
: > "$LOG"
out="$(run_job --job stack --tag digichat-v1.2.3 --repo "$REPO" --allowed-signers "$SIGNERS" 2>&1)" && rc=0 || rc=$?
if [ "$rc" -eq 0 ]; then fail "wrong prefix was accepted"; fi
ok "wrong tag prefix is refused"

# dirty tree
echo dirty >> "$REPO/f"
: > "$LOG"
out="$(run_job --job stack --tag stack-v1.2.3 --repo "$REPO" --allowed-signers "$SIGNERS" 2>&1)" && rc=0 || rc=$?
if [ "$rc" -eq 0 ]; then fail "dirty checkout was accepted"; fi
[ ! -s "$LOG" ] || fail "dirty checkout called wrangler"
git -C "$REPO" checkout -q -- f
ok "dirty checkout is refused"

# HEAD is not the tagged commit
echo next > "$REPO/g"
git -C "$REPO" add g
git -C "$REPO" commit -q -m "move HEAD"
: > "$LOG"
out="$(run_job --job stack --tag stack-v1.2.3 --repo "$REPO" --allowed-signers "$SIGNERS" 2>&1)" && rc=0 || rc=$?
if [ "$rc" -eq 0 ]; then fail "moved HEAD was accepted"; fi
[ ! -s "$LOG" ] || fail "moved HEAD called wrangler"
git -C "$REPO" reset -q --hard stack-v1.2.3
ok "HEAD that is not the tag is refused"

# --live on a good tag never calls wrangler
: > "$LOG"
out="$(run_job --job stack --tag stack-v1.2.3 --repo "$REPO" --allowed-signers "$SIGNERS" --live 2>&1)" && rc=0 || rc=$?
if [ "$rc" -ne 2 ]; then fail "--live exit $rc, want 2: $out"; fi
case "$out" in
  *DISARMED*) ;;
  *) fail "--live did not say DISARMED: $out" ;;
esac
[ ! -s "$LOG" ] || fail "--live called wrangler: $(cat "$LOG")"
ok "--live is refused and does not call wrangler"

# signed, clean, matching HEAD: dry-run only
: > "$LOG"
out="$(run_job --job stack --tag stack-v1.2.3 --repo "$REPO" --allowed-signers "$SIGNERS" 2>&1)" && rc=0 || rc=$?
if [ "$rc" -ne 0 ]; then fail "signed dry-run exit $rc: $out"; fi
case "$out" in
  *"PASS stack dry-run"*) ;;
  *) fail "signed dry-run missing PASS: $out" ;;
esac
case "$(cat "$LOG")" in
  *"deploy --dry-run"*) ;;
  *) fail "wrangler was not a dry-run: $(cat "$LOG")" ;;
esac
case "$(cat "$LOG")" in
  *"--live"*) fail "dry-run log contains --live" ;;
esac
ok "signed tag runs wrangler deploy --dry-run"

# the per-job entrypoint reaches the same gate
: > "$LOG"
out="$(PATH="$STUB:$PATH" WRANGLER_CALL_LOG="$LOG" \
  bash "$ROOT/scripts/deploy/stack.sh" --tag stack-v1.2.3 --repo "$REPO" --allowed-signers "$SIGNERS" 2>&1)" && rc=0 || rc=$?
if [ "$rc" -ne 0 ]; then fail "stack.sh exit $rc: $out"; fi
ok "stack.sh entrypoint dry-runs"

# corpus-index: signed tag, no source, no wrangler
: > "$LOG"
out="$(run_job --job corpus-index --tag corpus-index-v1.0.0 --repo "$REPO" --allowed-signers "$SIGNERS" 2>&1)" && rc=0 || rc=$?
if [ "$rc" -ne 2 ]; then fail "corpus-index exit $rc, want 2: $out"; fi
case "$out" in
  *"no Worker source"*) ;;
  *) fail "corpus-index did not report missing source: $out" ;;
esac
[ ! -s "$LOG" ] || fail "corpus-index called wrangler"
ok "corpus-index refuses with no source and does not call wrangler"

# --- OCC split ---------------------------------------------------------------

paths="apps/digichat-cloudflare/src/paths.ts"
before="$(cksum "$paths")"
out="$(bash scripts/occ_invite_key_deploy.sh 2>&1)" && rc=0 || rc=$?
after="$(cksum "$paths")"
if [ "$rc" -ne 0 ]; then fail "occ deploy dry-run exit $rc: $out"; fi
if [ "$before" != "$after" ]; then fail "occ deploy dry-run changed paths.ts"; fi
case "$out" in
  *"Nothing was changed"*) ;;
  *) fail "occ deploy dry-run missing the no-change line: $out" ;;
esac
out="$(bash scripts/occ_invite_key_deploy.sh --live 2>&1)" && rc=0 || rc=$?
after_live="$(cksum "$paths")"
if [ "$rc" -ne 2 ]; then fail "occ deploy --live exit $rc: $out"; fi
if [ "$before" != "$after_live" ]; then fail "occ deploy --live changed paths.ts"; fi
case "$out" in
  *DISARMED*) ;;
  *) fail "occ deploy --live did not say DISARMED: $out" ;;
esac
ok "OCC R5 deploy dry-run does not edit paths.ts and --live is refused"

if ! grep -q 'occ_invite_key_write.sh' scripts/occ_invite_key_rollout.sh; then
  fail "rollout entry does not call the R6 write half"
fi
if ! grep -q 'occ_invite_key_deploy.sh' scripts/occ_invite_key_rollout.sh; then
  fail "rollout entry does not name the R5 deploy half"
fi
ok "rollout entry points at the R6 write half and the R5 deploy half"

if [ "$fails" -ne 0 ]; then
  echo "FAILED: $fails" >&2
  exit 1
fi
echo "OK: deploy jobs stay disarmed and require a signed tag."
