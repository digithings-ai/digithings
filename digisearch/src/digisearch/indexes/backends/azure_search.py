"""Azure AI Search backend for DigiSearch."""

from __future__ import annotations

import logging
import os
from typing import Any

from digisearch.core.models import Chunk, Query, Result, SearchResponse

logger = logging.getLogger(__name__)

# OData comparison operators we support (Azure AI Search filter syntax)
# 'in' is handled separately via search.in()
_ODATA_OPS = frozenset({"eq", "ne", "gt", "ge", "lt", "le", "and", "or"})

# Optional: only import when azure-search-documents is installed
try:
    from azure.core.credentials import AzureKeyCredential
    from azure.search.documents import SearchClient

    _AZURE_AVAILABLE = True
except ImportError:
    _AZURE_AVAILABLE = False

# Connection: endpoint + api_key from .env only
AZURE_SEARCH_ENDPOINT = os.environ.get("AZURE_SEARCH_ENDPOINT", "")
AZURE_SEARCH_API_KEY = os.environ.get("AZURE_SEARCH_API_KEY", "")


def _get_index_config() -> dict[str, Any]:
    """Load index config from DIGISEARCH_INDEX_CONFIG. Else use env fallbacks."""
    from digisearch.core.config import get_index_config_path, load_index_config

    path = get_index_config_path()
    if path:
        cfg = load_index_config(path)
        if cfg:
            fm = cfg.get("field_mapping", {})
            return {
                "index_name": cfg.get("index_name", os.environ.get("AZURE_SEARCH_INDEX_NAME", "")),
                "content_field": fm.get("content_field", os.environ.get("AZURE_SEARCH_CONTENT_FIELD", "content")),
                "content_fallback": fm.get("content_fallback"),
                "key_field": fm.get("key_field", os.environ.get("AZURE_SEARCH_KEY_FIELD", "id")),
                "doc_id_field": fm.get("doc_id_field", os.environ.get("AZURE_SEARCH_DOC_ID_FIELD", "doc_id")),
                "result_metadata_fields": cfg.get("result_metadata_fields") or [],
                "filterable_fields": cfg.get("filterable_fields") or [],
                "allow_raw_filter": bool(cfg.get("allow_raw_filter", False)),
            }
    return {
        "index_name": os.environ.get("AZURE_SEARCH_INDEX_NAME", ""),
        "content_field": os.environ.get("AZURE_SEARCH_CONTENT_FIELD", "content"),
        "content_fallback": None,
        "key_field": os.environ.get("AZURE_SEARCH_KEY_FIELD", "id"),
        "doc_id_field": os.environ.get("AZURE_SEARCH_DOC_ID_FIELD", "doc_id"),
        "result_metadata_fields": [],
        "filterable_fields": [],
        "allow_raw_filter": False,
    }


def _build_odata_filter(structured_filters: list[dict[str, Any]], filterable_fields: list[str]) -> str | None:
    """Build OData filter string from structured filters. Only allows filterable_fields.

    Supported ops: eq, ne, gt, ge, lt, le, and for 'in' uses Azure search.in(field, 'v1,v2', ',').
    """
    allowlist = frozenset(filterable_fields)
    if not allowlist or not structured_filters:
        return None
    parts: list[str] = []
    for f in structured_filters:
        field = f.get("field")
        op = (f.get("op") or "eq").strip().lower()
        value = f.get("value")
        if field is None or field not in allowlist:
            continue
        # search.in(field, 'v1,v2', ',') for op 'in' (string fields; list or comma-sep string)
        if op == "in":
            if isinstance(value, list):
                vals = [str(v).replace("'", "''") for v in value]
                value_list = ",".join(vals)
            elif isinstance(value, str):
                value_list = value.replace("'", "''")
            else:
                continue
            if not value_list.strip():
                continue  # skip empty list/string to avoid invalid search.in(..., '', ',')
            parts.append(f"search.in({field}, '{value_list}', ',')")
            continue
        if op not in _ODATA_OPS:
            continue
        if op in ("and", "or"):
            continue  # binary ops handled separately if we add group support
        if value is None:
            parts.append(f"({field} eq null)")
            continue
        if isinstance(value, bool):
            parts.append(f"({field} eq {str(value).lower()})")
        elif isinstance(value, (int, float)):
            parts.append(f"({field} {op} {value})")
        elif isinstance(value, str):
            escaped = value.replace("'", "''")
            parts.append(f"({field} {op} '{escaped}')")
        else:
            escaped = str(value).replace("'", "''")
            parts.append(f"({field} {op} '{escaped}')")
    if not parts:
        return None
    return " and ".join(parts)


def _normalize_facets(raw: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]] | None:
    """Ensure facets dict is field -> list of {value, count} for JSON response."""
    if not raw:
        return None
    out: dict[str, list[dict[str, Any]]] = {}
    for field, buckets in raw.items():
        if not isinstance(buckets, list):
            continue
        out[field] = []
        for b in buckets:
            if isinstance(b, dict):
                out[field].append({"value": b.get("value"), "count": b.get("count", 0)})
            elif hasattr(b, "value") and hasattr(b, "count"):
                out[field].append({"value": getattr(b, "value", None), "count": getattr(b, "count", 0)})
    return out if out else None


