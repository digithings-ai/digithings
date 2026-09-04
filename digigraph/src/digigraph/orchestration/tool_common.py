"""Shared helpers for built-in orchestrator tool handlers."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

from digigraph.orchestration.registry import ToolContext
from digigraph.project_config import DigiProjectConfig

logger = logging.getLogger(__name__)

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
