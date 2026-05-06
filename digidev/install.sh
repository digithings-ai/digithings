#!/usr/bin/env bash
# digidev installer
#
# Layers a complete agentic coding workflow on any codebase. Reads
# digidev/digidev.yml, substitutes placeholders, and copies template files to
# their canonical locations. Asks about your existing tools (git platform, issue
# tracker, communication, database) and generates MCP config for each.
#
# Usage:
#   bash digidev/install.sh [--dry-run] [--force] [--setup-mcp]
#
# Options:
#   --dry-run    Print what would be done without writing anything
#   --force      Overwrite existing files (default: skip if present)
#   --setup-mcp  Re-run integration discovery and regenerate .mcp.json
#
# Idempotent: safe to re-run after editing digidev.yml.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
DIVIDEV_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$DIVIDEV_DIR/digidev.yml"

DRY_RUN=0
FORCE=0
SETUP_MCP=0
for arg in "$@"; do
  case "$arg" in
    --dry-run)   DRY_RUN=1 ;;
    --force)     FORCE=1 ;;
    --setup-mcp) SETUP_MCP=1 ;;
  esac
done

# ── Detect existing codebase properties ──────────────────────────────────────

_has_file() { [[ -f "$REPO_ROOT/$1" ]]; }

DETECTED_PYTHON=0; DETECTED_NODE=0; DETECTED_RUST=0; DETECTED_GO=0
DETECTED_MAKEFILE=0; DETECTED_GITHUB=0; DETECTED_GITLAB=0; DETECTED_EXISTING_CLAUDE=0

_has_file "pyproject.toml"   && DETECTED_PYTHON=1
_has_file "requirements.txt" && DETECTED_PYTHON=1
_has_file "setup.py"         && DETECTED_PYTHON=1
_has_file "package.json"     && DETECTED_NODE=1
_has_file "Cargo.toml"       && DETECTED_RUST=1
_has_file "go.mod"           && DETECTED_GO=1
_has_file "Makefile"         && DETECTED_MAKEFILE=1
_has_file ".github/workflows/$(ls "$REPO_ROOT/.github/workflows/" 2>/dev/null | head -1)" 2>/dev/null \
  && DETECTED_GITHUB=1