def _get_client() -> "SearchClient | None":
    """Create SearchClient if Azure is configured."""
    if not _AZURE_AVAILABLE:
        return None
    cfg = _get_index_config()
    index_name = cfg.get("index_name", "")
    if not all([AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_API_KEY, index_name]):
        return None
    return SearchClient(
        endpoint=AZURE_SEARCH_ENDPOINT.rstrip("/"),
        index_name=index_name,
        credential=AzureKeyCredential(AZURE_SEARCH_API_KEY),
    )


def query_azure(query: Query, index_name: str | None = None) -> SearchResponse:
    """Query Azure AI Search. Connection from env; field mapping from index config or env."""
    client = _get_client()
    if client is None:
        return SearchResponse(results=[], facets=None)

    cfg = _get_index_config()
    key_f = cfg["key_field"]
    content_f = cfg["content_field"]
    content_fb = cfg.get("content_fallback")
    doc_id_f = cfg["doc_id_field"]
    extra_fields = cfg.get("result_metadata_fields") or []
    filterable_fields = cfg.get("filterable_fields") or []
    allow_raw_filter = cfg.get("allow_raw_filter", False)

    # Build select: key, content, doc_id, then requested columns or all result_metadata_fields
    select = [key_f, content_f, doc_id_f]
    if content_fb and content_fb not in select:
        select.append(content_fb)
    if query.columns:
        allowed = [f for f in query.columns if f in extra_fields or f in (key_f, content_f, doc_id_f)]
        for f in allowed:
            if f not in select:
                select.append(f)
    else:
        for f in extra_fields:
            if f not in select:
                select.append(f)

    # Build OData filter from query.filters
    odata_filter: str | None = None
    filters_dict = query.filters or {}
    if allow_raw_filter and filters_dict.get("odata"):
        raw = filters_dict.get("odata")
        odata_filter = str(raw).strip() if raw else None
    elif filters_dict.get("structured"):
        structured = filters_dict.get("structured")
        if isinstance(structured, list):
            odata_filter = _build_odata_filter(structured, filterable_fields)

    results: list[Result] = []
    try:
        search_kw: dict[str, Any] = {
            "search_text": query.text,
            "top": query.top_k,
            "select": select,
            "query_type": "simple",
            "search_mode": "any",
        }
        if odata_filter:
            search_kw["filter"] = odata_filter
        if query.facets:
            search_kw["facets"] = query.facets
        if query.skip > 0:
            search_kw["skip"] = query.skip
        if query.include_total_count:
            search_kw["include_total_count"] = True
        if query.order_by:
            search_kw["order_by"] = query.order_by
        if query.highlight_fields:
            search_kw["highlight_fields"] = query.highlight_fields
        if query.highlight_pre_tag is not None:
            search_kw["highlight_pre_tag"] = query.highlight_pre_tag
        if query.highlight_post_tag is not None:
            search_kw["highlight_post_tag"] = query.highlight_post_tag
        search_results = client.search(**search_kw)
        for i, doc in enumerate(search_results):
            raw: dict[str, Any] = dict(doc)
            content = (
                raw.get(content_f)
                or (raw.get(content_fb) if content_fb else None)
                or raw.get("chunk_text")
                or raw.get("text")
                or raw.get("description")
                or ""
            )
            if not content:
                for v in raw.values():
                    if isinstance(v, str) and len(v) > 10:
                        content = v
                        break
            key = str(raw.get(key_f, raw.get("id", "")))
            doc_id = str(raw.get(doc_id_f, key))
            # Azure returns relevance score in result dict as "@search.score" (BM25); not as doc.search_score
            score = float(
                raw.get("@search.score")
                if raw.get("@search.score") is not None
                else getattr(doc, "search_score", 1.0)
            )
            chunk = Chunk(
                id=key,
                content=str(content) if content else "",
                doc_id=doc_id,
                embedding=None,
                metadata=raw,
            )
            results.append(Result(chunk=chunk, score=score, rank=i + 1))
        facets_raw = search_results.get_facets() if hasattr(search_results, "get_facets") else None
        facets = _normalize_facets(facets_raw) if facets_raw else None
        total_count: int | None = None
        if query.include_total_count and hasattr(search_results, "get_count"):
            try:
                total_count = search_results.get_count()
            except Exception:
                pass
        logger.debug("Azure query '%s' returned %d results (index=%s)", query.text[:80], len(results), index_name)
        return SearchResponse(results=results, facets=facets, total_count=total_count)
    except Exception as exc:
        logger.error("Azure AI Search query failed (index=%s): %s", index_name, exc)
        return SearchResponse(results=[], facets=None)


def is_azure_configured() -> bool:
    """True if Azure connection + index are configured (env or index config)."""
    if not _AZURE_AVAILABLE or not AZURE_SEARCH_ENDPOINT or not AZURE_SEARCH_API_KEY:
        return False
    cfg = _get_index_config()
    return bool(cfg.get("index_name"))
