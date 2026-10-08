#!/bin/bash
# DIG-2366 rehearsal driver.
#
# Boots an isolated Paperclip instance twice from the same rehearsal install
# store, swapping only the two bundle files between the phases, and runs the
# identical harness each time. The live pinned install is never touched.
#
#   phase 1 "control"  the two files exactly as the pinned bundle has them
#   phase 2 "patched"  the two patched files from ops/hotpatch/DIG-2366/patched
#
# Transcripts land in ops/hotpatch/DIG-2366/rehearsal/results/.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
HP="$(cd "$HERE/.." && pwd)"
DATA="$HERE/data-run"
INST="$DATA/cli/installs/npm/2026.1001.0"
DIST="$INST/node_modules/@paperclipai/server/dist"
RESULTS="$HERE/results"
PORT=3199
PGPORT=54339
COOKIE="$HERE/session.cookie"
FETCH='Sec-Fetch-Site: same-origin'
EMAIL='dig2366-rehearsal@example.com'
PASSWORD='Dig2366-rehearsal-1'
COMPANY=''
CT='Content-Type: application/json'
API="http://127.0.0.1:${PORT}/api"

mkdir -p "$RESULTS"

log()  { printf '%s\n' "$*"; }
step() { printf '\n== %s\n' "$*"; }

RUNNING_TAG=''
cleanup() {
  if [ -n "$RUNNING_TAG" ] && [ -f "$HERE/boot-${RUNNING_TAG}.pid" ]; then
    local pid; pid="$(cat "$HERE/boot-${RUNNING_TAG}.pid")"
    kill -TERM "$pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

psql_q() { PGPASSWORD=paperclip psql -h 127.0.0.1 -p "$PGPORT" -U paperclip -d paperclip -At -c "$1" | tr -d ' \n'; }

boot() {
  local tag="$1"
  local logfile="$HERE/boot-${tag}.log"
  local i
  cd "$HERE"
  nohup node "$INST/node_modules/paperclipai/dist/index.js" run -d "$DATA" -i dig2366 \
    > "$logfile" 2>&1 &
  echo $! > "$HERE/boot-${tag}.pid"
  RUNNING_TAG="$tag"
  for i in $(seq 1 60); do
    if [ "$(curl -s -m 3 -o /dev/null -w '%{http_code}' "${API}/health")" != "000" ]; then
      log "   booted ${tag} (pid $(cat "$HERE/boot-${tag}.pid")) after ~$((i * 2))s"
      return 0
    fi
    sleep 2
  done
  log "   FAILED to boot ${tag}; tail of ${logfile}:"
  tail -25 "$logfile"
  return 1
}

halt() {
  local tag="$1" pid i
  pid="$(cat "$HERE/boot-${tag}.pid")"
  kill -TERM "$pid" 2>/dev/null || true
  for i in $(seq 1 30); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
  if kill -0 "$pid" 2>/dev/null; then kill -KILL "$pid" 2>/dev/null || true; sleep 2; fi
  RUNNING_TAG=''
  log "   halted ${tag}"
}

install_files() {
  local which="$1" rel
  for rel in services/documents.js routes/issues.js; do
    cp -p "$HP/${which}/${rel}" "$DIST/${rel}"
  done
  sha256sum "$DIST/services/documents.js" "$DIST/routes/issues.js" | sed "s|^|   sha256 |"
}

ensure_session() {
  step "ensuring the rehearsal board session exists"
  rm -f "$COOKIE"
  local body
  body="$(curl -s -m 20 -c "$COOKIE" -X POST "${API}/auth/sign-up/email" -H "$CT" \
    -d "{\"email\":\"${EMAIL}\",\"password\":\"${PASSWORD}\",\"name\":\"DIG2366\"}")"
  if printf '%s' "$body" | grep -q '"token"'; then
    log "   created board account ${EMAIL}"
  else
    log "   board account ${EMAIL} already exists, signing in"
    body="$(curl -s -m 20 -c "$COOKIE" -X POST "${API}/auth/sign-in/email" -H "$CT" \
      -d "{\"email\":\"${EMAIL}\",\"password\":\"${PASSWORD}\"}")"
    printf '%s' "$body" | grep -q '"token"' \
      && log "   signed in" \
      || { log "   FAILED to authenticate: $(printf '%s' "$body" | head -c 200)"; exit 1; }
  fi

  local uid role
  uid="$(psql_q "select id from \"user\" where email = '${EMAIL}';")"
  role="$(psql_q "select role from instance_user_roles where user_id = '${uid}';")"
  if [ "$role" != "instance_admin" ]; then
    psql_q "insert into instance_user_roles (id,user_id,role,created_at,updated_at)
            select gen_random_uuid(), '${uid}', 'instance_admin', now(), now()
            where not exists (select 1 from instance_user_roles where user_id = '${uid}');" >/dev/null
    log "   granted instance_admin to ${uid} (rehearsal database only)"
  else
    log "   board account already holds instance_admin"
  fi
  curl -s -m 20 -b "$COOKIE" -o /dev/null -w '   get-session http=%{http_code}\n' "${API}/auth/get-session"

  local companies body
  companies="$(curl -s -m 20 -b "$COOKIE" -H "Origin: http://127.0.0.1:${PORT}" -H "$FETCH" "${API}/companies")"
  COMPANY="$(printf '%s' "$companies" | python3 -c 'import json,sys
d=json.load(sys.stdin); print(d[0]["id"] if d else "")' 2>/dev/null)"
  if [ -z "$COMPANY" ]; then
    body="$(curl -s -m 20 -b "$COOKIE" -H "Origin: http://127.0.0.1:${PORT}" -H "$FETCH" -H "$CT" \
      -X POST "${API}/companies" -d '{"name":"DIG-2366 rehearsal"}')"
    COMPANY="$(printf '%s' "$body" | python3 -c 'import json,sys
d=json.load(sys.stdin); print(d.get("id",""))' 2>/dev/null)"
    log "   created rehearsal company ${COMPANY}"
  fi
  [ -n "$COMPANY" ] || { log "   FAILED to obtain a company for ${EMAIL}"; exit 1; }
  log "   company ${COMPANY}"
}

phase() {
  local tag="$1" which="$2"
  step "phase ${tag} — bundle files installed from ${which}/"
  install_files "$which"
  boot "$tag"

  local out="$RESULTS/${tag}.txt" issue
  {
    printf '# DIG-2366 rehearsal, phase %s, files taken from %s/\n' "$tag" "$which"
    printf '# booted %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    "$HERE/harness.sh" "$tag" "$API" "$COOKIE" "$COMPANY"
  } > "$out"

  issue="$(sed -n 's/^issue_id_for_db=//p' "$out")"
  "$HERE/db-counts.sh" "$PGPORT" "$issue" >> "$out"

  log "   transcript -> ${out}"
  halt "$tag"
}

step "phase 0 — boot for session setup (patched bytes, no measurements taken)"
install_files patched >/dev/null
boot setup
ensure_session
halt setup

phase control baseline
phase patched  patched

step "leaving the rehearsal store on the patched bytes"
install_files patched

step "differential verdict"
"$HERE/compare.sh"
