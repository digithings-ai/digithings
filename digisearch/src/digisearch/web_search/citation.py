"""Shared citation atom for web grounding (#4064 Phase B, R2)."""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict

_DEFAULT_PORTS = {"http": 80, "https": 443}


class Citation(BaseModel):
    """A cited web source: url plus an optional display title and excerpt."""

    model_config = ConfigDict(extra="forbid")

    url: str
    title: str = ""
    excerpt: str = ""


def normalize_url(url: str) -> str:
    """Normalize *url* for citation identity.

    Lowercases the host, drops the scheme's default port (80 http /
    443 https), strips the fragment, and trims trailing slashes except on
    the root path. The query string is preserved verbatim.
    """
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    port = parts.port
    netloc = host if port is None or port == _DEFAULT_PORTS.get(scheme) else f"{host}:{port}"
    path = parts.path
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/") or "/"
    return urlunsplit((scheme, netloc, path, parts.query, ""))
