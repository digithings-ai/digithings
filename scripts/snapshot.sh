#!/usr/bin/env bash
# snapshot.sh — take a verified pg_dump of the Supabase exit databases.
#
# Ticket DIG-2888 (ticket 0, the gate for every other data-work ticket).
# Chris runs this by hand: it prompts for any database URL it was not given,
# and it never writes a URL or a password to disk, to the archive, or to the
# log. Supabase stays live and untouched; this script only READS.
#
# What it does, per database:
#   1. resolve pg_dump/pg_restore and refuse anything older than major 17
#   2. pg_dump --format=custom into $OUT_DIR/<ts>/<target>.dump
#   3. pg_restore -l  -> the archive table of contents (the brief's verify step)
#   4. shasum -a 256  -> SHA256SUMS, verifiable later with `shasum -c`
#   5. copy the whole set to R2 at backups/supabase-exit/<ts>/ and read each
#      object back to compare SHA-256
#
# Exit codes (distinct on purpose — a caller must be able to tell them apart):
#   0  snapshot written, verified, copied to R2 and read back matching
#   1  a stage failed; nothing is trusted
#   2  the LOCAL snapshot is complete and verified, but the R2 copy was
#      skipped because R2 credentials were missing (same fail-closed meaning
#      as .github/workflows/pipeline-checkpoint-archive.yml)
#   3  the local pg client tools are older than major 17 — refused before
#      anything is dumped
#
# It never deletes: no retention, no pruning, no cleanup.
#
# Usage:
#   scripts/snapshot.sh [core|twelve-x|all]        # default: all
#   SNAPSHOT_OUT_DIR=... scripts/snapshot.sh all
#
# Environment:
#   CORE_POSTGRES_URI   read-only DSN for the digithings core database
#                       (same name digiquant/ops/checkpoint_archive.py uses)
#   SUPABASE_DB_URL     read-only DSN for the twelve-x database
#                       (session-pooler URI on port 6543; the name
#                       .github/workflows/db-migrate.yml uses there)
#   R2_ACCOUNT_ID       Cloudflare account id  } all four are required for
#   R2_BUCKET           bucket name (digithings-archive) } the R2 copy; if
#   R2_ACCESS_KEY_ID    access key id                     } any is absent
#   R2_SECRET_ACCESS_KEY secret access key                } exit is 2
#   SNAPSHOT_PG_BIN     override the pg client tool directory
#   SNAPSHOT_OUT_DIR    override the destination (default ~/Backups/supabase-exit)

set -euo pipefail
umask 077

readonly REQUIRED_PG_MAJOR=17
readonly R2_PREFIX="backups/supabase-exit"
readonly PG_MAJOR_FLOOR=10

die() { printf 'snapshot.sh: %s\n' "$*" >&2; exit 1; }
note() { printf '==> %s\n' "$*"; }

# ---------------------------------------------------------------- arguments --

usage() { sed -n '2,50p' "$0" | sed 's/^# \{0,1\}//'; }

target_env_for() {
  case "$1" in
    core) printf 'CORE_POSTGRES_URI' ;;
    twelve-x) printf 'SUPABASE_DB_URL' ;;
    *) die "unknown target '$1'" ;;
  esac
}

TARGET=all
if [ "$#" -gt 0 ]; then
  case "$1" in
    core|twelve-x|all) TARGET="$1" ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "unexpected argument '$1'" ;;
  esac
fi

OUT_DIR="${SNAPSHOT_OUT_DIR:-$HOME/Backups/supabase-exit}"

# ------------------------------------------------------------- pg binaries ---
#
# PATH on this host resolves pg_dump to 16.15 while postgresql@17 is installed
# beside it, so the version is checked rather than trusted.

PG_BIN_DIR=""
for candidate in \
  "${SNAPSHOT_PG_BIN:-}" \
  /opt/homebrew/opt/postgresql@17/bin \
  /opt/homebrew/opt/postgresql@18/bin \
  /usr/local/opt/postgresql@17/bin
do
  [ -n "$candidate" ] && [ -x "$candidate/pg_dump" ] || continue
  PG_BIN_DIR="$candidate"
  break
done
if [ -z "$PG_BIN_DIR" ]; then
  PG_BIN_DIR="$(dirname "$(command -v pg_dump || true)")"
  [ -x "$PG_BIN_DIR/pg_dump" ] || {
    printf 'snapshot.sh: no pg_dump found; install postgresql@%s or set SNAPSHOT_PG_BIN\n' \
      "$REQUIRED_PG_MAJOR" >&2
    exit 3
  }
