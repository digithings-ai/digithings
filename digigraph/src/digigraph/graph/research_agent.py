"""Generic research-agent node for sub-graphs.

A phase node in an Atlas-style pipeline is "research this scope, produce
a validated structured output." The *how* (analyst persona, materiality
filter, citation discipline) lives in this module. The *what* (which sector,
which data sources, which output schema) is injected per call as
``skill_text`` + ``output_model``.

This lets sub-graphs — notably DigiQuant Atlas (#176/#177) — compose research
pipelines from declarative phase configs without re-authoring a prompt per
segment. The module stays generic: no Atlas-specific vocabulary here.

The existing ``digigraph.graph.research`` node is the RAG/tool-loop research
node invoked by the DigiGraph supervisor; it is a different concern and is
not touched.
"""

from __future__ import annotations

import json
import logging
import re

# The noqa below is read by repo-local `scripts/score.py` (not ruff) — that
# gate flags unscoped `Any` imports. Here Any matches heterogeneous LLM
# message content-part dicts used by LiteLLM / OpenAI clients.
from typing import Any, Callable, TypeVar  # noqa  # scored-lint suppression

from pydantic import BaseModel, ValidationError

from digigraph.llm import (
    chat_completion,
    chat_completion_with_tools,
    get_model_for_mode,
    get_model_for_phase,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

ANALYST_SYSTEM = """You are a disciplined research analyst producing a structured brief.

Principles:
- Material only. Skip noise. Include findings that meaningfully change the read on the scope; omit routine/cosmetic observations.
- Evidence-bound. Every claim rests on a source you retrieved or on data in the user block. Do not invent numbers, dates, or quotations.
- Cite. When citing a source, use the url or identifier provided in the user block. If the evidence is in the data bundle, reference the field name.
- Quantify when possible. Percent moves, basis points, date ranges, dollar flows — prefer numbers over adjectives.
- Flag uncertainty. If evidence is thin or conflicting, say so in the output's uncertainty/notes field; do not paper over it.
- Refuse to hallucinate. If the scope cannot be answered from the provided context, return the schema with empty findings and a note explaining what is missing.

Output format:
- Respond with a single JSON object that validates against the schema named in the user block.
- No markdown, no prose outside the JSON, no code fences.
"""


def _strip_json_fence(raw: str) -> str:
    s = re.sub(r"^```(?:json)?\s*", "", (raw or "").strip()).strip()
    return re.sub(r"\s*```$", "", s).strip()


def _format_scope_block(
    *,
    skill_text: str,
    phase_inputs: dict[str, Any],
    shared_context: dict[str, Any],
    output_schema: dict[str, Any],
    schema_name: str,
) -> list[dict[str, Any]]:
    """Build the user-message content parts.

    Structure (parts ordered from stable → volatile so caching hits downstream):
      1. shared_context JSON — stable across all phases in a run; cache-controlled.
      2. skill_text — stable per segment; cache-controlled.
      3. phase_inputs JSON — volatile (today's data layer, prior-phase outputs).
      4. output schema + name — stable per segment; cache-controlled.

    Returns an OpenAI-compatible content-parts list. LiteLLM passes ``cache_control``
    through to Anthropic when routing to Claude models; other providers ignore it.
    """
    shared_json = json.dumps(shared_context, default=str, sort_keys=True)
    inputs_json = json.dumps(phase_inputs, default=str, sort_keys=True)
    schema_json = json.dumps(output_schema, sort_keys=True)
    return [
        {
            "type": "text",
            "text": f"SHARED_CONTEXT:\n{shared_json}",
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": f"RESEARCH_SCOPE (skill):\n{skill_text}",
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": f"PHASE_INPUTS (today):\n{inputs_json}",
        },
        {
            "type": "text",
            "text": (
                f"OUTPUT_SCHEMA (name: {schema_name}):\n{schema_json}\n\n"
                f"Respond with a single JSON object that validates against {schema_name}."
            ),
            "cache_control": {"type": "ephemeral"},
        },
    ]


def run_research_agent(
    *,
    skill_text: str,
    phase_inputs: dict[str, Any],
    shared_context: dict[str, Any],
    output_model: type[T],
    model: str | None = None,
    phase_slug: str | None = None,
    temperature: float = 0.1,
    max_retries: int = 1,
    max_tokens: int | None = None,
    tools: list[dict[str, Any]] | None = None,
    execute_tool: Callable[[str, dict[str, Any]], str] | None = None,
    search_parameters: dict[str, Any] | None = None,
) -> T:
    """Run one research-agent LLM call and return a validated Pydantic instance.

    Raises:
        ValidationError: if the LLM output cannot be coerced into ``output_model``
            after ``max_retries`` attempts.

    Parameters:
        skill_text: Body of a SKILL.md file (without YAML frontmatter) — tells
            the agent *what* to research.
        phase_inputs: Volatile per-call inputs (today's data, prior-phase outputs).
        shared_context: Stable per-run context (config, investment profile,
            watchlist). Cached across phase calls within a run.
        output_model: Pydantic model the output must validate against.
        model: Explicit model override (highest priority).
        phase_slug: Segment slug used to look up per-phase model from phase_models
            config (second priority). Falls back to get_model_for_mode() when None
            or when the slug has no entry in phase_models.
        temperature: LLM temperature; default 0.1 (analyst work wants determinism).
        max_retries: How many times to re-call with the validator error appended
            before giving up. Default 1.
        max_tokens: Maximum output tokens for the completion. None (default) lets
            the provider use its own limit — no cap is imposed on the response.
        tools: Optional function-tool definitions. When supplied with
            ``execute_tool``, the agent runs a tool-calling loop
            (``chat_completion_with_tools``) so it can ground itself on real data
            before emitting the final JSON, which is still validated against
            ``output_model``. ``response_format`` is not used on this path (tools
            and json_schema are mutually exclusive in one API call).
        execute_tool: Dispatcher ``(name, args) -> json_str`` bound to the tools.
            Required for the tool path; ignored when ``tools`` is empty.
        search_parameters: Optional xAI Live Search descriptor, forwarded via
            ``extra_body`` for xAI models (no-op otherwise). Applies on both the
            tool and the structured-output paths.

    Provider notes:
        ``response_format=json_schema`` is passed to the API call so that providers
        that support native structured output (Gemini Flash, OpenAI) enforce the
        schema at token-generation time. Providers that silently ignore the field
        (Ollama, some LiteLLM backends) fall back to the prompt-embedded
        OUTPUT_SCHEMA block. The Pydantic field_validator on output models acts
        as a third defense-in-depth layer for synonym normalization regardless of
        which path is taken.
    """
    effective_model = (
        model or (get_model_for_phase(phase_slug) if phase_slug else None) or get_model_for_mode()
    )
    schema = output_model.model_json_schema()
    schema_name = output_model.__name__
    response_format: dict[str, Any] = {
        "type": "json_schema",
        "json_schema": {"name": schema_name, "schema": schema},
    }
    content_parts = _format_scope_block(
        skill_text=skill_text,
        phase_inputs=phase_inputs,
        shared_context=shared_context,
        output_schema=schema,
        schema_name=schema_name,
    )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": ANALYST_SYSTEM},
        {"role": "user", "content": content_parts},
    ]

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        if tools and execute_tool is not None:
            raw = chat_completion_with_tools(
                effective_model,
                messages,
                tools=tools,
                execute_tool=execute_tool,
                temperature=temperature,
                search_parameters=search_parameters,
            )
        else:
            raw = chat_completion(
                effective_model,
                messages,
                temperature=temperature,
                response_format=response_format,
                max_tokens=max_tokens,
                search_parameters=search_parameters,
            )
        if isinstance(raw, tuple):  # defensive: tuple only with tools
            raw = raw[0]
        try:
            data = json.loads(_strip_json_fence(raw or ""))
            return output_model.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = exc
            logger.warning(
                "research_agent attempt %d/%d failed for %s: %s",
                attempt + 1,
                max_retries + 1,
                schema_name,
                exc,
            )
            if attempt == max_retries:
                break
            messages = messages + [
                {"role": "assistant", "content": raw or ""},
                {
                    "role": "user",
                    "content": (
                        f"Your previous response did not validate against {schema_name}. "
                        f"Error: {exc}\n\nRe-emit a single JSON object that validates. "
                        f"No prose, no code fences."
                    ),
                },
            ]
    assert last_error is not None  # loop always records on failure
    raise last_error
