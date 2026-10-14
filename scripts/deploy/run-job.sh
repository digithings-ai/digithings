#!/usr/bin/env bash
# local-ci deploy job (DIG-3697).
#
# Checks a signed release tag, then runs `wrangler deploy --dry-run`.
# Live deploy is not implemented. --live is refused. No environment
# variable and no file turns that refusal off.
#
#   bash scripts/deploy/run-job.sh --job stack --tag stack-v1.2.3
#
# The default allowed-signers file is scripts/deploy/allowed_signers.
# It ships with no keys, so a tag is refused until Chris adds his
# public key. Tests pass --allowed-signers and --repo.
set -euo pipefail

JOB=""
TAG=""
REPO=""
SIGNERS=""

while [ $# -gt 0 ]; do
  case "$1" in
    --job)
      JOB="${2:-}"
      shift 2
      ;;
    --tag)
      TAG="${2:-}"
      shift 2
      ;;
    --repo)
      REPO="${2:-}"
      shift 2
      ;;
    --allowed-signers)
      SIGNERS="${2:-}"
      shift 2
      ;;
    --live)
      echo "DISARMED: live deploy is refused until Chris approves. Nothing was deployed." >&2
      exit 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [ -z "$JOB" ] || [ -z "$TAG" ]; then
  echo "Usage: $0 --job <id> --tag <prefix-vX.Y.Z> [--repo DIR] [--allowed-signers FILE]" >&2
  exit 2
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [ -z "$REPO" ]; then
  REPO="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
fi
if [ -z "$SIGNERS" ]; then
  SIGNERS="$SCRIPT_DIR/allowed_signers"
fi

MANIFEST="$SCRIPT_DIR/workers.tsv"
[ -f "$MANIFEST" ] || { echo "missing $MANIFEST" >&2; exit 2; }
[ -f "$SIGNERS" ] || { echo "missing allowed signers file: $SIGNERS" >&2; exit 1; }

line="$(awk -F '\t' -v id="$JOB" '$0 ~ /^#/ { next } $1 == id { print; exit }' "$MANIFEST")"
[ -n "$line" ] || { echo "unknown job: $JOB" >&2; exit 2; }
IFS="$(printf '\t')"
# shellcheck disable=SC2086
read -r id prefix app worker home <<EOF
$line
EOF
unset IFS

if ! printf '%s\n' "$TAG" | grep -Eq "^${prefix}-v[0-9]+\\.[0-9]+\\.[0-9]+$"; then
  echo "tag '$TAG' does not match ${prefix}-vX.Y.Z" >&2
  exit 1
fi

# An empty signers file still makes git print "Good signature" and then
# "No principal matched". Refuse before verify-tag so that line never
# looks like a pass.
if ! grep -Eq '^[^#[:space:]]' "$SIGNERS"; then
  echo "allowed_signers has no keys; refusing '$TAG'." >&2
  exit 1
fi

git -C "$REPO" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
  || { echo "not a git checkout: $REPO" >&2; exit 1; }

if ! git -C "$REPO" -c gpg.ssh.allowedSignersFile="$SIGNERS" verify-tag "$TAG" >&2; then
  echo "git verify-tag refused '$TAG'." >&2
  exit 1
fi

if [ -n "$(git -C "$REPO" status --porcelain)" ]; then
  echo "checkout is not clean; refusing." >&2
  exit 1
fi

head_sha="$(git -C "$REPO" rev-parse HEAD)"
tagged_sha="$(git -C "$REPO" rev-parse "${TAG}^{commit}")"
if [ "$head_sha" != "$tagged_sha" ]; then
  echo "HEAD is not the tagged commit; refusing." >&2
  exit 1
fi

echo "tag $TAG verified for $id ($worker, $home). Live deploy is disarmed."

if [ "$app" = "-" ] || [ ! -f "$REPO/$app/wrangler.toml" ]; then
  echo "no Worker source for $id. Nothing was deployed." >&2
  exit 2
fi

outdir="$(mktemp -d)"
trap 'rm -rf "$outdir"' EXIT
echo "dry-run for $app"
if command -v wrangler >/dev/null 2>&1; then
  (cd "$REPO/$app" && wrangler deploy --dry-run --containers-rollout=none --outdir "$outdir")
else
  (cd "$REPO/$app" && npm exec -- wrangler deploy --dry-run --containers-rollout=none --outdir "$outdir")
fi
echo "PASS $id dry-run. Nothing was deployed."
