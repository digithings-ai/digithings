#!/usr/bin/env bash
# Fail when the BerriAI LiteLLM container image reappears anywhere in tracked files,
# or when a LiteLLM image reference is left on a moving tag (DIG-1780).
#
# Chris ratified this as a red line on DIG-1768: LiteLLM from the Python package
# repository only, never the official Docker image. The vendor image ships BerriAI's
# proprietary `enterprise/` tree, and `enterprise/LICENSE.md` permits production use
# only under an Enterprise seat licence — so a vendor image in production is an
# unlicensed-use question, not a refactor. See `Dockerfile.litellm` for the
# compliant replacement and `docs/architecture/litellm-pypi-image.md` for the
# functional gap that buys us.
#
# The gate scans prose as well as configuration: the vendor registry path is not
# written down anywhere in tracked files, including in this file, because a
# rationale that reproduces the reference it forbids is a reference waiting to be
# copy-pasted back into a compose file. Name the vendor, not the pull command.
#
# Two checks:
#   1. no vendor image reference in tracked files (with narrow, self-verifying
#      exceptions for source fetches, which are not image pulls);
#   2. every litellm image reference names an exact tag that matches the pin in
#      Dockerfile.litellm — never `:latest` and never `:main-stable`.
#
# Scoped to tracked files on purpose. `.gitignore:41` ignores `/projects/*`, so
# `projects/sitaas/docker-compose.yml` is invisible to this gate and to every other
# boundary check in the repo. That is a pre-existing blind spot, tracked in DIG-1780,
# not something this script can close.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

command -v rg >/dev/null || {
  echo "::error::ripgrep not found — litellm vendor boundary gate cannot run"
  exit 1
}

# ── Config ───────────────────────────────────────────────────────────────────
# Single source of truth for the pin. Both the Dockerfile default and the compose
# tags are asserted against it below, so the three cannot drift apart silently.
LITELLM_VERSION="1.72.6"
DOCKERFILE_LITELLM_VERSION="Dockerfile.litellm"

# Source fetches for the licence review, not image pulls. An entry is only honoured
# when the matched line actually contains one of that entry's SOURCE_HOSTS values —
# so an image pull cannot be smuggled into an allowlisted file and inherit the
# exemption. Two lines of grep instead of an ignored-path list that rots.
SOURCE_EXCEPTIONS=(
  "scripts/provider_review/bootstrap.py"
  "docs/superpowers/plans/2026-05-01-provider-review.md"
)
SOURCE_HOST="raw.githubusercontent.com"

# Registry-side vendor image references. Registry prefixes are spelled out so the
# `raw.githubusercontent.com/BerriAI/litellm/...` URLs in SOURCE_EXCEPTIONS do not
# match — those read upstream source for the licence review, and are exactly the
# references a naive `berriai/litellm` pattern would fail on.
VENDOR_IMAGE_RE='docker\.litellm\.ai/|([a-z0-9.-]+\.)?(ghcr\.io|docker\.io|quay\.io|registry\.k8s\.io)/berriai/litellm'

status=0

# ── Check 1: no vendor image reference ────────────────────────────────────────
# `--hidden` so `.github/` is scanned (rg skips dotfiles by default and a workflow
# could pin the vendor image just as easily as a compose file).
# `--glob '!projects/**'` is belt-and-braces: `/projects/*` is gitignored already.
vendor_hits="$(rg -n --hidden --glob '!projects/**' -e "$VENDOR_IMAGE_RE" . || true)"

while IFS= read -r hit; do
  [[ -z "$hit" ]] && continue
  file="${hit%%:*}"
  rel="${file#./}"
  line_no="${hit#*:}"
  line="${hit#*:*}"

  exempt=false
  for allowed in "${SOURCE_EXCEPTIONS[@]}"; do
    if [[ "$rel" == "$allowed" && "$line" == *"$SOURCE_HOST"* ]]; then
      exempt=true
      break
    fi
  done

  if [[ "$exempt" == false ]]; then
    echo "::error file=${rel},line=${line_no}::vendor LiteLLM image reference (DIG-1780 red line)"
    echo "    $line"
    status=1
  fi
done <<<"$vendor_hits"

if ((status == 0)); then
  echo "vendor image boundary OK (${#SOURCE_EXCEPTIONS[@]} source-fetch exceptions)"
fi

# ── Check 2: litellm image tags are exact and match the pin ───────────────────
pin="$(sed -n 's/^ARG LITELLM_VERSION=\([0-9][^ ]*\)$/\1/p' "$DOCKERFILE_LITELLM_VERSION" | head -1)"
if [[ -z "$pin" ]]; then
  echo "::error::could not read ARG LITELLM_VERSION from ${DOCKERFILE_LITELLM_VERSION}"
  exit 1
fi
if [[ "$pin" != "$LITELLM_VERSION" ]]; then
  echo "::error::${DOCKERFILE_LITELLM_VERSION} pins litellm==${pin} but this gate expects ${LITELLM_VERSION}."
  echo "    Update LITELLM_VERSION in $(basename "${BASH_SOURCE[0]}") in the same commit."
  status=1
fi

compose_files=()
while IFS= read -r f; do compose_files+=("$f"); done < <(git ls-files | grep -E '(^|/)(docker-)?compose[^/]*\.ya?ml$')

for f in "${compose_files[@]}"; do
  while IFS= read -r img; do
    [[ -z "$img" ]] && continue
    # A digest is the strongest form of pin: the tag is irrelevant once content is
    # addressed, so accept and move on rather than trying to parse it as a tag.
    if [[ "$img" == *"@sha256:"* ]]; then
      continue
    fi
    ref="${img%%@*}"
    # Resolve `${VAR:-default}` to its in-repo default. A bare `${VAR}` has no
    # in-repo default to check, and is refused below: a compose file that pins the
    # LiteLLM tag only in an operator's .env has no pin a reader can verify.
    ref="$(printf '%s' "$ref" | sed -E 's/\$\{[A-Za-z_][A-Za-z0-9_]*:-([^}]*)\}/\1/g')"
    if [[ "$ref" == *'$'* ]]; then
      echo "::error file=${f}::litellm image '${img}' pins its tag only via a variable."
      echo "    Give the variable an in-repo default (…:-${pin}) so the pin is reviewable."
      status=1
      continue
    fi
    tag="${ref##*:}"
    if [[ "$tag" == "$ref" ]]; then
      echo "::error file=${f}::litellm image '${img}' has no tag — pin it to ${pin}"
      status=1
      continue
    fi
    if [[ "$tag" != "$pin" ]]; then
      echo "::error file=${f}::litellm image tag '${tag}' is not the pin '${pin}'."
      echo "    Never tag this image :latest or :main-stable — it is a moving tag (DIG-1780)."
      status=1
    fi
  done < <(sed -n 's/^[[:space:]]*image:[[:space:]]*\(.*litellm[^ ]*\)[[:space:]]*$/\1/p' "$f")
done

if ((status != 0)); then
  exit 1
fi

echo "litellm image pin OK (litellm==${pin}, exact tags only)"