[[ -d "$REPO_ROOT/.github" ]] && DETECTED_GITHUB=1
[[ -d "$REPO_ROOT/.gitlab-ci.yml" ]] || _has_file ".gitlab-ci.yml" && DETECTED_GITLAB=1
[[ -d "$REPO_ROOT/.claude" ]] && DETECTED_EXISTING_CLAUDE=1

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
  echo "────────────────────────────────────────────────────"
  echo "  digidev setup wizard"
  echo "  Layering agentic workflow on: $(basename "$REPO_ROOT")"
  echo "────────────────────────────────────────────────────"
  echo ""

  # Detect existing codebase signals and print summary
  [[ "$DETECTED_EXISTING_CLAUDE" = "1" ]] && echo "  ℹ  Existing .claude/ found — digidev will extend it."
  [[ "$DETECTED_PYTHON" = "1" ]]          && echo "  ℹ  Python project detected."
  [[ "$DETECTED_NODE" = "1" ]]            && echo "  ℹ  Node.js project detected."
  [[ "$DETECTED_RUST" = "1" ]]            && echo "  ℹ  Rust project detected."
  [[ "$DETECTED_GO" = "1" ]]              && echo "  ℹ  Go project detected."
  [[ "$DETECTED_MAKEFILE" = "1" ]]        && echo "  ℹ  Makefile found — will add 'include Makefile.digidev'."
  echo ""
  echo "  Press Ctrl-C to cancel. Edit digidev/digidev.example.yml manually instead."
  echo ""

  # prompt <label> <default>
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

  # Auto-detect from git remote
  REMOTE_URL="$(git -C "$REPO_ROOT" remote get-url origin 2>/dev/null || true)"
  DETECTED_ORG=""; DETECTED_REPO=""
  if [[ "$REMOTE_URL" =~ github\.com[:/]([^/]+)/([^/.]+)(\.git)?$ ]]; then
    DETECTED_ORG="${BASH_REMATCH[1]}"
    DETECTED_REPO="${BASH_REMATCH[2]}"
  elif [[ "$REMOTE_URL" =~ gitlab\.com[:/]([^/]+)/([^/.]+)(\.git)?$ ]]; then
    DETECTED_ORG="${BASH_REMATCH[1]}"
    DETECTED_REPO="${BASH_REMATCH[2]}"
  fi

  # Detect stack
  DEFAULT_STACK="python"
  [[ "$DETECTED_NODE" = "1" && "$DETECTED_PYTHON" = "0" ]] && DEFAULT_STACK="node"
  [[ "$DETECTED_NODE" = "1" && "$DETECTED_PYTHON" = "1" ]] && DEFAULT_STACK="python+node"
  [[ "$DETECTED_RUST" = "1" ]] && DEFAULT_STACK="rust"
  [[ "$DETECTED_GO" = "1" ]]   && DEFAULT_STACK="go"

  echo "── Project ──────────────────────────────────────────"
  WIZ_PROJECT="$(_prompt "Project name"      "$(basename "$REPO_ROOT")")"
  WIZ_DEFAULT="$(_prompt "Integration branch" "develop")"
  WIZ_MAIN="$(   _prompt "Production branch"  "main")"
  WIZ_STACK="$(  _prompt "Tech stack (python/node/python+node/rust/go)" "$DEFAULT_STACK")"
  WIZ_HANDLES="$(_prompt "Your handle(s), pipe-separated (for branch allowlist)" "${DETECTED_ORG:-contributor}")"

  echo ""
  echo "── Git platform ──────────────────────────────────────"
  echo "  1) GitHub  2) GitLab  3) Bitbucket  4) Other"
  read -r -p "  Git platform [1]: " _git_choice < /dev/tty
  case "${_git_choice:-1}" in
    2) WIZ_GIT_PLATFORM="gitlab"    ;;
    3) WIZ_GIT_PLATFORM="bitbucket" ;;
    4) WIZ_GIT_PLATFORM="other"     ;;
    *) WIZ_GIT_PLATFORM="github"    ;;
  esac

  if [[ "$WIZ_GIT_PLATFORM" == "github" || "$WIZ_GIT_PLATFORM" == "gitlab" ]]; then
    WIZ_ORG="$(   _prompt "  Org/username"    "$DETECTED_ORG")"
    WIZ_REPO="$(  _prompt "  Repository name" "${DETECTED_REPO:-$(basename "$REPO_ROOT")}")"
  else
    WIZ_ORG="$(   _prompt "  Org/username"    "")"
    WIZ_REPO="$(  _prompt "  Repository name" "$(basename "$REPO_ROOT")")"
  fi

  echo ""
  echo "── Issue / task tracker ──────────────────────────────"
  echo "  What do you use for issue management?"
  echo "  1) GitHub Issues  2) Jira  3) Linear  4) Notion  5) Other / none"
  read -r -p "  Choice [1]: " _tracker_choice < /dev/tty
  case "${_tracker_choice:-1}" in
    2) WIZ_ISSUE_TRACKER="jira"   ;;
    3) WIZ_ISSUE_TRACKER="linear" ;;
    4) WIZ_ISSUE_TRACKER="notion" ;;
    5) WIZ_ISSUE_TRACKER="other"  ;;
    *) WIZ_ISSUE_TRACKER="github" ;;
  esac

  echo ""
  echo "── Team communication ────────────────────────────────"
  echo "  1) None  2) Slack  3) Microsoft Teams  4) Discord"
  read -r -p "  Choice [1]: " _comm_choice < /dev/tty
  case "${_comm_choice:-1}" in
    2) WIZ_COMM="slack"  ;;
    3) WIZ_COMM="teams"  ;;
    4) WIZ_COMM="discord";;
    *) WIZ_COMM="none"   ;;
  esac

  echo ""
  echo "── Database ──────────────────────────────────────────"
  echo "  1) None  2) Supabase  3) PostgreSQL  4) SQLite  5) Other"
  read -r -p "  Choice [1]: " _db_choice < /dev/tty
  case "${_db_choice:-1}" in
    2) WIZ_DB="supabase"  ;;
    3) WIZ_DB="postgres"  ;;
    4) WIZ_DB="sqlite"    ;;
    5) WIZ_DB="other"     ;;
    *) WIZ_DB="none"      ;;
  esac

  echo ""
  echo "── Coding agents ─────────────────────────────────────"
  echo "  Which agents does your team use? (space-separated numbers)"
  echo "  1) Claude Code  2) GitHub Copilot  3) Cursor  4) All"
  read -r -p "  Choice [1]: " _agents_choice < /dev/tty
  WIZ_AGENTS="${_agents_choice:-1}"
  case "$WIZ_AGENTS" in
    *4*|"")         WIZ_AGENTS_LIST="claude copilot cursor" ;;
    *)
      WIZ_AGENTS_LIST=""
      [[ "$WIZ_AGENTS" == *1* ]] && WIZ_AGENTS_LIST="$WIZ_AGENTS_LIST claude"
      [[ "$WIZ_AGENTS" == *2* ]] && WIZ_AGENTS_LIST="$WIZ_AGENTS_LIST copilot"
      [[ "$WIZ_AGENTS" == *3* ]] && WIZ_AGENTS_LIST="$WIZ_AGENTS_LIST cursor"
      ;;
  esac

  echo ""
  echo "── Components ────────────────────────────────────────"
  echo "  Enter your project's services/modules (e.g. api, worker, frontend)."
  echo "  Blank line to finish."
  echo ""
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

  # Build allowed_hosts based on stack + integrations
  ALLOWED_HOSTS_LIST="  - \"github.com\"
  - \"api.github.com\"
  - \"raw.githubusercontent.com\"
  - \"anthropic.com\"
  - \"api.anthropic.com\"
  - \"claude.ai\"
  - \"cursor.com\"
  - \"localhost\"
  - \"127.0.0.1\""

  [[ "$WIZ_STACK" == *python* ]] && ALLOWED_HOSTS_LIST="$ALLOWED_HOSTS_LIST
  - \"pypi.org\"
  - \"files.pythonhosted.org\""
  [[ "$WIZ_STACK" == *node* ]] && ALLOWED_HOSTS_LIST="$ALLOWED_HOSTS_LIST
  - \"registry.npmjs.org\""
  [[ "$WIZ_GIT_PLATFORM" == "gitlab" ]] && ALLOWED_HOSTS_LIST="$ALLOWED_HOSTS_LIST
  - \"gitlab.com\""
  [[ "$WIZ_ISSUE_TRACKER" == "jira" ]] && ALLOWED_HOSTS_LIST="$ALLOWED_HOSTS_LIST
  - \"atlassian.net\"
  - \"atlassian.com\""
  [[ "$WIZ_ISSUE_TRACKER" == "linear" ]] && ALLOWED_HOSTS_LIST="$ALLOWED_HOSTS_LIST
  - \"linear.app\""
  [[ "$WIZ_ISSUE_TRACKER" == "notion" ]] && ALLOWED_HOSTS_LIST="$ALLOWED_HOSTS_LIST
  - \"notion.so\"
  - \"api.notion.com\""
  [[ "$WIZ_COMM" == "slack" ]] && ALLOWED_HOSTS_LIST="$ALLOWED_HOSTS_LIST
  - \"slack.com\"
  - \"api.slack.com\""
  [[ "$WIZ_DB" == "supabase" ]] && ALLOWED_HOSTS_LIST="$ALLOWED_HOSTS_LIST
  - \"supabase.com\"
  - \"supabase.io\""

  cat > "$CONFIG_FILE" <<YMLEOF
