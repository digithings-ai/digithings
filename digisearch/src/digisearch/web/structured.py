"""Phase B structured synthesis (#4064) — the EXA-shaped content + grounding path.

Same retrieval as :func:`digisearch.web.answer.grounded_answer` (``_live`` →
``_fetch`` → ``_rank`` reused verbatim from ``answer.py``, never copied), then
one digillm ``response_format`` json_schema call. The wire schema is the
WRAPPER ``{"content": <caller output_schema>, "grounding": [...]}`` — strict
json_schema cannot return caller-schema content and a sibling ``grounding``
key side by side, so the bare caller schema never goes on the wire. ``content``
is checked against the caller schema REQUIRED KEYS ONLY (a missing required
key raises :class:`WebResearchError`; deeper JSON-Schema validation would need
a new dependency and is out of scope) — a partial ``content`` is never
returned.

Every grounding entry passes through :func:`verify_grounding` before the
envelope is assembled, so ``WebSearchData.output`` is
``{"content", "grounding", "text"}`` (R1: the envelope stays ``web_exa``).

Fail-hard: any dependency failure, zero cited pages, a partial content, or an
unusable model payload raises :class:`WebResearchError`. The digillm import
stays inside the synthesis seam so ``import digisearch.web.structured`` works
on a base install, and fetched pages are never indexed (R3).
"""

# score:allow untyped any
# Caller-supplied output_schema and parsed wrapper JSON are dynamic; Any is the honest annotation.

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Sequence
from typing import Any

from pydantic import ValidationError

from digisearch.web.accounting import estimate_cost, finalize_usage, record_stage, start_clock
from digisearch.web.answer import (
    _SNIPPET_CHARS,
    SYNTHESIS_MODEL_ENV,
    _fetch,
    _live,
    _message_text,
    _numbered_sources,
    _rank,
)
from digisearch.web.grounding_models import (
    EFFORT_PRESETS,
    Confidence,
    EffortMode,
    FieldGrounding,
    StructuredSynthesis,
    TurnUsage,
    WebResearchConfig,
    WebResearchError,
)
from digisearch.web.retrieve import FetchedPage
from digisearch.web_exa import WebSearchData
from digisearch.web_search.citation import Citation

__all__ = ["GroundingEntry", "structured_synthesis", "verify_grounding"]

#: One verified grounding entry, in the shape it arrived in (model or dict).
GroundingEntry = FieldGrounding | dict[str, Any]

#: Name of the wrapper json_schema sent to digillm.
_WRAPPER_NAME = "web_structured"

_STRUCTURED_SYSTEM_PROMPT = (
    "You answer the user's question as a JSON object with `content` and `grounding`.\n"
    "Rules:\n"
    "1. Answer ONLY from the numbered sources; never invent facts or urls.\n"
    "2. `content` must match the requested JSON schema exactly.\n"
    "3. Return one `grounding` entry per leaf field of `content`; `field` is that "
    "field's dotted path, like `companies[0].name`.\n"
    "4. Every citation must point at one of the numbered source urls and carry "
    "`url`, `title`, and `excerpt`.\n"
    "5. `confidence` is high, medium, or low — use low when the sources only "
    "partly support the value."
)

#: Sentinel for a path that does not resolve inside ``content``.
_MISSING = object()

_DOWNGRADE = {
    Confidence.HIGH: Confidence.MEDIUM,
    Confidence.MEDIUM: Confidence.LOW,
    Confidence.LOW: Confidence.UNVERIFIED,
    Confidence.UNVERIFIED: Confidence.UNVERIFIED,
}

#: A list-index token inside a dotted field path (``companies[0].name``).
_INDEX_RE = re.compile(r"\[(\d+)\]")


def _retrieve_cited(question: str, config: WebResearchConfig) -> tuple[list[FetchedPage], set[str]]:
    """Task 3 retrieval reused through the landed ``answer`` seams.

    Returns the ranked (deduped) pages and their urls; zero cited pages raises
    :class:`WebResearchError` — fail-hard, never a citation-free synthesis.
    """
    hits = _live(question, config.live_top_n)
    pages = _fetch(hits, config.fetch_top_n)
    cited = _rank(question, pages, config.cited_top_n)
    if not cited:
        raise WebResearchError(
            f"web research found no citable sources for {question!r} "
            f"({len(pages)} fetched page(s) survived filtering)"
        )
    return cited, {page.url for page in cited}


