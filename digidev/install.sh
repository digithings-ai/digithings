#!/usr/bin/env bash
# digidev installer
#
# Reads digidev/digidev.yml, substitutes placeholders, and copies template
# files to their canonical locations in the repository.
#
# Usage:
#   bash digidev/install.sh [--dry-run] [--force]
#
# Options:
#   --dry-run   Print what would be done without writing anything
#   --force     Overwrite existing files (default: skip if present)
#
# Idempotent: safe to re-run after editing digidev.yml.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
DIVIDEV_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$DIVIDEV_DIR/digidev.yml"

DRY_RUN=0
FORCE=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --force)   FORCE=1 ;;
  esac
done

# ── Helpers ───────────────────────────────────────────────────────────────────

log()   { echo "  $*"; }
ok()    { echo "  ✓ $*"; }
skip()  { echo "  – $* (already exists; use --force to overwrite)"; }
dry()   { echo "  [dry] $*"; }

die() {
  echo "error: $*" >&2
  exit 1
}

# Copy a template file to target, applying substitutions.
# Usage: install_file <src> <dst> [description]
install_file() {
  local src="$1" dst="$2" desc="${3:-}"
  local dst_abs="$REPO_ROOT/$dst"
  mkdir -p "$(dirname "$dst_abs")"

  if [ "$DRY_RUN" = "1" ]; then
    dry "would install: $dst${desc:+ — $desc}"
    return
  fi

  if [ -f "$dst_abs" ] && [ "$FORCE" = "0" ]; then
    skip "$dst"
    return
  fi

  # Apply substitutions using Python (portable, handles multiline values).
  python3 - "$src" "$dst_abs" <<'PY'
import sys, re

src_path, dst_path = sys.argv[1], sys.argv[2]

with open(src_path, encoding='utf-8') as f:
    content = f.read()

import os

subs = {k: v for k, v in os.environ.items() if k.startswith('DIVIDEV_TMPL_')}

for key, value in subs.items():
    placeholder = '{{' + key[len('DIVIDEV_TMPL_'):] + '}}'
    content = content.replace(placeholder, value)

with open(dst_path, 'w', encoding='utf-8') as f:
    f.write(content)
PY

  ok "$dst"
}

# Make a file executable.
make_exec() {
  local path="$REPO_ROOT/$1"
  if [ -f "$path" ]; then
    chmod +x "$path"
    if [ "$DRY_RUN" = "0" ]; then
      ok "chmod +x $1"
    fi
  fi
}

# ── Interactive wizard (runs when digidev.yml doesn't exist) ──────────────────

if [ ! -f "$CONFIG_FILE" ]; then
  if [ "$DRY_RUN" = "1" ]; then
    die "digidev/digidev.yml not found. Copy digidev/digidev.example.yml to digidev/digidev.yml first."
  fi

  if [ ! -t 0 ]; then
    die "digidev/digidev.yml not found and stdin is not a terminal. Create it from digidev/digidev.example.yml first."
  fi

  echo ""
  echo "digidev setup wizard"
  echo "No digidev/digidev.yml found — answering a few questions will create it."
  echo "(Press Ctrl-C to cancel; edit digidev/digidev.example.yml manually instead)"
  echo ""

  # Try to detect org/repo from git remote
  REMOTE_URL="$(git -C "$REPO_ROOT" remote get-url origin 2>/dev/null || true)"
  DETECTED_ORG=""
  DETECTED_REPO=""
  if [[ "$REMOTE_URL" =~ github\.com[:/]([^/]+)/([^/.]+)(\.git)?$ ]]; then
    DETECTED_ORG="${BASH_REMATCH[1]}"
    DETECTED_REPO="${BASH_REMATCH[2]}"
  fi

  # prompt <label> <default>
  # Prints the entered value (or default) to stdout. Required if no default.
  _prompt() {
    local label="$1" default="$2" value=""
    if [ -n "$default" ]; then
      read -r -p "  $label [$default]: " value < /dev/tty
      printf '%s' "${value:-$default}"
    else
      while [ -z "$value" ]; do
        read -r -p "  $label (required): " value < /dev/tty
        [ -z "$value" ] && echo "    ↳ this field is required" >&2
      done
      printf '%s' "$value"
    fi
  }

  WIZ_PROJECT="$(_prompt "Project name"        "$(basename "$REPO_ROOT")")"
  WIZ_ORG="$(    _prompt "GitHub org/username"  "$DETECTED_ORG")"
  WIZ_REPO="$(   _prompt "GitHub repo name"     "${DETECTED_REPO:-$(basename "$REPO_ROOT")}")"
  WIZ_DEFAULT="$(_prompt "Integration branch"   "develop")"
  WIZ_MAIN="$(   _prompt "Production branch"    "main")"
  WIZ_HANDLES="$(_prompt "Your GitHub handle(s), pipe-separated" "${WIZ_ORG}")"
  WIZ_STACK="$(  _prompt "Tech stack (python/node/python+node)" "python")"

  echo ""
  echo "  Components — enter one per line, blank line when done:"
  WIZ_COMPONENTS_YAML=""
  while true; do
    read -r -p "  Component name (Enter to finish): " comp_name < /dev/tty
    [ -z "$comp_name" ] && break
    read -r -p "    Description: " comp_desc < /dev/tty
    read -r -p "    Test command [make test-unit]: " comp_test < /dev/tty
    comp_test="${comp_test:-make test-unit}"
    WIZ_COMPONENTS_YAML="${WIZ_COMPONENTS_YAML}  - name: ${comp_name}
    description: \"${comp_desc:-$comp_name}\"
    test_cmd: \"${comp_test}\"