project_name: "${WIZ_PROJECT}"
org_name: "${WIZ_ORG}"
repo_name: "${WIZ_REPO}"
default_branch: "${WIZ_DEFAULT}"
main_branch: "${WIZ_MAIN}"
contributor_handles: "${WIZ_HANDLES}"
tech_stack: "${WIZ_STACK}"

# Integrations — set during setup wizard (re-run with --setup-mcp to change)
git_platform: "${WIZ_GIT_PLATFORM}"
issue_tracker: "${WIZ_ISSUE_TRACKER}"
communication: "${WIZ_COMM}"
database: "${WIZ_DB}"
agents: "${WIZ_AGENTS_LIST}"

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
${ALLOWED_HOSTS_LIST}

github_projects:
  default_project: 1

project_token_secret: "PROJECT_TOKEN"
copilot_quota_state_issue: 0
YMLEOF

  echo ""
  ok "Created digidev/digidev.yml"

  # Set flag to also run MCP setup below
  SETUP_MCP=1
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

# ── Workflow scripts ──────────────────────────────────────────────────────────

echo "→ Workflow scripts"
scripts_src="$DIVIDEV_DIR/scripts"
scripts_dst="scripts"
for f in score.py run_task.sh list_tasks.sh commit_helper.sh \
          create_issue.sh create_pr.sh; do
  install_file "$scripts_src/$f" "$scripts_dst/$f"
