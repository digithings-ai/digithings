"""PII redaction for DigiSmith trace payloads before LangSmith submission.

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

The module has no runtime dependency on ``langsmith``; it operates on plain
Python structures. ``digismith.trace`` wires it into ``langsmith.traceable``
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
    "EMAIL_PATTERN",
    "API_KEY_PATTERN",
    "PHONE_PATTERN",
    "PiiRedactor",
    "default_redactor",
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
