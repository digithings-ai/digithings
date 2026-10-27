#!/usr/bin/env bash
# Git pre-push hook. Rejects:
#   • pushes to any remote URL other than GitHub, the Origin mirror, or Origin /local
#   • origin/<slug> drafts pushed anywhere except the Origin /local endpoint
#   • pushes to `main` without ALLOW_MAIN_PUSH=1
#   • pushes to `develop` without ALLOW_DEVELOP_PUSH=1
#   • pushes that touch live-trading paths without a `Human-Approved-By:` trailer
#   • pushes that introduce a secret, including a push made where gitleaks or
#     .gitleaks.toml is unavailable (DIG-5722 — "we could not look" is a refusal)
#
# Warns, and never blocks (DIG-1579):
#   • the branch being pushed is older than 10 days — see the policy pointer it prints
#
# Escaping the secret scan, in order of preference:
#   1. install gitleaks (`brew install gitleaks`) — the scan then runs as below;
#   2. `PRE_PUSH_SKIP_GITLEAKS=1` — skips the local secret scan for that push and
#      prints the ref it did not scan. It exists for synthetic hook fixtures and
#      for a machine that cannot install the binary. Nothing else scans the push:
#      .github/workflows/security-gitleaks.yml covers pull requests and pushes to
#      develop/main only, and the local forge has no scan yet (DIG-5722);
#   3. `git push --no-verify` — genuine emergencies only (see below).
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

# GitHub stays the public/release remote. Origin is the agent iteration host.
# The local Forgejo is the local working surface; /local on Origin accepts only
# refs/heads/origin/* and those refs never sync to GitHub.
github_url_regex='^(https://github\.com/digithings-ai/digithings(\.git)?|git@github\.com:digithings-ai/digithings(\.git)?)$'
origin_mirror_url_regex='^https://origin\.cursor\.com/chrizefan/digithings(\.git)?$'
origin_local_url_regex='^https://origin\.cursor\.com/chrizefan/digithings(\.git)?/local/?$'
origin_draft_regex='^origin/[a-z0-9][a-z0-9-]*$'
local_forge_url_regex='^http://(localhost|127\.0\.0\.1):3000/digithings-ai/digithings(\.git)?$'
local_change_regex='^change/[a-z0-9][a-z0-9-]*$'

# Allowed branch name taxonomy. Keep in sync with BRANCHING.md and
# scripts/github-rulesets/01-branch-naming.json. That file is the desired
# GitHub ruleset; it is not applied on the repo (see that directory's README).
# Do not say "on origin" — origin is the Cursor mirror, not GitHub.
#
# `DIG-<n>-<title-slug>` is the branch Paperclip checks out an execution
# workspace on. It matched no arm here, so a bare `git push` from such a
# workspace was refused outright — the hook validates the destination
# `remote_ref`, and there is no exemption for a branch the remote already holds.
# Admitting the shape is the whole fix; the digit is required so this cannot
# widen into a prefix match on `DIG`, and the slug is required so `DIG-47-` is
# not a branch name. Such a branch accumulates commits from unrelated issues and
# must not be blanket pushed — see the execution-workspace rule in BRANCHING.md.
#
# `rescue/<issue>-<date>` is the branch `kit/bin/dt-worktree-rescue` pushes work
# onto when a worktree is being retired. It is not a human-created name: the
# helper produces it, so the taxonomy has to admit it or the rescue push is
# refused and the worktree is kept forever — the leak DIG-4874 was about
# (DIG-4898, DIG-4218). The arm allows UPPERCASE on purpose: the conventional
# name carries an uppercase issue key, `rescue/DIG-1234-2026-10-21`, and a
# lowercase-only arm refuses exactly the name the helper tries first. The `-2`/
# `-3` suffix the helper adds when the name is taken is why this is a character
# class rather than `rescue/DIG-[0-9]+-[0-9]{4}-[0-9]{2}-[0-9]{2}`.
#
# Contributor namespaces (human handles) go in CONTRIBUTOR_HANDLES; add a new
# handle (GitHub login) here when a new human contributor joins.
CONTRIBUTOR_HANDLES='chrizefan'
branch_regex="^(main|develop|module/[a-z0-9-]+|release/v[0-9]+\.[0-9]+\.[0-9]+|release-please--branches--(develop|module/[a-z0-9-]+)--components--[a-z0-9-]+|task/[0-9]+-[a-z0-9-]+|(claude|codex|cursor|copilot)/[a-z0-9-]+|(${CONTRIBUTOR_HANDLES})/[a-z0-9-]+|(feat|fix|docs|chore|revert)/[a-z0-9-]+|bot/[a-z0-9-]+|rescue/[A-Za-z0-9-]+|DIG-[0-9]+-[a-z0-9-]+)$"

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

