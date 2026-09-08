"""Stable URL → filesystem slug helpers."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse, urlunparse

_SLUG_SAFE = re.compile(r"[^a-z0-9]+")

# CamelCase product names → lowercase prose (see AGENTS.md § Naming).
_DIGI_PRODUCT_CAMEL: tuple[tuple[str, str], ...] = (
    ("DigiThings", "digithings"),
    ("DigiChat", "digichat"),
    ("DigiGraph", "digigraph"),
    ("DigiVault", "digivault"),
    ("DigiSearch", "digisearch"),
    ("DigiKey", "digikey"),
    ("DigiQuant", "digiquant"),
    ("DigiSmith", "digismith"),
    ("DigiClaw", "digiclaw"),
    ("DigiBase", "digibase"),
    ("DigiSkills", "digiskills"),
    ("DigiLLM", "digillm"),
    ("DigiFetch", "digifetch"),
    ("DigiWeb", "digiweb"),
    ("DigiCorpus", "digicorpus"),
    ("DigiDev", "digidev"),
    ("DigiLink", "digilink"),
    ("DigiStore", "digistore"),
)


def normalize_digi_product_names(text: str) -> str:
    """Lowercase Digi product/module names in prose titles and frontmatter.

    Code identifiers (``DigiChatSession``, HTTP headers) are not matched — only
    standalone CamelCase product tokens.
    """
    result = text
    for wrong, right in _DIGI_PRODUCT_CAMEL:
        result = re.sub(rf"\b{re.escape(wrong)}\b", right, result)
    return result


def normalize_url(url: str) -> str:
    """Drop fragment and trailing slash (except bare origin) for stable identity."""
    parsed = urlparse(url.strip())
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return urlunparse((parsed.scheme, parsed.netloc.lower(), path, "", parsed.query, ""))


def slug_for_url(url: str, *, max_len: int = 80) -> str:
    """Deterministic filesystem-safe slug for a URL (no path separators)."""
    normalized = normalize_url(url)
    parsed = urlparse(normalized)
    host = parsed.netloc.replace(".", "-")
    path = parsed.path.strip("/") or "index"
    raw = f"{host}-{path}".lower()
    slug = _SLUG_SAFE.sub("-", raw).strip("-")
    if not slug:
        slug = "page"
    if len(slug) > max_len:
        digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:10]
        slug = f"{slug[: max_len - 11]}-{digest}"
    return slug
