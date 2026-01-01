#!/usr/bin/env bash
# Local replacement for .github/workflows/build-cloudflare-workers.yml
# (disabled on GitHub; Actions minutes exhausted).
#
# Builds every Cloudflare Worker with `wrangler deploy --dry-run`.
# Credential-free and Docker-free: --dry-run needs no Cloudflare login, and
# --containers-rollout=none skips the container image build that otherwise
# demands a Docker CLI even in dry-run mode.
#
# Usage: bash scripts/local-deploy/build_workers.sh [app ...]
#   No args: every apps/* workspace that ships a wrangler.toml AND pins
#   wrangler in devDependencies (the same derivation as
#   tests/scripts/test_worker_build_matrix.py, so the set cannot drift).
#   Names are directory names under apps/, not package names.
set -euo pipefail
cd "$(dirname "$0")/../.."

derive_apps() {
  for d in apps/*/; do
    app="${d#apps/}"; app="${app%/}"
    if [ -f "apps/$app/wrangler.toml" ] && [ -f "apps/$app/package.json" ] \
      && grep -q '"wrangler"' "apps/$app/package.json"; then
      echo "$app"
    fi
  done
}

if [ "$#" -gt 0 ]; then
  APPS=("$@")
else
  mapfile -t APPS < <(derive_apps)
fi

if [ "${#APPS[@]}" -eq 0 ]; then
  echo "ERROR: no Worker apps derived; refusing a vacuous green run." >&2
  exit 1
fi

echo "Building ${#APPS[@]} Worker(s): ${APPS[*]}"
fail=0
for app in "${APPS[@]}"; do
  if [ ! -f "apps/$app/wrangler.toml" ]; then
    echo "FAIL apps/$app: no wrangler.toml." >&2
    fail=1
    continue
  fi
  outdir="${TMPDIR:-/tmp}/wrangler-dry-run-$app-$$"
  if (cd "apps/$app" && npm exec -- wrangler deploy --dry-run --containers-rollout=none --outdir "$outdir"); then
    echo "PASS $app"
  else
    echo "FAIL $app (see output above)." >&2
    fail=1
  fi
  rm -rf "$outdir"
done

[ "$fail" -eq 0 ] || { echo "ERROR: $fail app(s) failed to build." >&2; exit 1; }
echo "All Worker builds passed."
