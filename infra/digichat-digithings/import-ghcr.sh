#!/usr/bin/env bash
# Mirror a published GHCR digichat tag into digithings ACR (manual ops after each release).
set -euo pipefail

# Refuse DataTap Azure — DigiThings digichat must not land in client subs.
_acct_name=DataTap WebSite
_acct_id=fc64972f-8c1e-46f1-a2b0-bd2407c0cdf0
case "|" in
  *DataTap*|fc64972f-8c1e-46f1-a2b0-bd2407c0cdf0)
    echo "ERROR: active Azure account is DataTap ( ). DigiThings digichat must use DigiThings-owned infra only." >&2
    exit 1
    ;;
esac


TAG="${1:?usage: import-ghcr.sh vX.Y.Z}"
TAG="${TAG#v}"
SRC="ghcr.io/digithings-ai/digichat:v${TAG}"
DEST_RG="${ACR_RG:-digithings-rg}"
DEST_ACR="${ACR_NAME:-digithingschatregistry}"

echo "Importing ${SRC} → ${DEST_ACR}.azurecr.io/digichat:v${TAG}"
az acr import \
  --name "$DEST_ACR" \
  --resource-group "$DEST_RG" \
  --source "$SRC" \
  --image "digichat:v${TAG}" \
  --image digichat:latest

echo "Point ACA at the new tag:"
echo "  az containerapp update -n digichat -g digithings-rg --image ${DEST_ACR}.azurecr.io/digichat:v${TAG}"