fi
PG_DUMP="$PG_BIN_DIR/pg_dump"
PG_RESTORE="$PG_BIN_DIR/pg_restore"

if [ ! -x "$PG_RESTORE" ]; then
  printf 'snapshot.sh: pg_restore not found next to pg_dump (%s)\n' "$PG_DUMP" >&2
  exit 3
fi

pg_major() {
  # "pg_dump (PostgreSQL) 17.11" -> 17
  "$1" --version 2>/dev/null | sed -n 's/.*[^0-9]\([0-9][0-9]*\)\.[0-9].*/\1/p' | head -1
}
PG_MAJOR="$(pg_major "$PG_DUMP")"
[ -n "$PG_MAJOR" ] || die "cannot read a major version from '$PG_DUMP --version'"
if [ "$PG_MAJOR" -lt "$PG_MAJOR_FLOOR" ] || [ "$PG_MAJOR" -lt "$REQUIRED_PG_MAJOR" ]; then
  printf 'snapshot.sh: pg_dump major %s at %s; this script requires %s or newer\n' \
    "$PG_MAJOR" "$PG_DUMP" "$REQUIRED_PG_MAJOR" >&2
  exit 3
fi
note "pg client: $PG_DUMP (major $PG_MAJOR), pg_restore: $PG_RESTORE"

PYTHON="$(command -v python3 || true)"
[ -n "$PYTHON" ] || die "python3 is required (it is the only R2 client on this host)"

# --------------------------------------------------------------------- DSN ---

read_dsn() {
  # Echoes the DSN on stdout and nothing else. The value is never logged.
  local var="$1" target="$2" value
  value="$(printenv "$var" || true)"
  if [ -n "$value" ]; then
    printf '%s' "$value"
    return 0
  fi
  if [ ! -t 0 ]; then
    die "$var is not set and stdin is not a terminal; cannot prompt for the $target DSN"
  fi
  printf '%s is not set. Paste the read-only %s DSN (input hidden, not stored): ' \
    "$var" "$target" >&2
  IFS= read -r -s value </dev/tty || die "no DSN supplied for $target"
  printf '\n' >&2
  [ -n "$value" ] || die "no DSN supplied for $target"
  printf '%s' "$value"
}

export_dsn_parts() {
  # Splits a DSN into libpq environment variables so the password never
  # appears in argv: `ps` shows another user's full command line on macOS.
  # The pairs come back on a pipe rather than a command line, so they are
  # never in this process's argv either.
  local line key value
  while IFS= read -r line; do
    key="${line%%=*}"
    value="${line#*=}"
    [ -n "$key" ] || continue
    export "$key=$value"
  done < <("$PYTHON" - "$1" <<'PYEOF'
import sys
from urllib.parse import urlparse, unquote, parse_qsl

raw = sys.argv[1].strip()
if "://" not in raw:
    raw = "postgresql://" + raw
p = urlparse(raw)
if not p.hostname:
    sys.exit("snapshot.sh: the DSN has no host")
out = {
    "PGHOST": p.hostname or "",
    "PGPORT": str(p.port or 5432),
    "PGUSER": unquote(p.username or ""),
    "PGPASSWORD": unquote(p.password or ""),
    "PGDATABASE": unquote((p.path or "/").lstrip("/")),
}
if not out["PGDATABASE"]:
    sys.exit("snapshot.sh: the DSN has no database name")
opts = dict(parse_qsl(p.query))
if opts.get("sslmode"):
    out["PGSSLMODE"] = opts["sslmode"]
for key, value in out.items():
    print(f"{key}={value}")
PYEOF
  ) || die "could not read a usable DSN"
  [ -n "${PGDATABASE:-}" ] || die "the DSN did not yield a database name"
}

# ------------------------------------------------------------------ R2 copy --

r2_ready() {
  [ -n "${R2_ACCOUNT_ID:-}" ] && [ -n "${R2_BUCKET:-}" ] \
    && [ -n "${R2_ACCESS_KEY_ID:-}" ] && [ -n "${R2_SECRET_ACCESS_KEY:-}" ]
}

