"""DigiSearch HTTP client: query the DigiSearch API and format results for display.

Used by DigiGraph and other callers. All display logic (table, columns, truncation) lives here;
callers only pass base_url and query parameters.
"""

from __future__ import annotations

import atexit
import re
from typing import Any

import httpx

# Persistent shared client for connection pooling. httpx.Client is thread-safe.
# Created lazily; closed on process exit via atexit.
_shared_client: httpx.Client | None = None


def _get_client() -> httpx.Client:
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.Client(timeout=15.0)
    return _shared_client


def _close_client() -> None:
    global _shared_client
    if _shared_client is not None and not _shared_client.is_closed:
        _shared_client.close()
    _shared_client = None


atexit.register(_close_client)

# Default column order when present in results (generic document/email search).
# Pass preferred_columns to override per project.
DEFAULT_PREFERRED_COLUMNS = (
    "subject",
    "fromName",
    "fromAddress",
    "sourceType",
    "itemType",
    "sentDateTime",
    "createdDateTime",
    "receivedDateTime",
    "webUrl",
    "fileName",
    "conversationId",
    "channelId",
    "teamId",
    "mailboxId",
    "parentId",
    "itemId",
)

DEFAULT_MAX_META_CELL = 60
DEFAULT_MAX_CONTENT_CELL = 300


def query_digisearch(
    base_url: str,
    text: str,
    index_name: str = "default",
    top_k: int = 10,
    mode: str = "hybrid",
    filter: str | None = None,
    filters: list[dict[str, Any]] | None = None,
    columns: list[str] | None = None,
    response_mode: str = "full",
    summarize_if_over: int | None = None,
) -> dict[str, Any] | None:
    """Call DigiSearch POST /query. Returns full response (results, query, index_name, total, summary?) or None."""
    if not (base_url and base_url.strip()):
        return None
    url = f"{base_url.rstrip('/')}/query"
    payload: dict[str, Any] = {"text": text, "index_name": index_name, "top_k": top_k, "mode": mode}
    if filter is not None and filter.strip():
        payload["filter"] = filter.strip()
    if filters:
        payload["filters"] = filters
    if columns:
        payload["columns"] = columns
    if response_mode and response_mode.strip().lower() != "full":
        payload["response_mode"] = response_mode.strip().lower()
    if summarize_if_over is not None:
        payload["summarize_if_over"] = summarize_if_over
    try:
        client = _get_client()
        r = client.post(url, json=payload)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def _strip_html(text: str, max_len: int = 400) -> str:
    """Remove HTML tags and collapse whitespace."""
    if not text:
        return ""
    s = re.sub(r"<[^>]+>", " ", text)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:max_len] + ("..." if len(s) > max_len else "")


def _cell(v: Any, max_len: int = DEFAULT_MAX_META_CELL) -> str:
    """Format a table cell: stringify, escape pipe, truncate."""
    if v is None:
        return ""
    s = str(v).strip()
    s = s.replace("|", "\\|").replace("\n", " ")
    return (s[:max_len] + "…") if len(s) > max_len else s


def _metadata_columns(results: list[dict], preferred: tuple[str, ...] | list[str] | None) -> list[str]:
    """Column names from all results; preferred order first, then rest sorted."""
    all_keys: set[str] = set()
    for r in results:
        meta = r.get("metadata") or {}
        all_keys.update(k for k in meta if not k.startswith("@"))
    preferred = preferred or DEFAULT_PREFERRED_COLUMNS
    ordered = [k for k in preferred if k in all_keys]
    rest = sorted(all_keys - set(ordered))
    return ordered + rest


def format_results_table(
    results: list[dict],
    query_text: str,
    *,
    preferred_columns: tuple[str, ...] | list[str] | None = None,
    max_meta_cell: int = DEFAULT_MAX_META_CELL,
    max_content_cell: int = DEFAULT_MAX_CONTENT_CELL,
    top_k: int | None = None,
) -> str:
    """Format API results as a markdown table. Universal; no project-specific logic."""
    if not results:
        return f"DigiSearch results for: {query_text!r}\n\nNo results."
    k = top_k if top_k is not None else len(results)
    meta_cols = _metadata_columns(results[:k], preferred_columns)
    show_chunk_id = any(r.get("chunk_id") for r in results[:k])
    headers = ["Rank", "Score", "doc_id"] + (["chunk_id"] if show_chunk_id else []) + meta_cols + ["Content"]
    header_line = "| " + " | ".join(headers) + " |"
    sep_line = "| " + " | ".join("---" for _ in headers) + " |"

    rows: list[str] = []
    for i, r in enumerate(results[:k], 1):
        score = r.get("score", 0)
        doc_id = _cell(r.get("doc_id", ""), max_meta_cell)
        chunk_cell = _cell(r.get("chunk_id", ""), max_meta_cell) if show_chunk_id else ""
        meta = r.get("metadata") or {}
        content = _strip_html(r.get("content", ""), max_len=max_content_cell)
        if len(content) > max_content_cell:
            content = content[:max_content_cell] + "…"
        content = content.replace("|", "\\|").replace("\n", " ")
        cells = [str(i), f"{score:.2f}", doc_id]
        if show_chunk_id:
            cells.append(chunk_cell)
        for col in meta_cols:
            cells.append(_cell(meta.get(col), max_meta_cell))
        cells.append(content)
        rows.append("| " + " | ".join(cells) + " |")

    table = "\n".join([header_line, sep_line] + rows)
    return f"DigiSearch results for: {query_text!r}\n\n{table}"


def search_documents(
    base_url: str,
    text: str,
    index_name: str = "default",
    top_k: int = 10,
    mode: str = "hybrid",
    filter: str | None = None,
    filters: list[dict[str, Any]] | None = None,
    columns: list[str] | None = None,
    response_mode: str = "full",
    summarize_if_over: int | None = None,
    preferred_columns: tuple[str, ...] | list[str] | None = None,
) -> str | None:
    """Query DigiSearch via HTTP and return results as a formatted markdown table string. Appends text_summary when present."""
    data = query_digisearch(
        base_url,
        text,
        index_name=index_name,
        top_k=top_k,
        mode=mode,
        filter=filter,
        filters=filters,
        columns=columns,
        response_mode=response_mode,
        summarize_if_over=summarize_if_over,
    )
    if data is None:
        return None
    results = data.get("results", [])
    table = format_results_table(
        results,
        text,
        preferred_columns=preferred_columns,
        top_k=top_k,
    )
    summary = data.get("summary") or {}
    if isinstance(summary, dict) and summary.get("text_summary"):
        table = table + "\n\n**Summary:** " + summary["text_summary"]
    return table
