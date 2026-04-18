#!/usr/bin/env bash
# Run SQL against the linked Supabase project or a Postgres URL (Supabase CLI).
#
#   # Option A — direct Postgres URI (Dashboard → Settings → Database → URI)
#   export DATABASE_URL='postgresql://postgres.[ref]:[PASSWORD]@aws-0-[region].pooler.supabase.com:6543/postgres'
#   ./scripts/db-query.sh scripts/sql/audit_activity_coverage.sql
#
#   # Option B — link once (stores project ref under .supabase/)
#   npx supabase link --project-ref YOUR_REF -p YOUR_DB_PASSWORD --yes
#   ./scripts/db-query.sh scripts/sql/audit_activity_coverage.sql
#
#   # Option C — local CLI database (no link): cp config/local.env.example config/local.env
#   ./scripts/db-query.sh scripts/sql/audit_activity_coverage.sql
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  cat <<'EOF'
Usage: db-query.sh path/to/file.sql

Run SQL via Supabase CLI (db query). Resolves connection in order:
  1. DATABASE_URL in the environment
  2. config/local.env (copy from config/local.env.example)
  3. Linked project: npx supabase link (creates .supabase/)

Examples:
  export DATABASE_URL='postgresql://...'
  ./scripts/db-query.sh scripts/sql/audit_activity_coverage.sql

  ./scripts/db-query.sh scripts/sql/audit_activity_coverage.sql
EOF
  exit 0
fi

SQL_FILE="${1:?Usage: $0 path/to/file.sql (use --help for details)}"

if [[ -z "${DATABASE_URL:-}" && -f "$ROOT/config/local.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/config/local.env"
  set +a
fi

if [[ -n "${DATABASE_URL:-}" ]]; then
  exec npx --yes supabase@latest db query --db-url "$DATABASE_URL" -f "$SQL_FILE" -o table --agent=no
fi

if [[ -d "$ROOT/.supabase" ]]; then
  exec npx --yes supabase@latest db query --linked -f "$SQL_FILE" -o table --agent=no
fi

echo "No DATABASE_URL and no linked project (.supabase/). See comments in $0" >&2
exit 1
