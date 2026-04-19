#!/usr/bin/env bash
# module_branches.sh — Manage long-lived module integration branches.
#
# Usage:
#   scripts/module_branches.sh status          # show each module branch vs develop
#   scripts/module_branches.sh sync            # fast-forward all module branches from develop
#   scripts/module_branches.sh switch MODULE   # checkout module/<MODULE>
#   scripts/module_branches.sh pr MODULE       # open a PR from module/<MODULE> → develop
#
# Module branches sit between develop and task branches:
#   develop ← module/<component> ← task/<N>-<slug>
#
# Each Claude Code session focused on a module should work on its module branch.
# Task branches (make task ISSUE=N) are created automatically from the right module branch.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

MODULES=(digigraph digiquant digisearch digichat digikey digismith digiclaw digibase)

die()    { echo "ERROR: $*" >&2; exit 1; }
header() { echo ""; echo "── $* ──"; }

cmd_status() {
  header "Module branch status"
  printf "%-25s %-10s %-10s %s\n" "BRANCH" "AHEAD" "BEHIND" "LAST COMMIT"
  printf "%-25s %-10s %-10s %s\n" "------" "-----" "------" "-----------"

  git fetch origin --quiet 2>/dev/null || true

  for mod in "${MODULES[@]}"; do
    branch="module/$mod"
    if ! git show-ref --verify --quiet "refs/remotes/origin/$branch" && \
       ! git show-ref --verify --quiet "refs/heads/$branch"; then
      printf "%-25s %s\n" "$branch" "(not found)"
      continue
    fi

    local_ref="refs/heads/$branch"
    remote_ref="refs/remotes/origin/$branch"
    ref="${local_ref}"
    git show-ref --verify --quiet "$local_ref" || ref="$remote_ref"

    ahead=$(git rev-list --count "origin/develop..${ref}" 2>/dev/null || echo "?")
    behind=$(git rev-list --count "${ref}..origin/develop" 2>/dev/null || echo "?")
    last=$(git log -1 --format="%ar" "$ref" 2>/dev/null || echo "unknown")

    printf "%-25s %-10s %-10s %s\n" "$branch" "+$ahead" "-$behind" "$last"
  done
  echo ""
}

cmd_sync() {
  header "Syncing module branches from develop"
  git fetch origin develop --quiet

  for mod in "${MODULES[@]}"; do
    branch="module/$mod"
    if git show-ref --verify --quiet "refs/heads/$branch"; then
      current=$(git branch --show-current)
      if [[ "$current" == "$branch" ]]; then
        echo "  $branch — skipped (currently checked out)"
        continue
      fi
      # Fast-forward only — refuse if diverged
      if git merge-base --is-ancestor "origin/develop" "$branch" 2>/dev/null; then
        echo "  $branch — already up to date"
      else
        git fetch origin "$branch:$branch" --quiet 2>/dev/null || true
        if git merge-base --is-ancestor "$branch" "origin/develop" 2>/dev/null; then
          git branch -f "$branch" origin/develop
          echo "  $branch — fast-forwarded to develop"
        else
          echo "  $branch — diverged from develop (manual merge required)"
        fi
      fi
    else
      git branch "$branch" origin/develop
      echo "  $branch — created from develop"
    fi
  done
}

cmd_switch() {
  local mod="${1:-}"
  [[ -z "$mod" ]] && die "Usage: module_branches.sh switch MODULE (e.g. digiquant)"
  mod="${mod#module/}"  # strip prefix if provided

  local found=false
  for m in "${MODULES[@]}"; do
    [[ "$m" == "$mod" ]] && found=true && break
  done
  $found || die "Unknown module '$mod'. Valid: ${MODULES[*]}"

  local branch="module/$mod"
  if ! git show-ref --verify --quiet "refs/heads/$branch"; then
    echo "Fetching $branch from origin..."
    git fetch origin "$branch:$branch"
  fi
  git checkout "$branch"
  echo ""
  echo "On $branch. Task branches created with 'make task ISSUE=N' will branch from here."
}

cmd_pr() {
  local mod="${1:-}"
  [[ -z "$mod" ]] && die "Usage: module_branches.sh pr MODULE (e.g. digiquant)"
  mod="${mod#module/}"
  local branch="module/$mod"

  git show-ref --verify --quiet "refs/heads/$branch" || \
    die "Branch $branch not found locally. Run: scripts/module_branches.sh switch $mod"

  # Count commits ahead of develop
  ahead=$(git rev-list --count "origin/develop..${branch}" 2>/dev/null || echo 0)
  if [[ "$ahead" -eq 0 ]]; then
    echo "No commits ahead of develop on $branch — nothing to PR."
    exit 0
  fi

  echo "Opening PR: $branch → develop ($ahead commits)"
  git push origin "$branch" --set-upstream --quiet

  COMMITS=$(git log --oneline "origin/develop..${branch}" | head -20)
  gh pr create \
    --title "module($mod): integrate $mod work into develop" \
    --base develop \
    --body "$(cat <<BODY
## Module integration PR — \`$mod\`

Batches completed task branches from \`module/$mod\` into \`develop\`.

### Commits included
\`\`\`
$COMMITS
\`\`\`

## Test plan
- [ ] Module unit tests pass: \`pytest -m unit -k $mod -v\`
- [ ] Score gate: \`make score\`
- [ ] End-to-end smoke: \`make test-e2e\` (if stack up)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
BODY
)"
}

CMD="${1:-status}"
shift || true

case "$CMD" in
  status) cmd_status ;;
  sync)   cmd_sync ;;
  switch) cmd_switch "${1:-}" ;;
  pr)     cmd_pr "${1:-}" ;;
  *) die "Unknown command: $CMD. Valid: status, sync, switch, pr" ;;
esac
