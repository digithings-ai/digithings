"""Pre-crawled page text for a site whose live pages sit behind a bot challenge.

Some sites answer every fetch from a datacenter IP with a challenge page
(SiteGround's sgcaptcha: HTTP 202 plus a meta refresh to
``/.well-known/sgcaptcha/``) instead of the page. For a caller that names a
page corpus, web_search enrichment still tries the live page first; only when
that fetch is a challenge or fails does it take the page text from the corpus.

A corpus is a directory of markdown files, one per page, each opening with a
``url:`` front-matter line. It is named by id and found under
``DIGISEARCH_PAGE_CORPUS_DIR/<id>/``. Nothing is fetched or written here: an
unset directory, an unknown id or a page outside the corpus leaves enrichment
exactly as it was.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

PAGE_CORPUS_DIR_ENV = "DIGISEARCH_PAGE_CORPUS_DIR"
CORPUS_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
#: Locale prefixes whose pages mirror the default-locale paths one to one.
MIRROR_PREFIXES = ("/en-au/",)
_CHALLENGE_PATH = "/.well-known/sgcaptcha"
_FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)


def normalize_page_url(url: str) -> str | None:
    """``https://www.Host/path?q#f`` -> ``host/path/`` (no scheme, query or fragment)."""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    host = parts.hostname.lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    path = parts.path or "/"
    if not path.endswith("/"):
        path += "/"
    return host + path


def is_challenge_page(status_code: int, final_url: str, text: str) -> bool:
    """True for a bot-challenge stub rather than the page itself."""
    if _CHALLENGE_PATH in (final_url or ""):
        return True
    head = (text or "")[:2000].lower()
    if _CHALLENGE_PATH in head:
        return True
    return status_code == 202 and len((text or "").strip()) < 1024


@lru_cache(maxsize=16)
def _load(root: str, corpus_id: str) -> dict[str, str]:
    pages: dict[str, str] = {}
    base = Path(root) / corpus_id
    if not base.is_dir():
        return pages
    for path in sorted(base.glob("*.md")):
        try:
            raw = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        m = _FRONT_MATTER_RE.match(raw)
        if not m:
            continue
        url = next(
            (
                ln.split(":", 1)[1].strip()
                for ln in m.group(1).splitlines()
                if ln.startswith("url:")
            ),
            "",
        )
        key = normalize_page_url(url)
        body = raw[m.end() :].strip()
        if key and body:
            pages[key] = body
    return pages


def corpus_page_text(corpus_id: str | None, url: str) -> str | None:
    """The corpus text for ``url``, or ``None`` (no corpus, unknown id, page not in it)."""
    if not corpus_id or not CORPUS_ID_RE.match(corpus_id):
        return None
    root = os.environ.get(PAGE_CORPUS_DIR_ENV, "").strip()
    if not root:
        return None
    key = normalize_page_url(url)
    if not key:
        return None
    pages = _load(root, corpus_id)
    if key in pages:
        return pages[key]
    host, _, path = key.partition("/")
    for prefix in MIRROR_PREFIXES:
        if ("/" + path).startswith(prefix):
            return pages.get(host + "/" + path[len(prefix) - 1 :])
    return None


__all__ = [
    "PAGE_CORPUS_DIR_ENV",
    "corpus_page_text",
    "is_challenge_page",
    "normalize_page_url",
]
