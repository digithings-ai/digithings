"""digisearch result formatting: render query results as a markdown table.

Display logic (table, columns, truncation) lives here; the HTTP query path
uses :mod:`digibase.http_client` directly. The ``query_digisearch`` /
``search_documents`` helpers and the module-level pooled client were removed
in DIG-3398: they had no callers (the only consumer of this module is
``server.py``'s ``format=table`` branch, via :func:`format_results_table`).
"""

from __future__ import annotations

import re
from typing import Any

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


def _metadata_columns(
    results: list[dict], preferred: tuple[str, ...] | list[str] | None
) -> list[str]:
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
        return f"digisearch results for: {query_text!r}\n\nNo results."
    k = top_k if top_k is not None else len(results)
    meta_cols = _metadata_columns(results[:k], preferred_columns)
    show_chunk_id = any(r.get("chunk_id") for r in results[:k])
    headers = (
        ["Rank", "Score", "doc_id"]
        + (["chunk_id"] if show_chunk_id else [])
        + meta_cols
        + ["Content"]
    )
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
    return f"digisearch results for: {query_text!r}\n\n{table}"
