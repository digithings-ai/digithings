"""Shared segment output-model primitives.

Every phase 1–5 segment produces a structured report; the shape has a common
core (segment, date, bias, headline, findings, sources, notes) plus
segment-specific extensions. Those extensions live with their phase modules;
this file defines the reusable core.

Kept minimal on purpose — the legacy Atlas system does not have strict
per-segment schemas beyond the overall digest/delta contracts in
``templates/schemas/``. We pick a clean Pydantic shape that makes the LLM's
output deterministic, covers everything the Phase 7 digest synthesis needs
to read, and leaves room for richer per-segment fields in sub-classes.
"""

from __future__ import annotations

import json
import logging
import time as _time
from collections.abc import Mapping
from datetime import date as _date
from types import UnionType
from typing import (
    Any,  # score:allow untyped any — raw pre-validation LLM body shape
    Literal,
    Union,
    get_args,
    get_origin,
)

from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

# Narrow stance vocabulary shared across asset classes / sectors.
# Phase 7 synthesis maps these to the digest's bias row.
Bias = Literal[
    "strong_bullish",
    "bullish",
    "neutral",
    "bearish",
    "strong_bearish",
    "mixed",
]

# Honest grade of the evidence behind a segment read (Pillar 1E). "absent" means no
# material data was available — the analyst should set it (with bias "neutral") instead of
# writing a confident "no data" brief; publish suppresses an absent + finding-free segment,
# and Phase 7 synthesis / the PM can discount thin ones.
DataQuality = Literal["high", "medium", "low", "absent"]


# LLM synonym → canonical Bias value. Applied before Pydantic validates the
# Literal so models never hard-fail on reasonable paraphrases (e.g. Gemini
# Flash returning "positive" instead of "bullish").
_BIAS_SYNONYMS: dict[str, str] = {
    "positive": "bullish",
    "negative": "bearish",
    "very_positive": "strong_bullish",
    "strongly_bullish": "strong_bullish",
    "strongly_positive": "strong_bullish",
    "very_negative": "strong_bearish",
    "strongly_bearish": "strong_bearish",
    "strongly_negative": "strong_bearish",
}


# ─── Generic Literal-axis normalization (#1741) ──────────────────────────────
#
# #1641 gave ``flow_direction`` a synonym validator and paired the edit-merge
# fallback with no telemetry, so the *other* 29 ``Literal[...]`` axes on Phase 1–5
# reports kept hard-failing ``model_validate`` — silently, as an invisible
# full-mode regeneration. Rather than 29 hand-written validators, the base class
# normalizes every Literal-typed field generically.
#
# Keyed by the normalized value the LLM emitted; the value is an *ordered tuple of
# candidate* canonical members, and the normalizer picks the first candidate that is
# actually a member of the target field's own ``Literal``. One table therefore serves
# every axis without cross-axis leakage: ``'neutral'`` resolves to ``'mixed'`` on
# ``risk_appetite`` (risk_on|mixed|risk_off), to ``'inline'`` on
# ``relative_strength_vs_spy`` (outperforming|underperforming|inline), to ``'balanced'``
# on ``funding_rate_bias`` and to ``'range'`` on ``dxy_trend``. Identity (including
# case/hyphen/space variants) is handled before this table is consulted, so no entry
# maps a value onto itself.
#
# An entry is admitted ONLY when the mapping is semantically exact on every axis that
# can consume it. Deliberately absent, even though observed in production:
#   * ``'improving'`` / ``'deteriorating'`` on ``market_breadth`` (broad|narrow|mixed) —
#     a breadth *trend* is not a breadth *state*, and neither word picks a member.
#   * ``'mixed'`` → ``'flat'`` on ``futures_oi_trend`` (expanding|contracting|flat) —
#     conflicting is not unchanged.
#   * ``'stable'`` / ``'steady'`` on ``growth`` (expanding|slowing|contracting) — the
#     axis has no non-directional member, so any mapping would invent a macro call.
# Those degrade to ``None`` on the Optional fields that emitted them (the fail-soft
# ``data_quality`` idiom) rather than being guessed at.
_LITERAL_SYNONYMS: dict[str, tuple[str, ...]] = {
    # Non-directional / "no call" vocabulary.
    "neutral": ("mixed", "balanced", "inline", "flat", "normal", "range"),
    "mixed": ("neutral", "balanced"),
    "balanced": ("mixed", "neutral"),
    "flat": ("range", "neutral"),
    "sideways": ("range", "flat", "neutral"),
    "range_bound": ("range", "flat", "neutral"),
    "unchanged": ("flat", "range", "neutral"),
    "in_line": ("inline",),
    # Directional vocabulary. Ordered most-specific first; no axis contains two
    # candidates from the same tuple, so the order is documentation, not a tie-break.
    "positive": ("bullish", "risk_on", "long", "inflow", "adding", "expanding"),
    "negative": ("bearish", "risk_off", "short", "outflow", "reducing", "contracting"),
    "bullish": ("risk_on", "long", "adding", "inflow"),
    "bearish": ("risk_off", "short", "reducing", "outflow"),
    "risk_on": ("bullish", "long", "adding", "inflow"),
    "risk_off": ("bearish", "short", "reducing", "outflow"),
    "upbeat": ("bullish", "risk_on", "long"),
    "downbeat": ("bearish", "risk_off", "short"),
    "greed": ("risk_on", "bullish", "long"),
    "fear": ("risk_off", "bearish", "short"),
    "buying": ("adding", "long", "inflow", "expanding"),
    "selling": ("reducing", "short", "outflow", "contracting"),
    "cautious": ("neutral", "mixed"),
    "outperform": ("outperforming",),
    "underperform": ("underperforming",),
    # Degree vocabulary (conviction / data_quality).
    "moderate": ("medium",),
    "med": ("medium",),
    "strong": ("high",),
    "weak": ("low",),
    # Macro-factor vocabulary (the four required Phase 3 axes).
    "hawkish": ("tightening",),
    "dovish": ("easing",),
    "sticky": ("hot",),
    "elevated": ("hot",),
    "disinflation": ("cooling",),
    "disinflationary": ("cooling",),
    "growing": ("expanding",),
    "shrinking": ("contracting",),
    "recessionary": ("contracting",),
}

