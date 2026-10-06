"""Credential-file path matching for the agent PreToolUse guards (DIG-1653).

Shared by ``credential-file-guard.sh`` for both tool surfaces (the ``Read`` /
``Grep`` path field and the ``Bash`` command string) so there is exactly one
copy of the patterns. Pure stdlib, no imports from the repo — a guard must run
before anything is installed.

Why this is separate from ``digitrace.redaction``:

* ``digitrace.redaction.CREDENTIAL_RULES`` matches credential **values**
  (opaque token text) — the shape that leaked in DIG-1639.
* This module matches credential **paths** — the file an agent is about to read.

The two sets are disjoint and must stay that way. A path is not a secret, so
naming one in a deny reason is safe and is what makes a block actionable.
"""

from __future__ import annotations

import os
import re
import shlex
import sys

# ── Credential path shapes ────────────────────────────────────────────────────
# Ordered most-specific first; the index is reported in the deny reason so the
# blocked operator can see which rule fired.
CREDENTIAL_PATTERNS: tuple[str, ...] = (
    # Cloudflare wrangler OAuth config — the file that leaked in DIG-1639.
    # Covers ~/Library/Preferences/.wrangler/ (macOS), ~/.config/.wrangler/,
    # and a repo-local .wrangler/. `(/|$)` so the bare directory counts too:
    # `grep -r secret ~/.aws` names no file, only the directory.
    r"(^|/)\.wrangler(/|$)",
    # Key material, keystores, private keys.
    r"\.(pem|key|p12|pfx|jks|keystore)$",
    r"(^|/)(id_rsa|id_dsa|id_ecdsa|id_ed25519)(\.pub)?$",
    # Client config files that carry a live token inline.
    r"(^|/)(\.npmrc|npmrc|\.netrc|_netrc|\.pypirc|\.git-credentials)$",
    r"(^|/)\.docker/config\.json$",
    # Dotenv / dev-vars. Exact `.env` plus environment-suffixed variants.
    r"(^|/)\.env$",
    r"(^|/)\.env\.(local|dev|development|test|testing|ci|prod|production|staging|preview)$",
    r"(^|/)\.dev\.vars$",
    r"(^|/)env\.(profile|profile-[ab])$",
    # Provider credential directories. `(/|$)` so the directory itself matches,
    # not only its contents — `grep -r secret ~/.aws` names no file.
    r"(^|/)\.aws(/|$)",
    r"(^|/)\.ssh(/|$)",
    r"(^|/)credentials($|[._/-])",
    r"(^|/)\.kube(/|$)",
    r"(^|/)\.gnupg(/|$)",
    r"(^|/)Library/Keychains(/|$)",
)

# Fragments that must be present for a command to be worth parsing at all. Every
# pattern above contains at least one, so a command with none cannot match.
# Mirrored in credential-file-guard.sh's `case` fast path — keep in sync.
FAST_FRAGMENTS: tuple[str, ...] = (
    "wrangler",
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    "credential",
    ".npmrc",
    ".netrc",
    ".pypirc",
    ".ssh",
    ".aws",
    ".docker",
    ".env",
    ".vars",
    "_rsa",
    "_ed25519",
    "id_ecdsa",
    "Keychain",
    "security find",
    "bw get",
    "bws secret",
)

# Name that matches a pattern above but provably carries no live value. Without
# these the guard blocks ordinary work: the repo tracks seven `.env.example`
# templates, a `…provider_credentials.sql` migration and
# `check_example_credentials.py`.
_SAFE_NAME_RE = re.compile(
    r"(example|template|sample|placeholder|dummy|fixture|fake)",
    re.IGNORECASE,
)
SAFE_SUFFIXES: tuple[str, ...] = (
    ".md",
    ".mdx",
    ".rst",
    ".sql",
    ".py",
    ".sh",
    ".ts",
    ".js",
)