def _wrapper_schema(output_schema: dict[str, Any]) -> dict[str, Any]:
    """The wrapper schema carried under ``json_schema.schema`` (erratum B7)."""
    citation = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "title": {"type": "string"},
            "excerpt": {"type": "string"},
        },
        "required": ["url"],
        "additionalProperties": False,
    }
    entry = {
        "type": "object",
        "properties": {
            "field": {"type": "string"},
            "citations": {"type": "array", "minItems": 1, "items": citation},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        },
        "required": ["field", "citations", "confidence"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "content": output_schema,
            "grounding": {"type": "array", "items": entry},
        },
        "required": ["content", "grounding"],
        "additionalProperties": False,
    }


def _response_format(output_schema: dict[str, Any]) -> dict[str, Any]:
    """digillm ``response_format`` descriptor wrapping the caller schema."""
    return {
        "type": "json_schema",
        "json_schema": {"name": _WRAPPER_NAME, "schema": _wrapper_schema(output_schema)},
    }


def _require_required_keys(content: Any, schema: dict[str, Any]) -> None:
    """Enforce the caller schema's top-level ``required`` keys only (no new dep)."""
    if not isinstance(content, dict):
        raise WebResearchError("structured web synthesis content is not a JSON object")
    required = schema.get("required") if isinstance(schema, dict) else None
    if not isinstance(required, list):
        return
    missing = [key for key in required if isinstance(key, str) and key not in content]
    if missing:
        raise WebResearchError(
            "structured web synthesis content is missing required key(s): " + ", ".join(missing)
        )


def _parse_synthesis(raw: str) -> StructuredSynthesis:
    """Parse the wrapper JSON into the landed atoms; unusable payloads fail hard."""
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise WebResearchError(
            f"structured web synthesis returned unparseable JSON: {exc}"
        ) from exc
    try:
        return StructuredSynthesis.model_validate(payload)
    except ValidationError as exc:
        raise WebResearchError(
            "structured web synthesis returned a payload that is not a "
            f"content+grounding object: {exc}"
        ) from exc


def _synthesize_structured(
    question: str,
    pages: list[FetchedPage],
    schema: dict[str, Any],
    config: WebResearchConfig,
) -> tuple[dict[str, Any], list[GroundingEntry], str]:
    """Wrapped-schema digillm call → required-keys check → ``verify_grounding``.

    Does not assemble the envelope: returns ``(content, verified_grounding,
    text)`` where ``text`` is the model message text (the wrapper JSON for a
    strict json_schema call; ``""`` when the model returned no text).
    """
    model = os.environ.get(SYNTHESIS_MODEL_ENV, "").strip()
    if not model:
        raise WebResearchError(
            f"{SYNTHESIS_MODEL_ENV} is not set — no model for structured web synthesis. "
            f"Set {SYNTHESIS_MODEL_ENV} to the digillm model id."
        )
    try:
        from digillm.client import completion
    except ImportError as exc:
        raise WebResearchError(
            "structured web synthesis requires the digillm client, which is not importable"
        ) from exc

    sources, rendered = _numbered_sources(pages, config.max_synthesis_chars)
    messages = [
        {"role": "system", "content": _STRUCTURED_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"{sources}\n\nQuestion: {question}\n\n"
                f"JSON schema for `content`:\n{json.dumps(schema, sort_keys=True)}"
            ),
        },
    ]
    try:
        response = completion(
            model, messages, usage_kind="web_search", response_format=_response_format(schema)
        )
    except Exception as exc:
        raise WebResearchError(f"structured web synthesis failed: {exc}") from exc

    raw = _message_text(response)
    synthesis = _parse_synthesis(raw)
    _require_required_keys(synthesis.content, schema)
    verified = verify_grounding(
        synthesis.content,
        synthesis.grounding,
        # Only sources rendered into the prompt are citable: a page truncated
        # out by ``max_synthesis_chars`` was never seen by the model.
        cited_urls={page.url for page in pages[:rendered]},
    )
    return synthesis.content, verified, raw


