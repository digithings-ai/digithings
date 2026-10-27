"""PII redaction for digitrace trace payloads.

``PiiRedactor`` walks arbitrary dict / list / tuple structures and replaces
PII-looking substrings inside string values with opaque sentinels. Built-in
patterns cover:

* Emails (RFC-5321-lite) → ``[REDACTED_EMAIL]``
* API key prefixes (``sk-``, ``sk_``, ``dgk_live_``, ``dgk_test_``, ``lsv2_``)
  → ``[REDACTED_KEY]``
* E.164 and common North-American phone formats → ``[REDACTED_PHONE]``

Two structural guards sit beside the value patterns (ADR-0036 §7):

* **Sensitive key names** — a mapping key that names a credential
  (``api_key``, ``openai_api_key``, ``authorization``, ``password``,
  ``session_token``, …) has its whole value replaced with ``[REDACTED]``,
  whatever the value looks like. Token *counts* such as ``total_tokens`` and
  ``max_tokens`` are deliberately not treated as credentials.
* **Long documents** — a string longer than ``max_document_chars`` is replaced
  with ``[DOCUMENT sha256:<digest> chars:<n>]``, so a full document body keeps
  its identity and size without leaving the text in the payload.

Additional comma-separated regexes from the ``DIGI_PII_PATTERNS`` environment
variable are appended and render as ``[REDACTED]``.
``DIGI_PII_MAX_DOCUMENT_CHARS`` overrides the document threshold (``0`` turns
summarisation off). Non-string values pass through (nested structures recurse).

The module has no runtime dependency on ``langsmith``; it operates on plain
Python structures. ``digitrace.trace`` reuses ``process_inputs`` /
``process_outputs`` on the OTel leg as well, where only a hash and a length of
the redacted payload reach the span.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "DEFAULT_MAX_DOCUMENT_CHARS",
    "DEFAULT_PATTERNS",
    "DEFAULT_SENSITIVE_KEYS",
    "EMAIL_PATTERN",
    "API_KEY_PATTERN",
    "PHONE_PATTERN",
    "PiiRedactor",
    "default_redactor",
]


EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
API_KEY_PATTERN = re.compile(r"(?:sk-|sk_|dgk_live_|dgk_test_|lsv2_)[A-Za-z0-9_-]{8,}")
PHONE_PATTERN = re.compile(r"(?:\+?\d{1,3}[-. ]?)?\(?\d{3}\)?[-. ]?\d{3}[-. ]?\d{4}")

#: Exact normalised key names whose value is a credential, never trace content.
DEFAULT_SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "access_key",
        "access_token",
        "api_key",
        "apikey",
        "auth",
        "authorization",
        "auth_token",
        "bearer",
        "client_secret",
        "cookie",
        "credential",
        "credentials",
        "id_token",
        "password",
        "passwd",
        "private_key",
        "pwd",
        "refresh_token",
        "secret",
        "session_token",
        "set_cookie",
        "token",
        "x_api_key",
    }
)

#: Key-name suffixes that name a credential (``openai_api_key``, ``db_password``).
_SENSITIVE_KEY_SUFFIXES: tuple[str, ...] = (
    "_api_key",
    "_apikey",
    "_auth_token",
    "_client_secret",
    "_password",
    "_private_key",
    "_refresh_token",
    "_secret",
    "_session_token",
)

#: Token *count* keys that must survive: they are metrics, not credentials.
_SAFE_TOKEN_COUNT_KEYS: frozenset[str] = frozenset(
    {
        "completion_tokens",
        "input_tokens",
        "max_tokens",
        "output_tokens",
        "prompt_tokens",
        "token_count",
        "tokens",
        "total_tokens",
    }
)

#: Strings longer than this become a hash + length marker.
DEFAULT_MAX_DOCUMENT_CHARS = 4000

_DOCUMENT_ENV = "DIGI_PII_MAX_DOCUMENT_CHARS"


def _normalise_key(key: str) -> str:
    """``openaiApiKey`` / ``openai-api-key`` → ``openai_api_key``."""
    spaced = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", key).lower()
    return re.sub(r"[^a-z0-9]+", "_", spaced).strip("_")


def _parse_max_document_chars(raw: str | None) -> int | None:
    """Parse ``DIGI_PII_MAX_DOCUMENT_CHARS``; ``None`` disables summarisation."""
    if raw is None or not raw.strip():
        return DEFAULT_MAX_DOCUMENT_CHARS
    value = raw.strip().lower()
    if value in {"0", "off", "false", "no", "none", "disabled"}:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return DEFAULT_MAX_DOCUMENT_CHARS
    return parsed if parsed > 0 else None


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

    Instances are cheap and stateless apart from their rule set and thresholds;
    the default factory reads ``DIGI_PII_PATTERNS`` and
    ``DIGI_PII_MAX_DOCUMENT_CHARS`` at construction time so tests can rebuild
    the redactor with a fresh environment via ``monkeypatch``.
    """

    rules: tuple[_Rule, ...] = field(default_factory=lambda: DEFAULT_PATTERNS)
    sensitive_keys: frozenset[str] = field(default_factory=lambda: DEFAULT_SENSITIVE_KEYS)
    max_document_chars: int | None = DEFAULT_MAX_DOCUMENT_CHARS

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> PiiRedactor:
        env = env if env is not None else os.environ
        extra = _parse_extra_patterns(env.get("DIGI_PII_PATTERNS"))
        return cls(
            rules=DEFAULT_PATTERNS + extra,
            max_document_chars=_parse_max_document_chars(env.get(_DOCUMENT_ENV)),
        )

    def is_sensitive_key(self, key: str) -> bool:
        """True when *key* names a credential rather than trace content."""
        normalised = _normalise_key(key)
        if not normalised or normalised in _SAFE_TOKEN_COUNT_KEYS:
            return False
        if normalised in self.sensitive_keys:
            return True
        return normalised.endswith(_SENSITIVE_KEY_SUFFIXES)

    def redact_text(self, value: str) -> str:
        out = value
        for rule in self.rules:
            out = rule.pattern.sub(rule.replacement, out)
        return out

    def summarise_document(self, value: str) -> str:
        """Replace a document-sized string with its digest and length."""
        limit = self.max_document_chars
        if limit is None or len(value) <= limit:
            return value
        digest = hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()
        return f"[DOCUMENT sha256:{digest} chars:{len(value)}]"

    def redact(self, value: Any) -> Any:
        """Return ``value`` with every nested string run through the ruleset."""
        if isinstance(value, str):
            return self.summarise_document(self.redact_text(value))
        if isinstance(value, Mapping):
            out: dict[Any, Any] = {}
            for key, item in value.items():
                if isinstance(key, str) and self.is_sensitive_key(key):
                    out[key] = "[REDACTED]"
                else:
                    out[key] = self.redact(item)
            return out
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
