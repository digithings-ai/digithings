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

# Allowed branch name taxonomy. Keep in sync with BRANCHING.md and the
# GitHub branch-naming ruleset on origin.
#
# Contributor namespaces (human handles) go in CONTRIBUTOR_HANDLES; add a new
# handle (GitHub login) here when a new human contributor joins.
CONTRIBUTOR_HANDLES='chrizefan'
branch_regex="^(main|develop|release/v[0-9]+\.[0-9]+\.[0-9]+|task/[0-9]+-[a-z0-9-]+|(claude|codex|cursor|copilot)/[a-z0-9-]+|(${CONTRIBUTOR_HANDLES})/[a-z0-9-]+|(feat|fix|docs|chore)/[a-z0-9-]+)$"

if [ -n "$url" ] && ! [[ "$url" =~ $allowed_url_regex ]]; then
  echo "pre-push: refusing to push to '$url'." >&2
  echo "         Only the pinned origin (github.com/digithings-ai/digithings) is allowed." >&2
  exit 1
fi

# Read refs being pushed from stdin: `<local_ref> <local_sha> <remote_ref> <remote_sha>`
while read -r local_ref local_sha remote_ref remote_sha; do
  [ -z "$local_ref" ] && continue

  # Branch name validation — only for refs/heads/; tags and notes are exempt.
  if [[ "$remote_ref" == refs/heads/* ]]; then
    branch_name="${remote_ref#refs/heads/}"
    if ! [[ "$branch_name" =~ $branch_regex ]]; then
      echo "pre-push: refusing to push branch '$branch_name' — doesn't match the taxonomy." >&2
      echo "         Allowed patterns (see BRANCHING.md):" >&2
      echo "           main | develop | release/vX.Y.Z" >&2
      echo "           task/<N>-<slug>" >&2
      echo "           {claude,codex,cursor,copilot}/<slug>" >&2
      echo "           {${CONTRIBUTOR_HANDLES//|/,}}/<slug>  (human contributors by GitHub handle)" >&2
      echo "           {feat,fix,docs,chore}/<slug>" >&2
      exit 1
    fi
  fi

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