"
  done
  [ -z "$WIZ_COMPONENTS_YAML" ] && WIZ_COMPONENTS_YAML='  - name: api
    description: "API service"
    test_cmd: "make test-unit"
'

  cat > "$CONFIG_FILE" <<YMLEOF
project_name: "${WIZ_PROJECT}"
org_name: "${WIZ_ORG}"
repo_name: "${WIZ_REPO}"
default_branch: "${WIZ_DEFAULT}"
main_branch: "${WIZ_MAIN}"
contributor_handles: "${WIZ_HANDLES}"
tech_stack: "${WIZ_STACK}"

components:
${WIZ_COMPONENTS_YAML}
scoring_thresholds:
  security: 8
  quality: 8
  optimization: 7
  accuracy: 9

protected_paths:
  - "SECURITY.md"
  - ".github/workflows/"
  - "docs/scoring/"

live_trading_regex: ""

allowed_hosts:
  - "github.com"
  - "api.github.com"
  - "raw.githubusercontent.com"
  - "pypi.org"
  - "files.pythonhosted.org"
  - "docker.io"
  - "ghcr.io"
  - "anthropic.com"
  - "api.anthropic.com"
  - "openai.com"
  - "api.openai.com"
  - "claude.ai"
  - "cursor.com"
  - "localhost"
  - "127.0.0.1"

github_projects:
  default_project: 1

project_token_secret: "PROJECT_TOKEN"
copilot_quota_state_issue: 0
YMLEOF

  echo ""
  ok "Created digidev/digidev.yml"
  echo ""
fi

# ── Read config ───────────────────────────────────────────────────────────────

# Parse YAML with Python and export as DIVIDEV_TMPL_* env vars for substitution.
eval "$(python3 - "$CONFIG_FILE" <<'PY'
import sys, re

try:
    import yaml
    with open(sys.argv[1]) as f:
        cfg = yaml.safe_load(f)
except ImportError:
    # Fallback: minimal YAML parser for simple key: value lines
    cfg = {}
    with open(sys.argv[1]) as f:
        for line in f:
            line = line.rstrip()
            if not line or line.lstrip().startswith('#'):
                continue
            m = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*"?([^"#\n]*)"?\s*$', line)
            if m:
                cfg[m.group(1)] = m.group(2).strip()

def sh_export(key, val):
    safe = str(val).replace("'", "'\\''")
    print(f"export DIVIDEV_TMPL_{key}='{safe}'")

project_name = cfg.get('project_name', 'myproject')
org_name     = cfg.get('org_name', 'myorg')
repo_name    = cfg.get('repo_name', 'myrepo')
default_branch = cfg.get('default_branch', 'develop')
main_branch    = cfg.get('main_branch', 'main')
contributor_handles = cfg.get('contributor_handles', 'contributor')
live_trading_regex  = cfg.get('live_trading_regex', '(live_trading|execute_trade)')
tech_stack = cfg.get('tech_stack', 'python')
project_token_secret = cfg.get('project_token_secret', 'PROJECT_TOKEN')
copilot_quota_issue  = str(cfg.get('copilot_quota_state_issue', 0))

