"""Stdlib-only security guards for the remote-ingestion path (``ingest_url.py``).

Three independent concerns, each addressing a specific risk of pulling
third-party content into a compiled skill package:

- :func:`is_allowed_scrape_url` — SSRF allowlist. Mirrors
  ``digisearch.ingestion.web_scrape.is_allowed_scrape_url`` (REM-064)
  exactly, but is duplicated rather than imported: ``digiskills[ingest]``
  must not gain a digisearch dependency for one function (see ARCHITECTURE.md
  "Core hard deps").
- :func:`redact_secrets` — best-effort regex redaction of common credential
  shapes (API keys, tokens, private-key blocks) before scraped text is
  written into a reference file or sent to a third-party LLM.
- :func:`scan_for_prompt_injection` — best-effort heuristic flags for text
  that reads like an attempt to redirect an agent's instructions. Never
  mutates or blocks content — regex heuristics are too false-positive/
  negative-prone for that; only flags it so callers can surface a warning
  and an untrusted-content banner.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse

_BLOCKED_SCHEMES = frozenset({"file", "ftp", "gopher", "data", "javascript"})


def is_allowed_scrape_url(url: str) -> bool:
    """Return True when *url* is safe to fetch during URL-source ingestion.

    Mirrors digisearch's REM-064 ``is_allowed_scrape_url``
    (``digisearch/src/digisearch/ingestion/web_scrape.py``): rejects
    non-http(s) schemes, localhost/``.local``/``.internal`` hostnames, and any
    hostname or DNS-resolved address that is private/loopback/link-local/
    reserved (blocks cloud metadata endpoints like ``169.254.169.254`` too).
    """
    raw = (url or "").strip()
    if not raw:
        return False
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()
    if not scheme or scheme in _BLOCKED_SCHEMES:
        return False
    if scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").strip().lower()
    if not host or host == "localhost":
        return False
    if host.endswith(".local") or host.endswith(".internal"):
        return False
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            return False
    try:
        for info in socket.getaddrinfo(host, None):
            ip = info[4][0]
            addr = ipaddress.ip_address(ip)
            if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
                return False
    except OSError:
        return False
    return True


# --- secret redaction ---------------------------------------------------

_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "private-key-block",
        re.compile(
            r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |)PRIVATE KEY-----[\s\S]+?"
            r"-----END (?:RSA |EC |OPENSSH |DSA |)PRIVATE KEY-----"
        ),
    ),
    ("aws-access-key-id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("openai-style-key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\b")),
    ("bearer-token", re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\-_.=]{16,}")),
    (
        "assigned-secret",
        re.compile(
            r"(?i)\b(?:api[_-]?key|secret|access[_-]?token|auth[_-]?token|password)"
            r"\s*[:=]\s*['\"]?[A-Za-z0-9\-_/+=]{12,}['\"]?"
        ),
    ),
]


def redact_secrets(text: str) -> tuple[str, int]:
    """Replace likely-credential substrings in *text* with ``[REDACTED:<kind>]``.

    Best-effort and pattern-based — not a substitute for the source not
    containing secrets in the first place. Returns the redacted text and how
    many replacements were made, so callers can surface it as a warning
    (:attr:`~digiskills.models.Corpus.redacted_count`).
    """
    total = 0
    for name, pattern in _SECRET_PATTERNS:
        text, count = pattern.subn(f"[REDACTED:{name}]", text)
        total += count
    return text, total


# --- prompt-injection heuristics -----------------------------------------

_INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "ignore-instructions",
        re.compile(r"(?i)\bignore\s+(?:all\s+|any\s+)?(?:previous|prior|above)\s+instructions?\b"),
    ),
    (
        "disregard-instructions",
        re.compile(r"(?i)\bdisregard\s+(?:all\s+)?(?:previous|prior|the\s+above)\b"),
    ),
    ("new-instructions", re.compile(r"(?i)\b(?:new|updated)\s+(?:system\s+)?instructions?\s*:")),
    ("role-override", re.compile(r"(?i)\byou\s+are\s+now\s+(?:a|an|in)\b")),
    (
        "reveal-system-prompt",
        re.compile(r"(?i)\b(?:reveal|print|show)\s+(?:your\s+)?(?:system\s+prompt|instructions)\b"),
    ),
    ("fake-role-marker", re.compile(r"(?im)^\s*(?:system|assistant)\s*:\s*\S")),
]


def scan_for_prompt_injection(text: str, *, max_flags: int = 5) -> list[str]:
    """Best-effort heuristic flags for injection-style phrasing in *text*.

    Never mutates or blocks content — only flags it. Returns up to
    ``max_flags`` short ``"<pattern-name>: <matched excerpt>"`` strings for
    the caller to surface as a warning and/or an untrusted-content banner.
    """
    flags: list[str] = []
    for name, pattern in _INJECTION_PATTERNS:
        match = pattern.search(text)
        if match:
            excerpt = match.group(0).strip()[:80]
            flags.append(f"{name}: {excerpt!r}")
            if len(flags) >= max_flags:
                break
    return flags
