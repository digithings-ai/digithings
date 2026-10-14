#!/usr/bin/env bash
# Local replacement for publish-digichat-image.yml and publish-digillm-image.yml
# (both disabled on GitHub; Actions minutes exhausted).
#
# DEFAULT BUILDS AND BOOT-PROBES BUT NEVER PUSHES. The image is loaded into
# the local Docker daemon, watched until it serves, and checked for the
# version and revision it was built as. Pushing needs --push AND a named
# approval (LOCAL_DEPLOY_APPROVED_BY, Chris for releases) AND a GHCR login.
#
# Usage:
#   bash scripts/local-deploy/publish_image.sh digichat [--tag digichat-vX.Y.Z | --ref <branch|sha>] [--push]
#   bash scripts/local-deploy/publish_image.sh digillm [--tag digillm-vX.Y.Z] [--push]
# With no tag/ref the head commit is built as a rehearsal image named
# :sha-<12 chars>. A rehearsal image never takes a release name.
set -euo pipefail
cd "$(dirname "$0")/../.."

IMAGE=""; TAG=""; REF=""; PUSH=0
for a in "$@"; do
  case "$a" in
    --push) PUSH=1 ;;
    --tag) WANT=tag ;;
    --ref) WANT=ref ;;
    --tag=*) TAG="${a#--tag=}" ;;
    --ref=*) REF="${a#--ref=}" ;;
    -*) echo "Unknown flag $a." >&2; exit 2 ;;
    *)
      if [ -z "$IMAGE" ]; then IMAGE="$a"
      elif [ "${WANT:-}" = "tag" ]; then TAG="$a"; WANT=""
      elif [ "${WANT:-}" = "ref" ]; then REF="$a"; WANT=""
      else echo "Unexpected argument $a." >&2; exit 2
      fi ;;
  esac
done
case "$IMAGE" in
  digichat|digillm) ;;
  *) echo "Usage: $0 [digichat|digillm] [--tag X | --ref R] [--push]" >&2; exit 2 ;;
esac
[ -z "$TAG" ] || [ -z "$REF" ] || { echo "ERROR: set --tag or --ref, not both." >&2; exit 1; }

LOGD="$HOME/.config/digithings/logs/local-deploy"
mkdir -p "$LOGD"
LOG="$LOGD/publish-$IMAGE-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee "$LOG") 2>&1