done
for f in run_task.sh list_tasks.sh commit_helper.sh create_issue.sh create_pr.sh; do
  make_exec "$scripts_dst/$f"
done

# ── MCP config generation ─────────────────────────────────────────────────────

if [ "$SETUP_MCP" = "1" ] && [ "$DRY_RUN" = "0" ]; then
  echo "→ Generating .mcp.json"
  python3 - "$CONFIG_FILE" "$REPO_ROOT/.mcp.json" <<'PY'
import json, re, sys
from pathlib import Path

config_file = sys.argv[1]
out_path = sys.argv[2]

try:
    import yaml
    cfg = yaml.safe_load(Path(config_file).read_text()) or {}
except ImportError:
    cfg = {}
    for line in Path(config_file).read_text().splitlines():
        m = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*"?([^"#\n]*)"?\s*$', line)
        if m:
            cfg[m.group(1)] = m.group(2).strip()

git_platform  = cfg.get('git_platform',  'github')
issue_tracker = cfg.get('issue_tracker', 'github')
comm          = cfg.get('communication', 'none')
database      = cfg.get('database',      'none')

servers = {}

# Git platform
if git_platform == 'github':
    servers['github'] = {
        'command': 'npx',
        'args': ['-y', '@modelcontextprotocol/server-github'],
        'env': {'GITHUB_PERSONAL_ACCESS_TOKEN': '${GITHUB_PERSONAL_ACCESS_TOKEN}'},
    }
elif git_platform == 'gitlab':
    servers['gitlab'] = {
        'command': 'npx',
        'args': ['-y', '@modelcontextprotocol/server-gitlab'],
        'env': {
            'GITLAB_PERSONAL_ACCESS_TOKEN': '${GITLAB_PERSONAL_ACCESS_TOKEN}',
            'GITLAB_API_URL': 'https://gitlab.com/api/v4',
        },
    }

# Issue tracker (if different from git platform)
if issue_tracker == 'jira':
    servers['jira'] = {
        'command': 'npx',
        'args': ['-y', 'mcp-atlassian'],
        'env': {
            'JIRA_URL': '${JIRA_BASE_URL}',
            'JIRA_USERNAME': '${JIRA_EMAIL}',
            'JIRA_API_TOKEN': '${JIRA_API_TOKEN}',
        },
    }
elif issue_tracker == 'linear':
    servers['linear'] = {
        'command': 'npx',
        'args': ['-y', '@linear/mcp-server'],
        'env': {'LINEAR_API_KEY': '${LINEAR_API_KEY}'},
    }
elif issue_tracker == 'notion':
    servers['notion'] = {
        'command': 'npx',
        'args': ['-y', '@notionhq/notion-mcp-server'],
        'env': {'NOTION_API_TOKEN': '${NOTION_API_TOKEN}'},
    }

