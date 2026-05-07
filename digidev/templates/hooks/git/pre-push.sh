#!/usr/bin/env bash
# Git pre-push hook.
#
# Rejects:
#   • pushes to any remote URL not matching the pinned origin
#   • pushes to `{{MAIN_BRANCH}}` without ALLOW_MAIN_PUSH=1
#   • pushes that touch sensitive paths without a Human-Approved-By trailer
#
# Installed by `make hooks-install`.

set -euo pipefail

remote="${1:-}"
url="${2:-}"

allowed_url_regex='^({{REPO_URL_HTTPS}}(\.git)?|{{REPO_URL_SSH}}(\.git)?)$'

# Branch naming taxonomy. Keep in sync with your team conventions.
# Add new contributor handles to CONTRIBUTOR_HANDLES.
CONTRIBUTOR_HANDLES='{{CONTRIBUTOR_HANDLES}}'
branch_regex="^({{MAIN_BRANCH}}|{{DEFAULT_BRANCH}}|module/[a-z0-9-]+|release/v[0-9]+\.[0-9]+\.[0-9]+|task/[0-9]+-[a-z0-9-]+|(claude|codex|cursor|copilot)/[a-z0-9-]+|(${CONTRIBUTOR_HANDLES})/[a-z0-9-]+|(feat|fix|docs|chore)/[a-z0-9-]+)$"

if [ -n "$url" ] && ! [[ "$url" =~ $allowed_url_regex ]]; then
  echo "pre-push: refusing to push to '$url'." >&2
  echo "         Only the pinned origin ({{REPO_FULL}}) is allowed." >&2
  exit 1
fi

while read -r local_ref local_sha remote_ref remote_sha; do
  [ -z "$local_ref" ] && continue

  # Branch name validation.
  if [[ "$remote_ref" == refs/heads/* ]]; then
    branch_name="${remote_ref#refs/heads/}"
    if ! [[ "$branch_name" =~ $branch_regex ]]; then
      echo "pre-push: refusing to push branch '$branch_name' — doesn't match the taxonomy." >&2
      echo "         Allowed patterns:" >&2
      echo "           {{MAIN_BRANCH}} | {{DEFAULT_BRANCH}} | release/vX.Y.Z" >&2
      echo "           module/<component>" >&2
      echo "           task/<N>-<slug>" >&2
      echo "           {claude,codex,cursor,copilot}/<slug>" >&2
      echo "           {${CONTRIBUTOR_HANDLES//|/,}}/<slug>" >&2
      echo "           {feat,fix,docs,chore}/<slug>" >&2
      exit 1
    fi
  fi

  # Block push to main or default integration branch without explicit opt-in.
  if [[ "$remote_ref" = "refs/heads/{{MAIN_BRANCH}}" || "$remote_ref" = "refs/heads/{{DEFAULT_BRANCH}}" ]] \
      && [ "${ALLOW_MAIN_PUSH:-0}" != "1" ]; then
    branch_name="${remote_ref#refs/heads/}"
    echo "pre-push: refusing to push to '${branch_name}'. Set ALLOW_MAIN_PUSH=1 if this is intentional." >&2
    exit 1
  fi

  # Skip deletions and new-branch pushes (no range to scan).
  if [ "$local_sha" = "0000000000000000000000000000000000000000" ]; then
    continue
  fi

  # Determine diff range.
  if [ "$remote_sha" = "0000000000000000000000000000000000000000" ] || [ -z "$remote_sha" ]; then
    base="$(git merge-base "$local_sha" "origin/{{DEFAULT_BRANCH}}" 2>/dev/null || echo '')"
  else
    base="$remote_sha"
  fi
  [ -z "$base" ] && continue

  # Scan for sensitive paths.
  sensitive_regex='{{LIVE_TRADING_REGEX}}'
  if [ -n "$sensitive_regex" ]; then
    changed="$(git diff --name-only "$base" "$local_sha" 2>/dev/null || true)"
    if echo "$changed" | grep -Eq "$sensitive_regex"; then
      if ! git log --format=%B "$base..$local_sha" | grep -Eiq '^Human-Approved-By:'; then
        echo "pre-push: sensitive paths changed but no Human-Approved-By trailer found in commits." >&2
        echo "         Add 'Human-Approved-By: <name>' to a commit message, or remove the sensitive changes." >&2
        exit 1
      fi
    fi
  fi
done

exit 0
