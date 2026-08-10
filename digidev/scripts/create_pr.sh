#!/usr/bin/env bash
# digidev create_pr.sh — open a PR using the project template
# Usage: scripts/create_pr.sh
set -euo pipefail

BRANCH=$(git rev-parse --abbrev-ref HEAD)

# ── Extract issue number from branch name ──────────────────────────────────────
ISSUE_NUM=""
if [[ "$BRANCH" =~ ^task/([0-9]+)- ]]; then
  ISSUE_NUM="${BASH_REMATCH[1]}"
fi

# ── Read config ───────────────────────────────────────────────────────────────
DEFAULT_BRANCH="develop"
ISSUE_TRACKER="github"
if [[ -f "agents.yml" ]]; then
  eval "$(python3 - <<'PY'
import re
try:
    import yaml
    cfg = yaml.safe_load(open("agents.yml"))
    print(f"DEFAULT_BRANCH='{cfg.get('default_branch', 'develop')}'")
    print(f"ISSUE_TRACKER='{cfg.get('issue_tracker', 'github')}'")
except ImportError:
    txt = open("agents.yml").read()
    m = re.search(r"default_branch:\s*(\S+)", txt)
    print(f"DEFAULT_BRANCH='{m.group(1) if m else 'develop'}'")
    m2 = re.search(r"issue_tracker:\s*(\S+)", txt)
    print(f"ISSUE_TRACKER='{m2.group(1) if m2 else 'github'}'")
PY
)"
fi

# ── Determine base branch ─────────────────────────────────────────────────────
BASE="$DEFAULT_BRANCH"
# If there's a module/* branch that matches, target that instead
if [[ "$BRANCH" =~ ^task/[0-9]+-(.+)$ ]]; then
  SLUG="${BASH_REMATCH[1]}"
  # Look up component from agents.yml
  COMPONENT=$(python3 - "$SLUG" <<'PY' 2>/dev/null || echo "")
import sys, re
slug = sys.argv[1]
try:
    import yaml
    cfg = yaml.safe_load(open("agents.yml"))
    for comp in cfg.get("components", []):
        name = comp.get("name", comp) if isinstance(comp, dict) else str(comp)
        if name in slug:
            print(name)
            sys.exit(0)
except Exception:
    pass
PY
  if [[ -n "$COMPONENT" ]]; then
    MODULE_BRANCH="module/${COMPONENT}"
    if git show-ref --verify --quiet "refs/remotes/origin/${MODULE_BRANCH}" 2>/dev/null; then
      BASE="$MODULE_BRANCH"
    fi
  fi
fi

# ── Detect git platform ───────────────────────────────────────────────────────
GIT_PLATFORM="github"
if [[ -f "agents.yml" ]]; then
  GIT_PLATFORM=$(python3 -c "
import re
try:
    import yaml
    cfg = yaml.safe_load(open('agents.yml'))
    print(cfg.get('git_platform', 'github'))
except ImportError:
    txt = open('agents.yml').read()
    m = re.search(r'git_platform:\s*(\S+)', txt)
    print(m.group(1) if m else 'github')
" 2>/dev/null || echo "github")
fi

# ── Build PR body ─────────────────────────────────────────────────────────────
FIXES_LINE=""
[[ -n "$ISSUE_NUM" ]] && FIXES_LINE="Closes #${ISSUE_NUM}"

SCORE_JSON=".score-last.json"
SCORE_SUMMARY=""
if [[ -f "$SCORE_JSON" ]]; then
  SCORE_SUMMARY=$(python3 - "$SCORE_JSON" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    lines = [f"- {k}: {v['score']}/10 ({'✓' if v['passed'] else '✗'})" for k,v in d.items()]
    print('\n'.join(lines))
except Exception:
    pass
PY
)
fi

PR_BODY=$(cat <<BODY
## Summary

<!-- What changed and why -->

${FIXES_LINE}

## Self-score

${SCORE_SUMMARY:-<!-- Run \`make score\` and paste results here -->}

## Testing evidence

<!-- Paste relevant test output or describe manual testing -->

## Human gates

Mark any that apply — these require human review before merge:

- [ ] Touches authentication / authorization
- [ ] Adds or changes a secret / credential / API key
- [ ] Exposes a new network port or endpoint
- [ ] Changes live-trading or financial execution paths
- [ ] Adds a new service or external dependency
- [ ] Introduces novel architecture not covered by ARCHITECTURE.md
BODY
)

# ── Create PR ─────────────────────────────────────────────────────────────────
echo ""
echo "→ Branch: $BRANCH"
echo "→ Base:   $BASE"
[[ -n "$ISSUE_NUM" ]] && echo "→ Issue:  #$ISSUE_NUM"
echo ""

case "$GIT_PLATFORM" in
  gitlab)
    if command -v glab &>/dev/null; then
      glab mr create \
        --source-branch "$BRANCH" \
        --target-branch "$BASE" \
        --title "$(git log -1 --pretty=%s)" \
        --description "$PR_BODY" \
        --draft
    else
      echo "Install glab CLI: https://gitlab.com/gitlab-org/cli"
      echo "Or open a MR manually from: $(git remote get-url origin)"
    fi
    ;;
  *)
    if ! command -v gh &>/dev/null; then
      echo "Error: gh CLI required. Install: https://cli.github.com/"
      exit 1
    fi
    git push -u origin "$BRANCH" 2>/dev/null || git push --set-upstream origin "$BRANCH"
    gh pr create \
      --base "$BASE" \
      --title "$(git log -1 --pretty=%s)" \
      --body "$PR_BODY" \
      --draft
    ;;
esac
echo ""