# ── Non-disclosing commands ───────────────────────────────────────────────────
# A credential path may legitimately be named by a command that never reveals
# its content: create the directory, delete a stale config, list names.
# `mkdir -p ~/.wrangler/config` has to keep working or the guard gets disabled
# wholesale. Everything NOT here is denied when a credential path is present,
# and that is where the fail-closed behaviour comes from.
ALLOWED_COMMANDS: frozenset[str] = frozenset(
    {
        # Filesystem lifecycle — no content disclosure.
        "mkdir",
        "rmdir",
        "rm",
        "unlink",
        "chmod",
        "chown",
        "ls",
        "touch",
        "test",
        "true",
        "false",
        "pwd",
        "stat",
        # Repository plumbing reads names and refs, never blobs or config values.
        # `git config --get` and `git show` can print content, so the guard's
        # path rule is what limits those — the command alone is not enough to
        # make a read safe.
        "git",
        "gh",
    }
)

# Words that wrap another command: `env FOO=bar cmd`, `sudo cmd`, `xargs cmd`.
_COMMAND_WRAPPERS: frozenset[str] = frozenset(
    {"env", "sudo", "nohup", "time", "command", "xargs", "then", "do", "else", "!"}
)

# Shell separators that end one command and start the next.
_BREAKERS: frozenset[str] = frozenset({"|", "||", "&&", ";", "&", "(", ")", "{", "}"})


def is_credential_path(raw: str) -> str | None:
    """Return the pattern that classifies ``raw`` as a credential file, else None."""
    if not raw:
        return None
    s = raw.strip().strip("\"'").rstrip(",;").rstrip("/")
    if not s:
        return None
    base = s.rsplit("/", 1)[-1]
    # A public half is not the private half.
    if base.endswith(".pub"):
        return None
    if _SAFE_NAME_RE.search(base) or base.endswith(SAFE_SUFFIXES):
        return None
    for pattern in CREDENTIAL_PATTERNS:
        if re.search(pattern, s):
            return pattern
    return None


def tokens_of(raw: str) -> list[str]:
    """Tokenise a command, degrading to whitespace split rather than giving up.

    A parse failure must not become an allow — that is the exact failure mode
    that produced DIG-1639. Whitespace splitting is cruder but still sees the
    path, which is what the decision rests on.
    """
    try:
        lex = shlex.shlex(raw, posix=True, punctuation_chars=True)
        lex.whitespace = " \t\r\n"
        return list(lex)
    except Exception:
        return raw.split()


def command_words(toks: list[str]) -> list[str]:
    """Extract the leading word of every command in the pipeline."""
    out: list[str] = []
    expect = True
    for tok in toks:
        if tok in _BREAKERS:
            expect = True
            continue
        if tok.startswith("-"):
            continue  # a flag, never a command name
        if not expect:
            continue
        base = tok.rsplit("/", 1)[-1]
        if base in _COMMAND_WRAPPERS:
            continue  # the real command is the next word
        out.append(base)
        expect = False
    return out


def credential_paths_in(toks: list[str]) -> list[str]:
    """Every distinct credential path mentioned anywhere in the token stream."""
    hits: list[str] = []
    for tok in toks:
        # A path can arrive glued to other syntax: `~/.aws/credentials)`,
        # `$(cat ~/.npmrc)`, `file://…/.ssh/id_rsa`.
        for chunk in re.split(r"[\s;|&<>()$`\"'\[\]{},]+", tok):
            if chunk and is_credential_path(chunk) and chunk not in hits:
                hits.append(chunk)
                break
    return hits


def disclosing_commands_in(toks: list[str]) -> list[str]:
    """Command words that are not on the non-disclosing allowlist."""
    return [w for w in command_words(toks) if w not in ALLOWED_COMMANDS]


def normalize(path: str, root: str | None = None) -> str:
    """Absolutise a relative path against ``root`` so patterns anchored on ``^/`` apply."""
    if not path:
        return ""
    root = root or os.getcwd()
    if path.startswith("~/"):
        return os.path.expanduser(path)
    if os.path.isabs(path):
        return os.path.normpath(path)
    return os.path.normpath(os.path.join(root, path))