if [ "$IMAGE" = "digichat" ]; then
  REPO="ghcr.io/digithings-ai/digichat"
  DOCKERFILE="apps/digichat/Dockerfile"
  VERSION="$(node -p "require('./apps/digichat/package.json').version")"
  if [ -n "$TAG" ]; then
    [[ "$TAG" =~ ^digichat-v[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "ERROR: $TAG is not a digichat-vX.Y.Z release tag." >&2; exit 1; }
    [ "${TAG#digichat-v}" = "$VERSION" ] || { echo "ERROR: $TAG does not match apps/digichat/package.json ($VERSION)." >&2; exit 1; }
    COMMIT="$(git rev-list -n1 "$TAG" 2>/dev/null || true)"
    [ -n "$COMMIT" ] || { echo "ERROR: $TAG does not resolve to a commit." >&2; exit 1; }
    NAME="$REPO:v$VERSION"
  else
    COMMIT="$(git rev-parse HEAD)"
    NAME="$REPO:sha-$(git rev-parse --short=12 HEAD)"
  fi
  BUILD_ARGS=(--build-arg "DIGICHAT_VERSION=$VERSION" --build-arg "DIGICHAT_REVISION=$COMMIT")
  LABELS=(--label "org.opencontainers.image.revision=$COMMIT")
  HEALTH_PATH="/healthz"; VERSION_PATH="/api/health"
else
  REPO="ghcr.io/digithings-ai/digillm"
  DOCKERFILE="Dockerfile.digillm"
  if [ -n "$TAG" ]; then
    [[ "$TAG" =~ ^digillm-v([0-9]+\.[0-9]+\.[0-9]+)$ ]] || { echo "ERROR: bad tag $TAG." >&2; exit 1; }
    VERSION="${BASH_REMATCH[1]}"
    grep -q "image: ghcr.io/digithings-ai/digillm:${VERSION}" docker-compose.yml \
      || { echo "ERROR: docker-compose.yml does not pin digillm:${VERSION}." >&2; exit 1; }
    COMMIT="$(git rev-list -n1 "$TAG" 2>/dev/null || true)"
    [ -n "$COMMIT" ] || { echo "ERROR: $TAG does not resolve to a commit." >&2; exit 1; }
    NAME="$REPO:$VERSION"
  else
    [ -z "$REF" ] || echo "(digillm builds the working tree; --ref is informational only)"
    VERSION="ci"; COMMIT="$(git rev-parse HEAD)"
    NAME="digillm:ci"
  fi
  BUILD_ARGS=(--label "org.opencontainers.image.revision=$COMMIT")
  LABELS=()
  HEALTH_PATH="/health/liveliness"; VERSION_PATH=""
fi

echo "Building $NAME from commit $COMMIT (push=$PUSH)."
docker build -f "$DOCKERFILE" "${BUILD_ARGS[@]}" "${LABELS[@]}" -t "$NAME" .

echo "--- boot probe ---"
if [ "$IMAGE" = "digillm" ]; then
  docker run -d --name "${IMAGE}-probe-$$" -p 127.0.0.1:4000:4000 \
    -e LITELLM_MASTER_KEY=sk-smoke -v "$PWD/config:/app/config:ro" "$NAME"
  probe_container="${IMAGE}-probe-$$"
  probe_cleanup() { docker rm --force "$probe_container" >/dev/null 2>&1 || true; }
else
  probe_container="$(docker run --detach --rm --publish 127.0.0.1::3000 "$NAME")"
  probe_cleanup() { docker rm --force "$probe_container" >/dev/null 2>&1 || true; }
fi
trap probe_cleanup EXIT
if [ "$IMAGE" = "digichat" ]; then
  revision="$(docker inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$NAME")"
  [ "$revision" = "$COMMIT" ] || { echo "ERROR: revision label '$revision', expected '$COMMIT'." >&2; exit 1; }
  port="$(docker port "$probe_container" 3000/tcp | head -n1 | sed 's/.*://')"
  base="http://127.0.0.1:${port}"
  code="000"; deadline=$(( SECONDS + 120 ))
  while [ "$SECONDS" -lt "$deadline" ]; do
    [ "$(docker inspect --format '{{ .State.Running }}' "$probe_container" 2>/dev/null || true)" = "true" ] \
      || { echo "ERROR: container exited before serving." >&2; docker logs "$probe_container" 2>&1 || true; exit 1; }
    code="$(curl --silent --output /dev/null --write-out '%{http_code}' --max-time 5 "$base/healthz" || true)"
    [ "$code" = "200" ] || { sleep 3; continue; }
    break
  done
  [ "$code" = "200" ] || { echo "ERROR: /healthz never 200 (last '$code')." >&2; docker logs "$probe_container" 2>&1 || true; exit 1; }
  [ "$(curl --silent --show-error --fail "$base/healthz" | node -p "JSON.parse(require('fs').readFileSync(0,'utf8')).ok")" = "true" ] \
    || { echo "ERROR: /healthz did not report ok=true." >&2; exit 1; }
  reported="$(curl --silent --show-error --fail "$base/api/health" | node -p "JSON.parse(require('fs').readFileSync(0,'utf8')).version")"
  [ "$reported" = "$VERSION" ] || { echo "ERROR: serves version '$reported', built '$VERSION'." >&2; exit 1; }
else
  for _ in $(seq 60); do
    status=$(docker inspect -f '{{.State.Health.Status}}' "$probe_container")
    [ "$status" = healthy ] && break
    [ "$(docker inspect -f '{{.State.Running}}' "$probe_container")" = true ] || break
    sleep 2
  done
  [ "$(docker inspect -f '{{.State.Health.Status}}' "$probe_container")" = healthy ] \
    || { echo "ERROR: digillm container never healthy." >&2; docker logs "$probe_container" 2>&1 | tail -n 50 || true; exit 1; }
  curl -fsS http://127.0.0.1:4000/health/liveliness
  uid=$(docker exec "$probe_container" id -u)
  [ "$uid" != 0 ] || { echo "ERROR: digillm runs as root." >&2; exit 1; }
fi
echo "PASS $NAME boot probe."

if [ "$PUSH" -eq 0 ]; then
  echo "Not pushing (no --push). Image stays local."
  exit 0
fi

: "${LOCAL_DEPLOY_APPROVED_BY:?--push needs LOCAL_DEPLOY_APPROVED_BY naming the approver (Chris for releases).}"
case "$NAME" in
  *:sha-*|digillm:ci)
    echo "ERROR: rehearsal image $NAME must never be pushed under a release name." >&2; exit 1 ;;
esac
if out=$(docker manifest inspect "$NAME" 2>&1); then
  echo "ERROR: $NAME is already published; cut a new patch version." >&2; exit 1
fi
echo "$out" | grep -qiE "manifest unknown|not found" \
  || { echo "ERROR: could not determine whether $NAME is published; refusing to guess." >&2; exit 1; }
docker push "$NAME"
echo "PUSHED $NAME (approved by $LOCAL_DEPLOY_APPROVED_BY)."