# Communication
if comm == 'slack':
    servers['slack'] = {
        'command': 'npx',
        'args': ['-y', '@modelcontextprotocol/server-slack'],
        'env': {
            'SLACK_BOT_TOKEN': '${SLACK_BOT_TOKEN}',
            'SLACK_TEAM_ID': '${SLACK_TEAM_ID}',
        },
    }

# Database
if database == 'supabase':
    servers['supabase'] = {
        'command': 'npx',
        'args': ['-y', '@supabase/mcp-server-supabase',
                 '--access-token', '${SUPABASE_ACCESS_TOKEN}'],
    }
elif database == 'postgres':
    servers['postgres'] = {
        'command': 'npx',
        'args': ['-y', '@modelcontextprotocol/server-postgres', '${DATABASE_URL}'],
    }

out = {'mcpServers': servers}

# Merge with existing .mcp.json if present (don't overwrite user customisations)
existing = {}
try:
    existing = json.loads(Path(out_path).read_text())
except Exception:
    pass
existing_servers = existing.get('mcpServers', {})
# Add new servers; preserve existing ones
for k, v in servers.items():
    if k not in existing_servers:
        existing_servers[k] = v
out = {'mcpServers': existing_servers}

Path(out_path).write_text(json.dumps(out, indent=2) + '\n')
print(f'  ✓ .mcp.json — {len(servers)} server(s) configured')
PY

  # Generate setup guide for selected integrations
  python3 - "$CONFIG_FILE" "$REPO_ROOT/digidev-mcp-setup.md" <<'PY'
import re, sys
from pathlib import Path

config_file = sys.argv[1]
out_path = sys.argv[2]

try:
    import yaml
    cfg = yaml.safe_load(Path(config_file).read_text()) or {}
except ImportError:
    cfg = {}
    for line in Path(config_file).read_text().splitlines():
        m = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*"?([^"#\n]*)"?\s*$', line)
        if m:
            cfg[m.group(1)] = m.group(2).strip()

git_platform  = cfg.get('git_platform',  'github')
issue_tracker = cfg.get('issue_tracker', 'github')
comm          = cfg.get('communication', 'none')
database      = cfg.get('database',      'none')

lines = [
    "# digidev MCP setup guide",
    "",
    "Generated by `bash digidev/install.sh`. Complete these steps to connect your tools.",
    "",
]

steps = []

if git_platform == 'github':
    steps.append(("GitHub MCP", [
        "export GITHUB_PERSONAL_ACCESS_TOKEN=ghp_...",
        "# Scopes needed: repo, read:org, project (for board routing)",
        "# Create at: https://github.com/settings/tokens",
    ]))
elif git_platform == 'gitlab':
    steps.append(("GitLab MCP", [
        "export GITLAB_PERSONAL_ACCESS_TOKEN=glpat-...",
        "# Scopes needed: api",
        "# Create at: https://gitlab.com/-/profile/personal_access_tokens",
        "npm install -g @modelcontextprotocol/server-gitlab",
    ]))

if issue_tracker == 'jira':
    steps.append(("Jira MCP", [
        "export JIRA_BASE_URL=https://your-org.atlassian.net",
        "export JIRA_EMAIL=you@company.com",
        "export JIRA_API_TOKEN=...",
        "# Create token at: https://id.atlassian.com/manage-profile/security/api-tokens",
        "npm install -g mcp-atlassian",
        "# See: digidev/integrations/jira/README.md",
    ]))
elif issue_tracker == 'linear':
    steps.append(("Linear MCP", [
        "export LINEAR_API_KEY=lin_api_...",
        "# Create at: https://linear.app/settings/api",
        "npm install -g @linear/mcp-server",
        "# See: digidev/integrations/linear/README.md",
    ]))
elif issue_tracker == 'notion':
    steps.append(("Notion MCP", [
        "export NOTION_API_TOKEN=secret_...",
        "# Create integration at: https://www.notion.so/my-integrations",
        "npm install -g @notionhq/notion-mcp-server",
        "# See: digidev/integrations/notion/README.md",
    ]))

