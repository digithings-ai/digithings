"""Per-tenant site graphs for the built-in web_search tool description.

One markdown file per tenant slug (``<slug>.md``) ships in this package. A
tenant whose corpus-map entry pins ``webSearchDomains`` and whose slug has a
file here gets that file appended to its ``web_search`` tool description, so
the model knows which page answers what before it searches. The file lives in
the repo, not in the corpus map, because a page-by-page graph does not fit the
map's 5 KiB secret budget.

The id is always the server-resolved tenant slug, never a client value, and it
is validated before it touches the filesystem.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

WEB_SEARCH_SITES_DIR = Path(__file__).resolve().parent
_SITE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
# A guard, not a budget: the graph rides every turn's tool list.
MAX_SITE_GRAPH_BYTES = 16 * 1024


def _path_for(site_id: str) -> Path | None:
    if not isinstance(site_id, str) or not _SITE_ID.match(site_id):
        return None
    return WEB_SEARCH_SITES_DIR / f"{site_id}.md"


def has_web_search_site_graph(site_id: str) -> bool:
    """True when a site graph ships for ``site_id``."""
    path = _path_for(site_id)
    return bool(path and path.is_file())


@lru_cache(maxsize=32)
def load_web_search_site_graph(site_id: str) -> str | None:
    """The site graph text for ``site_id``, or ``None`` (unknown, empty or oversized)."""
    path = _path_for(site_id)
    if path is None or not path.is_file():
        return None
    raw = path.read_bytes()
    if not raw.strip() or len(raw) > MAX_SITE_GRAPH_BYTES:
        return None
    return raw.decode("utf-8").strip()


__all__ = [
    "MAX_SITE_GRAPH_BYTES",
    "WEB_SEARCH_SITES_DIR",
    "has_web_search_site_graph",
    "load_web_search_site_graph",
]
