"""Phase 7 — master digest synthesis (single LLM node).

Research-only: summarizes findings from phases 1–5. Portfolio positioning,
thesis lifecycle, and trade recommendations are Hermes's domain (phases 7C–7E).
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any, Literal  # noqa: F401 — used for JSON-derived dict shape

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase
from digigraph.graph.research_agent import run_research_agent
from pydantic import BaseModel, Field

from digiquant.olympus.atlas.phases._node_factory import (
    _edit_phase_inputs,
    _shared_context,
)
from digiquant.olympus.atlas.segments import SegmentReport
from digiquant.olympus.atlas.skills import load_skill, load_skill_edit
from digiquant.olympus.atlas.state import (
    AtlasResearchState,
    PhaseError,
    refresh_scope_forces_full,
)
from digiquant.olympus.edit_mode import DocumentPatch, MergeError, merge_document_patch
from digiquant.olympus.edit_mode.models import TriageSignal
from digiquant.olympus.edit_mode.prior import PriorPublished
from digiquant.olympus.edit_mode.resolve import resolve_edit_mode

logger = logging.getLogger(__name__)


class SegmentFreshness(BaseModel):
    """Per-segment provenance marker used by the dashboard."""

    source: Literal["today", "baseline"]
    as_of: str = Field(description="ISO date")


class ActionableItem(BaseModel):
    priority: int = Field(ge=1, le=5)
    label: str = Field()
    rationale: str = Field()


class RiskItem(BaseModel):
    horizon_hours: int = Field(ge=1, le=168)
    label: str = Field()
    trigger: str = Field()


class DigestSnapshot(SegmentReport):
    """Phase 7 master synthesis payload."""

    market_regime_snapshot: str = Field()
    alt_data_dashboard: str = Field()
    institutional_summary: str = Field()
    asset_classes_summary: str = Field()
    us_equities_summary: str = Field()
    # Deprecated — kept for schema backward compat; always empty (Hermes owns positioning).
    thesis_tracker: str = Field(
        default="",
        description="Deprecated — Hermes owns thesis lifecycle; always empty on new runs.",
    )
    portfolio_recommendations: str = Field(
        default="",
        description="Deprecated — Hermes owns allocation; always empty on new runs.",
    )
    actionable_summary: list[ActionableItem] = Field(default_factory=list)
    risk_radar: list[RiskItem] = Field(default_factory=list)
    segment_freshness: dict[str, SegmentFreshness] = Field(
        default_factory=dict,
        description="Per-segment provenance (today vs. carried) — populated from state",
    )
    # Short machine-readable regime token for the dashboard chip.
    # The LLM is asked to populate this from phase3; when it omits it we
    # deterministically backfill from state.phase3_output.payload.body.get("regime_label")
    # — same fail-soft pattern used for segment_freshness above.
    regime_label: str = Field(
        default="",
        description=(
            "Short regime token, e.g. 'Risk-on / Policy easing' — "
            "NOT the full market_regime_snapshot paragraph."
        ),
    )


def _segment_freshness(state: AtlasResearchState) -> dict[str, SegmentFreshness]:
    """Derive the freshness map from state — does not rely on the LLM."""
    out: dict[str, SegmentFreshness] = {}
    for bag in (
        state.phase1_outputs,
        state.phase2_outputs,
        state.phase4_outputs,
        state.phase5_outputs,
    ):
        for slug, slot in bag.items():
            source = "today" if slot.payload.source == "today" else "baseline"
            as_of_val = getattr(slot.payload, "as_of", None) or getattr(
                slot.payload, "baseline_date", None
            )
            as_of = as_of_val.isoformat() if as_of_val else ""
            out[slug] = SegmentFreshness(source=source, as_of=as_of)  # type: ignore[arg-type]
    if state.phase3_output is not None:
        source = "today" if state.phase3_output.payload.source == "today" else "baseline"
        as_of_val = getattr(state.phase3_output.payload, "as_of", None) or getattr(
            state.phase3_output.payload, "baseline_date", None
        )
        out["macro"] = SegmentFreshness(
            source=source,  # type: ignore[arg-type]
            as_of=as_of_val.isoformat() if as_of_val else "",
        )
    return out


# Deterministic rewrite of allocation/trade verbs into research-watchlist
# language. Atlas is research-only (ADR-0015): the digest may *flag* what to
# watch but must not issue allocation directives — that is Hermes's domain.
# The digest skill is told this, but the LLM still slips trade verbs into
# ``actionable_summary`` items; this map neutralizes them deterministically.
# Ordered longest-phrase-first so multi-word verbs match before single words
# (e.g. "reduce exposure" before any bare "reduce"). Each pattern carries word
# boundaries so substrings inside larger words are left intact.
_TRADE_VERB_REWRITES: tuple[tuple[str, str], ...] = (
    ("reduce exposure to", "monitor downside risk in"),
    ("increase exposure to", "monitor upside potential in"),
    ("reduce exposure", "monitor downside risk"),
    ("increase exposure", "monitor upside potential"),
    ("rotate into", "watch relative strength in"),
    ("add to", "watch for confirmation in"),
    ("overweight", "favorable risk/reward in"),
    ("underweight", "unfavorable risk/reward in"),
    ("trim", "watch for weakness in"),
)

_TRADE_VERB_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(rf"\b{re.escape(verb)}\b", re.IGNORECASE), replacement)
    for verb, replacement in _TRADE_VERB_REWRITES
)


def _strip_trade_verbs(text: str) -> str:
    """Rewrite allocation/trade verbs in ``text`` into research/watchlist language."""
    for pattern, replacement in _TRADE_VERB_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _enforce_research_only_boundary(digest: DigestSnapshot) -> DigestSnapshot:
    """Strip position-oriented fields the LLM may still emit despite the skill boundary.

    ``thesis_tracker`` and ``portfolio_recommendations`` are zeroed (#859);
    trade/allocation verbs inside ``actionable_summary`` items are rewritten
    into research/watchlist language (#927) rather than dropped, so the
    research signal survives without an allocation directive.
    """
    rewritten_summary = [
        item.model_copy(
            update={
                "label": _strip_trade_verbs(item.label),
                "rationale": _strip_trade_verbs(item.rationale),
            }
        )
        for item in digest.actionable_summary
    ]
    return digest.model_copy(
        update={
            "thesis_tracker": "",
            "portfolio_recommendations": "",
            "actionable_summary": rewritten_summary,
        }
    )


def _digest_document_key(state: AtlasResearchState) -> str:
    if state.custom_prompt:
        return f"custom-research/{state.run_id}"
    if state.run_type == "delta":
        return "digest-delta"
    return "digest"


def _digest_triage_signal(state: AtlasResearchState) -> TriageSignal | None:
    if state.triage is None:
        return None
    if state.triage.decisions and all(d.decision == "carry" for d in state.triage.decisions):
        return TriageSignal(mode="quiet")
    return TriageSignal(mode="stale")


class _DigestPriorLoader:
    def __init__(self, state: AtlasResearchState, document_key: str) -> None:
        self._state = state
        self._document_key = document_key

    def load(self, artifact_key: tuple[str, str], run_date: date) -> PriorPublished | None:
        del artifact_key
        row = self._state.prior_context.latest_segments.get(self._document_key)
        if isinstance(row, dict):
            row_date = row.get("date")
            payload = row.get("payload")
            if isinstance(row_date, str) and isinstance(payload, dict):
                published = date.fromisoformat(row_date)
                if published < run_date:
                    return PriorPublished(
                        date=published,
                        document_key=self._document_key,
                        payload=dict(payload),
                    )
        if not self._state.prior_context.last_snapshots:
            return None
        snap_row = self._state.prior_context.last_snapshots[0]
        if not isinstance(snap_row, dict):
            return None
        snap_date = snap_row.get("date")
        snapshot = snap_row.get("snapshot")
        if not isinstance(snap_date, str) or not isinstance(snapshot, dict):
            return None
        published = date.fromisoformat(snap_date)
        if published >= run_date:
            return None
        return PriorPublished(
            date=published,
            document_key=self._document_key,
            payload=dict(snapshot),
        )


# Master-digest receives every fresh segment body on baseline runs — without
# compression the prompt can exceed the 64k context window of the reasoning-tier
# model (Jun-2026 incident: 68k–77k tokens → BadRequestError, Atlas crash, no
# Hermes book, dashboard stale for 3 days).
_DIGEST_TEXT_MAX = 400
_DIGEST_FINDING_SUMMARY_MAX = 200
_DIGEST_MAX_FINDINGS = 8
_DIGEST_MAX_SOURCES = 10


def _truncate_str(value: str, max_len: int) -> str:
    if len(value) <= max_len:
        return value
    return value[:max_len] + "..."


def _slim_segment_body(body: dict[str, Any]) -> dict[str, Any]:
    """Compress one segment body for master-digest synthesis inputs.

    Keeps the fields Phase 7 actually synthesizes from (stance, headline,
    findings, sources) and drops/truncates verbose prose so a baseline Sunday
    run with every segment fresh stays inside the model context window.
    """
    out: dict[str, Any] = {}
    for key in ("segment", "date", "bias", "headline", "data_quality", "regime_label"):
        if key in body:
            out[key] = body[key]

    findings = body.get("material_findings")
    if isinstance(findings, list):
        out["material_findings"] = [
            {
                "label": item.get("label", ""),
                "summary": _truncate_str(
                    str(item.get("summary", "")),
                    _DIGEST_FINDING_SUMMARY_MAX,
                ),
                "source_ids": item.get("source_ids", [])[:3]
                if isinstance(item.get("source_ids"), list)
                else [],
            }
            for item in findings[:_DIGEST_MAX_FINDINGS]
            if isinstance(item, dict)
        ]

    sources = body.get("sources")
    if isinstance(sources, list):
        out["sources"] = [
            {k: src[k] for k in ("id", "title", "url") if k in src}
            for src in sources[:_DIGEST_MAX_SOURCES]
            if isinstance(src, dict)
        ]

    notes = body.get("notes")
    if isinstance(notes, str) and notes:
        out["notes"] = _truncate_str(notes, _DIGEST_TEXT_MAX)

    for key, val in body.items():
        if key in out or key in ("material_findings", "sources", "notes"):
            continue
        if isinstance(val, str) and val:
            out[key] = _truncate_str(val, _DIGEST_TEXT_MAX)
        elif isinstance(val, (int, float, bool)) or val is None:
            out[key] = val

    return out


def _digest_shared_context(state: AtlasResearchState) -> dict[str, Any]:
    """Shared context for master-digest — slim by design.

    Phase inputs already carry the upstream segment bodies; the full
    ``data_layer`` ETF/macro dump and the multi-snapshot history are redundant
    here and were the main driver of the Jun-2026 context-overflow failures.
    """
    return _shared_context(state, data_layer_scope="none", slim_snapshots=True)


def _digest_phase_inputs(state: AtlasResearchState) -> dict[str, Any]:
    phase_inputs: dict[str, Any] = {
        "segment": "master-digest",
        "document_key": _digest_document_key(state),
        "bias_row": state.phase6_bias_row or {},
        "phase1": _bodies(state.phase1_outputs),
        "phase2": _bodies(state.phase2_outputs),
        "phase3": _body(state.phase3_output),
        "phase4": _bodies(state.phase4_outputs),
        "phase5": _bodies(state.phase5_outputs),
    }
    if state.custom_prompt:
        phase_inputs["custom_prompt"] = state.custom_prompt
    return phase_inputs


def _finalize_digest(state: AtlasResearchState, body: dict[str, Any]) -> dict[str, Any]:
    result = DigestSnapshot.model_validate(body)
    overrides: dict[str, Any] = {"segment_freshness": _segment_freshness(state)}
    if not result.regime_label:
        overrides["regime_label"] = _regime_label_from_phase3(state)
    digest = _enforce_research_only_boundary(result.model_copy(update=overrides))
    merged = digest.model_dump(mode="json")
    merged["date"] = state.run_date.isoformat()
    return merged


def _carry_prior_digest(state: AtlasResearchState, prior: PriorPublished) -> dict[str, Any]:
    body = dict(prior.payload)
    return _finalize_digest(state, body)


def _prior_is_valid_digest(prior: PriorPublished) -> bool:
    try:
        DigestSnapshot.model_validate(prior.payload)
    except Exception:
        return False
    return True


def _carry_prior_digest_or_raise(
    state: AtlasResearchState, document_key: str, exc: Exception
) -> dict[str, Any]:
    """Fail-soft degrade: carry a valid prior digest instead of aborting Atlas."""
    prior = _DigestPriorLoader(state, document_key).load(
        ("digest", document_key), state.run_date
    )
    if prior is not None and _prior_is_valid_digest(prior):
        logger.warning(
            "master-digest failed (%s: %s); carrying prior digest from %s",
            type(exc).__name__,
            exc,
            prior.date.isoformat(),
        )
        return {
            "phase7_digest": _carry_prior_digest(state, prior),
            "errors": [
                PhaseError(
                    phase="phase7_synthesis",
                    node="master-digest",
                    message=f"{type(exc).__name__}: {exc}"[:500],
                    retryable=True,
                )
            ],
        }
    raise exc


def _synthesis_node(state: AtlasResearchState) -> dict[str, Any]:
    document_key = _digest_document_key(state)
    mode = resolve_edit_mode(
        artifact_key=("digest", document_key),
        run_date=state.run_date,
        prior_loader=_DigestPriorLoader(state, document_key),
        triage=_digest_triage_signal(state),
        force_full_rewrite=refresh_scope_forces_full(state.refresh_scope, artifact="digest"),
    )
    phase_inputs = _digest_phase_inputs(state)
    shared = _digest_shared_context(state)

    if mode == "skip":
        prior = _DigestPriorLoader(state, document_key).load(
            ("digest", document_key), state.run_date
        )
        if prior is not None and _prior_is_valid_digest(prior):
            return {"phase7_digest": _carry_prior_digest(state, prior)}

    if mode == "edit":
        prior = _DigestPriorLoader(state, document_key).load(
            ("digest", document_key), state.run_date
        )
        if prior is not None and _prior_is_valid_digest(prior):
            skill_text = load_skill_edit("digest")
            edit_inputs = _edit_phase_inputs(
                base_inputs=phase_inputs,
                prior=prior,
                triage_reason="digest_edit",
            )
            try:
                patch = run_research_agent(
                    skill_text=skill_text,
                    phase_inputs=edit_inputs,
                    shared_context=shared,
                    output_model=DocumentPatch,
                    phase_slug="master-digest",
                )
            except Exception as exc:  # noqa: BLE001 — observable degrade, not a swallow
                return _carry_prior_digest_or_raise(state, document_key, exc)
            if not isinstance(patch, DocumentPatch):
                msg = f"digest edit expected DocumentPatch, got {type(patch).__name__}"
                raise TypeError(msg)
            try:
                merge_result = merge_document_patch(prior.payload, patch)
                digest = _finalize_digest(state, merge_result.materialized)
            except (MergeError, Exception) as exc:
                logger.warning("digest edit merge failed (%s); falling back to full", exc)
            else:
                if patch.status == "updated" and patch.ops:
                    return {
                        "phase7_digest": digest,
                        "document_deltas": {
                            document_key: merge_result.delta.model_dump(mode="json")
                        },
                    }

    skill_text = load_skill("digest")
    try:
        result = run_research_agent(
            skill_text=skill_text,
            phase_inputs=phase_inputs,
            shared_context=shared,
            output_model=DigestSnapshot,
            phase_slug="master-digest",
        )
    except Exception as exc:  # noqa: BLE001 — observable degrade, not a swallow
        return _carry_prior_digest_or_raise(state, document_key, exc)
    return {"phase7_digest": _finalize_digest(state, result.model_dump(mode="json"))}


def _regime_label_from_phase3(state: AtlasResearchState) -> str:
    """Return the short regime token from phase3's macro body (fail-soft to empty string)."""
    if state.phase3_output is None or state.phase3_output.payload.source != "today":
        return ""
    return str(state.phase3_output.payload.body.get("regime_label") or "")  # type: ignore[union-attr]


def _body(slot: Any) -> dict[str, Any]:
    if slot is None or slot.payload.source != "today":
        return {}
    return _slim_segment_body(dict(slot.payload.body))


def _bodies(bag: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return only today-source segment bodies (parity with ``_body``).

    On delta runs, carried (``source != "today"``) slots are baseline
    segments. Feeding them back into Phase 7 makes the digest re-synthesize
    unchanged baseline material, violating the research-only / delta boundary
    (ADR-0015). Carried provenance is still surfaced via ``segment_freshness``,
    which is derived from full state — not from this digest-input map.

    Bodies are slimmed before serialization so baseline runs with every segment
    fresh stay inside the reasoning-tier model context window.
    """
    return {
        slug: {
            **{k: v for k, v in slot.payload.model_dump(mode="json").items() if k != "body"},
            "body": _slim_segment_body(slot.payload.body),
        }
        for slug, slot in bag.items()
        if slot.payload.source == "today"
    }


def build_phase7() -> PipelinePhase:
    return PipelinePhase(
        name="phase7_synthesis",
        nodes=[NodeSpec(name="master-digest", run=_synthesis_node)],
    )


__all__ = [
    "ActionableItem",
    "DigestSnapshot",
    "RiskItem",
    "SegmentFreshness",
    "build_phase7",
    "_enforce_research_only_boundary",
    "_slim_segment_body",
]
