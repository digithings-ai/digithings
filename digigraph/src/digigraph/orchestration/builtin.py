"""Register built-in orchestrator tools and skills. Import this module to populate the registry."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

from digigraph.agents.analysis.runner import run_analysis_agent
from digigraph.agents.analysis.schema import ANALYSIS_AGENT_TOOL
from digigraph.agents.data_engineer.runner import run_data_engineer_agent
from digigraph.agents.data_engineer.schema import DATA_ENGINEER_AGENT_TOOL
from digigraph.agents.data_manipulation.runner import run_data_manipulation_agent
from digigraph.agents.data_manipulation.schema import DATA_MANIPULATION_AGENT_TOOL
from digigraph.agents.data_prep.runner import run_data_prep_agent
from digigraph.agents.data_prep.schema import DATA_PREP_AGENT_TOOL
from digigraph.agents.visualization.runner import run_visualization_agent
from digigraph.agents.visualization.schema import VISUALIZATION_AGENT_TOOL
from digigraph.orchestration.plugins import load_entrypoint_tools
from digigraph.orchestration.registry import ToolContext, register_skill, register_tool
from digigraph.policy import code_execution_allowed, federated_hub_enabled
from digigraph.project_config import DigiProjectConfig
from digigraph.trace_events import rag_sources_from_results
from digigraph.vertical_orchestrator import (
    fetch_digiquant_tool_dicts,
    fetch_digisearch_tool_dicts,
    fetch_digivault_tool_dicts,
    invoke_digiquant_tool,
    invoke_digisearch_tool,
    invoke_digivault_tool,
)

logger = logging.getLogger(__name__)

DELEGATE_TAGS = {"delegate", "parallel_safe"}

_ORCHESTRATOR_CLIENT_ERRORS = (
    httpx.HTTPStatusError,
    httpx.RequestError,
    json.JSONDecodeError,
    OSError,
    TypeError,
    ValueError,
)

_STORE_ERRORS = (OSError, TypeError, ValueError, RuntimeError)


def _merged_digisearch_filters(
    context: ToolContext, args: dict[str, Any]
) -> list[dict[str, Any]] | None:
    """Merge workflow state research_filters / evidence_tier_preference with per-call tool args."""
    parts: list[dict[str, Any]] = []
    st = context.state or {}
    wf_filters = st.get("research_filters")
    if isinstance(wf_filters, list):
        for x in wf_filters:
            if isinstance(x, dict):
                parts.append(x)
    arg_filters = args.get("filters")
    if isinstance(arg_filters, list):
        for x in arg_filters:
            if isinstance(x, dict):
                parts.append(x)
    tiers = st.get("evidence_tier_preference")
    if isinstance(tiers, list) and tiers:
        parts.append({"field": "evidence_tier", "op": "in", "value": list(tiers)})
    return parts or None


# Max size of search result payload sent to the LLM (avoids context explosion).
_LLM_SEARCH_PREVIEW_ROWS = 5
_LLM_SEARCH_PREVIEW_CHARS = 300
# Per-value budget for non-content fields, and caps on structured values. These bound a
# metadata object without collapsing it to a string — see _preview_field (#2306).
_LLM_PREVIEW_FIELD_CHARS = 200
_LLM_PREVIEW_LIST_ITEMS = 20
_LLM_PREVIEW_DICT_KEYS = 24


def _preview_field(value: Any) -> Any:
    """Shrink one non-content field for the LLM preview without destroying its shape.

    The previous implementation was ``str(value)`` clipped to _LLM_SEARCH_PREVIEW_CHARS,
    which had two failure modes for the dicts that actually matter here (#2306):

    * A dict became a Python repr — single-quoted, not JSON — so a model told to read
      ``metadata.vault_path`` received an opaque string to parse rather than a field it
      could address.
    * The clip was then applied to that repr. Realistic digisearch metadata serializes to
      just over the budget with ``vault_path`` last, so the one key the model was told to
      read was the first thing cut, and it would pass a half-path to digivault_get_note
      and get a 404 — a failure that looks like a bad path, not a truncated payload.

    Clipping long *values* while keeping every key addressable fixes both: the object
    stays JSON, and short-but-critical keys survive regardless of what else is present.
    """
    if isinstance(value, dict):
        return {
            str(k): _preview_field(v)
            for k, v in list(value.items())[:_LLM_PREVIEW_DICT_KEYS]
            if v is not None
        }
    if isinstance(value, list):
        return [_preview_field(v) for v in value[:_LLM_PREVIEW_LIST_ITEMS]]
    if isinstance(value, bool | int | float):
        return value
    text = value if isinstance(value, str) else str(value)
    if len(text) > _LLM_PREVIEW_FIELD_CHARS:
        return text[:_LLM_PREVIEW_FIELD_CHARS] + "..."
    return text


def _search_payload_for_llm(
    results: list[dict[str, Any]],
    total: int,
    *,
    dataset_ref: str | None = None,
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a small payload for the tool message so we do not send full results to the LLM."""
    payload: dict[str, Any] = {"total": total}
    if dataset_ref:
        payload["dataset_ref"] = dataset_ref
        payload["note"] = (
            "Full data is stored at dataset_ref; use it with visualization_agent, analysis_agent, data_prep_agent, etc."
        )
    if summary and isinstance(summary, dict):
        payload["summary"] = summary
    if results:
        preview: list[dict[str, Any]] = []
        for r in results[:_LLM_SEARCH_PREVIEW_ROWS]:
            if not isinstance(r, dict):
                continue
            row: dict[str, Any] = {}
            for k, v in r.items():
                if k == "content" and isinstance(v, str):
                    row[k] = v[:_LLM_SEARCH_PREVIEW_CHARS] + (
                        "..." if len(v) > _LLM_SEARCH_PREVIEW_CHARS else ""
                    )
                elif k != "content" and v is not None:
                    row[k] = _preview_field(v)
            preview.append(row)
        payload["preview"] = preview
    return payload


def _digisearch_available(_context: ToolContext) -> bool:
    url = os.environ.get("DIGISEARCH_URL", "")
    return bool(url and url.strip())


def _digivault_available(_context: ToolContext) -> bool:
    url = os.environ.get("DIGIVAULT_URL", "").strip()
    if url:
        return True
    try:
        cfg_url = DigiProjectConfig.load().get_digivault_url()
        return bool(str(cfg_url).strip())
    except Exception as exc:
        logger.debug("digivault availability check via project config failed: %s", exc)
        return False


def _digi_bearer_from_context(context: ToolContext) -> str | None:
    st = context.state
    if isinstance(st, dict):
        raw = st.get("digi_bearer")
        return str(raw).strip() if raw else None
    return None


def _digisearch_service_base() -> str:
    return DigiProjectConfig.load().get_digisearch_url()


def _digiquant_service_base() -> str:
    return DigiProjectConfig.load().get_digiquant_url()


def _digivault_service_base() -> str:
    return DigiProjectConfig.load().get_digivault_url()


def _schema_from_digisearch_manifest(ctx: ToolContext, tool_name: str) -> dict[str, Any]:
    try:
        by_name = fetch_digisearch_tool_dicts(
            _digisearch_service_base(),
            ctx.index_config if isinstance(ctx.index_config, dict) else {},
            _digi_bearer_from_context(ctx),
            ctx.request_id,
        )
        t = by_name.get(tool_name)
        if t:
            return t
    except _ORCHESTRATOR_CLIENT_ERRORS as exc:
        logger.warning("digisearch manifest fetch failed for %s: %s", tool_name, exc)
    if tool_name == "digisearch_fetch_all":
        return {
            "type": "function",
            "function": {
                "name": "digisearch_fetch_all",
                "description": "Fetch all matching documents (pagination). Requires reachable digisearch orchestrator API.",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
        }
    return {
        "type": "function",
        "function": {
            "name": "digisearch",
            "description": "Search documents via digisearch. Requires DIGISEARCH_URL and POST /v1/orchestrator_tools.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    }


def _schema_from_digivault_manifest(ctx: ToolContext, tool_name: str) -> dict[str, Any]:
    try:
        by_name = fetch_digivault_tool_dicts(
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
        inv = invoke_digivault_tool(
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


def _mark_truncated_excerpts(
    payload: dict[str, Any],
    results: list[dict[str, Any]],
    *,
    load_hint: str,
) -> None:
    """Label clipped excerpts as data the model can branch on (#2306).

    _search_payload_for_llm clips each body to _LLM_SEARCH_PREVIEW_CHARS and appends a
    bare "...", which is indistinguishable from ordinary prose punctuation. In production
    the model received exactly the right note, clipped immediately before the first row
    of the table it was asked about, judged the excerpt sufficient, never called
    digivault_get_note, and answered wrong — then closed with a completeness claim ("no
    other X was found") that its own truncated input could not support.

    Nothing mechanical prevented the second round: the tool was registered, allowed, and
    described, doc_id was in the payload, and run_tools permits four rounds. The missing
    piece was that "is this excerpt enough" is unanswerable for a model that cannot tell
    an excerpt from a whole note. So state which rows are incomplete, and name the exact
    follow-up call rather than leaving it to judgment.

    Applied to BOTH search sinks on purpose. Marking only digivault rows would make the
    flag's absence on a digisearch row read as "this one is complete" — the same wrong
    inference #2306 is about, reintroduced on the sink that returns most hits. digisearch
    rows carry their own upstream ``content_truncated`` (its 500-char preview cap, see
    digisearch/core/standard_hits.py) before digigraph clips again to 300, so either
    signal marks the row.

    *load_hint* names the field this sink puts the loadable path in — they differ, and
    naming the wrong one sends the model to a 404.

    Only rows that actually reached the preview are marked — `results` may be longer than
    _LLM_SEARCH_PREVIEW_ROWS, and claiming a count the model cannot see would be its own
    inaccuracy.
    """
    preview = payload.get("preview") or []
    # Positional pairing mirrors how _search_payload_for_llm builds preview: in order,
    # over dict rows only. Keying on doc_id instead would silently skip digisearch rows,
    # whose doc_id is a repo path shared across chunks of the same document.
    sources = [r for r in results if isinstance(r, dict)][: len(preview)]
    marked = 0
    for row, src in zip(preview, sources, strict=False):
        body = src.get("content")
        clipped_here = isinstance(body, str) and len(body) > _LLM_SEARCH_PREVIEW_CHARS
        if clipped_here or src.get("content_truncated") is True:
            row["truncated"] = True
            marked += 1
    if not marked:
        return
    payload["excerpts_truncated"] = True
    payload["next_step"] = (
        f"{marked} of the excerpts above are cut off and are NOT the whole document. "
        "Before answering anything that depends on content past the cut — a table, a "
        "list, a procedure, a count, or any 'every/all' question — call "
        f"digivault_get_note with {load_hint} and answer from the full note it returns. "
        "Never say something is absent from a document whose excerpt is truncated; you "
        "have not seen the rest of it."
    )


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
        inv = invoke_digivault_tool(
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
            "rag_sources": rag_sources_from_results([result]),
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
        "rag_sources": rag_sources_from_results(results),
    }


def _handle_digisearch(args: dict[str, Any], context: ToolContext) -> str | dict[str, Any]:
    q = args.get("query", "")
    if not q or not str(q).strip():
        return "No search query provided."
    args_eff = dict(args)
    # Security (#2265): overwrite unconditionally, never default-if-missing — a
    # model-supplied index_name must not reach another tenant's vector corpus.
    # index_name is not declared on the digisearch schema, but that never stopped
    # a model from supplying one anyway: OrchestratorInvokeRequest.arguments (on
    # the digisearch side) is dict[str, Any], never schema-validated. Mirrors the
    # vault handlers' mandatory fix (_handle_digivault_search /
    # _handle_digivault_get_note) — the digisearch index is the other half of
    # the same tenant boundary #2265 closed for digivault's path_prefix.
    args_eff["index_name"] = context.index_name
    merged = _merged_digisearch_filters(context, args_eff)
    if merged:
        args_eff["filters"] = merged
    try:
        inv = invoke_digisearch_tool(
            _digisearch_service_base(),
            "digisearch",
            args_eff,
            default_index_name=context.index_name,
            bearer_token=_digi_bearer_from_context(context),
            request_id=context.request_id,
        )
    except _ORCHESTRATOR_CLIENT_ERRORS as e:
        return f"digisearch orchestrator invoke failed: {e}"
    if not inv.get("ok"):
        return json.dumps(inv)
    data = inv.get("data")
    if not isinstance(data, dict):
        # A completed (ok=True) search with no usable payload is a zero-hit search,
        # not a "never searched" — return a dict (not a bare string) so execute_search
        # (research.py) can attach hit_count=0/query for the activity trace. The
        # "content" string is unchanged, so the model still reads the same text.
        return {"content": "No results found.", "results": [], "rag_sources": []}
    results = data.get("results", [])
    summary = data.get("summary")
    total = data.get("total", len(results))
    dataset_ref: str | None = None
    stored_profile: dict[str, Any] | None = None
    if context.has_run_data_dir and results:
        try:
            from digigraph.run_storage import write_search_results

            dataset_ref = write_search_results(context.session_id, results)
            cols = list(results[0].keys()) if results and isinstance(results[0], dict) else []
            stored_profile = {
                "ref": dataset_ref,
                "profile": {"row_count": len(results), "columns": cols},
            }
        except _STORE_ERRORS as exc:
            logger.warning("write_search_results failed: %s", exc)
    if not results and not summary:
        # Real zero-hit case: the search ran, dig(i)search answered, nothing matched.
        # Dict (not a bare string) so execute_search can attach hit_count=0/query.
        return {"content": "No results found.", "results": [], "rag_sources": []}
    payload_for_llm = _search_payload_for_llm(
        results, total, dataset_ref=dataset_ref, summary=summary
    )
    # Vault-sourced digisearch chunks are loadable, but via metadata.vault_path -- this
    # sink's doc_id is a repo path digivault_get_note cannot resolve (#2306).
    _mark_truncated_excerpts(
        payload_for_llm,
        results,
        load_hint="that row's metadata.vault_path (only rows that carry one are loadable)",
    )
    out: dict[str, Any] = {
        "content": json.dumps(payload_for_llm),
        "results": results,
        "summary": summary,
        "rag_sources": rag_sources_from_results(results),
    }
    if dataset_ref:
        out["dataset_ref"] = dataset_ref
    if stored_profile:
        out["stored_dataset_profile"] = stored_profile
    return out


def _handle_digisearch_fetch_all(
    args: dict[str, Any], context: ToolContext
) -> str | dict[str, Any]:
    q = args.get("query", "")
    if not q or not str(q).strip():
        return "No search query provided."
    args_eff = dict(args)
    # Security (#2265): same unconditional overwrite as _handle_digisearch. Not
    # reachable from the production allowlist today (digisearch_fetch_all is not in
    # infra/digichat-release/config/digiproject.yaml's allowed_tools), but leaving one
    # half of the tenant boundary on the old default-if-missing pattern is how it comes
    # back the moment this tool is allowlisted.
    args_eff["index_name"] = context.index_name
    merged = _merged_digisearch_filters(context, args_eff)
    if merged:
        args_eff["filters"] = merged
    # Clamp max_results to the configured limit.
    limits = DigiProjectConfig.load().get_limits()
    cap = limits.max_rows_per_fetch
    caller_max = args_eff.get("max_results")
    if caller_max is None:
        args_eff["max_results"] = cap
    elif isinstance(caller_max, int) and caller_max > cap:
        args_eff["max_results"] = cap
    try:
        inv = invoke_digisearch_tool(
            _digisearch_service_base(),
            "digisearch_fetch_all",
            args_eff,
            default_index_name=context.index_name,
            bearer_token=_digi_bearer_from_context(context),
            request_id=context.request_id,
        )
    except _ORCHESTRATOR_CLIENT_ERRORS as e:
        return f"digisearch orchestrator invoke failed: {e}"
    if not inv.get("ok"):
        return json.dumps(inv)
    data = inv.get("data")
    if not isinstance(data, dict):
        return "No results found."
    results = data.get("results", [])
    total = data.get("total", len(results))
    dataset_ref = None
    stored_profile = None
    if context.has_run_data_dir and results:
        try:
            from digigraph.run_storage import write_search_results

            dataset_ref = write_search_results(context.session_id, results)
            cols = list(results[0].keys()) if results and isinstance(results[0], dict) else []
            stored_profile = {
                "ref": dataset_ref,
                "profile": {"row_count": len(results), "columns": cols},
            }
        except _STORE_ERRORS as exc:
            logger.warning("write_search_results failed: %s", exc)
    payload_for_llm = _search_payload_for_llm(results, total, dataset_ref=dataset_ref)
    out = {
        "content": json.dumps(payload_for_llm),
        "results": results,
        "total": total,
        "rag_sources": rag_sources_from_results(results),
    }
    if dataset_ref:
        out["dataset_ref"] = dataset_ref
    if stored_profile:
        out["stored_dataset_profile"] = stored_profile
    return out


def _handle_visualization(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    result = run_visualization_agent(
        dataset_ref=args.get("dataset_ref", ""),
        task=args.get("task", ""),
        session_id=context.session_id,
        options=args.get("options"),
    )
    return {"content": result}


def _handle_analysis(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    result = run_analysis_agent(
        dataset_ref=args.get("dataset_ref", ""),
        task=args.get("task", ""),
        session_id=context.session_id,
        options=args.get("options"),
    )
    return {"content": result}


def _handle_data_prep(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    result = run_data_prep_agent(
        dataset_ref=args.get("dataset_ref", ""),
        task=args.get("task", ""),
        session_id=context.session_id,
        options=args.get("options"),
    )
    return {"content": result}


def _handle_data_manipulation(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    result = run_data_manipulation_agent(
        dataset_ref=args.get("dataset_ref", ""),
        task=args.get("task", ""),
        session_id=context.session_id,
        second_dataset_ref=args.get("second_dataset_ref"),
        options=args.get("options"),
    )
    return {"content": result}


def _handle_data_engineer(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    result = run_data_engineer_agent(
        dataset_ref=args.get("dataset_ref", ""),
        task=args.get("task", ""),
        session_id=context.session_id,
        additional_dataset_refs=args.get("additional_dataset_refs"),
        options=args.get("options"),
    )
    return {"content": result}


DIGISTORE_LIST_TOOL = {
    "type": "function",
    "function": {
        "name": "digistore_list",
        "description": "List datasets stored in this session (read-only). Returns name and row_count for each. Use to discover available dataset_refs before calling visualization_agent, analysis_agent, or data_manipulation_agent.",
        "parameters": {
            "type": "object",
            "properties": {
                "include_row_count": {
                    "type": "boolean",
                    "description": "Include row count per dataset (default true).",
                },
            },
        },
    },
}

DIGISTORE_PROFILE_TOOL = {
    "type": "function",
    "function": {
        "name": "digistore_profile",
        "description": "Get schema and sample rows for a stored dataset (read-only). Use to inspect columns and sample data before visualization or manipulation.",
        "parameters": {
            "type": "object",
            "properties": {
                "dataset_ref": {
                    "type": "string",
                    "description": "Dataset name or ref (e.g. search_1) from digistore_list or a previous search result.",
                },
                "sample_size": {
                    "type": "integer",
                    "description": "Number of sample rows to return (default 5).",
                },
            },
            "required": ["dataset_ref"],
        },
    },
}


def _handle_digistore_list(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    from digigraph.digistore import digistore_list

    include_row_count = args.get("include_row_count", True)
    datasets = digistore_list(context.session_id, include_row_count=include_row_count)
    return {"content": json.dumps({"datasets": datasets})}


def _handle_digistore_profile(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    from digigraph.digistore import digistore_profile

    ref = args.get("dataset_ref")
    if not ref or not str(ref).strip():
        return {"content": json.dumps({"error": "dataset_ref is required."})}
    sample_size = args.get("sample_size", 5)
    try:
        profile = digistore_profile(context.session_id, str(ref), sample_size=sample_size)
        return {"content": json.dumps(profile)}
    except ValueError as e:
        return {"content": json.dumps({"error": str(e)})}


TODO_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "todo",
        "description": "Emit a list of intended tasks or steps for this request. Use to make your plan explicit before executing tools (e.g. 'search all from X', 'chart by date', 'export CSV'). The list is recorded for context; execution continues with the normal tool loop.",
        "parameters": {
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ordered list of task descriptions.",
                }
            },
            "required": ["tasks"],
        },
    },
}


def _handle_todo(args: dict[str, Any], context: ToolContext) -> str | dict[str, Any]:
    """Record the LLM's intended task list; return a short confirmation."""
    tasks = args.get("tasks") or []
    if not isinstance(tasks, list):
        tasks = [str(tasks)]
    tasks = [str(t) for t in tasks if t]
    if context.state is not None:
        context.state["todo_plan"] = tasks
    n = len(tasks)
    return {"content": f"Recorded {n} task(s). Proceed with your tools."}


CREATE_PLAN_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "create_plan",
        "description": "Submit a structured execution plan: ordered steps with agent names, arguments, and optional depends_on. Use {{step_id.field}} in args to reference prior step outputs (e.g. {{1.dataset_ref}}). The executor will run steps in dependency order and in parallel when independent.",
        "parameters": {
            "type": "object",
            "properties": {
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "Step id (e.g. '1', '2')."},
                            "agent": {
                                "type": "string",
                                "description": "Tool/agent name (e.g. digisearch_fetch_all, visualization_agent).",
                            },
                            "args": {
                                "type": "object",
                                "description": "Arguments for the agent. Use {{step_id.field}} for placeholders.",
                            },
                            "depends_on": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Step ids that must complete before this step.",
                            },
                        },
                        "required": ["id", "agent"],
                    },
                    "description": "Ordered steps to execute.",
                }
            },
            "required": ["steps"],
        },
    },
}


def _handle_create_plan(args: dict[str, Any], context: ToolContext) -> str | dict[str, Any]:
    """Store the structured plan in state for the executor; return confirmation and plan."""
    steps = args.get("steps") or []
    if not isinstance(steps, list):
        return {"content": "steps must be a list."}
    normalized = []
    for s in steps:
        if not isinstance(s, dict):
            continue
        step_id = s.get("id")
        agent = s.get("agent")
        if not step_id or not agent:
            continue
        normalized.append(
            {
                "id": str(step_id),
                "agent": str(agent),
                "args": s.get("args") if isinstance(s.get("args"), dict) else {},
                "depends_on": [str(d) for d in s.get("depends_on") or []]
                if isinstance(s.get("depends_on"), list)
                else [],
            }
        )
    if context.state is not None:
        context.state["plan"] = normalized
    return {
        "content": f"Plan recorded ({len(normalized)} steps). Executor will run when planning_mode is enabled.",
        "plan": normalized,
    }


def _schema_digisearch_research_delegate(ctx: ToolContext) -> dict[str, Any]:
    return _schema_from_digisearch_manifest(ctx, "digisearch_research_delegate")


def _schema_digiquant_pipeline_delegate(ctx: ToolContext) -> dict[str, Any]:
    try:
        by_name = fetch_digiquant_tool_dicts(
            _digiquant_service_base(),
            _digi_bearer_from_context(ctx),
            ctx.request_id,
        )
        t = by_name.get("digiquant_pipeline_delegate") or by_name.get("digiquant_run_pipeline")
        if t:
            return t
    except _ORCHESTRATOR_CLIENT_ERRORS as exc:
        logger.warning("digiquant manifest fetch failed: %s", exc)
    return {
        "type": "function",
        "function": {
            "name": "digiquant_pipeline_delegate",
            "description": "Run digiquant pipeline. Requires DIGIQUANT_URL and POST /v1/orchestrator_tools.",
            "parameters": {
                "type": "object",
                "properties": {
                    "strategy_name": {"type": "string"},
                    "symbols": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["strategy_name", "symbols"],
            },
        },
    }


def _handle_digisearch_research_delegate(
    args: dict[str, Any], context: ToolContext
) -> str | dict[str, Any]:
    msg = str(args.get("user_message") or "").strip()
    if not msg:
        return {"content": "user_message is required."}
    args_eff = dict(args)
    args_eff["user_message"] = msg
    # Security (#2265): same unconditional overwrite as _handle_digisearch. Gated behind
    # federated_hub_enabled() and not in any production allowlist today, but the tenant
    # boundary should not have a third shape.
    args_eff["index_name"] = context.index_name
    merged = _merged_digisearch_filters(context, args_eff)
    if merged:
        args_eff["filters"] = merged
    args_eff["session_id"] = context.session_id
    try:
        inv = invoke_digisearch_tool(
            _digisearch_service_base(),
            "digisearch_research_delegate",
            args_eff,
            default_index_name=context.index_name,
            bearer_token=_digi_bearer_from_context(context),
            request_id=context.request_id,
        )
    except _ORCHESTRATOR_CLIENT_ERRORS as e:
        return {"content": f"digisearch orchestrator invoke failed: {e}"}
    if not inv.get("ok"):
        return json.dumps(inv)
    data = inv.get("data")
    if not isinstance(data, dict):
        return json.dumps(inv)
    fc = str(data.get("formatted_context") or "")
    payload_preview = (
        fc if fc else json.dumps({"total": data.get("total"), "note": "no formatted_context"})
    )
    return {
        "content": payload_preview,
        "rag_sources": data.get("rag_sources") or [],
        "results": data.get("results"),
        "trace": data.get("trace"),
        "service": "digisearch",
    }


def _handle_digiquant_pipeline_delegate(
    args: dict[str, Any], context: ToolContext
) -> str | dict[str, Any]:
    sym_raw = args.get("symbols")
    if isinstance(sym_raw, str):
        symbols = [sym_raw.strip().upper()] if sym_raw.strip() else []
    elif isinstance(sym_raw, list):
        symbols = [str(s).strip().upper() for s in sym_raw if s is not None and str(s).strip()]
    else:
        symbols = []
    strategy = str(args.get("strategy_name") or "").strip()
    if not strategy or not symbols:
        return {"content": json.dumps({"error": "strategy_name and non-empty symbols required"})}
    payload: dict[str, Any] = {
        "strategy_name": strategy,
        "symbols": symbols,
        "data_path": args.get("data_path"),
        "data_dir": args.get("data_dir"),
        "strategy_params": args.get("strategy_params"),
        "export_target": args.get("export_target") or "nautilus",
        "run_optimize": bool(args.get("run_optimize", True)),
        "run_export": bool(args.get("run_export", True)),
        "method": str(args.get("method") or "grid"),
        "n_trials": int(args.get("n_trials") or 50),
        "constraints": args.get("constraints"),
    }
    try:
        inv = invoke_digiquant_tool(
            _digiquant_service_base(),
            "digiquant_pipeline_delegate",
            payload,
            bearer_token=_digi_bearer_from_context(context),
            request_id=context.request_id,
        )
    except _ORCHESTRATOR_CLIENT_ERRORS as e:
        return json.dumps({"ok": False, "error": str(e)})
    if not inv.get("ok"):
        return json.dumps(inv)
    data = inv.get("data")
    if not isinstance(data, dict):
        return json.dumps(inv)
    return {
        "content": json.dumps(
            {
                k: data.get(k)
                for k in ("trace", "backtest", "optimize", "export", "error")
                if k in data
            },
            default=str,
        ),
        "service": "digiquant",
        "trace": data.get("trace"),
    }


def _federated_delegate_tool_names() -> list[str]:
    if not federated_hub_enabled():
        return []
    return ["digisearch_research_delegate", "digiquant_pipeline_delegate"]


def _register_tools() -> None:
    register_tool(
        "digisearch",
        None,
        _handle_digisearch,
        schema_factory=lambda ctx: _schema_from_digisearch_manifest(ctx, "digisearch"),
    )
    register_tool(
        "digisearch_fetch_all",
        None,
        _handle_digisearch_fetch_all,
        schema_factory=lambda ctx: _schema_from_digisearch_manifest(ctx, "digisearch_fetch_all"),
    )
    register_tool(
        "digivault_search_notes",
        None,
        _handle_digivault_search,
        schema_factory=lambda ctx: _schema_from_digivault_manifest(ctx, "digivault_search_notes"),
    )
    register_tool(
        "digivault_get_note",
        None,
        _handle_digivault_get_note,
        schema_factory=lambda ctx: _schema_from_digivault_manifest(ctx, "digivault_get_note"),
    )
    register_tool(
        "visualization_agent",
        VISUALIZATION_AGENT_TOOL,
        _handle_visualization,
        tags=DELEGATE_TAGS,
    )
    register_tool(
        "analysis_agent",
        ANALYSIS_AGENT_TOOL,
        _handle_analysis,
        tags=DELEGATE_TAGS,
    )
    register_tool(
        "data_prep_agent",
        DATA_PREP_AGENT_TOOL,
        _handle_data_prep,
        tags=DELEGATE_TAGS,
    )
    register_tool(
        "data_manipulation_agent",
        DATA_MANIPULATION_AGENT_TOOL,
        _handle_data_manipulation,
        tags=DELEGATE_TAGS,
    )
    if code_execution_allowed():
        register_tool(
            "data_engineer_agent",
            DATA_ENGINEER_AGENT_TOOL,
            _handle_data_engineer,
            tags=DELEGATE_TAGS,
        )
    register_tool(
        "digistore_list",
        DIGISTORE_LIST_TOOL,
        _handle_digistore_list,
    )
    register_tool(
        "digistore_profile",
        DIGISTORE_PROFILE_TOOL,
        _handle_digistore_profile,
    )
    register_tool(
        "todo",
        TODO_TOOL,
        _handle_todo,
    )
    register_tool(
        "create_plan",
        CREATE_PLAN_TOOL,
        _handle_create_plan,
    )
    if federated_hub_enabled():
        register_tool(
            "digisearch_research_delegate",
            None,
            _handle_digisearch_research_delegate,
            tags=DELEGATE_TAGS,
            schema_factory=_schema_digisearch_research_delegate,
        )
        register_tool(
            "digiquant_pipeline_delegate",
            None,
            _handle_digiquant_pipeline_delegate,
            tags=DELEGATE_TAGS,
            schema_factory=_schema_digiquant_pipeline_delegate,
        )


def _project_rag_tool_names() -> list[str]:
    names = [
        "digisearch",
        "digisearch_fetch_all",
        "digistore_list",
        "digistore_profile",
        "visualization_agent",
        "analysis_agent",
        "data_prep_agent",
        "data_manipulation_agent",
    ]
    if code_execution_allowed():
        names.append("data_engineer_agent")
    names.extend(["todo", "create_plan", *_federated_delegate_tool_names()])
    return names


def _register_skills() -> None:
    search_bundle = ["digisearch", "digisearch_fetch_all", *_federated_delegate_tool_names()[:1]]
    register_skill(
        "search",
        search_bundle,
        when=lambda ctx: _digisearch_available(ctx),
    )
    register_skill(
        "project_rag",
        _project_rag_tool_names(),
        when=lambda ctx: ctx.has_run_data_dir,
    )
    register_skill(
        "digivault",
        ["digivault_search_notes", "digivault_get_note"],
        when=lambda ctx: _digivault_available(ctx),
    )


_register_tools()
_register_skills()
load_entrypoint_tools()