# ── CLI ───────────────────────────────────────────────────────────────────────
# Invoked by credential-file-guard.sh. Prints `DENY\t<reason>` and exits 0 when
# the call must be blocked; prints nothing and exits 0 when it may proceed; exits
# non-zero only when it could not reach a verdict, so the hook can fail closed.

_WRANGLER_DIRECT = re.compile(r"(^|[\s/;&|(])wrangler(\s|$)")
_WRANGLER_SANCTIONED = ("wrangler-auth",)
# `security find-generic-password … -w` prints the Keychain value. The path rule
# cannot see it: no credential path is named at all.
_KEYCHAIN_REVEAL = re.compile(r"(^|\s)security\s+.*find-(generic|internet)-password")
_KEYCHAIN_VALUE_FLAG = re.compile(r"(^|\s)-(w|w0|g)\b")
# Bitwarden CLIs print the value too; the inventory and `secret list` do not.
_BWS_REVEAL = re.compile(r"(^|\s)bws\s+secret\s+get\b")
_BW_REVEAL = re.compile(r"(^|\s)bw\s+get\s+(password|totp|uris)\b")


def _deny(reason: str) -> None:
    print(f"DENY\t{reason}")


def evaluate_command(cmd: str, root: str | None = None) -> None:
    """Print a DENY line when `cmd` must be blocked. Prints nothing to allow."""
    # 1. Wrangler must go through the wrapper (see the header).
    if _WRANGLER_DIRECT.search(cmd) and not any(s in cmd for s in _WRANGLER_SANCTIONED):
        _deny(
            "wrangler invoked directly, which disarms its auth: the agent "
            "harness sets XDG_CONFIG_HOME to a temp dir, so wrangler reads an "
            'empty config and answers "Not logged in" while the real '
            "credential file is untouched. Use scripts/wrangler-auth.sh, which "
            "unsets XDG_CONFIG_HOME and CLOUDFLARE_API_TOKEN for you."
        )
        return

    # 2. Reveal commands name no credential path, so the path rule would miss
    #    them entirely.
    if _KEYCHAIN_REVEAL.search(cmd) and _KEYCHAIN_VALUE_FLAG.search(cmd):
        _deny(
            "`security … -w` prints a Keychain secret into the transcript. "
            "Read it with dt-keys, or rotate it — never echo the value."
        )
        return
    if _BWS_REVEAL.search(cmd) or _BW_REVEAL.search(cmd):
        _deny(
            "that Bitwarden command prints the secret value. Use "
            "`bws secret list` (names only) or docs/ops/SECRETS_INVENTORY.md."
        )
        return

    # 3. The path rule.
    toks = tokens_of(cmd)
    hits = credential_paths_in(toks)
    if not hits:
        return
    unknown = disclosing_commands_in(toks)
    if unknown:
        _deny(
            f"this would print the contents of a credential file "
            f"({', '.join(sorted(hits))}). A credential value must never enter "
            f"an agent transcript — that is how DIG-1639 leaked a Cloudflare "
            f"OAuth refresh_token. Read the value with dt-keys / bws / the "
            f"provider CLI, or rotate it. Use a non-disclosing command "
            f"(mkdir/rm/ls/git) if you only need the path to exist."
        )


def evaluate_path(target: str, root: str | None = None) -> None:
    """Print a DENY line when reading `target` must be blocked."""
    absolute = normalize(target.strip().strip("\"'"), root)
    pattern = is_credential_path(absolute)
    if pattern is not None:
        _deny(f"{absolute} (matched {pattern})")


def main(argv: list[str]) -> int:
    if "--command" in argv:
        cmd = os.environ.get("CRED_GUARD_CMD", "")
        if not cmd:
            return 1  # no verdict reachable
        evaluate_command(cmd, os.environ.get("CRED_GUARD_ROOT"))
        return 0
    if "--path" in argv:
        target = os.environ.get("CRED_GUARD_TARGET", "")
        if not target:
            return 0  # empty target: nothing to classify
        evaluate_path(target, os.environ.get("CRED_GUARD_ROOT"))
        return 0
    print("usage: credential_paths.py --command | --path", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