if comm == 'slack':
    steps.append(("Slack MCP", [
        "export SLACK_BOT_TOKEN=xoxb-...",
        "export SLACK_TEAM_ID=T...",
        "# Create app at: https://api.slack.com/apps",
        "npm install -g @modelcontextprotocol/server-slack",
        "# See: digidev/integrations/slack/README.md",
    ]))

if database == 'supabase':
    steps.append(("Supabase MCP", [
        "export SUPABASE_ACCESS_TOKEN=sbp_...",
        "# Create token at: https://supabase.com/dashboard/account/tokens",
        "npm install -g @supabase/mcp-server-supabase",
        "# See: digidev/integrations/supabase/README.md",
    ]))
elif database == 'postgres':
    steps.append(("PostgreSQL MCP", [
        "export DATABASE_URL=postgresql://user:pass@localhost/dbname",
        "npm install -g @modelcontextprotocol/server-postgres",
    ]))

for title, cmds in steps:
    lines.append(f"## {title}")
    lines.append("")
    lines.append("```bash")
    lines.extend(cmds)
    lines.append("```")
    lines.append("")

lines.extend([
    "## Verify MCP servers are active",
    "",
    "```bash",
    "claude mcp list    # should show all configured servers",
    "```",
    "",
    "## Add tokens to Claude Code environment",
    "",
    "Add secrets to `~/.claude/.env` (not committed to git):",
    "",
    "```bash",
    "# ~/.claude/.env",
    "GITHUB_PERSONAL_ACCESS_TOKEN=...",
    "# JIRA_API_TOKEN=...",
    "# LINEAR_API_KEY=...",
    "# SLACK_BOT_TOKEN=...",
    "```",
    "",
    "See `digidev/integrations/` for full setup guides.",
])

Path(out_path).write_text('\n'.join(lines) + '\n')
print(f'  ✓ digidev-mcp-setup.md — follow this to complete integration setup')
PY
fi

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
  echo "       (or rename Makefile.digidev to Makefile if you don't have one)"
  echo ""
  echo "  2. Install the git pre-push hook:"
  echo "       make hooks-install"
  echo ""
  # Read git platform from config
  _GIT_PLATFORM=$(python3 -c "
import re
try:
    import yaml
    cfg = yaml.safe_load(open('${CONFIG_FILE}'))
    print(cfg.get('git_platform', 'github'))
except Exception:
    txt = open('${CONFIG_FILE}').read()
    m = re.search(r'git_platform:\s*(\S+)', txt)
    print(m.group(1) if m else 'github')
" 2>/dev/null || echo "github")

  if [ "$_GIT_PLATFORM" = "github" ]; then
    echo "  3. Create GitHub labels (run once per repo):"
    echo "       gh label create 'agent-task'   --color 'ededed'"
    echo "       gh label create 'exec:claude'  --color '7057ff'"
    echo "       gh label create 'exec:cursor'  --color '0075ca'"
    echo "       gh label create 'exec:copilot' --color 'cfd3d7'"
    echo "       gh label create 'risk:low'     --color '0e8a16'"
    echo "       gh label create 'risk:med'     --color 'e4e669'"
    echo "       gh label create 'risk:high'    --color 'd93f0b'"
    echo "       # Plus one 'component:<name>' label per component"
    echo ""
  fi

  if [ "$SETUP_MCP" = "1" ]; then
    echo "  3. Complete MCP server setup:"
    echo "       cat digidev-mcp-setup.md"
    echo "       (follow each step to connect your tools)"
    echo ""
  fi

  echo "  4. Commit:"
  echo "       git add .claude/ .github/ scripts/ agents.yml AGENTS.md Makefile.digidev"
  echo "       git add */AGENTS.md docs/scoring/ docs/agents/ digidev/ .mcp.json"
  echo "       git commit -m 'chore: install digidev agentic workflow kit'"
  echo "       git push"
  echo ""
  echo "  5. Verify:"
  echo "       make status      # list open agent-task issues"
  echo "       make new-task    # create your first task"
fi
echo ""
