#!/usr/bin/env bash
# Client deploy: validate -> upload R2 seeds -> write the KV tenant doc -> (own Workers) wrangler deploy.
# TEMPLATE STUB: refuses to run. A client repo wires each step once Guard has issued
# a scoped Cloudflare token (KV tenant namespace + R2 seeds prefix + client-<client-slug>-* Workers).
set -euo pipefail
env="${1:-}"
case "$env" in staging|prod) ;; *) echo "usage: deploy/deploy.sh staging|prod" >&2; exit 2;; esac
if [ "$env" = prod ]; then
  tag="$(git describe --exact-match --tags HEAD 2>/dev/null || true)"
  [ -n "$tag" ] || { echo "refused: prod deploys run only from a release tag" >&2; exit 1; }
  git verify-tag "$tag" || { echo "refused: tag $tag is not signed by an allowed signer" >&2; exit 1; }
fi
echo "refused: deploy/deploy.sh is a template stub; nothing was changed" >&2
exit 1
