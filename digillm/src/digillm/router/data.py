"""The router table both implementations read.

``router_data.json`` is the only copy of the example phrases, the structural
rules, and the preset each category calls. This module loads it. The
TypeScript port in digichat imports the same file. Neither copy of the
scorer may restate those lists.
"""

from __future__ import annotations

import json
from functools import cache
from importlib.resources import files
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RouterRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    route: str
    op: Literal["match", "search", "search_or_long"]
    pattern: str
    flags: str = ""
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)
    max_chars: int | None = None
    unless_pattern: str | None = None
    unless_flags: str = ""
    numbered_pattern: str | None = None
    numbered_flags: str = ""
    long_chars: int | None = None


class RouterTableRoute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    description: str
    exemplars: list[str]


class RouterPresetModels(BaseModel):
    """Models the digichat picker resolved for its default catalog policy."""

    model_config = ConfigDict(extra="forbid")

    auto: str
    reasoning: str
    fast: str
    light: str


class RouterCatalogModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    prompt_usd_per_million: float | None = None
    output_usd_per_million: float | None = None
    tool_call: bool


class RouterTable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dim: int = Field(ge=1)
    weak: float = Field(ge=0.0, le=1.0)
    stopwords: list[str]
    token_pattern: str
    bind: Literal["catalog_presets"]
    presets: RouterPresetModels
    price_note: str
    rules: list[RouterRule]
    routes: list[RouterTableRoute]
    models: list[RouterCatalogModel]


@cache
def router_table() -> RouterTable:
    raw = files("digillm.router").joinpath("router_data.json").read_text(encoding="utf-8")
    return RouterTable.model_validate(json.loads(raw))