def _path_tokens(path: str) -> list[str | int]:
    """Split ``companies[0].name`` into ``["companies", 0, "name"]``; [] when malformed."""
    tokens: list[str | int] = []
    for part in path.replace("[", ".[").split("."):
        if not part:
            return []
        index = _INDEX_RE.fullmatch(part)
        if index is not None:
            tokens.append(int(index.group(1)))
        elif "[" in part or "]" in part:
            return []
        else:
            tokens.append(part)
    return tokens


def _resolve(value: Any, tokens: Sequence[str | int]) -> Any:
    """Walk *tokens* through *value*; ``_MISSING`` when any step does not resolve."""
    current = value
    for token in tokens:
        if isinstance(token, int):
            if not isinstance(current, (list, tuple)) or token >= len(current):
                return _MISSING
            current = current[token]
        else:
            if not isinstance(current, dict) or token not in current:
                return _MISSING
            current = current[token]
    return current


def _echoes(value: str, sibling: str) -> bool:
    """Case-insensitive containment either way, ignoring blank values."""
    left = value.strip().lower()
    right = sibling.strip().lower()
    return bool(left) and bool(right) and (left in right or right in left)


def _echoes_sibling(parent: Any, key: str | int, value: Any) -> bool:
    """True when *value* echoes a sibling leaf that precedes it under *parent*.

    The first sibling to claim a value keeps its confidence; each later echo
    (e.g. the live EXA ``launcher == name`` payload) is downgraded one level.
    """
    if not isinstance(value, str) or not value.strip():
        return False
    if isinstance(parent, dict) and isinstance(key, str):
        preceding: list[Any] = []
        for sibling_key, sibling_value in parent.items():
            if sibling_key == key:
                break
            preceding.append(sibling_value)
        else:
            return False  # the field's own key is not in the parent
    elif isinstance(parent, (list, tuple)) and isinstance(key, int):
        preceding = list(parent[:key])
    else:
        return False
    return any(isinstance(sibling, str) and _echoes(value, sibling) for sibling in preceding)


def _confidence_from(value: Any) -> Confidence:
    """Parse a loose confidence; unknown or missing is never rendered verified."""
    if isinstance(value, Confidence):
        return value
    if isinstance(value, str):
        try:
            return Confidence(value.strip().lower())
        except ValueError:
            return Confidence.UNVERIFIED
    return Confidence.UNVERIFIED


def _citation_url(citation: Any) -> str:
    """The landed ``Citation`` url for a loose citation, ``""`` when unusable."""
    if isinstance(citation, Citation):
        return citation.url
    if isinstance(citation, dict):
        url = citation.get("url")
        return url if isinstance(url, str) else ""
    return ""


def _citation_row(citation: Any) -> dict[str, Any]:
    """Serialize one loose citation as the landed ``Citation`` shape."""
    if isinstance(citation, Citation):
        return citation.model_dump(mode="json")
    if isinstance(citation, dict):
        try:
            return Citation.model_validate(citation).model_dump(mode="json")
        except ValidationError:
            return dict(citation)
    return {}


