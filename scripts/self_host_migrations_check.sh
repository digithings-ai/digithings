#!/usr/bin/env bash
# Apply the digiquant Supabase migration chain to a CLEAN, DISPOSABLE PostgreSQL
# database, in filename order, and prove every file applies.
#
# This is parity arm (b) of the self-host reference stack plan
# (DIG-2758 plan section 8): "supabase db reset on clean PG17 applies all
# migrations". It does NOT use the supabase CLI and does NOT need Docker:
# `digiquant/supabase/config.toml` pins major_version = 17, and the chain needs
# only `pgcrypto` (the one CREATE EXTENSION in the whole chain) and guards its
# pg_cron use behind a pg_extension check in 061_checkpointer_retention.sql.
#
# Two deliberate non-features, both so the check cannot lie:
#
#   * It REJECTS any target database whose name does not start with
#     `parity_` (override with PARITY_DB_PREFIX). This host already runs three
#     other people's PostgreSQL servers -- including Paperclip's own board
#     database on port 54329 and another seat's DIG-1781 cluster on 55432 --
#     so "the port answers" is not evidence that the server is ours.
#   * `migrations/cutover/` is EXCLUDED. Those files are staged on purpose and
#     say so in their own headers ("NOT AUTO-APPLIED").
#
# Modes:
#   --plan        print the ordered migration list and every guard's verdict,
#                 then exit. No database connection. Used by the test suite.
#   (default)     create the target database, apply the chain, report.
#
# Environment (standard libpq, so CI's `services:` block feeds it directly):
#   PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE
#   PARITY_DB_PREFIX   default `parity_`
#   PARITY_KEEP_DB     set to 1 to skip dropping the database on success
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
migrations_dir="${PARITY_MIGRATIONS_DIR:-$repo_root/digiquant/supabase/migrations}"
db_prefix="${PARITY_DB_PREFIX:-parity_}"
db_name="${PGDATABASE:-parity_migrations_check}"
psql_bin="${PARITY_PSQL:-psql}"
createdb_bin="${PARITY_CREATEDB:-createdb}"
dropdb_bin="${PARITY_DROPDB:-dropdb}"
plan_only=0
continue_on_error=""
json_out=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --plan) plan_only=1 ;;
    --continue-on-error) continue_on_error=1 ;;
    --json-out) json_out="$2"; shift ;;
    --help|-h) sed -n '2,30p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

fail() { echo "SELF-HOST MIGRATIONS CHECK: FAIL: $*" >&2; exit 1; }
note() { echo "  $*"; }

# --- guard 1: the database name says this database is disposable -------------
case "$db_name" in
  "$db_prefix"*) : ;;
  *) fail "refusing to touch database '$db_name': a self-host parity apply is
    destructive and must only ever run against a disposable database whose name
    starts with '$db_prefix'. This host runs other people's PostgreSQL servers
    (Paperclip's board DB, other seats' clusters); an empty-looking answer from
    a port you do not own is not evidence that it is empty." ;;
esac

# --- guard 2: the migrations directory exists --------------------------------
[ -d "$migrations_dir" ] || fail "migrations directory not found: $migrations_dir"

# --- guard 3: cutover/ is staged, not applied --------------------------------
if [ -d "$migrations_dir/cutover" ]; then
  staged="$(ls -1 "$migrations_dir/cutover"/*.sql 2>/dev/null | wc -l | tr -d ' ')"
  note "excluded $staged staged file(s) in migrations/cutover/ (NOT AUTO-APPLIED by design)"
fi

# --- the ordered chain ---------------------------------------------------------
# shellcheck disable=SC2012
chain="$(ls -1 "$migrations_dir"/*.sql 2>/dev/null | sed "s|^$migrations_dir/||" | LC_ALL=C sort)"
[ -n "$chain" ] || fail "no .sql files in $migrations_dir"
count="$(printf '%s\n' "$chain" | wc -l | tr -d ' ')"

