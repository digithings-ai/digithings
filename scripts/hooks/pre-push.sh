#!/usr/bin/env bash
# Git pre-push hook. Rejects:
#   • pushes to any remote URL not matching the pinned digithings origin
#   • pushes to `main` without ALLOW_MAIN_PUSH=1
#   • pushes that touch live-trading paths without a `Human-Approved-By:` trailer
#
# Installed by `make hooks-install` (and by `make agents-init`), which installs
# this file **as committed on origin/develop**, not your working copy — one hook
# is shared by every linked worktree, so installing a task branch's copy would
# change the policy for all of them. When editing this hook, install your
# uncommitted version with `HOOKS_REF=WORKTREE make hooks-install` — an
# override that any later default install, from any worktree, replaces.
#
# Bypass with `git push --no-verify` only in genuine emergencies (the commit
# message should say so).

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
branch_regex="^(main|develop|module/[a-z0-9-]+|release/v[0-9]+\.[0-9]+\.[0-9]+|release-please--branches--(develop|module/[a-z0-9-]+)--components--[a-z0-9-]+|task/[0-9]+-[a-z0-9-]+|(claude|codex|cursor|copilot)/[a-z0-9-]+|(${CONTRIBUTOR_HANDLES})/[a-z0-9-]+|(feat|fix|docs|chore)/[a-z0-9-]+|bot/[a-z0-9-]+)$"

# A ref deletion pushes an all-zero sha as the local sha; a branch that does not
# exist upstream yet reports an all-zero remote sha. The width follows the repo's
# hash algorithm — 40 hex digits under sha1, 64 under sha256 — so test for "all
# zeros" instead of comparing against a fixed-width literal. A 40-zero literal
# silently stops matching in a sha256 repository, which would both re-impose the
# taxonomy on deletions (the regression #2468 fixed) and, via an unresolvable
# diff base, disarm the live-trading scan below.
is_zero_sha() {
  [[ "$1" =~ ^0+$ ]]
}

if [ -n "$url" ] && ! [[ "$url" =~ $allowed_url_regex ]]; then
  echo "pre-push: refusing to push to '$url'." >&2
  echo "         Only the pinned origin (github.com/digithings-ai/digithings) is allowed." >&2
  exit 1
fi

# A non-zero exit aborts the whole push either way — git has no partial push — but
# exiting *inside* the loop also stops the refs after this one from being examined.
# That loses the live-trading scan on every later ref, so one ref with no diff base
# would hide a real violation on the next. Record the refusal, keep going, and exit
# after the loop. `while read` runs in this shell (git feeds stdin directly, no
# pipeline), so `failed` survives the loop.
failed=0

