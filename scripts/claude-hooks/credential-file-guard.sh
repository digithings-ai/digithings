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
#   "Could not read it" is never "nothing there". Four separate shapes of that
#   mistake are closed below, and all four shipped fail-open in the first cut of
#   this hook:
#     * an unparseable payload, or one whose tool_input lacks the field we read,
#       used to yield an empty string and fall through to `exit 0`;
#     * a `tool_input` that is a string rather than an object used to crash the
#       payload extractor, and `set -euo pipefail` turned that crash into a
#       NON-BLOCKING exit — the call ran unevaluated;
#     * the Read and Grep branches used `|| verdict=""`, which turned an
#       evaluator crash into an allow;
#     * the Bash branch let the evaluator's own exit code reach the harness. Any
#       code other than 0 or 2 is a NON-BLOCKING error per _lib.sh, so a crash
#       exited 7 — which runs the tool call anyway.
#   Each now denies explicitly, with exit 2.
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

tool_rc=0
tool="$(hook_tool)" || tool_rc=$?
if [ "$tool_rc" -ne 0 ]; then
  deny "credential-file-guard could not parse its payload (exit $tool_rc), so it \
cannot establish what was requested and is blocking the call."
fi

# An empty tool name means the payload did not parse, or carried no tool_name.
# Falling through to the `*) exit 0` below would read that as "not a tool this
# guard covers" — i.e. allow. Deny instead: an unreadable request is not an
# approved one.
if [ -z "$tool" ]; then
  deny "credential-file-guard could not read a tool name from its payload, so \
it cannot establish what was requested and is blocking the call. If this is a \
real operation, re-issue it as a plain Bash/Read/Grep call."
fi

# hook_field prints '' for an unparseable payload, but it can also exit non-zero:
# a tool_input that is a string rather than an object makes the extractor raise,
# and `set -euo pipefail` would then abort this hook with a NON-BLOCKING exit,
# running the tool call unexamined. Capture the code and turn it into a deny.
EXTRACTED=""
hook_field_deny() {
  local key="$1" rc=0
  EXTRACTED="$(hook_field "$key")" || rc=$?
  if [ "$rc" -ne 0 ]; then
    deny "credential-file-guard could not read '$key' from its payload (exit \
$rc), so it cannot establish what was requested and is blocking the call."
  fi
}

case "$tool" in
  Read | NotebookRead)
    hook_field_deny file_path
    target="$EXTRACTED"
    if [ -z "$target" ]; then
      hook_field_deny notebook_path
      target="$EXTRACTED"
    fi
    # A Read with no path is malformed. The first cut returned 0 here, which let
    # a payload whose field had been renamed or dropped through unexamined.
    if [ -z "$target" ]; then
      deny "credential-file-guard received a $tool call with no readable file path \
and cannot tell what file it names, so it is blocking the call."
    fi
    rc=0
    verdict="$(CRED_GUARD_TARGET="$target" CRED_GUARD_ROOT="$PROJECT_ROOT" python3 \
      "$(dirname "$0")/credential_paths.py" --path 2>&1)" || rc=$?
    if [ "$rc" -ne 0 ]; then
      deny "credential-file-guard could not evaluate '$target' (evaluator exit \
$rc), so the read is blocked rather than passed unchecked."
    fi
    case "$verdict" in
      DENY*) deny "reading credential file is blocked: ${verdict#DENY	} \
A credential value must never enter an agent transcript. Read it with the \
provisioning tool (dt-keys / bws / the provider CLI) or rotate it — see \
docs/ops/SECRETS_ROTATION.md. This is not a bug to work around." ;;
    esac
    exit 0
    ;;
  Grep)
    hook_field_deny path
    target="$EXTRACTED"
    # A Grep with no path searches the working tree, which can still reach a
    # credential file the caller never named. Deny the unanswerable case; a
    # Grep that names no path is not something this guard can clear.
    if [ -z "$target" ]; then
      deny "credential-file-guard received a Grep with no readable path, so it \
cannot establish which files would be searched and is blocking the call. \
Name the path explicitly."
    fi
    rc=0
    verdict="$(CRED_GUARD_TARGET="$target" CRED_GUARD_ROOT="$PROJECT_ROOT" python3 \
      "$(dirname "$0")/credential_paths.py" --path 2>&1)" || rc=$?
    if [ "$rc" -ne 0 ]; then
      deny "credential-file-guard could not evaluate '$target' (evaluator exit \
$rc), so the grep is blocked rather than passed unchecked."
    fi
    case "$verdict" in
      DENY*) deny "grepping credential file is blocked: ${verdict#DENY	} \
grep -r over a credential path prints matching lines, which is the value." ;;
    esac
    exit 0
    ;;
  Bash) ;;
  # Registered on Read, Grep and Bash only, so anything else means the hook
  # wiring and this script disagree. Allow the tool (it is not a read this guard
  # governs) but say so, rather than silently widening coverage.
  *) exit 0 ;;
esac

hook_field_deny command
cmd="$EXTRACTED"
# A Bash call with no readable command is malformed. Allow-by-default here is
# exactly the hole above: the first cut exited 0, so a payload with the command
# under an unexpected key ran unexamined.
if [ -z "$cmd" ]; then
  deny "credential-file-guard received a Bash call with no readable command, so \
it cannot evaluate what would run and is blocking the call."
fi

rc=0
verdict="$(CRED_GUARD_CMD="$cmd" CRED_GUARD_ROOT="$PROJECT_ROOT" python3 \
  "$(dirname "$0")/credential_paths.py" --command 2>&1)" || rc=$?

case "$verdict" in
  DENY*) deny "${verdict#DENY	}" ;;
esac

if [ "$rc" -ne 0 ]; then
  # A non-zero exit with no DENY line means the evaluator could not reach a
  # verdict. Denying is the only safe reading of "I could not evaluate this".
  # This branch is load-bearing: any exit code other than 0 or 2 is a
  # NON-BLOCKING error to the harness, so letting the evaluator's own code
  # through would run the command unguarded.
  deny "credential-file-guard could not evaluate this command (exit $rc), so it \
is blocked. Simplify the command into a single pipeline, or set \
DIGIDEV_ALLOW_CREDENTIAL_READ=1 in a human session."
fi

exit 0