"""Retrieval helpers for document-mode RAG (#3417 / #3418).

Force-tool: the embed slash commands ``/search`` and ``/docs`` pass the user's
string as the tool argument. The model is not hinted — we inject the tool call
ourselves, then let it synthesize.

Auto second-hop: after a locate (digisearch / digivault_search_notes) we load
full notes via ``digivault_get_note`` (batch ≤20) so the model does not ask
permission to read what it already found.
"""

from __future__ import annotations

import json
from typing import Any

GET_NOTE_TOOL = "digivault_get_note"
GET_NOTE_BATCH_MAX = 20

SEARCH_TOOLS_FOR_NOTE_HOP = frozenset(
    {"digisearch", "digisearch_fetch_all", "digivault_search_notes"}
)

# Public slash names → orchestrator tool ids. ``digivault_get_note`` is not a
# force-tool: it is the automatic second hop, never a user-facing slash.
_FORCE_TOOL_ALIASES: dict[str, str] = {
    "search": "digisearch",
    "digisearch": "digisearch",
    "docs": "digivault_search_notes",
    "digivault": "digivault_search_notes",
    "digivault_search_notes": "digivault_search_notes",
}


def resolve_force_tool(raw: str | None) -> str | None:
    """Map a header/body force-tool token onto a registered search tool, or None."""
    if not raw or not str(raw).strip():
        return None
    token = str(raw).strip().lstrip("/").lower()
    return _FORCE_TOOL_ALIASES.get(token)


def query_from_tool_args(args: dict[str, Any] | None) -> str | None:
    """Short query string for activity rows — never the whole user turn when we
    can name a path or a batch count instead."""
    if not isinstance(args, dict):
        return None
    query = args.get("query")
    if isinstance(query, str) and query.strip():
        return query.strip()
    vault_path = args.get("vault_path")
    if isinstance(vault_path, str) and vault_path.strip():
        return vault_path.strip()
    vault_paths = args.get("vault_paths")
    if isinstance(vault_paths, list) and vault_paths:
        n = len([p for p in vault_paths if isinstance(p, str) and p.strip()])
        if n:
            return f"{n} note" if n == 1 else f"{n} notes"
    return None


def _path_from_source(tool_name: str, source: dict[str, Any]) -> str | None:
    meta = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
    if tool_name == "digivault_search_notes":
        raw = source.get("doc_id") or meta.get("vault_path") or source.get("vault_path")
    else:
        # digisearch doc_id is a repo path; only metadata.vault_path is loadable.
        raw = meta.get("vault_path") or source.get("vault_path")
    if not isinstance(raw, str):
        return None
    path = raw.strip()
    if not path or path.startswith("repo://"):
        return None
    return path


def vault_paths_from_retrieval(tool_name: str, result: dict[str, Any]) -> list[str]:
    """Loadable vault paths from a locate-tool result, capped at the get_note batch."""
    sources = result.get("rag_sources")
    if not isinstance(sources, list):
        sources = result.get("results") if isinstance(result.get("results"), list) else []
    out: list[str] = []
    seen: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            continue
        path = _path_from_source(tool_name, source)
        if not path or path in seen:
            continue
        seen.add(path)
        out.append(path)
        if len(out) >= GET_NOTE_BATCH_MAX:
            break
    return out


def force_tool_messages(
    tool_name: str,
    query: str,
    result: str | dict[str, Any],
) -> list[dict[str, Any]]:
    """Assistant tool_call + tool result so the model synthesizes without being
    told to search. ``query`` is the user's string, used as the tool argument."""
    call_id = "forced_0"
    content = result.get("content") if isinstance(result, dict) else result
    if not isinstance(content, str):
        content = json.dumps(content) if content is not None else ""
    return [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps({"query": query}, ensure_ascii=False),
                    },
                }
            ],
        },
        {"role": "tool", "tool_call_id": call_id, "content": content},
    ]


def merge_loaded_notes(
    search_result: dict[str, Any],
    note_result: dict[str, Any],
) -> dict[str, Any]:
    """Attach already-loaded notes onto the locate result so the model answers
    from full notes instead of asking permission."""
    merged = dict(search_result)
    note_content = note_result.get("content")
    if isinstance(note_content, str) and note_content.strip():
        try:
            parsed = json.loads(search_result.get("content") or "{}")
        except json.JSONDecodeError:
            parsed = {}
        if not isinstance(parsed, dict):
            parsed = {}
        parsed["loaded_notes"] = note_content
        parsed["notes_already_loaded"] = True
        merged["content"] = json.dumps(parsed, ensure_ascii=False)
    note_sources = note_result.get("rag_sources")
    if isinstance(note_sources, list) and note_sources:
        existing = list(merged.get("rag_sources") or [])
        seen = {
            (s.get("source_id") or s.get("doc_id"))
            for s in existing
            if isinstance(s, dict) and (s.get("source_id") or s.get("doc_id"))
        }
        for item in note_sources:
            if not isinstance(item, dict):
                continue
            key = item.get("source_id") or item.get("doc_id")
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            existing.append(item)
        merged["rag_sources"] = existing
    return merged


def auto_load_notes(
    *,
    locate_tool: str,
    locate_result: dict[str, Any],
    execute_fn: Any,
    emit: Any,
    allowed_names: frozenset[str] | None,
) -> dict[str, Any]:
    """If *locate_result* has loadable vault paths, call digivault_get_note and
    merge. No-op when the tool is disallowed, the locate tool is not a search
    sink, or there are no paths. *emit* is ``(event_type, data) -> None``."""
    if locate_tool not in SEARCH_TOOLS_FOR_NOTE_HOP:
        return locate_result
    if allowed_names is not None and GET_NOTE_TOOL not in allowed_names:
        return locate_result
    paths = vault_paths_from_retrieval(locate_tool, locate_result)
    if not paths:
        return locate_result
    hop_args = {"vault_paths": paths}
    emit("tool_call", {"name": GET_NOTE_TOOL, "arguments": hop_args})
    note_result = execute_fn(GET_NOTE_TOOL, hop_args)
    if not isinstance(note_result, dict):
        emit(
            "tool_result",
            {"name": GET_NOTE_TOOL, "content": str(note_result), "rag_sources": []},
        )
        return locate_result
    note_result.setdefault("hit_count", len(note_result.get("rag_sources") or []))
    note_query = query_from_tool_args(hop_args)
    if note_query:
        note_result.setdefault("query", note_query)
    emit("tool_result", {**note_result, "name": GET_NOTE_TOOL})
    return merge_loaded_notes(locate_result, note_result)