def verify_grounding(
    content: dict[str, Any],
    grounding: Sequence[GroundingEntry] | None,
    *,
    cited_urls: set[str],
) -> list[GroundingEntry]:
    """Flag and downgrade model-claimed grounding (pure; never raises).

    Rules (exactly what is enforced):

    1. Entries whose parent path does not resolve inside ``content`` are
       dropped — the entry annotates a field outside the content structure.
       A leaf missing under a resolvable container is kept and, when uncited,
       flagged (rule 2).
    2. An entry with no citation pointing at ``cited_urls`` is kept with
       ``confidence=unverified`` — never silently dropped.
    3. A leaf string value that case-insensitively contains (or is contained
       in) an earlier sibling leaf value under the same parent object is
       downgraded one level (high → medium → low → unverified).
    4. Cited-but-irrelevant entries are NOT detected and keep their
       model-assigned confidence.

    Returns the same element type it received: ``FieldGrounding`` models for
    model input, plain ``{"field", "citations", "confidence"}`` dicts for dict
    input. Unknown or missing confidence is treated as ``unverified``.
    """
    verified: list[GroundingEntry] = []
    for entry in grounding or []:
        if isinstance(entry, FieldGrounding):
            field = entry.field
            citations: list[Any] = list(entry.citations)
            confidence = entry.confidence
        elif isinstance(entry, dict):
            field = entry.get("field")
            if not isinstance(field, str):
                continue
            raw_citations = entry.get("citations")
            citations = list(raw_citations) if isinstance(raw_citations, (list, tuple)) else []
            confidence = _confidence_from(entry.get("confidence"))
        else:
            continue
        if not field.strip():
            continue
        tokens = _path_tokens(field.strip())
        if not tokens:
            continue
        parent = _resolve(content, tokens[:-1])
        if not isinstance(parent, (dict, list, tuple)):
            continue
        if not any(url in cited_urls for url in map(_citation_url, citations) if url):
            confidence = Confidence.UNVERIFIED
        if _echoes_sibling(parent, tokens[-1], _resolve(content, tokens)):
            confidence = _DOWNGRADE[confidence]
        if isinstance(entry, FieldGrounding):
            verified.append(entry.model_copy(update={"confidence": confidence}))
        else:
            verified.append(
                {
                    "field": field,
                    "citations": [_citation_row(citation) for citation in citations],
                    "confidence": confidence.value,
                }
            )
    return verified


def structured_synthesis(
    question: str, *, output_schema: dict[str, Any], config: WebResearchConfig | None = None
) -> tuple[WebSearchData, TurnUsage]:
    """Run structured web research and return the envelope plus per-turn usage.

    Retrieval is the Task 3 chain (``_retrieve_cited``); synthesis is one
    wrapped-schema digillm call whose verified result becomes
    ``output={"content", "grounding", "text"}``. Raises
    :class:`WebResearchError` on any dependency failure, zero cited pages, a
    missing required key, or an unusable model payload. Usage travels as the
    explicit second tuple element — ``WebSearchData`` is ``extra="ignore"``
    and drops extras.
    """
    cfg = config or EFFORT_PRESETS[EffortMode.FAST]
    timer = start_clock()

    # ``_retrieve_cited`` is one opaque block (search + fetch + rank); its
    # time lands in ``rerank_ms``, the citation-producing stage.
    started = time.perf_counter()
    cited, cited_urls = _retrieve_cited(question, cfg)
    record_stage(timer, "rerank_ms", int((time.perf_counter() - started) * 1000))

    started = time.perf_counter()
    content, grounding, text = _synthesize_structured(question, cited, output_schema, cfg)
    record_stage(timer, "synthesis_ms", int((time.perf_counter() - started) * 1000))

    # Re-checked at envelope assembly so a partial content can never ship,
    # even if the synthesizer is replaced.
    _require_required_keys(content, output_schema)

    # ``_retrieve_cited`` returns only the ranked pages (fetch-stage totals and
    # the search-surface score/engine are not re-exposed), so ``pages_fetched``
    # counts cited pages and the results rows carry neutral score/engine.
    usage = finalize_usage(
        timer,
        searches=1,
        pages_fetched=len(cited),
        pages_cited=len(cited_urls),
        llm_calls=1,
    )
    results: list[dict[str, Any]] = [
        {
            "title": page.title,
            "url": page.url,
            "snippet": page.markdown[:_SNIPPET_CHARS],
            "score": 0.0,
            "engine": "",
        }
        for page in cited
    ]
    data = WebSearchData(
        results=results,
        output={
            "content": content,
            "grounding": [
                entry.model_dump(mode="json") if isinstance(entry, FieldGrounding) else entry
                for entry in grounding
            ],
            "text": text,
        },
        search_type=f"web-{cfg.effort.value}",
        cost_dollars=estimate_cost(searches=1, pages_fetched=len(cited), llm_calls=1).model_dump(),
    )
    return data, usage
