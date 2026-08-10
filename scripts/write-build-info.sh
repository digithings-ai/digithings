#!/usr/bin/env bash
# Emit the deploy build stamp that the daily site smoke check reads (#1759).
#
# Nothing in the digiquant.io static export carried a build identity, so a
# Cloudflare Pages project that stops producing deployments is invisible from
# outside: every probed URL keeps serving the last good build with a 200 and a
# fresh `date:` header. A frozen deploy was therefore *discovered* (someone
# noticed the dashboard was old) rather than *detected*. This writes a small
# JSON file into the export root so `smoke-site.yml` can read *when* the live
# bundle was built instead of only *that* it answers.
#
# Bash-only on purpose. This runs inside the Cloudflare Pages build image, where
# node is guaranteed (npm/next) but a `python3` interpreter is not; a stamp
# writer that breaks the production build would be strictly worse than no stamp.
#
# Usage: bash scripts/write-build-info.sh <output-path> <site>
set -euo pipefail

out="${1:?usage: write-build-info.sh <output-path> <site>}"
site_raw="${2:?usage: write-build-info.sh <output-path> <site>}"

# Values land in a JSON string. They are commit shas, branch names and a
# hostname, so strip anything outside a conservative allowlist rather than
# escaping: one stray quote or backslash out of the build environment would
# emit invalid JSON, and the freshness probe would report a malformed stamp on
# a perfectly healthy deploy. Length-capped for the same reason.
_sanitize() {
  printf '%s' "${1-}" | tr -cd 'A-Za-z0-9._/@+-' | cut -c1-200
}

_first_nonempty() {
  local value
  for value in "$@"; do
    if [ -n "$value" ]; then
      printf '%s' "$value"
      return 0
    fi
  done
  printf 'unknown'
}

# Cloudflare Pages exports CF_PAGES_*; GitHub Actions exports GITHUB_*; a local
# run falls back to git. `git rev-parse` is allowed to fail (shallow checkout,
# tarball build) — the stamp degrades to "unknown", it never aborts the build.
commit="$(_first_nonempty \
  "$(_sanitize "${CF_PAGES_COMMIT_SHA:-}")" \
  "$(_sanitize "${GITHUB_SHA:-}")" \
  "$(_sanitize "$(git rev-parse HEAD 2>/dev/null || true)")")"
branch="$(_first_nonempty \
  "$(_sanitize "${CF_PAGES_BRANCH:-}")" \
  "$(_sanitize "${GITHUB_REF_NAME:-}")" \
  "$(_sanitize "$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)")")"
site="$(_first_nonempty "$(_sanitize "$site_raw")")"

if [ "${CF_PAGES:-}" = "1" ]; then
  builder="cloudflare-pages"
elif [ "${GITHUB_ACTIONS:-}" = "true" ]; then
  builder="github-actions"
else
  builder="local"
fi

# Second resolution, always UTC, always suffixed Z — `datetime.fromisoformat`
# in the freshness checker parses this directly.
built_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

mkdir -p "$(dirname "$out")"
cat >"$out" <<JSON
{
  "site": "$site",
  "commit": "$commit",
  "branch": "$branch",
  "builder": "$builder",
  "built_at": "$built_at"
}
JSON

echo "build stamp: $site $branch@$commit built_at=$built_at builder=$builder -> $out"