repo_url_https = f"https://github.com/{org_name}/{repo_name}"
repo_url_ssh   = f"git@github.com:{org_name}/{repo_name}"
repo_full      = f"{org_name}/{repo_name}"

# Extract scoring thresholds
thresholds = cfg.get('scoring_thresholds', {})
if isinstance(thresholds, dict):
    score_security     = str(thresholds.get('security', 8))
    score_quality      = str(thresholds.get('quality', 8))
    score_optimization = str(thresholds.get('optimization', 7))
    score_accuracy     = str(thresholds.get('accuracy', 9))
else:
    score_security = score_quality = '8'
    score_optimization = '7'
    score_accuracy = '9'

# Build component list
components_raw = cfg.get('components', [])
if isinstance(components_raw, list):
    component_names = [c.get('name', c) if isinstance(c, dict) else str(c)
                       for c in components_raw]
else:
    component_names = ['api']
components_space  = ' '.join(component_names)
components_comma  = ', '.join(component_names)

# Protected paths
protected_raw = cfg.get('protected_paths', [])
if isinstance(protected_raw, list):
    protected_list = '\n  '.join(f'"$PROJECT_ROOT/{p}"' for p in protected_raw)
else:
    protected_list = '"$PROJECT_ROOT/SECURITY.md"\n  "$PROJECT_ROOT/.github/workflows/"'

# Allowed hosts
allowed_raw = cfg.get('allowed_hosts', [])
if isinstance(allowed_raw, list):
    allowed_hosts_bash = '\n  '.join(f'"{h}"' for h in allowed_raw)
else:
    allowed_hosts_bash = '"github.com"\n  "localhost"'

sh_export('PROJECT_NAME', project_name)
sh_export('ORG_NAME', org_name)
sh_export('REPO_NAME', repo_name)
sh_export('REPO_FULL', repo_full)
sh_export('REPO_URL_HTTPS', repo_url_https)
sh_export('REPO_URL_SSH', repo_url_ssh)
sh_export('DEFAULT_BRANCH', default_branch)
sh_export('MAIN_BRANCH', main_branch)
sh_export('CONTRIBUTOR_HANDLES', contributor_handles)
sh_export('LIVE_TRADING_REGEX', live_trading_regex)
sh_export('TECH_STACK', tech_stack)
sh_export('PROJECT_TOKEN_SECRET', project_token_secret)
sh_export('COPILOT_QUOTA_ISSUE', copilot_quota_issue)
sh_export('SCORE_SECURITY', score_security)
sh_export('SCORE_QUALITY', score_quality)
sh_export('SCORE_OPTIMIZATION', score_optimization)
sh_export('SCORE_ACCURACY', score_accuracy)
checkbox_lines = '\n'.join(f'- [ ] {n}' for n in component_names)

# YAML block for agents.yml components section
agents_yml_comps = []
for comp in (components_raw if isinstance(components_raw, list) else []):
    if isinstance(comp, dict):
        n = comp.get('name', '')
        d = comp.get('description', n)
        t = comp.get('test_cmd', f'make test-unit')
        p = comp.get('port')
        entry = f'  - name: {n}\n    description: "{d}"\n    test_cmd: "{t}"'
        if p:
            entry += f'\n    port: {p}'
        agents_yml_comps.append(entry)
agents_yml_components = '\n'.join(agents_yml_comps) if agents_yml_comps else '  - name: api\n    description: "API service"\n    test_cmd: "make test-unit"'
sh_export('COMPONENTS_SPACE', components_space)
sh_export('COMPONENTS_COMMA', components_comma)
sh_export('COMPONENT_CHECKBOXES', checkbox_lines)
sh_export('AGENTS_YML_COMPONENTS', agents_yml_components)
sh_export('PROTECTED_PATHS_BASH', protected_list)
sh_export('ALLOWED_HOSTS_BASH', allowed_hosts_bash)
PY
)"

# Validate required fields.
if [ "$DIVIDEV_TMPL_PROJECT_NAME" = "YOUR_PROJECT" ]; then
  die "digidev.yml: project_name is not set. Edit digidev/digidev.yml first."
fi
if [ "$DIVIDEV_TMPL_ORG_NAME" = "YOUR_ORG" ]; then
  die "digidev.yml: org_name is not set. Edit digidev/digidev.yml first."
