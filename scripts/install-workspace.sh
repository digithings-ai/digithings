#!/usr/bin/env bash
# Install monorepo workspace packages in dependency order for CI.
#
# Why this exists: sibling packages like `digismith` are listed as hard
# dependencies in some pyproject.toml files (e.g. digigraph) but are NOT on
# PyPI — they live in this monorepo. A naive `pip install -e ./digigraph`
# therefore fails in CI because pip cannot resolve `digismith>=0.1.0`.
# This script installs the workspace in the correct topological order so
# downstream packages always find their siblings already on sys.path.
#
# Usage:
#   scripts/install-workspace.sh                # install all packages
#   scripts/install-workspace.sh digigraph      # install up to & including digigraph
#   scripts/install-workspace.sh --with-dev     # add [dev] extras where available
#
# The script fast-fails on the first pip error.
set -euo pipefail

WITH_DEV=0
PACKAGES=()
for arg in "$@"; do
  case "$arg" in
    --with-dev) WITH_DEV=1 ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) PACKAGES+=("$arg") ;;
  esac
done

python -m pip install -U pip

# Dependency-ordered workspace. digibase and digismith are leaves that many
# other packages depend on, so they go first. Apps depend on the services
# so they go last.
ALL=(digibase digismith digikey digigraph digiquant digisearch digiclaw)

# Which packages actually have a [dev] extra? (Keeps --with-dev safe.)
has_dev() {
  case "$1" in
    digibase|digikey|digismith|digigraph|digiquant|digisearch|digiclaw) return 0 ;;
    *) return 1 ;;
  esac
}

install_one() {
  local pkg="$1"
  local spec="./${pkg}"
  if [[ "$WITH_DEV" == "1" ]] && has_dev "$pkg"; then
    spec="./${pkg}[dev]"
  fi
  echo "==> pip install -e ${spec}"
  pip install -e "${spec}"
}

if [[ ${#PACKAGES[@]} -eq 0 ]]; then
  for pkg in "${ALL[@]}"; do install_one "$pkg"; done
else
  # Install every ordered package up to and including each requested one.
  # This guarantees sibling deps are present without forcing the caller to
  # name them explicitly.
  declare -A WANT=()
  for p in "${PACKAGES[@]}"; do WANT["$p"]=1; done

  MAX_IDX=-1
  for i in "${!ALL[@]}"; do
    if [[ -n "${WANT[${ALL[$i]}]:-}" ]]; then MAX_IDX=$i; fi
  done

  if [[ "$MAX_IDX" -lt 0 ]]; then
    echo "error: no matching workspace package in: ${PACKAGES[*]}" >&2
    echo "known packages: ${ALL[*]}" >&2
    exit 2
  fi

  for i in $(seq 0 "$MAX_IDX"); do install_one "${ALL[$i]}"; done
fi

echo "workspace install complete"