# (allowed string members, field accepts None) per Literal-typed field, per model.
# Derived once per class from ``model_fields`` — the annotation walk is not free and
# every segment body is validated at least twice (patch merge + publish).
_LITERAL_FIELDS_CACHE: dict[type[BaseModel], dict[str, tuple[frozenset[str], bool]]] = {}


def _string_literal_members(annotation: object) -> frozenset[str] | None:
    """Return the members of a ``Literal[...]`` of plain strings, else None."""
    if get_origin(annotation) is not Literal:
        return None
    args = get_args(annotation)
    if not args or not all(isinstance(arg, str) for arg in args):
        return None
    return frozenset(args)


def _literal_field_spec(annotation: object) -> tuple[frozenset[str], bool] | None:
    """``(members, optional)`` for a ``Literal[...]`` / ``Literal[...] | None`` field.

    Returns None for anything else, including a Literal of non-strings or a union
    that mixes a Literal with another concrete type — normalizing those would be
    guessing about a shape this module does not own.
    """
    direct = _string_literal_members(annotation)
    if direct is not None:
        return direct, False
    if get_origin(annotation) not in (Union, UnionType):
        return None
    members: set[str] = set()
    optional = False
    for arg in get_args(annotation):
        if arg is type(None):
            optional = True
            continue
        inner = _string_literal_members(arg)
        if inner is None:
            return None
        members.update(inner)
    return (frozenset(members), optional) if members else None


def _fields_with_own_before_validator(model: type[BaseModel]) -> frozenset[str]:
    """Fields that declare their own ``mode="before"`` field validator.

    The generic pass **must not** touch these: a dedicated validator owns its field's
    vocabulary and fail-soft policy, and pre-empting it silently narrows it. Concretely,
    ``_FLOW_DIRECTION_SYNONYMS`` knows ``'net inflows' → 'inflow'`` and the generic table
    does not, so degrading to None here would have regressed #1641's own fix.
    """
    owned: set[str] = set()
    for decorator in model.__pydantic_decorators__.field_validators.values():
        if decorator.info.mode == "before":
            owned.update(decorator.info.fields)
    return frozenset(owned)


def _literal_fields(model: type[BaseModel]) -> dict[str, tuple[frozenset[str], bool]]:
    cached = _LITERAL_FIELDS_CACHE.get(model)
    if cached is None:
        owned = _fields_with_own_before_validator(model)
        cached = {}
        for name, field in model.model_fields.items():
            if name in owned:
                continue
            spec = _literal_field_spec(field.annotation)
            if spec is not None:
                cached[name] = spec
        _LITERAL_FIELDS_CACHE[model] = cached
    return cached