upload_to_r2() {
  # $1 = local dir, $2 = destination prefix inside the bucket.
  # Prints nothing about the objects' contents; reads every object back and
  # compares SHA-256, so a silent truncation cannot pass as a copy.
  "$PYTHON" - "$1" "$2" "$R2_PREFIX" <<'PYEOF'
import hashlib, io, os, sys
from pathlib import Path

src, dest, prefix_root = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
key_prefix = f"{prefix_root}/{dest}"

import boto3  # deferred: only the R2 stage needs it

s3 = boto3.client(
    "s3",
    endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
    aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
)
bucket = os.environ["R2_BUCKET"]

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

files = sorted(p for p in src.iterdir() if p.is_file())
if not files:
    sys.exit(f"snapshot.sh: nothing to upload from {src}")

for path in files:
    key = f"{key_prefix}/{path.name}"
    data = path.read_bytes()
    want = hashlib.sha256(data).hexdigest()
    s3.upload_fileobj(io.BytesIO(data), bucket, key)
    buf = io.BytesIO()
    s3.download_fileobj(bucket, key, buf)
    got = hashlib.sha256(buf.getvalue()).hexdigest()
    if got != want:
        sys.exit(f"snapshot.sh: R2 read-back mismatch for {key}")
    print(f"    r2 ok  {key}  {len(data)} bytes  sha256 {want[:16]}…")
PYEOF
}

# ------------------------------------------------------------------- driver --

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="$OUT_DIR/$STAMP"
mkdir -p "$RUN_DIR"

TARGETS=()
RECORDS=()
case "$TARGET" in
  all) TARGETS=(core twelve-x) ;;
  *) TARGETS=("$TARGET") ;;
esac

for t in "${TARGETS[@]}"; do
  dsn="$(read_dsn "$(target_env_for "$t")" "$t")"
  export_dsn_parts "$dsn"
  unset dsn

  dump="$RUN_DIR/$t.dump"
  note "$t: pg_dump -> $dump"
  "$PG_DUMP" --format=custom --no-owner --no-privileges --dbname="$PGDATABASE" -f "$dump" \
    || die "pg_dump failed for $t"

  list="$RUN_DIR/$t.dump.list"
  note "$t: pg_restore -l -> $list"
  "$PG_RESTORE" -l "$dump" > "$list" || die "pg_restore -l failed for $t"
  entries="$(grep -cv '^;' "$list" || true)"
  [ "${entries:-0}" -gt 0 ] || die "pg_restore -l listed no entries for $t — archive is unusable"
  note "$t: $entries table-of-contents entries"

  ( cd "$RUN_DIR" && shasum -a 256 "$t.dump" "$t.dump.list" > SHA256SUMS )
  ( cd "$RUN_DIR" && shasum -a 256 -c SHA256SUMS >/dev/null ) \
    || die "local SHA256 verification failed for $t"

  record="$("$PYTHON" - "$t" "$dump" "$list" "$entries" <<'PYEOF'
import hashlib, json, sys
from pathlib import Path

target, dump, list_path, entries = sys.argv[1:5]

def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

print(json.dumps({
    "target": target,
    "archive": {
        "file": f"{target}.dump",
        "format": "custom",
        "bytes": Path(dump).stat().st_size,
        "sha256": sha256(dump),
    },
    "table_of_contents": {
        "file": f"{target}.dump.list",
        "entries": int(entries),
        "sha256": sha256(list_path),
    },
}, sort_keys=True))
PYEOF
)" || die "could not build the manifest record for $t"
  RECORDS+=("$record")


  unset PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE PGSSLMODE
done

"$PYTHON" - "$RUN_DIR" "$STAMP" "$PG_MAJOR" "${RECORDS[@]}" <<'PYEOF'
import json, sys
from datetime import datetime, timezone
from pathlib import Path

run_dir, stamp, pg_major, *records = sys.argv[1:]
manifest = {
    "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "stamp": stamp,
    "pg_dump_major": int(pg_major),
    "producer": "scripts/snapshot.sh (DIG-2888 ticket 0)",
    "databases": [json.loads(r) for r in records],
}
(Path(run_dir) / "manifest.json").write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n"
)
PYEOF

note "local snapshot verified: $RUN_DIR"
( cd "$RUN_DIR" && ls -1 ) | sed 's/^/    /'

if ! r2_ready; then
  printf 'snapshot.sh: R2 credentials missing (need R2_ACCOUNT_ID, R2_BUCKET, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY)\n' >&2
  printf 'snapshot.sh: the LOCAL snapshot above is complete and verified; only the copy is missing\n' >&2
  exit 2
fi

note "copying to R2 $R2_BUCKET/$R2_PREFIX/$STAMP/"
upload_to_r2 "$RUN_DIR" "$STAMP"
note "done"
exit 0
