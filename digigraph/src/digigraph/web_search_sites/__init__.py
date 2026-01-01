"""Per-tenant site graphs for the built-in web_search tool description.

A site graph is one markdown file per tenant slug (``<slug>.md``) kept OUTSIDE
this repo, in the directory named by ``DIGIGRAPH_WEB_SEARCH_SITES_DIR``. A
tenant whose corpus-map entry pins ``webSearchDomains`` and whose slug has a
file there gets that file appended to its ``web_search`` tool description, so
the model knows which page answers what before it searches. The graph lives in
a file, not in the corpus map, because a page-by-page graph does not fit the
map's 5 KiB secret budget; it lives outside the repo because it is tenant
content. Unset directory: no tenant has a site graph.

The id is always the server-resolved tenant slug, never a client value, and it
is validated before it touches the filesystem.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

WEB_SEARCH_SITES_DIR_ENV = "DIGIGRAPH_WEB_SEARCH_SITES_DIR"
_SITE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
# A guard, not a budget: the graph rides every turn's tool list.
MAX_SITE_GRAPH_BYTES = 16 * 1024


def web_search_sites_dir() -> Path | None:
    """The configured site-graph directory, or ``None`` when unset."""
    raw = os.environ.get(WEB_SEARCH_SITES_DIR_ENV, "").strip()
    return Path(raw) if raw else None


def _path_for(site_id: str) -> Path | None:
    if not isinstance(site_id, str) or not _SITE_ID.match(site_id):
        return None
    root = web_search_sites_dir()
    return root / f"{site_id}.md" if root is not None else None


def has_web_search_site_graph(site_id: str) -> bool:
    """True when the site-graph directory holds a file for ``site_id``."""
    path = _path_for(site_id)
    return bool(path and path.is_file())


def load_web_search_site_graph(site_id: str) -> str | None:
    """The site graph text for ``site_id``, or ``None`` (unset dir, unknown, empty or oversized)."""
    path = _path_for(site_id)
    if path is None or not path.is_file():
        return None
    return _read(str(path), path.stat().st_mtime_ns)


@lru_cache(maxsize=32)
def _read(path: str, _mtime_ns: int) -> str | None:
    raw = Path(path).read_bytes()
    if not raw.strip() or len(raw) > MAX_SITE_GRAPH_BYTES:
        return None
    return raw.decode("utf-8").strip()


__all__ = [
    "MAX_SITE_GRAPH_BYTES",
    "WEB_SEARCH_SITES_DIR_ENV",
    "has_web_search_site_graph",
    "load_web_search_site_graph",
    "web_search_sites_dir",
]
