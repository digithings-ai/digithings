#!/usr/bin/env bash
# Build digichat into digithingschatregistry from a clean git archive.
# Avoids az acr build failing on .git/fsmonitor--daemon.ipc sockets.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

REGISTRY="${ACR_NAME:-digithingschatregistry}"
RG="${ACR_RG:-digithings-rg}"
TAG="${IMAGE_TAG:-phase3-preview}"

HOSTS_FILE="${EMBED_HOSTS_FILE:-frontend/digichat/embed-hosts.txt}"
BASE_HOSTS=$(grep -v '^\s*#' "$HOSTS_FILE" | grep -v '^\s*$' | paste -sd, -)
EMBED_HOSTS="${DIGICHAT_EMBED_HOSTS:-digithings.ai,www.digithings.ai,${BASE_HOSTS}}"

TMP=$(mktemp -d /tmp/digichat-acr-XXXXXX)
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

echo "Packing clean tree → $TMP"
git archive HEAD | tar -x -C "$TMP"

echo "Building ${REGISTRY}.azurecr.io/digichat:${TAG}"
echo "DIGICHAT_EMBED_HOSTS=${EMBED_HOSTS}"
(
  cd "$TMP"
  az acr build \
    --registry "$REGISTRY" \
    --resource-group "$RG" \
    --image "digichat:${TAG}" \
    --image digichat:latest \
    --file frontend/digichat/Dockerfile \
    --build-arg "DIGICHAT_EMBED_HOSTS=${EMBED_HOSTS}" \
    .
)

echo "Done. Update ACA with:"
echo "  az containerapp update -n digichat -g digithings-rg --image ${REGISTRY}.azurecr.io/digichat:${TAG}"