# Read refs being pushed from stdin: `<local_ref> <local_sha> <remote_ref> <remote_sha>`
while read -r local_ref local_sha remote_ref remote_sha; do
  [ -z "$local_ref" ] && continue

  # Deletions are exempt from the taxonomy: a branch created outside it — a
  # `bot/*` ref from project-stub-fields.yml, or anything predating a tightening
  # of the rules — must still be deletable. Enforcing a name on the way out only
  # strands the refs the rule was meant to discourage. The `main` guard below
  # still applies: deleting main is at least as serious as pushing to it.
  is_deletion=0
  if is_zero_sha "$local_sha"; then
    is_deletion=1
  fi

  # Branch name validation — only for refs/heads/; tags, notes and deletions are exempt.
  if [ "$is_deletion" -eq 0 ] && [[ "$remote_ref" == refs/heads/* ]]; then
    branch_name="${remote_ref#refs/heads/}"
    if ! [[ "$branch_name" =~ $branch_regex ]]; then
      echo "pre-push: refusing to push branch '$branch_name' — doesn't match the taxonomy." >&2
      echo "         Allowed patterns (see BRANCHING.md):" >&2
      echo "           main | develop | release/vX.Y.Z" >&2
      echo "           module/<component>  (e.g. module/digiquant, module/digigraph)" >&2
      echo "           release-please--branches--<target>--components--<component>" >&2
      echo "                        (pushed by the release-please-*.yml workflows)" >&2
      echo "           task/<N>-<slug>" >&2
      echo "           {claude,codex,cursor,copilot}/<slug>" >&2
      echo "           {${CONTRIBUTOR_HANDLES//|/,}}/<slug>  (human contributors by GitHub handle)" >&2
      echo "           {feat,fix,docs,chore}/<slug>" >&2
      echo "           bot/<slug>  (pushed by project-stub-fields.yml," >&2
      echo "                        agent-backlog-snapshot.yml, pipeline-provider-review.yml)" >&2
      failed=1
      continue
    fi
  fi

  # Block push to main without explicit opt-in.
  if [ "$remote_ref" = "refs/heads/main" ] && [ "${ALLOW_MAIN_PUSH:-0}" != "1" ]; then
    echo "pre-push: refusing to push to 'main'. Set ALLOW_MAIN_PUSH=1 if this is intentional." >&2
    failed=1
    continue
  fi

  # Deletions have no commit range to scan; new-branch pushes are handled below.
  if [ "$is_deletion" -eq 1 ]; then
    continue
  fi

  # Determine the diff range: against the remote sha if present, else against origin/develop.
  if is_zero_sha "$remote_sha" || [ -z "$remote_sha" ]; then
    base="$(git merge-base "$local_sha" origin/develop 2>/dev/null || echo '')"
  else
    base="$remote_sha"
  fi

  # No base means the scan below cannot run. Refuse instead of skipping: "we could
  # not look" must never be indistinguishable from "we looked and it was clean" on
  # the one guard standing between a live-trading edit and origin.
  if [ -z "$base" ]; then
    echo "pre-push: cannot determine a diff base for '$local_ref' — refusing to push unscanned." >&2
    echo "         Usually origin/develop is just missing locally: run 'git fetch origin' and retry." >&2
    echo "         A ref whose history is unrelated to develop — an imported tag, a grafted" >&2
    echo "         branch — has no base by nature and cannot be scanned at all; that is the" >&2
    echo "         emergency the --no-verify escape at the top of this file exists for." >&2
    failed=1
    continue
  fi

  # Scan changed paths for live-trading touch. The directory fragment is
  # anchored to digiquant — a bare '/live/' also matched design-reference
  # screenshots under frontend/**/references/**/live/ (false positives).
  # `|| true` here would turn a failed diff into an empty file list, and an empty
  # list can never match — silently disarming the guard. Fail closed instead.
  if ! changed="$(git diff --name-only "$base" "$local_sha" 2>/dev/null)"; then
    echo "pre-push: 'git diff $base $local_sha' failed — refusing to push unscanned." >&2
    echo "         Run 'git fetch origin' and retry; the live-trading scan needs a diff." >&2
    failed=1
    continue
  fi

  # grep is deliberately not -q. Under `set -o pipefail`, -q exits at the first
  # match, the writer takes SIGPIPE, and the pipeline reports 141 — so a *matching*
  # diff reads as no match and skips the guard. The threshold is the pipe buffer in
  # bytes, not a path count, and it is implementation-split: measured here, BSD grep
  # inverts once the path list passes ~64KB while GNU grep 3.8 holds to ~128KB, so
  # the same push can be scanned on CI and skipped on a maintainer's mac. It also
  # needs the match to precede grep draining the buffer. Without -q, grep reads all
  # of stdin and only its own status matters.
  if echo "$changed" | grep -E '(live_trading|execute_trade|place_order|(^|/)digiquant/(.*/)?live/)' >/dev/null; then
    # Require an explicit human co-sign trailer in at least one commit in the range.
    # Only `Human-Approved-By:` counts — the trailer that ONBOARDING.md, SECURITY.md
    # and this hook's own error message all promise. The former second arm,
    # `Co-Authored-By:[[:space:]]+[^C]`, tested the first letter of a co-author's
    # name and nothing else. So it cleared unrelated bots (`dependabot`,
    # `github-actions`) on a gate labelled *human*, while rejecting every name
    # starting with a C — which is most of what this repo actually writes: the agent
    # `Claude` trailer that `scripts/commit_helper.sh` appends (opt-in, not mandated
    # anywhere) and the one human contributor here, whose name starts with a C too.
    # `-i` only widened the rejection: it case-folds the bracket expression, so
    # `[^C]` also excluded a lowercase `c`.
    #
    # Read the trailer with git's own parser rather than grepping %B for a line.
    # `^Human-Approved-By:` matches the marker anywhere in the message, so a commit
    # that merely *documents* the gate — "add a line reading Human-Approved-By:
    # <name>" — cleared it, as did the marker sitting mid-body above ordinary prose.
    # `%(trailers:key=...)` only considers the trailer block, matches the key
    # case-insensitively (so the old `-i` tolerance is kept), and emits nothing for a
    # bare label, which the non-blank test then rejects.
    if ! git log --format='%(trailers:key=Human-Approved-By,valueonly)' "$base..$local_sha" \
         | grep -E '[^[:space:]]' >/dev/null; then
      echo "pre-push: live-trading paths changed but no Human-Approved-By trailer found in commits." >&2
      echo "         Add 'Human-Approved-By: <name>' to a commit message, or remove the live-trading changes." >&2
      failed=1
      continue
    fi
  fi
done

[ "$failed" -eq 0 ] || exit 1

exit 0