bad_name="$(printf '%s\n' "$chain" | grep -vE '^[0-9]{3}_[a-z0-9_]+\.sql$' || true)"
if [ -n "$bad_name" ]; then
  printf 'migration filenames must be NNN_lower_snake.sql:\n%s\n' "$bad_name" >&2
  fail "naming guard"
fi

dupes="$(printf '%s\n' "$chain" | sed 's/_.*//' | LC_ALL=C sort | uniq -d || true)"
[ -z "$dupes" ] || { printf 'duplicate numeric prefixes: %s\n' "$dupes" >&2; fail "ordering guard"; }

# Lexical order must equal numeric order, or "sort by name" is not "apply in
# order" and the whole check would be a fiction.
if ! diff <(printf '%s\n' "$chain") \
          <(printf '%s\n' "$chain" | LC_ALL=C sort -t_ -k1,1n) >/dev/null; then
  fail "lexical and numeric order differ; apply order is not filename order"
fi

first="$(printf '%s\n' "$chain" | head -1)"
last="$(printf '%s\n' "$chain" | tail -1)"

if [ "$plan_only" -eq 1 ]; then
  echo "SELF-HOST MIGRATIONS CHECK: PLAN"
  note "migrations_dir $migrations_dir"
  note "db_name        $db_name (prefix guard ok)"
  note "chain          $count migrations, $first .. $last"
  note "cutover/       excluded"
  exit 0
fi

command -v "$psql_bin" >/dev/null 2>&1 || fail "$psql_bin not found on PATH"

# Probe the maintenance database, NOT the target: the target is created a few
# lines below and does not exist yet on a clean server, so probing it here would
# fail on a perfectly healthy cluster.
maintenance_db="${PARITY_MAINTENANCE_DB:-postgres}"
server_version="$("$psql_bin" -X -q -At -d "$maintenance_db" -c 'show server_version;' 2>/dev/null || true)"
[ -n "$server_version" ] || fail "cannot reach the target PostgreSQL server on $maintenance_db (check PGHOST/PGPORT/PGUSER)"

config_major="$(sed -n 's/^[[:space:]]*major_version *= *\([0-9][0-9]*\).*/\1/p' \
  "$repo_root/digiquant/supabase/config.toml" 2>/dev/null | head -1 || true)"
server_major="${server_version%%.*}"
echo "SELF-HOST MIGRATIONS CHECK"
note "server         PostgreSQL $server_version (digiquant/supabase/config.toml pins major_version = ${config_major:-unknown})"
if [ -n "$config_major" ] && [ "$config_major" != "$server_major" ]; then
  note "NOTE: server major $server_major != pinned $config_major. The chain is plain"
  note "      PostgreSQL, so this proves the chain but NOT the pinned version."
fi
note "db_name        $db_name"
note "chain          $count migrations, $first .. $last"

log_dir="$(mktemp -d "${TMPDIR:-/tmp}/self-host-migrations.XXXXXX")"
cleanup() {
  if [ "${PARITY_KEEP_DB:-0}" != "1" ]; then
    "$dropdb_bin" --if-exists "$db_name" >/dev/null 2>&1 || true
  fi
  rm -rf "$log_dir"
}
trap cleanup EXIT

"$dropdb_bin" --if-exists "$db_name" >/dev/null 2>&1 || true
"$createdb_bin" "$db_name" || fail "could not create $db_name"

# --- guard 4: the Supabase surface the chain depends on ----------------------
# Measured 2026-10-10 against the real chain: `anon` 540 refs, `service_role`
# 488, `authenticated` 483 (21 files GRANT to them), and `auth.uid()` is called
# in RLS policies in 098/105/107/108/109/117 -- PostgreSQL validates a policy
# expression at CREATE POLICY time, so the function has to exist before the
# chain runs. `supabase db reset` gets these from Supabase's own bootstrap; a
# plain postgres image gets nothing.
#
# This bootstrap reproduces THAT bootstrap and nothing else. auth.uid() is a
# stub, because this check's question is "does the chain apply in order on a
# clean database", not "does authentication work". The stub is the reason this
# is a migration-apply check and not a substitute for `supabase db reset`.
roles="$(printf '%s\n' "$chain" | xargs grep -hoE '\b(to|owner to) (anon|authenticated|service_role)\b' 2>/dev/null \
  | awk '{print $NF}' | LC_ALL=C sort -u | tr '\n' ' ' || true)"