fi
if [ "$DIVIDEV_TMPL_REPO_NAME" = "YOUR_REPO" ]; then
  die "digidev.yml: repo_name is not set. Edit digidev/digidev.yml first."
fi

echo ""
echo "digidev installer"
echo "  project : $DIVIDEV_TMPL_PROJECT_NAME"
echo "  repo    : $DIVIDEV_TMPL_ORG_NAME/$DIVIDEV_TMPL_REPO_NAME"
echo "  branch  : $DIVIDEV_TMPL_DEFAULT_BRANCH ← task/* ← module/*"
echo "  stack   : $DIVIDEV_TMPL_TECH_STACK"
echo ""

# ── Claude Code surface ───────────────────────────────────────────────────────

echo "→ Claude Code settings"
install_file "$DIVIDEV_DIR/templates/claude-settings.json" ".claude/settings.json"

# ── Claude hooks ──────────────────────────────────────────────────────────────

echo "→ Claude Code hook scripts"
hooks_src="$DIVIDEV_DIR/templates/hooks/claude"
hooks_dst="scripts/claude-hooks"

for f in _lib.sh project-root-guard.sh protected-path-guard.sh branch-warn.sh \
          remote-guard.sh network-host-guard.sh protected-path-bash-guard.sh \
          component-router-preflight.sh auto-format.sh; do
  install_file "$hooks_src/$f" "$hooks_dst/$f"
done

# Make hook scripts executable.
for f in project-root-guard.sh protected-path-guard.sh branch-warn.sh \
          remote-guard.sh network-host-guard.sh protected-path-bash-guard.sh \
          component-router-preflight.sh auto-format.sh; do
  make_exec "$hooks_dst/$f"
done

# ── Git hooks ─────────────────────────────────────────────────────────────────

echo "→ Git hook scripts"
install_file "$DIVIDEV_DIR/templates/hooks/git/pre-push.sh" "scripts/hooks/pre-push.sh"
make_exec "scripts/hooks/pre-push.sh"

# ── GitHub templates ──────────────────────────────────────────────────────────

echo "→ GitHub issue + PR templates"
install_file "$DIVIDEV_DIR/templates/github/ISSUE_TEMPLATE/agent_task.yml" \
             ".github/ISSUE_TEMPLATE/agent_task.yml"
install_file "$DIVIDEV_DIR/templates/github/ISSUE_TEMPLATE/config.yml" \
             ".github/ISSUE_TEMPLATE/config.yml"
install_file "$DIVIDEV_DIR/templates/github/PULL_REQUEST_TEMPLATE.md" \
             ".github/PULL_REQUEST_TEMPLATE.md"

echo "→ GitHub workflows"
install_file "$DIVIDEV_DIR/templates/github/workflows/claude-code-dispatch.yml" \
             ".github/workflows/claude-code-dispatch.yml"
install_file "$DIVIDEV_DIR/templates/github/workflows/auto-assign-copilot.yml" \
             ".github/workflows/auto-assign-copilot.yml"
install_file "$DIVIDEV_DIR/templates/github/workflows/route-issues-to-projects.yml" \
             ".github/workflows/route-issues-to-projects.yml"

# ── Project manifest ──────────────────────────────────────────────────────────

echo "→ agents.yml project manifest"
install_file "$DIVIDEV_DIR/templates/agents.yml" "agents.yml"

echo "→ AGENTS.md"
install_file "$DIVIDEV_DIR/templates/AGENTS.md" "AGENTS.md"

# ── Makefile.include ──────────────────────────────────────────────────────────

echo "→ Makefile.include"
install_file "$DIVIDEV_DIR/Makefile.include" "Makefile.digidev" \
  "Add 'include Makefile.digidev' to your Makefile to get agent workflow targets"

# ── Scoring docs ──────────────────────────────────────────────────────────────

echo "→ Scoring rubrics"
for doc in README.md SECURITY.md QUALITY.md OPTIMIZATION.md ACCURACY.md; do
  install_file "$DIVIDEV_DIR/docs/scoring/$doc" "docs/scoring/$doc"
done

# ── Per-component AGENTS.md ───────────────────────────────────────────────────

echo "→ Component AGENTS.md files"
python3 - "$CONFIG_FILE" "$DIVIDEV_DIR/templates/COMPONENT_AGENTS.md" \
  "$REPO_ROOT" "$DRY_RUN" "$FORCE" <<'PY'
import sys, os, re

