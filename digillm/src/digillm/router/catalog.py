"""Resolve Auto, Reasoning, Fast, and Light from the model catalog.

The rules match the digichat model picker (PR 6193): newest generation of
each family, then the standard output-price cap. A model flagged ``premium``
(above that cap and at or under the premium cap) is manual selection only.
Winners are computed from ``model_catalog.json``. They are not stored as ids.
"""

from __future__ import annotations

import json
from datetime import date
from functools import cache
from importlib.resources import files

from pydantic import BaseModel, ConfigDict, Field

from digillm.router.types import RouterError


class CatalogModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str
    family: str
    generation: float
    input_per_m: float = Field(alias="inputPerM")
    output_per_m: float = Field(alias="outputPerM")
    context: int
    tools: bool
    reasoning: bool
    reasoning_score: float = Field(alias="reasoningScore")
    ttft_samples: int = Field(alias="ttftSamples")
    ttft_p50_ms: float = Field(alias="ttftP50Ms")
    released: str | None = None
    premium: bool = False


class CatalogPolicy(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    price_cap_usd_per_million: float = Field(alias="priceCapUsdPerMillion")
    premium_cap_usd_per_million: float = Field(alias="premiumCapUsdPerMillion")
    min_context_tokens: int = Field(alias="minContextTokens")
    min_ttft_samples: int = Field(alias="minTtftSamples")
    latest_generations_per_family: int = Field(alias="latestGenerationsPerFamily")
    max_age_days: int | None = Field(alias="maxAgeDays")
    as_of: str = Field(alias="asOf")


class CatalogPreset(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    model: str | None = None


class ModelCatalog(BaseModel):
    model_config = ConfigDict(extra="ignore")

    policy: CatalogPolicy
    presets: list[CatalogPreset]
    models: list[CatalogModel]


def load_catalog() -> ModelCatalog:
    raw = files("digillm.router").joinpath("model_catalog.json").read_text(encoding="utf-8")
    return ModelCatalog.model_validate(json.loads(raw))


def _age_days(as_of: str, released: str) -> int | None:
    try:
        end = date.fromisoformat(as_of)
        start = date.fromisoformat(released)
    except ValueError:
        return None
    return (end - start).days


def _generation_window(catalog: ModelCatalog) -> list[CatalogModel]:
    policy = catalog.policy
    latest_n = policy.latest_generations_per_family
    if latest_n < 1:
        raise RouterError("model catalog: latestGenerationsPerFamily must be a positive integer")
    floored = [
        model
        for model in catalog.models
        if model.tools and model.context >= policy.min_context_tokens
    ]
    by_family: dict[str, list[CatalogModel]] = {}
    for model in floored:
        if not model.family:
            raise RouterError(f"model catalog: {model.id} has no family or generation")
        by_family.setdefault(model.family, []).append(model)
    kept: list[CatalogModel] = []
    for rows in by_family.values():
        generations = sorted({row.generation for row in rows}, reverse=True)
        keep = set(generations[:latest_n])
        for row in rows:
            if row.generation not in keep:
                continue
            if policy.max_age_days is not None and row.released:
                age = _age_days(policy.as_of, row.released)
                if age is not None and age > policy.max_age_days:
                    continue
            kept.append(row)
    return kept


def _is_premium(model: CatalogModel, policy: CatalogPolicy, pinned_id: str) -> bool:
    """True when the catalog flags the row, or its price sits in the premium band.

    The band is above the standard cap and at or under the premium cap. The
    pinned Auto model stays standard even if a deployment price would catch it.
    """

    if model.premium:
        return True
    if model.id == pinned_id:
        return False
    return (
        policy.price_cap_usd_per_million < model.output_per_m <= policy.premium_cap_usd_per_million
    )


def premium_ids(catalog: ModelCatalog | None = None) -> frozenset[str]:
    """Ids in the newest generation that the picker marks manual-only.

    That is the premium group #6193 builds: ``premium: true``, or an output
    price above the standard cap and at or under the premium cap.
    """

    table = catalog if catalog is not None else load_catalog()
    pinned_id = _auto_id(table)
    window = {model.id for model in _generation_window(table)}
    return frozenset(
        model.id
        for model in table.models
        if model.id in window and _is_premium(model, table.policy, pinned_id)
    )


def _auto_id(catalog: ModelCatalog) -> str:
    for preset in catalog.presets:
        if preset.id == "auto" and preset.model:
            return preset.model
    raise RouterError("model catalog: auto preset has no model")


def resolve_preset_ids(
    catalog: ModelCatalog | None = None,
    *,
    price_cap: float | None = None,
) -> dict[str, str]:
    """Map auto, reasoning, fast, and light to catalog model ids.

    ``price_cap`` overrides the catalog policy. The shipped file is what a
    deployment uses when the argument is omitted.
    """

    table = catalog if catalog is not None else load_catalog()
    policy = table.policy
    cap = policy.price_cap_usd_per_million if price_cap is None else price_cap
    current = _generation_window(table)
    pinned_id = _auto_id(table)
    pinned = next((model for model in current if model.id == pinned_id), None)
    if pinned is None:
        raise RouterError(
            "model catalog: default model is not in the current generation "
            "or is under the context floor"
        )
    blocked = premium_ids(table)
    capped = [
        model
        for model in current
        if model.id not in blocked and (model.output_per_m <= cap or model.id == pinned.id)
    ]

    reasoning = sorted(
        (model for model in capped if model.reasoning and model.reasoning_score > 0),
        key=lambda model: (-model.reasoning_score, model.output_per_m, model.id),
    )
    fast = sorted(
        (
            model
            for model in capped
            if model.ttft_samples >= policy.min_ttft_samples and model.ttft_p50_ms > 0
        ),
        key=lambda model: (model.ttft_p50_ms, model.id),
    )
    light = sorted(capped, key=lambda model: (model.output_per_m, model.input_per_m, model.id))
    if not reasoning or not fast or not light:
        raise RouterError("model catalog: a preset has no model under the cap")
    return {
        "auto": pinned.id,
        "reasoning": reasoning[0].id,
        "fast": fast[0].id,
        "light": light[0].id,
    }


@cache
def preset_ids() -> dict[str, str]:
    return resolve_preset_ids(load_catalog())