is_origin_local=0
is_local_forge=0
if [[ "$url" =~ $origin_local_url_regex ]]; then
  is_origin_local=1
elif [[ "$url" =~ $local_forge_url_regex ]]; then
  is_local_forge=1
elif [ -n "$url" ] && ! [[ "$url" =~ $github_url_regex || "$url" =~ $origin_mirror_url_regex ]]; then
  echo "pre-push: refusing to push to '$url'." >&2
  echo "         Allowed: github.com/digithings-ai/digithings, origin.cursor.com/chrizefan/digithings (and its /local endpoint), or the local forge at localhost:3000." >&2
  exit 1
fi

# A non-zero exit aborts the whole push either way — git has no partial push — but
# exiting *inside* the loop also stops the refs after this one from being examined.
# That loses the live-trading scan on every later ref, so one ref with no diff base
# would hide a real violation on the next. Record the refusal, keep going, and exit
# after the loop. `while read` runs in this shell (git feeds stdin directly, no
# pipeline), so `failed` survives the loop.
failed=0
gitleaks_skip_noted=0

# Read refs being pushed from stdin: `<local_ref> <local_sha> <remote_ref> <remote_sha>`
while read -r local_ref local_sha remote_ref remote_sha; do
  [ -z "$local_ref" ] && continue

  # Deletions are exempt from the taxonomy: a branch created outside it — a
  # leftover `bot/*` ref from a workflow that no longer exists (project-stub-fields.yml
  # was removed in #4919), or anything predating a tightening of the rules — must
  # still be deletable. Enforcing a name on the way out only strands the refs the
  # rule was meant to discourage. The `main` guard below still applies: deleting
  # main is at least as serious as pushing to it.
  is_deletion=0
  if is_zero_sha "$local_sha"; then
    is_deletion=1
  fi

  # Branch name validation — only for refs/heads/; tags, notes and deletions are exempt.
  if [ "$is_deletion" -eq 0 ] && [[ "$remote_ref" == refs/heads/* ]]; then
    branch_name="${remote_ref#refs/heads/}"
    if [ "$is_origin_local" -eq 1 ]; then
      if ! [[ "$branch_name" =~ $origin_draft_regex ]]; then
        echo "pre-push: '$branch_name' cannot go to the Origin-only endpoint." >&2
        echo "         origin-local accepts only origin/<slug>. Push promotion branches to origin or github." >&2
        failed=1
        continue
      fi
    elif [[ "$branch_name" == origin/* ]]; then
      echo "pre-push: refusing to push '$branch_name' onto GitHub or the mirror remote." >&2
      echo "         Publish Origin drafts with 'origin push local'. Promote with a task/, module/, or release/ branch." >&2
      failed=1
      continue
    elif [ "$is_local_forge" -eq 1 ] && [[ "$branch_name" =~ $local_change_regex ]]; then
      : # sctl change branches are local-forge only
    elif ! [[ "$branch_name" =~ $branch_regex ]]; then
      echo "pre-push: refusing to push branch '$branch_name' — doesn't match the taxonomy." >&2
      echo "         Allowed patterns (see BRANCHING.md):" >&2
      echo "           main | develop | release/vX.Y.Z" >&2
      echo "           module/<component>  (e.g. module/digiquant, module/digigraph)" >&2
      echo "           release-please--branches--<target>--components--<component>" >&2
      echo "                        (no release-please workflow remains; the pattern" >&2
      echo "                        stays so a leftover ref can still be pushed)" >&2
      echo "           task/<N>-<slug>" >&2
      echo "           {claude,codex,cursor,copilot}/<slug>" >&2
      echo "           {${CONTRIBUTOR_HANDLES//|/,}}/<slug>  (human contributors by GitHub handle)" >&2
      echo "           {feat,fix,docs,chore,revert}/<slug>" >&2
      echo "           bot/<slug>  (pushed by agent-backlog-snapshot.yml" >&2
      echo "                        and pipeline-provider-review.yml)" >&2
      echo "           rescue/<issue>-<date>  (kit/bin/dt-worktree-rescue;" >&2
      echo "                        e.g. rescue/DIG-1234-2026-10-21)" >&2
      echo "           DIG-<n>-<slug>  (a Paperclip execution workspace; push" >&2
      echo "                        per-issue, never blanket — BRANCHING.md)" >&2
      echo "           change/<id>    (local Forgejo sctl change; local forge only)" >&2
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

  # Block push to develop without explicit opt-in. develop carries
  # required_pull_request_reviews: null (BRANCHING.md), so unlike main there
  # is no server-side PR gate on it and this hook is the only guard.
  if [ "$remote_ref" = "refs/heads/develop" ] && [ "${ALLOW_DEVELOP_PUSH:-0}" != "1" ]; then
    echo "pre-push: refusing to push to 'develop'. Set ALLOW_DEVELOP_PUSH=1 if this is intentional." >&2
    echo "         Usual cause: this branch tracks develop upstream, so a bare 'git push' lands there. Fix: git branch --set-upstream-to=github/<branch> <branch>." >&2
    failed=1
    continue
  fi

  # Deletions have no commit range to scan; new-branch pushes are handled below.
  if [ "$is_deletion" -eq 1 ]; then
    continue
  fi

  # Determine the diff range: against the remote sha if present, else against origin/develop.
  if is_zero_sha "$remote_sha" || [ -z "$remote_sha" ]; then
    if [ "$is_local_forge" -eq 1 ]; then
      base="$(git merge-base "$local_sha" local/develop 2>/dev/null \
        || git merge-base "$local_sha" origin/develop 2>/dev/null || echo '')"
    else
      base="$(git merge-base "$local_sha" origin/develop 2>/dev/null || echo '')"
    fi
  else
    base="$remote_sha"
  fi

  # No base means the scan below cannot run. Refuse instead of skipping: "we could
  # not look" must never be indistinguishable from "we looked and it was clean" on
  # the one guard standing between a live-trading edit and origin.
  if [ -z "$base" ]; then
    echo "pre-push: cannot determine a diff base for '$local_ref' — refusing to push unscanned." >&2
    echo "         Usually origin/develop (or local/develop for the local forge) is missing locally:" >&2
    echo "         run 'git fetch origin' or 'git fetch local' and retry." >&2
    echo "         A ref whose history is unrelated to develop — an imported tag, a grafted" >&2
    echo "         branch — has no base by nature and cannot be scanned at all; that is the" >&2
    echo "         emergency the --no-verify escape at the top of this file exists for." >&2
    failed=1
    continue
  fi

  # Scan changed paths for live-trading touch. The directory fragment is
  # anchored to digiquant — a bare '/live/' also matched design-reference
  # screenshots under packages/**/references/**/live/ (false positives).
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

  # ── gitleaks: refuse a push that introduces a secret ───────────────────────
  # Same diff base as the live-trading scan above. This is the only scan a
  # topic-branch push gets: .github/workflows/security-gitleaks.yml runs on pull
  # requests and on pushes to develop/main, and the local forge has no scan at
  # all (scripts/forgejo-gitleaks-woodpecker-step.yml is a template with no
  # .woodpecker.yml behind it). So an unusable scanner is a refusal, not a
  # warning — "we could not look" must never read as "we looked and it was clean",
  # the same reason the base check above refuses.
  #
  # DIG-5722. Before this, a missing binary or config printed a line claiming
  # "CI still scans" and let the push through, which silently disarmed the guard
  # on exactly the machines where it was the only one. PRE_PUSH_SKIP_GITLEAKS=1
  # is the documented escape (see the header) and it is loud: it names the ref it
  # did not scan, so the bypass is discoverable in the operator's own output.
  gitleaks_root="$(git rev-parse --show-toplevel 2>/dev/null || echo '')"
  gitleaks_config="${gitleaks_root:+$gitleaks_root/.gitleaks.toml}"
  if [ "${PRE_PUSH_SKIP_GITLEAKS:-0}" = "1" ]; then
    if [ "$gitleaks_skip_noted" -eq 0 ]; then
      echo "pre-push: WARNING: secret scan skipped — PRE_PUSH_SKIP_GITLEAKS=1." >&2
      echo "         No other scan covers this push: GitHub gitleaks runs on pull" >&2
      echo "         requests and develop/main pushes only, and the local forge has none." >&2
      echo "         Use this for synthetic fixtures, not for a push you believe is clean." >&2
      echo "         Refs not scanned:" >&2
      gitleaks_skip_noted=1
    fi
    # One line per ref, not one per push: the header promises the escape prints
    # which refs it skipped, and throttling the whole note would name only the
    # first of a multi-ref push — the rest would read as scanned (DIG-5722 review).
    echo "           ${branch_name:-$local_ref}" >&2
  elif ! command -v gitleaks >/dev/null 2>&1; then
    echo "pre-push: gitleaks not found — refusing to push '${branch_name:-$local_ref}' unscanned." >&2
    echo "         Install it ('brew install gitleaks'; see SECURITY.md \"Secrets scanning\")" >&2
    echo "         and retry, or set PRE_PUSH_SKIP_GITLEAKS=1 to skip the scan for this" >&2
    echo "         push — that prints what it skips." >&2
    failed=1
    continue
  elif [ -z "$gitleaks_config" ] || [ ! -f "$gitleaks_config" ]; then
    echo "pre-push: .gitleaks.toml not found in '${gitleaks_root:-this checkout}' — refusing to push '${branch_name:-$local_ref}' unscanned." >&2
    echo "         Run this hook from a checkout of the repo and retry, or set" >&2
    echo "         PRE_PUSH_SKIP_GITLEAKS=1 to skip the scan for this push." >&2
    failed=1
    continue
  else
    if ! gitleaks detect --source "$gitleaks_root" --config "$gitleaks_config" --redact --no-banner \
         --log-opts="$base..$local_sha" >/dev/null 2>&1; then
      echo "pre-push: gitleaks found a secret in $base..$local_sha — refusing to push." >&2
      echo "         Remove the secret, rotate it if it was real, and retry." >&2
      failed=1
      continue
    fi
  fi

  # ── DIG-1589: duplicate-work guard (resume before create) ──────────────────
  # Appended last so a content refusal above is never masked by this one: the
  # live-trading arm is the safety gate, and the operator should read that
  # message first. Deliberately additive — no existing arm is modified.
  #
  # Runs on refs/heads/ only, because the guard is about branching: a tag or a
  # note pushed from an unmerged commit is not a second attempt at the work.
  if [ "$is_deletion" -eq 0 ] && [[ "$remote_ref" == refs/heads/* ]]; then
    # The guard refuses a *rebuild*, a second attempt at work already in flight.
    # It cannot tell a rebuild from an update on its own, so the kind of push has
    # to be stated here: git reports a ref the remote does not have as an
    # all-zero sha, which is the signal the diff base above already reads.
    # Without it the arm refuses every follow-up commit to an unmerged branch,
    # because such a branch keeps overlapping its siblings at every later commit.
    if [ -n "$remote_sha" ] && ! is_zero_sha "$remote_sha"; then
      push_kind="--is-update"
    else
      push_kind="--is-create"
    fi
    # An installed hook is a *copy* under .git/hooks, shared by every worktree,
    # so $0 cannot find the checker. Resolve it from the repository the push is
    # running in — the checker is committed, so a real checkout always has it.
    top="$(git rev-parse --show-toplevel 2>/dev/null || echo '')"
    checker="${BRANCH_RESTART_CHECK_PATH:-${top:+$top/scripts/branch_restart_check.py}}"
    if [ -z "$checker" ] || [ ! -f "$checker" ]; then
      echo "pre-push: duplicate-work guard skipped — scripts/branch_restart_check.py not found." >&2
      echo "         Run 'git fetch origin' and retry; without it a rebuilt branch cannot be detected." >&2
    elif ! command -v "${BRANCH_RESTART_CHECK_PYTHON:-python3}" >/dev/null 2>&1; then
      echo "pre-push: duplicate-work guard skipped — '${BRANCH_RESTART_CHECK_PYTHON:-python3}' not found." >&2
    elif ! restart_out="$("${BRANCH_RESTART_CHECK_PYTHON:-python3}" "$checker" "$local_sha" \
                            --branch-name "${branch_name:-$local_ref}" "$push_kind" 2>&1)"; then
      # Non-zero is a refusal; the checker has already written the reason and the
      # sibling list, and it carries the escapes that permit the push.
      printf '%s\n' "$restart_out" >&2
      failed=1
      continue
    elif [ -n "$restart_out" ]; then
      # Allowed, but something worth recording — an applied escape, or a
      # fail-open path. An escape that is invisible is an escape nobody trusts.
      printf '%s\n' "$restart_out" >&2
    fi
  fi

  # ── DIG-1579: branch-age warning (never blocks) ────────────────────────────
  # Appended last for the same reason as the arm above: a content refusal must
  # never be masked by a warning. Also purely additive — no existing arm moves.
  #
  # Deletions are exempt here too, and for a second reason to the taxonomy one:
  # § 4 of the policy clears stale refs with `git push origin --delete`, so
  # warning on the way out would print at the operator during exactly the
  # cleanup this hook exists to make cheap — and it must never become the reason
  # such a push fails.
  if [ "$is_deletion" -eq 0 ] && [[ "$remote_ref" == refs/heads/* ]]; then
    age_top="$(git rev-parse --show-toplevel 2>/dev/null || echo '')"
    age_checker="${BRANCH_AGE_WARNING_PATH:-${age_top:+$age_top/scripts/branch_age_warning.py}}"
    if [ -z "$age_checker" ] || [ ! -f "$age_checker" ]; then
      echo "pre-push: branch-age warning skipped — scripts/branch_age_warning.py not found." >&2
      echo "         Run 'git fetch origin' and retry." >&2
    elif ! command -v "${BRANCH_AGE_WARNING_PYTHON:-python3}" >/dev/null 2>&1; then
      echo "pre-push: branch-age warning skipped — '${BRANCH_AGE_WARNING_PYTHON:-python3}' not found." >&2
    else
      # `|| true` is load-bearing, not defensive noise: the module already exits 0
      # on every path, but a traceback or a signal must not become a non-zero
      # exit the way a refusal is. This arm has no opinion on the push.
      "${BRANCH_AGE_WARNING_PYTHON:-python3}" "$age_checker" "$local_sha" \
        --branch-name "${branch_name:-$local_ref}" 2>&1 || true
    fi
  fi
done

[ "$failed" -eq 0 ] || exit 1

exit 0