note "supabase roles referenced by the chain: ${roles:-none}"
"$psql_bin" -X -q -v ON_ERROR_STOP=1 -d "$db_name" <<'BOOTSTRAP_SQL'
DO $boot$
DECLARE r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
      EXECUTE format('CREATE ROLE %I NOLOGIN', r);
    END IF;
  END LOOP;
END
$boot$;
CREATE SCHEMA IF NOT EXISTS auth;
CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid
  LANGUAGE sql STABLE AS $$ SELECT NULL::uuid::uuid $$;
BOOTSTRAP_SQL
note "bootstrap      roles anon/authenticated/service_role (NOLOGIN) + stub auth.uid()"

applied=0
failed_json=""
: >"$log_dir/failures.txt"
while IFS= read -r m; do
  if ! "$psql_bin" -X -q -v ON_ERROR_STOP=1 --single-transaction \
        -f "$migrations_dir/$m" >"$log_dir/$m.log" 2>&1; then
    # Quotes and backslashes are folded to apostrophes so the JSON report stays
    # valid without an escaping helper. The text is diagnostic only.
    err="$(grep -m1 'ERROR:' "$log_dir/$m.log" | sed 's/^psql:[^ ]*:[0-9]*: //' | tr -d '\\' | tr '"' "'" || true)"
    if [ -z "$continue_on_error" ]; then
      echo "  FAILED on $m" >&2
      tail -25 "$log_dir/$m.log" >&2
      fail "migration $m did not apply (applied=$applied of $count)"
    fi
    note "FAILED  $m  ${err:-see log}"
    printf '%s\t%s\n' "$m" "${err:-unknown error}" >>"$log_dir/failures.txt"
    continue
  fi
  applied=$((applied + 1))
done <<EOF
$chain
EOF

tables="$("$psql_bin" -X -q -At -d "$db_name" \
  -c "select count(*) from information_schema.tables where table_schema='public';")"
note "applied        $applied/$count migrations, one transaction each"
note "public tables  $tables"

if [ -n "$json_out" ]; then
  "$psql_bin" --version >/dev/null 2>&1 || true
  {
    printf '{\n'
    printf '  "serverVersion": "%s",\n' "$server_version"
    printf '  "pinnedMajorVersion": "%s",\n' "${config_major:-}"
    printf '  "database": "%s",\n' "$db_name"
    printf '  "totalMigrations": %s,\n' "$count"
    printf '  "appliedMigrations": %s,\n' "$applied"
    printf '  "excludedStaged": %s,\n' "${staged:-0}"
    printf '  "failures": ['
    first_row=1
    while IFS=$'\t' read -r fm ferr; do
      [ "$first_row" -eq 1 ] || printf ','
      first_row=0
      printf '\n    {"migration": "%s", "error": "%s"}' "$fm" "$ferr"
    done <"$log_dir/failures.txt"
    [ "$first_row" -eq 1 ] || printf '\n  '
    printf ']\n}\n'
  } >"$json_out"
  note "json           $json_out"
fi

if [ -s "$log_dir/failures.txt" ]; then
  note "RESULT: $(( $(wc -l <"$log_dir/failures.txt" | tr -d ' ') )) migration file(s) did not apply."
  note "Compare them against config/self-host/parity-baseline.json:"
  note "a NEW failure fails this check; a baseline entry that STOPPED failing also fails it."
  exit 1
fi

echo "SELF-HOST MIGRATIONS CHECK: PASS"
