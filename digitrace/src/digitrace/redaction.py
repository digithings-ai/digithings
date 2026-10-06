"""PII and credential redaction for digitrace trace payloads.

``PiiRedactor`` walks arbitrary dict / list / tuple structures and replaces
PII-looking substrings inside string values with opaque sentinels. Built-in
patterns cover:

* Emails (RFC-5321-lite) → ``[REDACTED_EMAIL]``
* API key prefixes (``sk-``, ``sk_``, ``dgk_live_``, ``dgk_test_``, ``lsv2_``)
  → ``[REDACTED_KEY]``
* E.164 and common North-American phone formats → ``[REDACTED_PHONE]``

Additional comma-separated regexes from the ``DIGI_PII_PATTERNS`` environment
variable are appended and render as ``[REDACTED]``. Non-string values pass
through (nested structures recurse).

## Credential rules (separate, on purpose)

``DEFAULT_PATTERNS`` is deliberately left untouched: it is the PII ruleset that
traces have always used, and widening it in place would silently change
existing trace payloads. Credential detection lives in its own ruleset
(:data:`CREDENTIAL_RULES`) with two entry points:

* :func:`detect_credential_value` — **detection**, returning the *name* of the
  rule that fired and never the matched text. Used by fail-closed guards.
* :func:`redact_credentials` — replacement with ``[REDACTED_CREDENTIAL]``.

This split exists because of DIG-1639: a Cloudflare OAuth ``refresh_token`` was
printed into an agent transcript and the ``PiiRedactor`` ruleset ran over it
without matching anything. None of the PII patterns can match an opaque OAuth
token — there is no prefix to anchor on — so credential *shapes* had to be
added as their own patterns.

The module has no runtime dependency on ``langsmith``; it operates on plain
Python structures. ``digitrace.trace`` wires it into ``langsmith.traceable``
via the SDK's native ``process_inputs`` / ``process_outputs`` hooks.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "DEFAULT_PATTERNS",
    "CREDENTIAL_RULES",
    "EMAIL_PATTERN",
    "API_KEY_PATTERN",
    "PHONE_PATTERN",
    "PEM_PRIVATE_KEY_PATTERN",
    "JWT_PATTERN",
    "GENERIC_SECRET_ASSIGNMENT_PATTERN",
    "PiiRedactor",
    "default_redactor",
    "detect_credential_value",
    "redact_credentials",
]


EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
API_KEY_PATTERN = re.compile(r"(?:sk-|sk_|dgk_live_|dgk_test_|lsv2_)[A-Za-z0-9_-]{8,}")
PHONE_PATTERN = re.compile(r"(?:\+?\d{1,3}[-. ]?)?\(?\d{3}\)?[-. ]?\d{3}[-. ]?\d{4}")


@dataclass(frozen=True)
class _Rule:
    pattern: re.Pattern[str]
    replacement: str


# Order matters: API keys first (they can contain digits that phone would match).
DEFAULT_PATTERNS: tuple[_Rule, ...] = (
    _Rule(API_KEY_PATTERN, "[REDACTED_KEY]"),
    _Rule(EMAIL_PATTERN, "[REDACTED_EMAIL]"),
    _Rule(PHONE_PATTERN, "[REDACTED_PHONE]"),
)


# ── Credential rules (DIG-1653) ────────────────────────────────────────────────
#
# Kept out of DEFAULT_PATTERNS on purpose: widening the trace ruleset would
# change payloads for every existing span, and these shapes are only ever
# matched against *untrusted output*, never against a PII field.
#
# Each rule carries a human-readable `name`. `detect_credential_value` returns
# that name — never the matched text — so a guard can report *why* it failed
# closed without echoing a secret into the transcript it is protecting.

PEM_PRIVATE_KEY_PATTERN = re.compile(
    r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----[\s\S]*?-----END (?:[A-Z ]+ )?PRIVATE KEY-----"
)
JWT_PATTERN = re.compile(r"\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\b")
BEARER_PATTERN = re.compile(r"(?i:\bbearer)\s+[A-Za-z0-9._~+/-]{20,}={0,2}")

# `refresh_token = "…"`, `client_secret: …`, `password=…`. The key name is the
# signal; there is no prefix to anchor on the way `sk-` works for PII.
_GENERIC_ASSIGNMENT_RE = (
    r"(?i)\b(?P<key>"
    r"refresh_token|access_token|id_token|client_secret|api_token|api_key|apikey|"
    r"secret_key|secret_access_key|private_key|encryption_key|app_secret|"
    r"session_token|auth_token|access_key_secret|passwd|password|passphrase|"
    r"client_secret_key|authorization|token|secret"
    r")\b\s*[:=]\s*[\"']?(?P<value>[^\s\"'#,}]{12,})"
)
GENERIC_SECRET_ASSIGNMENT_PATTERN = re.compile(_GENERIC_ASSIGNMENT_RE)

# Minimum value length before an assignment counts as a live credential. Keeps
# `token: "abc"` and `password: null` out of the ruleset.
_MIN_SECRET_VALUE_LEN = 16

# Values that look like credentials to a regex but carry no secret. Checked on
# the captured value, not in the pattern, so each exclusion is unit-testable.
_PLACEHOLDER_WORDS = frozenset(
    {
        "none",
        "null",
        "nil",
        "true",
        "false",
        "changeme",
        "change_me",
        "placeholder",
        "example",
        "dummy",
        "sample",
        "test",
        "todo",
        "unset",
        "empty",
        "redacted",
        "value_encrypted",
    }
)
_PLACEHOLDER_PREFIXES = (
    "replace",
    "your",
    "your-",
    "your_",
    "insert",
    "example",
    "dummy",
    "fake",
    "notarealkey",
    "redacted",
    "<",
    "${",
    "$((",
)


def _is_placeholder(value: str) -> bool:
    """True when a matched value carries no secret (placeholder or reference)."""
    v = value.strip().strip("\"'")
    if len(v) < _MIN_SECRET_VALUE_LEN:
        return True
    low = v.lower()
    if low in _PLACEHOLDER_WORDS:
        return True
    if low.startswith(_PLACEHOLDER_PREFIXES):
        return True
    # A single repeated character is a mask, not a key: ***, xxx, 0000000000.
    if len(set(v)) == 1:
        return True
    # A shell/CI variable reference: $VAR, ${VAR}, ${VAR:-default}
    stripped = low.lstrip("$")
    if stripped.startswith("{") and stripped.endswith("}"):
        return True
    return False


@dataclass(frozen=True)
class _CredentialRule:
    name: str
    pattern: re.Pattern[str]
    replacement: str = "[REDACTED_CREDENTIAL]"


# Ordered most-specific first: a PEM block is unambiguous, an opaque
# `token = <hex>` assignment is the broadest and must come last.
CREDENTIAL_RULES: tuple[_CredentialRule, ...] = (
    _CredentialRule("private-key-block", PEM_PRIVATE_KEY_PATTERN),
    _CredentialRule("jwt", JWT_PATTERN),
    _CredentialRule("bearer-token", BEARER_PATTERN),
    _CredentialRule("secret-assignment", GENERIC_SECRET_ASSIGNMENT_PATTERN),
)


def _redact_secret_assignment(match: re.Match[str]) -> str:
    """Keep the key name, replace a live value — the one shape with a capture group."""
    value = match.group("value")
    if _is_placeholder(value):
        return match.group(0)
    return match.group(0).replace(value, "[REDACTED_CREDENTIAL]")


def detect_credential_value(text: str) -> str | None:
    """Return the name of the first credential rule that fires on ``text``.

    Returns ``None`` when nothing matches. The matched value is never returned
    — callers report the rule name, so a detection report is itself safe to put
    in a transcript. Placeholder values (see :func:`_is_placeholder`) do not
    count as detections, which is what keeps guard fixtures like
    ``token = "replace-with-real-value"`` from tripping the guard on themselves.
    """
    if not text:
        return None
    for rule in CREDENTIAL_RULES:
        for match in rule.pattern.finditer(text):
            if rule.name == "secret-assignment" and _is_placeholder(match.group("value")):
                continue
            return rule.name
    return None


def redact_credentials(text: str) -> str:
    """Replace live credential values in ``text`` with ``[REDACTED_CREDENTIAL]``.

    Placeholder-shaped values are preserved so redacting a config template or a
    guard fixture does not destroy the thing you were trying to read.
    """
    out = text
    for rule in CREDENTIAL_RULES:
        if rule.name == "secret-assignment":
            out = rule.pattern.sub(_redact_secret_assignment, out)
        else:
            out = rule.pattern.sub(rule.replacement, out)
    return out


def _parse_extra_patterns(raw: str | None) -> tuple[_Rule, ...]:
    """Parse ``DIGI_PII_PATTERNS`` into a tuple of extra redaction rules.

    Mirrors the split/strip/filter idiom used by ``digigraph.tool_policy`` and
    ``digibase.cors``. Invalid regexes are silently skipped to avoid crashing
    tracing on a config typo.
    """
    if not raw:
        return ()
    parts = [entry.strip() for entry in raw.split(",") if entry.strip()]
    rules: list[_Rule] = []
    for entry in parts:
        try:
            rules.append(_Rule(re.compile(entry), "[REDACTED]"))
        except re.error:
            continue
    return tuple(rules)


@dataclass
class PiiRedactor:
    """Redact PII substrings inside nested dict / list / tuple structures.

    Instances are cheap and stateless apart from their rule list; the default
    factory reads ``DIGI_PII_PATTERNS`` at construction time so tests can
    rebuild the redactor with a fresh environment via ``monkeypatch``.
    """

    rules: tuple[_Rule, ...] = field(default_factory=lambda: DEFAULT_PATTERNS)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> PiiRedactor:
        env = env if env is not None else os.environ
        extra = _parse_extra_patterns(env.get("DIGI_PII_PATTERNS"))
        return cls(rules=DEFAULT_PATTERNS + extra)

    def redact_text(self, value: str) -> str:
        out = value
        for rule in self.rules:
            out = rule.pattern.sub(rule.replacement, out)
        return out

    def redact(self, value: Any) -> Any:
        """Return ``value`` with every nested string run through the ruleset."""
        if isinstance(value, str):
            return self.redact_text(value)
        if isinstance(value, Mapping):
            return {k: self.redact(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.redact(v) for v in value]
        if isinstance(value, tuple):
            return tuple(self.redact(v) for v in value)
        return value

    # Convenience wrappers matching LangSmith's process_inputs / process_outputs
    # signature (they receive a dict, must return a dict).
    def process_inputs(self, inputs: dict[str, Any]) -> dict[str, Any]:
        redacted = self.redact(inputs)
        return redacted if isinstance(redacted, dict) else {"inputs": redacted}

    def process_outputs(self, outputs: Any) -> Any:
        return self.redact(outputs)


def default_redactor() -> PiiRedactor:
    """Return a redactor initialized from the current process environment."""
    return PiiRedactor.from_env()