def _literal_token(value: str) -> str:
    """Case/whitespace/hyphen-insensitive form: ``'Risk-On '`` → ``'risk_on'``."""
    return "_".join(value.strip().lower().replace("-", " ").replace("_", " ").split())


def canonical_literal(raw: str, members: frozenset[str]) -> str | None:
    """Resolve *raw* onto a member of *members*, or None when no exact synonym exists."""
    token = _literal_token(raw)
    if token in members:
        return token
    for candidate in _LITERAL_SYNONYMS.get(token, ()):
        if candidate in members:
            return candidate
    return None


def _parse_json_object(value: object) -> object:
    """Parse a JSON-object string; leave anything else untouched."""
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped.startswith("{"):
        return value
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return value
    return parsed if isinstance(parsed, dict) else value


def _string_value(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    if isinstance(value, Mapping):
        inner = value.get("stringValue") or value.get("string_value")
        if isinstance(inner, str) and inner.strip():
            return inner
    return None


def _as_field_mapping(value: object) -> Mapping[str, Any] | None:
    """Gemini Struct maps arrive as JSON objects *or* lists of ``[key, value]`` pairs.

    House GHA 33426508863 truncated the live envelope as
    ``'{"completionState":"comp...k."}]],"type":"Object"}'`` — the ``}]],`` before
    ``type`` is a list-of-pairs map, not a JSON object. A mixed/invalid sequence is
    not flattened.
    """
    if isinstance(value, Mapping):
        return value
    if isinstance(value, str) or not isinstance(value, (list, tuple)) or not value:
        return None
    out: dict[str, Any] = {}
    for item in value:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            key, val = item[0], item[1]
        elif isinstance(item, Mapping) and isinstance(item.get("key"), str):
            key, val = item["key"], item.get("value")
        else:
            return None
        if not isinstance(key, str) or not key.strip() or key in out:
            return None
        out[key] = val
    return out


def _flatten_wrapped_record(data: Mapping[str, Any]) -> dict[str, Any]:
    """Unwrap Gemini/LiteLLM object envelopes onto a flat Finding/Source dict."""
    if any(key in data for key in ("label", "summary", "id", "text", "description", "detail")):
        return dict(data)
    for wrapper_key in ("properties", "fields", "structValue", "value"):
        inner = _as_field_mapping(data.get(wrapper_key))
        if inner is None:
            continue
        flat: dict[str, Any] = {}
        for key, val in inner.items():
            text = _string_value(val)
            flat[key] = text if text is not None else val
        if flat:
            return flat
    return dict(data)


def _pick_aliased_str(data: Mapping[str, Any], names: tuple[str, ...]) -> str | None:
    for name in names:
        text = _string_value(data.get(name))
        if text is not None:
            return text
    return None


def _first_clause(summary: str) -> str | None:
    """First clause for a derived label; ``$45.36`` must not split on the decimal."""
    for idx, char in enumerate(summary):
        if char in ".?!" and (idx + 1 == len(summary) or summary[idx + 1].isspace()):
            return summary[:idx].strip()[:80] or None
    return summary.strip()[:80] or None


def _coerce_finding_record(data: object) -> object:
    """Map LLM hedges onto Finding without a full-mode regeneration.

    House GHA 33426508863 ``sector-real-estate``: attempt 1 omitted ``summary``
    (``as_of`` + a long prose field); attempt 2 emitted JSON-string Gemini
    Object envelopes. Carrying the sector baseline is the expensive outcome.
    """
    data = _parse_json_object(data)
    if not isinstance(data, Mapping):
        return data
    out = _flatten_wrapped_record(data)
    if _string_value(out.get("summary")) is None:
        picked = _pick_aliased_str(
            out, ("text", "description", "detail", "body", "finding", "content", "narrative")
        )
        if picked is not None:
            out["summary"] = picked
    if _string_value(out.get("label")) is None:
        picked = _pick_aliased_str(out, ("title", "headline", "name"))
        if picked is None:
            picked = _first_clause(_string_value(out.get("summary")) or "")
        if picked is not None:
            out["label"] = picked
    return out


def _coerce_source_record(data: object) -> object:
    data = _parse_json_object(data)
    if not isinstance(data, Mapping):
        return data
    out = _flatten_wrapped_record(data)
    if _string_value(out.get("id")) is None:
        picked = _pick_aliased_str(out, ("source_id", "sourceId", "name"))
        if picked is not None:
            out["id"] = picked
    return out


class Finding(BaseModel):
    """One material finding produced by a segment analyst."""

    label: str = Field(
        description="Short noun phrase labeling the finding (e.g. 'Breakout above 200-DMA')",
    )
    summary: str = Field(
        description=(
            "1-3 sentence description in analyst voice. Quantified where possible. "
            "When you quote a number, date it — either inline ('SPY flat at $738.93 (Jul 24)') "
            "or in the 'as_of' field."
        ),
    )
    source_ids: list[str] = Field(
        default_factory=list,
        description="Source IDs from the sources list this finding cites.",
    )
    as_of: str | None = Field(
        default=None,
        description=(
            "ISO date (YYYY-MM-DD) the quoted numbers describe. REQUIRED whenever this finding "
            "states a price, percentage, or other market figure; omit only for a purely "
            "qualitative finding. This is the date of the DATA, not the date of the run."
        ),
    )

    @field_validator("as_of", mode="before")
    @classmethod
    def _normalize_as_of(cls, v: object) -> object:
        """Coerce a loose date to ISO, and NEVER raise on one that will not parse.

        Two hard constraints shape this field, both learned the expensive way.

        **It must stay optional.** ``merge_document_patch`` re-validates the *materialized* body
        — which is derived from the PRIOR published row — through
        ``spec.output_model.model_validate``. Every one of the ~660 existing ``documents`` rows
        has findings with no ``as_of``, so a required field would raise ValidationError on every
        edit-mode merge, and #1641 turns that into a full regeneration. Making this mandatory
        would quietly triple the run's LLM bill.

        **It must not be strict.** #1740's lesson verbatim: a hard schema constraint on an
        informational field discarded the ENTIRE ``DocumentPatch`` when the model overran a
        240-char ``reason``, costing 1-4 researched segments per run and once the master digest
        itself. A model writing "Jul 24" must not cost a segment. So a value that parses is
        normalized to ISO; one that does not is kept verbatim as human-readable disclosure,
        because "Jul 24" still tells a reader more than silence. Consumers wanting to compare
        dates should check for the ISO shape rather than assume it.
        """
        if v is None:
            return None
        if isinstance(v, _date):
            return v.isoformat()
        if not isinstance(v, str):
            return None
        raw = v.strip()
        if not raw:
            return None
        try:
            return _date.fromisoformat(raw).isoformat()
        except ValueError:
            pass
        for fmt in ("%b %d %Y", "%b %d, %Y", "%d %b %Y", "%Y/%m/%d", "%m/%d/%Y"):
            try:
                # ``time.strptime`` rather than ``datetime.strptime``: this is a calendar date,
                # so a timezone is meaningless and attaching one to satisfy DTZ007 would imply a
                # precision the value does not have.
                parsed = _time.strptime(raw, fmt)
            except ValueError:
                continue
            return _date(parsed.tm_year, parsed.tm_mon, parsed.tm_mday).isoformat()
        # Unparseable but non-empty: keep it, capped. Disclosure beats silence.
        return raw[:32]

    @model_validator(mode="before")
    @classmethod
    def _coerce_llm_shape(cls, data: object) -> object:
        return _coerce_finding_record(data)


class Source(BaseModel):
    """One source cited by the segment's findings."""

    id: str = Field(description="Stable identifier used by Finding.source_ids")
    title: str | None = Field(default=None)
    url: str | None = Field(default=None)

    @model_validator(mode="before")
    @classmethod
    def _coerce_llm_shape(cls, data: object) -> object:
        return _coerce_source_record(data)


class SegmentReport(BaseModel):
    """Common shape for Phase 1–5 segment reports.

    Phase-specific sub-classes add structured metrics (sentiment scores,
    flow direction, yield curve shape, etc.). Phase 7 synthesis reads only
    the fields here when assembling the master digest, so downstream
    consumers never depend on segment-specific extensions.
    """

    segment: str = Field(
        description="Stable segment slug, e.g. 'alt-sentiment-news', 'macro'.",
    )
    date: _date
    bias: Bias = Field(
        description=(
            "Directional read for the segment. Make a call — reserve 'mixed'/'neutral' for "
            "genuinely conflicting or absent signals, not as a hedge when you are merely "
            "unsure. Encode uncertainty in 'confidence', not by defaulting the bias."
        ),
    )
    headline: str = Field(
        description="One-sentence executive summary; the strongest single signal today.",
    )
    material_findings: list[Finding] = Field(
        default_factory=list,
        description="Material findings, ordered by importance.",
    )
    sources: list[Source] = Field(
        default_factory=list,
        description="Every source referenced by findings.source_ids.",
    )
    notes: str = Field(
        default="",
        description="Free-form analyst notes — uncertainty, contradictions, regime caveats.",
    )
    data_quality: DataQuality | None = Field(
        default=None,
        description=(
            "Honest grade of the evidence behind this read: 'high'/'medium'/'low' when real "
            "data (prices, technicals, macro, retrieved sources) backs it; 'absent' when no "
            "material data was available — set 'absent' with bias 'neutral' rather than "
            "writing a confident brief on nothing."
        ),
    )
    confidence: float | None = Field(
        default=None,
        description=(
            "Self-rated confidence in the bias/findings, 0.0–1.0, calibrated to evidence "
            "strength and source quality — not a round default. Thin/absent data → low "
            "confidence (and a low/absent 'data_quality'); strong corroborated signals → "
            "high. Note in 'notes' when it diverges from the data_quality grade."
        ),
    )

    @field_validator("material_findings", "sources", mode="before")
    @classmethod
    def _parse_json_list_items(cls, v: object) -> object:
        """Gemini sometimes emits nested objects as JSON strings (house GHA 33426508863)."""
        if not isinstance(v, list):
            return v
        return [_parse_json_object(item) for item in v]

    @model_validator(mode="before")
    @classmethod
    def _normalize_literal_axes(cls, data: object) -> object:
        """Map LLM synonyms onto every ``Literal[...]`` field of *any* subclass (#1741).

        ``cls`` is the concrete subclass here, so one validator on the base covers all
        30 Literal axes across the six phase modules — including the ones that had no
        validator at all and therefore hard-failed ``model_validate`` on values like
        ``relative_strength_vs_spy='neutral'`` or ``risk_appetite='neutral'``.

        Fields that declare their own ``mode="before"`` validator (``bias``,
        ``data_quality``, ``flow_direction``) are skipped outright — see
        ``_fields_with_own_before_validator``.

        Two fail-soft tiers, deliberately different:
        * **Optional** axis with no exact synonym → ``None``. Informational field;
          an unparseable value must never fail a merge (the #1641 contract).
        * **Required** axis with no exact synonym → the raw value is left untouched
          so Pydantic still rejects it. ``growth`` (expanding|slowing|contracting)
          and ``inflation`` (hot|cooling|cold) have no non-directional member, so a
          "total" mapping would have to invent a macro call that Phases 4–7 then
          consume as fact. A loud failure is the honest outcome.
        """
        if not isinstance(data, Mapping):
            return data
        fields = _literal_fields(cls)
        if not fields:
            return data
        patched: dict[str, Any] | None = None
        for name, (members, optional) in fields.items():
            raw = data.get(name)
            if not isinstance(raw, str) or raw in members:
                continue
            canonical = canonical_literal(raw, members)
            if canonical is None and not optional:
                logger.warning(
                    "%s.%s: no synonym for %r on a required axis %s — rejecting",
                    cls.__name__,
                    name,
                    raw,
                    sorted(members),
                )
                continue
            if patched is None:
                patched = dict(data)
            patched[name] = canonical
            logger.info("%s.%s: normalized %r → %r", cls.__name__, name, raw, canonical)
        return data if patched is None else patched

    @field_validator("bias", mode="before")
    @classmethod
    def _normalize_bias(cls, v: object) -> object:
        if isinstance(v, str):
            return _BIAS_SYNONYMS.get(v.lower(), v)
        return v

    @field_validator("data_quality", mode="before")
    @classmethod
    def _normalize_data_quality(cls, v: object) -> object:
        """Lower/strip the LLM's grade; an unrecognized value degrades to None so a
        malformed grade never hard-fails the run (it just publishes ungraded). This is
        fully fail-soft — unlike ``bias`` normalization, which only maps known synonyms and
        still rejects truly unknown values."""
        if isinstance(v, str):
            cleaned = v.strip().lower()
            return cleaned if cleaned in ("high", "medium", "low", "absent") else None
        return v

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp_confidence(cls, v: object) -> object:
        """Clamp to [0, 1]; a non-numeric value degrades to None (never hard-fail a run)."""
        if v is None:
            return None
        try:
            return max(0.0, min(1.0, float(v)))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
