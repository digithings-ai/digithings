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

# A ref deletion pushes an all-zero sha as the local sha; a branch not yet present
# upstream reports an all-zero remote sha. The width follows the repository's hash
# algorithm — 40 hex digits under sha1, 64 under sha256 — so test for "all zeros"
# rather than comparing against a fixed-width literal, which silently stops
# matching in a sha256 repository.
is_zero_sha() {
  [[ "$1" =~ ^0+$ ]]
}

if [ -n "$url" ] && ! [[ "$url" =~ $allowed_url_regex ]]; then
  echo "pre-push: refusing to push to '$url'." >&2
  echo "         Only the pinned origin ({{REPO_FULL}}) is allowed." >&2
  exit 1
fi

while read -r local_ref local_sha remote_ref remote_sha; do
  [ -z "$local_ref" ] && continue

  # Deletions are exempt from the taxonomy: a ref created outside it — or one
  # predating a tightening of the rules — must still be deletable. Enforcing a
  # name on the way out only strands the branches the rule meant to discourage.
  # The main/default guard below still applies to deletions.
  is_deletion=0
  if is_zero_sha "$local_sha"; then
    is_deletion=1
  fi

  # Branch name validation — deletions exempt.
  if [ "$is_deletion" -eq 0 ] && [[ "$remote_ref" == refs/heads/* ]]; then
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

  # Deletions have no commit range to scan; new-branch pushes are handled below.
  if [ "$is_deletion" -eq 1 ]; then
    continue
  fi

  # Determine diff range.
  if is_zero_sha "$remote_sha" || [ -z "$remote_sha" ]; then
    base="$(git merge-base "$local_sha" "origin/{{DEFAULT_BRANCH}}" 2>/dev/null || echo '')"
  else
    base="$remote_sha"
  fi

  # Scan for sensitive paths.
  sensitive_regex='{{LIVE_TRADING_REGEX}}'
  if [ -n "$sensitive_regex" ]; then
    # Refuse rather than skip when the scan cannot run — "we could not look" must
    # not read the same as "we looked and it was clean". Both checks live inside
    # this block on purpose: with no sensitive_regex configured there is nothing to
    # protect, so an unresolvable base is harmless and must not block the push.
    if [ -z "$base" ]; then
      echo "pre-push: cannot determine a diff base for '$local_ref' — refusing to push unscanned." >&2
      echo "         Run 'git fetch origin' so origin/{{DEFAULT_BRANCH}} is present, then retry." >&2
      echo "         A branch with unrelated history has no base by nature; use --no-verify." >&2
      exit 1
    fi
    # `|| true` would turn a failed diff into an empty file list, and an empty list
    # can never match — silently disarming the scan.
    if ! changed="$(git diff --name-only "$base" "$local_sha" 2>/dev/null)"; then
      echo "pre-push: 'git diff $base $local_sha' failed — refusing to push unscanned." >&2
      echo "         Run 'git fetch origin' and retry." >&2
      exit 1
    fi
    # grep is deliberately not -q: under `set -o pipefail`, -q exits at the first
    # match, the writer takes SIGPIPE and the pipeline reports 141, so a path list
    # exceeding the pipe buffer makes a matching diff read as no match.
    if echo "$changed" | grep -E "$sensitive_regex" >/dev/null; then
      # The ':' and a non-blank value reject 'Human-Approved-Byte' and a bare label.
      if ! git log --format=%B "$base..$local_sha" | grep -Ei '^Human-Approved-By:[[:space:]]*[^[:space:]]' >/dev/null; then
        echo "pre-push: sensitive paths changed but no Human-Approved-By trailer found in commits." >&2
        echo "         Add 'Human-Approved-By: <name>' to a commit message, or remove the sensitive changes." >&2
        exit 1
      fi
    fi
  fi
done

exit 0
