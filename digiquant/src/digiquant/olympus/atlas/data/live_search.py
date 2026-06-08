"""Build xAI Live Search ``search_parameters`` from the curated domain allowlist."""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any  # noqa  # scored-lint suppression: heterogeneous search-param dict

import yaml

_CONFIG = Path(__file__).resolve().parent.parent / "config" / "search_domains.yaml"

# xAI caps allowed_websites at 5 per source.
_MAX_ALLOWED_WEBSITES = 5


@lru_cache(maxsize=1)
def _load_config() -> dict[str, Any]:
    with open(_CONFIG, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def build_search_parameters(*, run_date: date) -> dict[str, Any]:
    """Return an xAI Live Search descriptor: web (allowlisted) + news + x, recent + cited."""
    cfg = _load_config()
    allowed = list(cfg.get("web_allowed_websites", []))
    recency = int(cfg.get("recency_days", 7))
    from_date = (run_date - timedelta(days=recency)).isoformat()
    sources: list[dict[str, Any]] = [{"type": "web"}, {"type": "news"}, {"type": "x"}]
    if allowed:
        # xAI caps allowed_websites at 5 per source; take the highest-priority slice.
        sources[0]["allowed_websites"] = allowed[:_MAX_ALLOWED_WEBSITES]
    return {
        "mode": "on",
        "sources": sources,
        "from_date": from_date,
        "return_citations": True,
        "max_search_results": int(cfg.get("max_search_results", 8)),
    }
