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

# Exiting inside the loop aborts the push (git has no partial push) *and* stops the
# refs after this one from being scanned, so one unscannable ref would mask a real
# violation on the next. Record and continue; exit after the loop. `while read` runs
# in this shell — git feeds stdin directly, no pipeline — so `failed` survives.
failed=0

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
      failed=1
      continue
    fi
  fi

  # Block push to main or default integration branch without explicit opt-in.
  if [[ "$remote_ref" = "refs/heads/{{MAIN_BRANCH}}" || "$remote_ref" = "refs/heads/{{DEFAULT_BRANCH}}" ]] \
      && [ "${ALLOW_MAIN_PUSH:-0}" != "1" ]; then
    branch_name="${remote_ref#refs/heads/}"
    echo "pre-push: refusing to push to '${branch_name}'. Set ALLOW_MAIN_PUSH=1 if this is intentional." >&2
    failed=1
    continue
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
  # An unsubstituted placeholder is a non-empty string, so it passes the -n test
  # below and the guard looks armed while `grep -E '{{...}}'` can never match a
  # path. That is the exact fail-open shape this hook exists to avoid, so refuse.
  case "$sensitive_regex" in
    *'{{'*)
      echo "pre-push: hook template was installed without substituting LIVE_TRADING_REGEX." >&2
      echo "         Reinstall the hook via digidev so the placeholder is filled, then retry." >&2
      failed=1
      continue
      ;;
  esac
  if [ -n "$sensitive_regex" ]; then
    # Refuse rather than skip when the scan cannot run — "we could not look" must
    # not read the same as "we looked and it was clean". Both checks live inside
    # this block on purpose: with no sensitive_regex configured there is nothing to
    # protect, so an unresolvable base is harmless and must not block the push.
    if [ -z "$base" ]; then
      echo "pre-push: cannot determine a diff base for '$local_ref' — refusing to push unscanned." >&2
      echo "         Run 'git fetch origin' so origin/{{DEFAULT_BRANCH}} is present, then retry." >&2
      echo "         A ref whose history is unrelated to {{DEFAULT_BRANCH}} has no base by nature" >&2
      echo "         and cannot be scanned at all; that is what the --no-verify escape is for." >&2
      failed=1
      continue
    fi
    # `|| true` would turn a failed diff into an empty file list, and an empty list
    # can never match — silently disarming the scan.
    if ! changed="$(git diff --name-only "$base" "$local_sha" 2>/dev/null)"; then
      echo "pre-push: 'git diff $base $local_sha' failed — refusing to push unscanned." >&2
      echo "         Run 'git fetch origin' and retry." >&2
      failed=1
      continue
    fi
    # grep is deliberately not -q: under `set -o pipefail`, -q exits at the first
    # match, the writer takes SIGPIPE and the pipeline reports 141, so a path list
    # exceeding the pipe buffer makes a matching diff read as no match.
    # Unlike the repo's own hook, this pattern comes from configuration, so it can be
    # malformed. grep answers "no match" with 1 and "bad pattern" with 2, and a bare
    # `if grep ...` collapses the two into the same else branch — a typo'd regex would
    # skip the scan and exit 0. Capture the status and treat anything above 1 as a
    # refusal. `|| grep_rc=$?` keeps errexit from firing on a plain no-match.
    grep_rc=0
    echo "$changed" | grep -E "$sensitive_regex" >/dev/null || grep_rc=$?
    if [ "$grep_rc" -gt 1 ]; then
      echo "pre-push: sensitive-path regex is not valid ERE (grep exit $grep_rc) — refusing" >&2
      echo "         to push unscanned. Fix LIVE_TRADING_REGEX and reinstall the hook." >&2
      failed=1
      continue
    fi
    if [ "$grep_rc" -eq 0 ]; then
      # Use git's trailer parser, not a line regex over %B: `^Human-Approved-By:`
      # also matches the marker quoted in ordinary body text, so a commit that
      # merely documents the gate cleared it. `key=` matches case-insensitively and
      # emits nothing for a bare label, which the non-blank test rejects.
      if ! git log --format='%(trailers:key=Human-Approved-By,valueonly)' "$base..$local_sha" \
           | grep -E '[^[:space:]]' >/dev/null; then
        echo "pre-push: sensitive paths changed but no Human-Approved-By trailer found in commits." >&2
        echo "         Add 'Human-Approved-By: <name>' to a commit message, or remove the sensitive changes." >&2
        failed=1
        continue
      fi
    fi
  fi
done

[ "$failed" -eq 0 ] || exit 1

exit 0
