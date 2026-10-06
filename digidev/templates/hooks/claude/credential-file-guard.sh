#!/usr/bin/env bash
# Credential-file guard (DIG-1653).
#
# WHY THIS EXISTS
#   DIG-1639 leaked a Cloudflare OAuth `refresh_token` into a Paperclip run
#   transcript. A redaction pass ran over the command's output and did not match
#   the value, so the raw token reached the transcript. gitleaks cannot help:
#   `.github/workflows/security-gitleaks.yml` and `.gitleaks.toml` scan committed
#   git content, never what an agent prints.
#
# WHAT IT DOES
#   Blocks tool calls that would put the *content* of a known credential file
#   into anything that becomes a transcript. It never opens the credential, so
#   it never has to redact one — there is no value in this process to leak, and
#   no value in the deny reason either (paths are safe to print; values are not).
#
# HOW IT FAILS
#   Closed. deny ⇔ (credential path present) ∧ (a command word ∉ allowlist).
#   Anything unparseable, unrecognised, or merely suspicious is blocked. Reads
#   are allowed only through the explicit non-disclosing allowlist in
#   credential_paths.py (mkdir / rm / ls / git / gh …), which is what keeps
#   `mkdir -p ~/.wrangler/config` and stale-config cleanup working.
#
# SCOPE
#   * Path shapes live in credential_paths.py — one copy, shared with the tests.
#   * Value shapes (opaque token text) live in digitrace.redaction
#     (CREDENTIAL_RULES) and are applied by scripts/check_transcript_secrets.py.
#     The two are disjoint and must stay that way: this guard never sees a value.
#
# WRANGLER
#   Any wrangler invocation must go through scripts/wrangler-auth.sh. The agent
#   harness sets XDG_CONFIG_HOME to a temp dir, so wrangler reads an empty
#   config and answers "Not logged in" while the real credential file at
#   ~/Library/Preferences/.wrangler/config/default.toml is untouched — a silent
#   no-op that reads as success. The wrapper is the only path that unsets it.
#
# EXIT CODES (see _lib.sh): 0 = allow, 2 = block with the reason on stderr.
source "$(dirname "$0")/_lib.sh"

# Human override (intentionally not documented to agents). An agent cannot reach
# it: the harness builds this hook's stdin payload itself, so a per-command env
# prefix like `DIGIDEV_ALLOW_CREDENTIAL_READ=1 cat …` never reaches this process
# — only session-level env set by a human does. The guard test sets
# DIGI_FORCE_GUARD_TEST=1 so an org-wide override cannot weaken deny assertions
# on CI runners.
if [ "${DIGI_FORCE_GUARD_TEST:-0}" != "1" ] && [ "${DIGIDEV_ALLOW_CREDENTIAL_READ:-0}" = "1" ]; then
  exit 0
fi

tool="$(hook_tool)"

case "$tool" in
  Read | NotebookRead)
    target="$(hook_field file_path)"
    [ -z "$target" ] && target="$(hook_field notebook_path)"
    [ -z "$target" ] && exit 0
    verdict="$(CRED_GUARD_TARGET="$target" CRED_GUARD_ROOT="$PROJECT_ROOT" python3 \
      "$(dirname "$0")/credential_paths.py" --path 2>&1)" || verdict=""
    case "$verdict" in
      DENY*) deny "reading credential file is blocked: ${verdict#DENY	} \
A credential value must never enter an agent transcript. Read it with the \
provisioning tool (dt-keys / bws / the provider CLI) or rotate it — see \
docs/ops/SECRETS_ROTATION.md. This is not a bug to work around." ;;
    esac
    exit 0
    ;;
  Grep)
    target="$(hook_field path)"
    [ -z "$target" ] && exit 0
    verdict="$(CRED_GUARD_TARGET="$target" CRED_GUARD_ROOT="$PROJECT_ROOT" python3 \
      "$(dirname "$0")/credential_paths.py" --path 2>&1)" || verdict=""
    case "$verdict" in
      DENY*) deny "grepping credential file is blocked: ${verdict#DENY	} \
grep -r over a credential path prints matching lines, which is the value." ;;
    esac
    exit 0
    ;;
  Bash) ;;
  *) exit 0 ;;
esac

cmd="$(hook_field command)"
[ -z "$cmd" ] && exit 0

verdict="$(CRED_GUARD_CMD="$cmd" CRED_GUARD_ROOT="$PROJECT_ROOT" python3 \
  "$(dirname "$0")/credential_paths.py" --command 2>&1)"
rc=$?

case "$verdict" in
  DENY*) deny "${verdict#DENY	}" ;;
esac

if [ "$rc" -ne 0 ]; then
  # A non-zero exit with no DENY line means the evaluator could not reach a
  # verdict. Denying is the only safe reading of "I could not evaluate this".
  deny "credential-file-guard could not evaluate this command (exit $rc), so it \
is blocked. Simplify the command into a single pipeline, or set \
DIGIDEV_ALLOW_CREDENTIAL_READ=1 in a human session."
fi

exit 0