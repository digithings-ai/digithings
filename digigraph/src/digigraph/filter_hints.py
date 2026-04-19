"""NL → filter hints for SITAAS search.

Extract lightweight, structured filter hints (year, region, topic) from a natural-language
query so downstream search can pre-narrow without the user specifying formal filters.

The extraction is a tiny LLM call on the hot path. It is fail-open: any error returns
an empty :class:`FilterHints` so search still runs. Results ride the shared
``chat_completion`` cache (``DIGI_LLM_CACHE_TTL_SECONDS``) so repeated queries are free.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

from digigraph.llm import chat_completion, get_model_for_mode

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You extract search filter hints from a user's natural-language query.
Return exactly one JSON object (no markdown, no prose) with these optional keys:
- "year": 4-digit integer (e.g. 2024) if the query mentions a specific year; otherwise null
- "region": geographic region/country/continent if mentioned (e.g. "Europe", "Asia", "US"); otherwise null
- "topic": a short subject phrase (2-6 words) capturing what the query is about; otherwise null

Rules:
- Only fill fields the query clearly implies. Omit or use null when uncertain.
- Do NOT infer a year from vague phrases like "this week", "recently", "last quarter".
- Keep "topic" concise — no more than 6 words, lowercase, no trailing punctuation.
- Output JSON only. No explanation."""


class FilterHints(BaseModel):
    """Structured hints extracted from an NL query for pre-narrowing search."""

    year: int | None = Field(default=None, ge=1900, le=2100)
    region: str | None = None
    topic: str | None = None

    @field_validator("region", "topic", mode="before")
    @classmethod
    def _blank_to_none(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return v

    def is_empty(self) -> bool:
        return self.year is None and not self.region and not self.topic

    def as_context_block(self) -> str:
        """Return a compact bracketed block to prepend to the user message, or "" if empty."""
        if self.is_empty():
            return ""
        parts: list[str] = []
        if self.year is not None:
            parts.append(f"year={self.year}")
        if self.region:
            parts.append(f"region={self.region}")
        if self.topic:
            parts.append(f"topic={self.topic}")
        return "[Detected filter hints: " + ", ".join(parts) + "]"


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.DOTALL)


def _strip_fence(s: str) -> str:
    return _FENCE_RE.sub("", (s or "").strip()).strip()


def _parse_hints_json(content: str) -> dict[str, Any]:
    s = _strip_fence(content)
    if not s:
        return {}
    decoder = json.JSONDecoder()
    try:
        obj, _ = decoder.raw_decode(s)
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        pass
    start = s.find("{")
    if start == -1:
        return {}
    try:
        obj, _ = decoder.raw_decode(s, start)
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        return {}


def _is_disabled() -> bool:
    return os.environ.get("DIGI_FILTER_HINTS", "1").strip().lower() in ("0", "false", "no", "off")


def extract_filter_hints(query: str) -> FilterHints:
    """Extract :class:`FilterHints` from an NL query. Fail-open on any error.

    Disabled when ``DIGI_FILTER_HINTS=0``. Results ride the shared LLM cache so
    repeated queries are effectively free on the hot path.
    """
    if _is_disabled():
        return FilterHints()
    q = (query or "").strip()
    if not q:
        return FilterHints()
    try:
        content = chat_completion(
            model=get_model_for_mode(),
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": q},
            ],
            temperature=0.0,
        )
        if not isinstance(content, str) or not content.strip():
            return FilterHints()
        data = _parse_hints_json(content)
        if not data:
            return FilterHints()
        # Only keep known keys to avoid pydantic strict-mode surprises on future fields.
        allowed = {k: data.get(k) for k in ("year", "region", "topic") if k in data}
        return FilterHints.model_validate(allowed)
    except Exception as exc:
        logger.debug("extract_filter_hints failed (fail-open): %s", exc)
        return FilterHints()
