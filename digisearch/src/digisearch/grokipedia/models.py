"""Pydantic envelopes for the unofficial grokipedia JSON APIs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class GrokipediaSearchHit(BaseModel):
    """One full-text-search hit. Extra upstream keys (e.g. viewCount) are kept."""

    model_config = ConfigDict(extra="allow")

    slug: str = ""
    title: str = ""
    snippet: str = ""


class GrokipediaSearchResponse(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    ok: Literal[True] = True
    query: str
    results: list[GrokipediaSearchHit] = Field(default_factory=list)
    total_count: int | None = Field(default=None, alias="totalCount")


class GrokipediaPage(BaseModel):
    """page-preview ``page`` object. Extra upstream keys are kept."""

    model_config = ConfigDict(extra="allow")

    slug: str = ""
    title: str = ""
    content: str = ""
    truncated: bool = False


class GrokipediaPageResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    ok: Literal[True] = True
    found: bool = False
    page: GrokipediaPage | None = None


class GrokipediaError(BaseModel):
    """Tool JSON error — never raised out of the MCP tools."""

    ok: Literal[False] = False
    error: str
    status_code: int | None = None
    retryable: bool = False
