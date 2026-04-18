#!/usr/bin/env bash
# Git pre-push hook. Rejects:
#   • pushes to any remote URL not matching the pinned digithings origin
#   • pushes to `main` without ALLOW_MAIN_PUSH=1
#   • pushes that touch live-trading paths without a human co-sign trailer
#
# Installed by `make hooks-install`. Bypass with `git push --no-verify` only
# in genuine emergencies (the commit message should say so).

set -euo pipefail

remote="${1:-}"
url="${2:-}"

allowed_url_regex='^(https://github\.com/digithings-ai/digithings(\.git)?|git@github\.com:digithings-ai/digithings(\.git)?)$'

if [ -n "$url" ] && ! [[ "$url" =~ $allowed_url_regex ]]; then
  echo "pre-push: refusing to push to '$url'." >&2
  echo "         Only the pinned origin (github.com/digithings-ai/digithings) is allowed." >&2
  exit 1
fi

# Read refs being pushed from stdin: `<local_ref> <local_sha> <remote_ref> <remote_sha>`
while read -r local_ref local_sha remote_ref remote_sha; do
  [ -z "$local_ref" ] && continue

  # Block push to main without explicit opt-in.
  if [ "$remote_ref" = "refs/heads/main" ] && [ "${ALLOW_MAIN_PUSH:-0}" != "1" ]; then
    echo "pre-push: refusing to push to 'main'. Set ALLOW_MAIN_PUSH=1 if this is intentional." >&2
    exit 1
  fi

  # Skip deletions and new-branch pushes (no range to scan).
  if [ "$local_sha" = "0000000000000000000000000000000000000000" ]; then
    continue
  fi

  # Determine the diff range: against the remote sha if present, else against origin/develop.
  if [ "$remote_sha" = "0000000000000000000000000000000000000000" ] || [ -z "$remote_sha" ]; then
    base="$(git merge-base "$local_sha" origin/develop 2>/dev/null || echo '')"
  else
    base="$remote_sha"
  fi
  [ -z "$base" ] && continue

  # Scan changed paths for live-trading touch.
  changed="$(git diff --name-only "$base" "$local_sha" 2>/dev/null || true)"
  if echo "$changed" | grep -Eq '(live_trading|execute_trade|place_order|/live/)'; then
    # Require a human co-sign trailer in at least one commit in the range.
    if ! git log --format=%B "$base..$local_sha" | grep -Eiq '^(Human-Approved-By|Co-Authored-By:[[:space:]]+[^C])'; then
      echo "pre-push: live-trading paths changed but no Human-Approved-By trailer found in commits." >&2
      echo "         Add 'Human-Approved-By: <name>' to a commit message, or remove the live-trading changes." >&2
      exit 1
    fi
  fi
done

exit 0
