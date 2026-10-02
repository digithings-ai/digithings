"""Pydantic models for the unofficial grokipedia.com JSON API (spike).

Upstream payloads are camelCase and extra-field-heavy. Models ignore unknowns
and accept aliases so a live shape drift does not crash the read-only tools.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GrokipediaModel(BaseModel):
    """Shared config: ignore extra keys, populate snake_case from camelCase."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class GrokipediaSearchHit(GrokipediaModel):
    slug: str
    title: str = ""
    snippet: str = ""
    view_count: int | None = Field(default=None, alias="viewCount")
    score: float | None = None
    url: str = ""

    @field_validator("slug", "title", "snippet", mode="before")
    @classmethod
    def _stringify(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value)


class GrokipediaSearchResponse(GrokipediaModel):
    query: str
    results: list[GrokipediaSearchHit] = Field(default_factory=list)
    total_count: int | None = Field(default=None, alias="totalCount")


class GrokipediaCitation(GrokipediaModel):
    title: str = ""
    url: str = ""


class GrokipediaPage(GrokipediaModel):
    slug: str
    title: str = ""
    description: str | None = None
    content: str | None = None
    citations: list[GrokipediaCitation] = Field(default_factory=list)
    url: str = ""
    truncated: bool = False

    @field_validator("citations", mode="before")
    @classmethod
    def _citations(cls, value: object) -> object:
        return [] if value is None else value


class GrokipediaTypeaheadResponse(GrokipediaModel):
    query: str
    results: list[GrokipediaSearchHit] = Field(default_factory=list)
