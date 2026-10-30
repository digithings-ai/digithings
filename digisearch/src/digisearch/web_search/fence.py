"""Site fence for a pinned tenant's web tools: which URLs a pin list admits.

A pin is ``host``, ``host/path``, ``host/path/seg*`` or ``host/path?k=v`` (the
canonical forms digigraph's corpus map validates). The semantics match
``digigraph.orchestration.web_search_tools.url_within_pins`` exactly; a parity
test runs both over the same table, so the fence digisearch applies on every
fetch hop can never be wider than the one digigraph applies to results.

- ``host`` admits the host and every subdomain of it (``academy.example.com``),
  never a look-alike (``example.com.evil.net``, ``evilexample.com``).
- ``host/path`` admits that path and anything under it, on the host or a
  subdomain; ``host/path/seg*`` admits ``/path/seg<more>`` only.
- ``host/path?k=v`` admits that one page carrying ``k=v``.
- A leading ``www.`` is ignored on both sides.
- The URL path is normalised before matching: ``.`` and ``..`` segments
  (plain or percent-encoded) are resolved, so ``/company/acme/../other`` is
  matched as ``/other``; a segment hiding an encoded ``/`` or ``\\`` is refused.
"""

from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import parse_qsl, unquote, urlsplit


class FenceRefusedError(RuntimeError):
    """A URL (or a redirect hop) falls outside the tenant's allowed sites."""


def _domain_within(domain: str, pin_host: str) -> bool:
    return domain == pin_host or domain.endswith("." + pin_host)


def _split_pin(pin: str) -> tuple[str, str]:
    host, sep, path = pin.strip().lower().split("?", 1)[0].rstrip("*").rstrip("/").partition("/")
    host = host.rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    return host, ("/" + path if sep and path else "")


def _pin_query(pin: str) -> list[tuple[str, str]]:
    _, sep, query = pin.strip().lower().partition("?")
    return parse_qsl(query, keep_blank_values=False) if sep else []


def normalize_path(path: str) -> str | None:
    """Lower-cased URL path with dot segments resolved and no trailing ``/``.

    ``None`` when a segment decodes to something holding ``/`` or ``\\``: a
    server may decode it into a different path than the one matched here.
    """
    out: list[str] = []
    for seg in (path or "/").split("/"):
        dec = unquote(seg)
        if "/" in dec or "\\" in dec:
            return None
        if dec in ("", "."):
            continue
        if dec == "..":
            if out:
                out.pop()
            continue
        out.append(seg)
    return ("/" + "/".join(out)).lower().rstrip("/")


def clean_pins(pins: Iterable[object] | None) -> list[str]:
    """Non-empty string pins, stripped; anything else is dropped."""
    out: list[str] = []
    for p in pins or ():
        if isinstance(p, str) and p.strip() and p.strip() not in out:
            out.append(p.strip())
    return out


def url_in_fence(url: object, pins: Iterable[str]) -> bool:
    """True when ``url`` (http/https) falls inside one pin."""
    if not isinstance(url, str):
        return False
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return False
    if parts.scheme not in ("http", "https"):
        return False
    try:
        host = (parts.hostname or "").lower().rstrip(".")
    except ValueError:
        return False
    if not host:
        return False
    path = normalize_path(parts.path)
    if path is None:
        return False
    for pin in pins:
        pin_host, pin_path = _split_pin(pin)
        if not pin_host or not _domain_within(host, pin_host):
            continue
        pin_query = _pin_query(pin)
        if pin_query:
            have = set(parse_qsl((parts.query or "").lower(), keep_blank_values=False))
            if path == pin_path and all(kv in have for kv in pin_query):
                return True
            continue
        if pin.strip().endswith("*"):
            if pin_path and path.startswith(pin_path) and len(path) > len(pin_path):
                return True
            continue
        if not pin_path or path == pin_path or path.startswith(pin_path + "/"):
            return True
    return False


def fence_guard(pins: Iterable[str]):
    """A digifetch ``url_guard`` that refuses any hop outside ``pins``."""
    fixed = clean_pins(pins)

    def guard(url: str) -> None:
        if not url_in_fence(url, fixed):
            raise FenceRefusedError(f"outside the allowed sites: {url}")

    return guard