config_file = sys.argv[1]
template_path = sys.argv[2]
repo_root = sys.argv[3]
dry_run = sys.argv[4] == '1'
force = sys.argv[5] == '1'

try:
    import yaml
    with open(config_file) as f:
        cfg = yaml.safe_load(f)
except ImportError:
    cfg = {}

components = cfg.get('components', [])
if not isinstance(components, list):
    sys.exit(0)

with open(template_path, encoding='utf-8') as f:
    template = f.read()

for comp in components:
    if isinstance(comp, dict):
        name = comp.get('name', '')
        desc = comp.get('description', name)
        test_cmd = comp.get('test_cmd', f'pytest -m unit -k {name} -v')
    else:
        name = str(comp)
        desc = name
        test_cmd = f'pytest -m unit -k {name} -v'

    if not name:
        continue

    content = template.replace('{{COMPONENT_NAME}}', name)
    content = content.replace('{{COMPONENT_DESCRIPTION}}', desc)
    content = content.replace('{{COMPONENT_TEST_CMD}}', test_cmd)
    content = content.replace('{{DEFAULT_BRANCH}}', os.environ.get('DIVIDEV_TMPL_DEFAULT_BRANCH', 'develop'))

    dst = os.path.join(repo_root, name, 'AGENTS.md')
    if dry_run:
        print(f'  [dry] would create: {name}/AGENTS.md')
        continue
    if os.path.exists(dst) and not force:
        print(f'  – {name}/AGENTS.md (already exists; use --force to overwrite)')
        continue
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'  ✓ {name}/AGENTS.md')
PY

# ── Claude Code subagents ─────────────────────────────────────────────────────

echo "→ Claude Code subagents"
agents_src="$DIVIDEV_DIR/templates/claude/agents"
agents_dst=".claude/agents"
for f in component-router.md dictation-normalizer.md spec-writer.md \
          pr-reviewer.md security-reviewer.md test-first-implementer.md; do
  install_file "$agents_src/$f" "$agents_dst/$f"
done

# ── Claude Code skills ────────────────────────────────────────────────────────

echo "→ Claude Code skills"
skills_src="$DIVIDEV_DIR/templates/claude/skills"
skills_dst=".claude/skills"
for skill in finish-task score-and-fix worktree-task-start \
             write-acceptance-criteria ci-triage triage; do
  install_file "$skills_src/$skill/SKILL.md" "$skills_dst/$skill/SKILL.md"
done

# ── Claude Code slash commands ────────────────────────────────────────────────

echo "→ Claude Code slash commands"
cmds_src="$DIVIDEV_DIR/templates/claude/commands"
cmds_dst=".claude/commands"
for cmd in normalize.md spec.md score.md task.md triage.md; do
  install_file "$cmds_src/$cmd" "$cmds_dst/$cmd"
done

# ── Done ──────────────────────────────────────────────────────────────────────

echo ""
if [ "$DRY_RUN" = "1" ]; then
  echo "Dry run complete — no files written."
else
  echo "Installation complete."
  echo ""
  echo "Next steps:"
  echo ""
  echo "  1. Add to your Makefile:"
  echo "       include Makefile.digidev"
  echo ""
  echo "  2. Install the git pre-push hook:"
  echo "       make hooks-install"
  echo ""
  echo "  3. Create GitHub labels (run once per repo):"
  echo "       gh label create 'agent-task'   --color 'ededed'"
  echo "       gh label create 'exec:claude'  --color '7057ff'"
  echo "       gh label create 'exec:cursor'  --color '0075ca'"
  echo "       gh label create 'exec:copilot' --color 'cfd3d7'"
  echo "       gh label create 'risk:low'     --color '0e8a16'"
  echo "       gh label create 'risk:med'     --color 'e4e669'"
  echo "       gh label create 'risk:high'    --color 'd93f0b'"
  echo "       # Plus one component label per component in your project"
  echo ""
  echo "  4. Commit:"
  echo "       git add .claude/ .github/ scripts/ agents.yml AGENTS.md Makefile.digidev"
  echo "       git add */AGENTS.md docs/scoring/ docs/agents/ digidev/"
  echo "       git commit -m 'chore: install digidev agentic workflow kit'"
  echo "       git push"
  echo ""
  echo "  5. Verify:"
  echo "       make status      # list open agent-task issues"
  echo "       make new-task    # create your first task"
fi
echo ""
