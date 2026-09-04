"""digivault built-in tool schemas and handlers (via vertical_orchestrator hub)."""

from __future__ import annotations

import json
import logging
from typing import Any

from digigraph.orchestration.registry import ToolContext
from digigraph.orchestration.tool_common import (
    _ORCHESTRATOR_CLIENT_ERRORS,
    _digi_bearer_from_context,
    _digivault_service_base,
    _mark_truncated_excerpts,
    _search_payload_for_llm,
)
from digigraph.trace_events import rag_sources_from_results

logger = logging.getLogger(__name__)


def _invoke_dv(*args, **kwargs):
    """Late-bind through builtin so tests can patch ``builtin.invoke_digivault_tool``."""
    from digigraph.orchestration import builtin as _reg

    return _reg.invoke_digivault_tool(*args, **kwargs)


def _fetch_dv(*args, **kwargs):
    from digigraph.orchestration import builtin as _reg

    return _reg.fetch_digivault_tool_dicts(*args, **kwargs)


def _schema_from_digivault_manifest(ctx: ToolContext, tool_name: str) -> dict[str, Any]:
    try:
        by_name = _fetch_dv(
            _digivault_service_base(),
            _digi_bearer_from_context(ctx),
            ctx.request_id,
        )
        t = by_name.get(tool_name)
        if t:
            return t
    except _ORCHESTRATOR_CLIENT_ERRORS as exc:
        logger.warning("digivault manifest fetch failed for %s: %s", tool_name, exc)
    if tool_name == "digivault_get_note":
        return {
            "type": "function",
            "function": {
                "name": "digivault_get_note",
                "description": (
                    "Load one or more vault notes in full, instead of reasoning from "
                    "excerpts. For a single note, pass vault_path copied from a prior "
                    "digivault_search_notes hit's doc_id field (that hit's JSON has no "
                    "field literally named vault_path). For several notes at once, pass "
                    "vault_paths (array) instead — prefer that over repeated single-path "
                    "calls. Do not use a digisearch hit's doc_id here — digisearch's "
                    "doc_id is a repo path, not a vault path, and this tool will refuse or "
                    "404 on it. D1-only: requires DIGIVAULT_URL, POST /v1/orchestrator_tools, "
                    "and a D1-backed digivault deployment."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "vault_path": {
                            "type": "string",
                            "description": (
                                "Copy this from a digivault_search_notes hit's doc_id "
                                "field — not from a digisearch hit's doc_id, which is a "
                                "repo path this tool cannot load. Use vault_paths instead "
                                "when loading more than one note."
                            ),
                        },
                        "vault_paths": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Load several notes in one call (same path rules as "
                                "vault_path). Prefer over repeated single-path calls. "
                                "Provide exactly one of vault_path or vault_paths."
                            ),
                        },
                        "path_prefix": {"type": "string"},
                    },
                    # Match the live digivault manifest: path_prefix required;
                    # vault_path vs vault_paths is enforced by the handler.
                    "required": ["path_prefix"],
                },
            },
        }
    return {
        "type": "function",
        "function": {
            "name": "digivault_search_notes",
            "description": (
                "Full-text search over the digithings architecture vault. "
                "Requires DIGIVAULT_URL and POST /v1/orchestrator_tools."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    }


# Literal error strings digivault's own orchestrator_invoke handler returns when a
# request reaches it with no path_prefix (digivault/src/digivault/server.py's
# "path_prefix is required when the D1 backend is configured" / "path_prefix is
# required for digivault_get_note" branches). The "no tenant corpus" substitution
# below must key on *this* — the actual error digivault returned — not on
# `context.vault_path_prefix is None`: a digivault outage, an expired D1 token, or a
# malformed D1_DATABASE_MAP can also produce ok=False while vault_path_prefix happens
# to be None, and those must surface their own error, not get mislabeled as a session
# configuration gap (#2295 review).
_DIGIVAULT_SEARCH_NO_PREFIX_ERROR = "path_prefix is required when the D1 backend is configured"
_DIGIVAULT_GET_NOTE_NO_PREFIX_ERROR = "path_prefix is required for digivault_get_note"


def _handle_digivault_search(args: dict[str, Any], context: ToolContext) -> str | dict[str, Any]:
    q = args.get("query", "")
    if not q or not str(q).strip():
        return "No search query provided."
    args_eff = dict(args)
    # Security (#2265): overwrite unconditionally, never default-if-missing — a
    # model-supplied path_prefix must not reach another tenant's corpus. Mirrors
    # _handle_digivault_get_note's mandatory fix; extended to match rather than
    # left on the old conditional-default (see #2265 and the digivault_get_note
    # commit on this branch, #2240).
    args_eff["path_prefix"] = context.vault_path_prefix
    try:
        inv = _invoke_dv(
            _digivault_service_base(),
            "digivault_search_notes",
            args_eff,
            bearer_token=_digi_bearer_from_context(context),
            request_id=context.request_id,
        )
    except _ORCHESTRATOR_CLIENT_ERRORS as e:
        return f"digivault orchestrator invoke failed: {e}"
    if not inv.get("ok"):
        if inv.get("error") == _DIGIVAULT_SEARCH_NO_PREFIX_ERROR:
            # Important 2 (#2240 final-branch review): digivault's own
            # "path_prefix is required" sentence is written for a direct API
            # caller that can just add the argument. The model can't act on it:
            # it already supplied path_prefix (the schema marks it required),
            # and this handler discards whatever it sent and substitutes None
            # unconditionally (the #2265 overwrite, above) because no tenant
            # corpus is mapped for this session. Relaying the raw sentence costs
            # a full completions/round trip per retry — measured at 5
            # completions / 4 digivault round-trips to produce nothing before
            # this fix — because the model keeps retrying something outside its
            # control. Mirrors _handle_digivault_get_note's equivalent branch.
            #
            # Keyed on digivault's actual returned error (#2295 review), not on
            # `context.vault_path_prefix is None`: that session-state check would
            # also catch a digivault outage, an expired D1 token, or a malformed
            # D1_DATABASE_MAP that happens to fire while vault_path_prefix is
            # None, mislabeling a real infra failure as a session config gap.
            return json.dumps(
                {
                    "ok": False,
                    "error": (
                        "No tenant corpus is configured for this chat session, so "
                        "digivault_search_notes cannot search the vault here — "
                        "this is a session configuration gap, not something you "
                        "can fix by resupplying path_prefix. Do not retry this "
                        "tool; answer from what digisearch already returned, or "
                        "tell the user vault search is unavailable."
                    ),
                }
            )
        return json.dumps(inv)
    data = inv.get("data")
    if not isinstance(data, dict):
        # A completed (ok=True) search with no usable payload is a zero-hit search,
        # not a "never searched" — return a dict (not a bare string) so execute_search
        # (research.py) can attach hit_count=0/query for the activity trace. The
        # "content" string is unchanged, so the model still reads the same text.
        return {"content": "No results found.", "results": [], "rag_sources": []}
    hits = data.get("hits", [])
    if not hits:
        return {
            "content": "No matching documentation was found in the digivault for that query.",
            "results": [],
            "rag_sources": [],
        }
    results = [
        {
            "content": h.get("body_markdown"),
            "score": h.get("rank"),
            "doc_id": h.get("vault_path"),
            "metadata": {"title": h.get("title"), "tags": h.get("tags")},
        }
        for h in hits
        if isinstance(h, dict)
    ]
    payload_for_llm = _search_payload_for_llm(results, len(results))
    _mark_truncated_excerpts(payload_for_llm, results, load_hint="that row's doc_id")
    return {
        "content": json.dumps(payload_for_llm),
        "results": results,
        "rag_sources": rag_sources_from_results(results),
    }


def _note_to_result_and_payload(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Convert one digivault note dict into (result-for-citations, payload-for-llm).

    Shared by the single-path and batch branches of _handle_digivault_get_note so the
    two response shapes stay in lockstep rather than drifting into two hand-maintained
    copies of the same field list.
    """
    result = {
        "content": data.get("body_markdown", ""),
        "score": None,
        "doc_id": data.get("vault_path"),
        "metadata": {"title": data.get("title"), "tags": data.get("tags")},
    }
    payload_for_llm = {
        "vault_path": data.get("vault_path"),
        "title": data.get("title"),
        "summary": data.get("summary"),
        "tags": data.get("tags"),
        "body_markdown": data.get("body_markdown"),
    }
    # Segment identity (#2306). Most of this corpus is not whole documents: 1190 of 1279
    # digithings notes and 300 of 328 OCC notes are one page or section of a larger
    # source, so "load the whole note" routinely hands the model one page of forty with
    # nothing saying so. That is the same wrong-answer shape as the excerpt bug one layer
    # down — a table continuing onto the next page reads as a complete table — and it is
    # also what makes the tool description's "search for the neighbouring page" rule
    # actionable. Emitted only when present, so a whole-document note is unchanged.
    for key in ("parent_doc", "segment_index", "segment_label"):
        value = data.get(key)
        if value is not None:
            payload_for_llm[key] = value
    return result, payload_for_llm


def _handle_digivault_get_note(args: dict[str, Any], context: ToolContext) -> str | dict[str, Any]:
    """Load one or more vault notes in full (the locate-then-load follow-up to
    digivault_search_notes, which only returns a short excerpt per hit).

    Batch support (#2306 follow-up): vault_paths (plural) fetches several notes in one
    call — one activity row in digichat instead of N, since the UI groups repeated tool
    calls by (tool, query) and every vault_path is a different query. vault_path
    (singular) keeps its original request/response shape completely unchanged; only a
    caller that sends vault_paths gets the new {"notes": [...], "errors": {...}}
    payload shape, so nothing here can regress an existing single-path caller.
    """
    vault_paths_arg = args.get("vault_paths")
    is_batch = isinstance(vault_paths_arg, list) and len(vault_paths_arg) > 0
    # A blank/whitespace vault_path is treated as absent everywhere else in this
    # handler (see the single-path branch below), so it must not count as "also
    # supplied" here either — only a real second selector triggers the rejection.
    vault_path_also_supplied = bool(str(args.get("vault_path") or "").strip())
    if is_batch and vault_path_also_supplied:
        # CodeRabbit finding (#2327 review): this schema's fallback description
        # says "Provide exactly one of vault_path or vault_paths" and a comment near
        # the schema claimed "vault_path vs vault_paths is enforced by the handler"
        # — but nothing here actually enforced it; a model supplying both silently
        # got the batch path with vault_path discarded, no error. Supplying both is
        # far more likely a mistake (which one did the model mean?) than a case
        # worth silently resolving, so reject it explicitly instead.
        return json.dumps(
            {
                "ok": False,
                "error": ("Provide exactly one of vault_path or vault_paths, not both."),
            }
        )
    if is_batch:
        # Mirror digivault's server-side cap so an oversized batch fails before the
        # HTTP round-trip. digillm also caps the whole tool message
        # (DIGI_TOOL_MESSAGE_MAX_CHARS, default 12000) for the LLM — that limit
        # applies to the serialized batch as one tool result, not per note.
        if len(vault_paths_arg) > 20:
            return json.dumps(
                {
                    "ok": False,
                    "error": (
                        f"vault_paths exceeds maximum batch size of 20 (got {len(vault_paths_arg)})"
                    ),
                }
            )
    else:
        vault_path = args.get("vault_path", "")
        if not vault_path or not str(vault_path).strip():
            return "vault_path is required."
    args_eff = dict(args)
    # Security: overwrite unconditionally, never default-if-missing. A model that
    # supplies its own path_prefix must not be able to select another tenant's corpus.
    # If context has no prefix (unmapped tenant slug), this passes None through — we do
    # not fall back to an unscoped read; digivault's own handler refuses that with
    # ok=False rather than serving the whole vault. Applies identically to every path
    # in a batch call — digivault's own handler loops the same per-path enforcement,
    # not just the first path.
    args_eff["path_prefix"] = context.vault_path_prefix
    try:
        inv = _invoke_dv(
            _digivault_service_base(),
            "digivault_get_note",
            args_eff,
            bearer_token=_digi_bearer_from_context(context),
            request_id=context.request_id,
        )
    except _ORCHESTRATOR_CLIENT_ERRORS as e:
        return f"digivault orchestrator invoke failed: {e}"
    if not inv.get("ok"):
        if inv.get("error") == _DIGIVAULT_GET_NOTE_NO_PREFIX_ERROR:
            # digivault's own "path_prefix is required" sentence is written for a
            # direct API caller that can just add the argument. The model can't act
            # on it: it already supplied path_prefix (the schema marks it required),
            # and this handler discards whatever it sent and substitutes None
            # unconditionally (the #2265 overwrite, above) because no tenant corpus
            # is mapped for this session. Telling it to do something outside its
            # control just burns retries against the 4-round tool budget — give it
            # an instruction it can actually follow instead.
            #
            # Keyed on digivault's actual returned error (#2295 review), not on
            # `context.vault_path_prefix is None`: that session-state check would
            # also catch a digivault outage, an expired D1 token, or a malformed
            # D1_DATABASE_MAP that happens to fire while vault_path_prefix is
            # None, mislabeling a real infra failure as a session config gap.
            return json.dumps(
                {
                    "ok": False,
                    "error": (
                        "No tenant corpus is configured for this chat session, so "
                        "digivault_get_note cannot look up a vault note here — this "
                        "is a session configuration gap, not something you can fix "
                        "by resupplying path_prefix. Do not retry this tool; answer "
                        "from what digisearch or digivault_search_notes already "
                        "returned, or tell the user vault lookup is unavailable."
                    ),
                }
            )
        return json.dumps(inv)
    data = inv.get("data")
    if not isinstance(data, dict):
        return "Note not found."

    if not is_batch:
        result, payload_for_llm = _note_to_result_and_payload(data)
        return {
            "content": json.dumps(payload_for_llm),
            "results": [result],
            # Full note body for digichat DocumentPane (#3419); locate paths stay snippet-only.
            "rag_sources": rag_sources_from_results([result], include_body=True),
        }

    # Batch: digivault's response shape here is {"notes": [...], "errors": {...}} —
    # see the server-side TOOL_VAULT_GET_NOTE branch. A partial failure (some paths
    # found, some not) still has ok=True at the digivault layer, since it's the
    # model's own input at fault for the failed paths, not an infra error — so a
    # non-empty errors dict alone must not be mistaken for the whole call failing.
    notes = data.get("notes")
    errors = data.get("errors") or {}
    if not isinstance(notes, list):
        return "Note not found."
    results: list[dict[str, Any]] = []
    payloads: list[dict[str, Any]] = []
    for note_data in notes:
        if not isinstance(note_data, dict):
            continue
        result, payload_for_llm = _note_to_result_and_payload(note_data)
        results.append(result)
        payloads.append(payload_for_llm)
    if not results and not errors:
        return "Note not found."
    content: dict[str, Any] = {"notes": payloads}
    if errors:
        content["errors"] = errors
    return {
        "content": json.dumps(content),
        "results": results,
        # Full note body for digichat DocumentPane (#3419); locate paths stay snippet-only.
        "rag_sources": rag_sources_from_results(results, include_body=True),
    }
