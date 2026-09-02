"""Phase 7 — digest subsection fan-out + markdown stitcher.

Research-only: topical subsection agents write markdown; the stitcher assembles
one long briefing. Portfolio positioning, thesis lifecycle, and trade
recommendations are portfolio's domain (phases 7C–7E).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal  # score:allow untyped any — used for JSON-derived dict shape

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase
from digigraph.graph.research_agent import run_research_agent
from pydantic import BaseModel, ConfigDict, Field, model_validator

from digiquant.dashboard.edit_mode import DocumentPatch, MergeError, merge_document_patch
from digiquant.dashboard.edit_mode.content_identity import (
    UNCHANGED_FLAG_KEY,
    UNCHANGED_SINCE_KEY,
)
from digiquant.dashboard.edit_mode.models import TriageSignal
from digiquant.dashboard.edit_mode.prior import PriorPublished
from digiquant.dashboard.edit_mode.resolve import resolve_edit_mode
from digiquant.dashboard.research_retrieval.planner import AttentionRolloutMode
from digiquant.research.phases._node_factory import (
    _edit_phase_inputs,
    _shared_context,
)
from digiquant.research.research_attention import (
    apply_digest_metric_patch,
    artifact_target_key,
    research_attention_enforce_path,
    resolve_attention_plan_for_node,
    resolve_research_attention_rollout_mode,
)
from digiquant.research.segments import (
    Source,
    compose_legacy_digest_body,
    compose_legacy_research_body,
)
from digiquant.research.skills import load_skill, load_skill_edit
from digiquant.research.state import (
    PhaseError,
    ResearchState,
    refresh_scope_forces_full,
)

logger = logging.getLogger(__name__)


class SegmentFreshness(BaseModel):
    """Per-segment provenance marker used by the dashboard.

    ``frozen`` (#1749) means the segment *was* regenerated today and the merge changed
    nothing, so the body is byte-identical to an earlier one and ``as_of`` is the date that
    content last materially changed — not the run date. It is distinct from ``baseline``,
    which means the segment was not regenerated at all (an explicit ``Carried`` slot).

    Keep this in lockstep with :class:`digiquant.research.snapshot.SegmentFreshness`,
    which validates rows on the *read* path with ``extra="forbid"`` and would reject a value
    this model can emit but that one cannot accept.
    """

    source: Literal["today", "baseline", "frozen"]
    as_of: str = Field(description="ISO date")


class ActionableItem(BaseModel):
    priority: int = Field(ge=1, le=5)
    label: str = Field()
    rationale: str = Field()


# Live digest edit merge (house GHA 33426508863) sent ``horizon_hourse``.


def _alias_horizon_hours_payload(data: object) -> object:
    if not isinstance(data, Mapping):
        return data
    if "horizon_hourse" not in data:
        return data
    out = dict(data)
    out["horizon_hours"] = out.pop("horizon_hourse")
    return out


class RiskItem(BaseModel):
    horizon_hours: int = Field(ge=1, le=168)
    label: str = Field()
    trigger: str = Field()

    @model_validator(mode="before")
    @classmethod
    def _alias_horizon_hours(cls, data: object) -> object:
        return _alias_horizon_hours_payload(data)


class DigestSnapshot(BaseModel):
    """Phase 7 master briefing — markdown ``body`` plus a thin envelope."""

    model_config = ConfigDict(extra="allow")

    segment: str = Field(default="master-digest")
    date: date
    body: str = Field(
        default="",
        description="Stitched markdown briefing with topical headings and inline links.",
    )
    regime_label: str = Field(
        default="",
        description=(
            "Short regime token, e.g. 'Risk-on / Policy easing' — "
            "NOT a restatement of the regime section."
        ),
    )
    sources: list[Source] = Field(default_factory=list)
    segment_freshness: dict[str, SegmentFreshness] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _compose_legacy_body(cls, data: object) -> object:
        if not isinstance(data, Mapping):
            return data
        if str(data.get("body") or "").strip():
            return data
        composed = compose_legacy_digest_body(data)
        if not composed.strip():
            return data
        out = dict(data)
        out["body"] = composed
        return out


class DigestSubsection(BaseModel):
    """One topical digest subsection (macro, alt-data, …)."""

    model_config = ConfigDict(extra="allow")

    slug: str
    date: date
    body: str = Field(default="")
    sources: list[Source] = Field(default_factory=list)


@dataclass(frozen=True)
class DigestSubsectionSpec:
    slug: str
    heading: str
    phase: Literal["phase1", "phase2", "phase3", "phase4", "phase5"]


DIGEST_SUBSECTION_SPECS: tuple[DigestSubsectionSpec, ...] = (
    DigestSubsectionSpec("macro", "Macro", "phase3"),
    DigestSubsectionSpec("alt-data", "Alt-data", "phase1"),
    DigestSubsectionSpec("institutional", "Institutional", "phase2"),
    DigestSubsectionSpec("asset-classes", "Asset classes", "phase4"),
    DigestSubsectionSpec("us-equities", "US equities", "phase5"),
)


def _slot_freshness(payload: object) -> SegmentFreshness:
    """One slot's freshness marker, derived from the slot — never from the LLM."""
    structural_as_of = getattr(payload, "as_of", None) or getattr(payload, "baseline_date", None)
    as_of = structural_as_of.isoformat() if structural_as_of else ""
    if getattr(payload, "source", None) != "today":
        return SegmentFreshness(source="baseline", as_of=as_of)
    body = getattr(payload, "body", None)
    if isinstance(body, dict) and body.get(UNCHANGED_FLAG_KEY):
        since = body.get(UNCHANGED_SINCE_KEY)
        return SegmentFreshness(
            source="frozen", as_of=since if isinstance(since, str) and since else as_of
        )
    return SegmentFreshness(source="today", as_of=as_of)


def _segment_freshness(state: ResearchState) -> dict[str, SegmentFreshness]:
    """Derive the freshness map from state — does not rely on the LLM."""
    out: dict[str, SegmentFreshness] = {}
    for bag in (
        state.phase1_outputs,
        state.phase2_outputs,
        state.phase4_outputs,
        state.phase5_outputs,
    ):
        for slug, slot in bag.items():
            out[slug] = _slot_freshness(slot.payload)
    if state.phase3_output is not None:
        out["macro"] = _slot_freshness(state.phase3_output.payload)
    return out


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
    """Strip trade/allocation verbs from the briefing body (ADR-0015)."""
    return digest.model_copy(update={"body": _strip_trade_verbs(digest.body)})


def _digest_document_key(state: ResearchState) -> str:
    if state.custom_prompt:
        return f"custom-research/{state.run_id}"
    if state.run_type == "delta":
        return "digest-delta"
    return "digest"


def _digest_triage_signal(state: ResearchState) -> TriageSignal | None:
    if state.triage is None:
        return None
    if state.triage.decisions and all(d.decision == "carry" for d in state.triage.decisions):
        return TriageSignal(mode="quiet")
    return TriageSignal(mode="stale")


class _DigestPriorLoader:
    def __init__(self, state: ResearchState, document_key: str) -> None:
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


_DIGEST_MODEL_CONTEXT_TOKENS = 64_000
_DIGEST_NON_SEGMENT_RESERVE_TOKENS = 24_000
_DIGEST_CHARS_PER_TOKEN = 3
_DIGEST_SEGMENT_INPUTS_BUDGET_CHARS = (
    _DIGEST_MODEL_CONTEXT_TOKENS - _DIGEST_NON_SEGMENT_RESERVE_TOKENS
) * _DIGEST_CHARS_PER_TOKEN
_DIGEST_SEGMENT_MIN_CHARS = 1_200
_DIGEST_BODY_MAX = 8_000
# Full prior briefing, not the #1559 300-char slim — still bounded for context.
_DIGEST_PRIOR_BODY_MAX = 24_000

_DIGEST_CONTEXT_KEYS: tuple[str, ...] = ("digest", "digest-delta")
_PUBLISHED_DIGEST_KEYS: tuple[str, ...] = (
    "segment",
    "date",
    "body",
    "regime_label",
    "sources",
    "segment_freshness",
)
_DIGEST_PASSTHROUGH_KEYS: tuple[str, ...] = (
    "metric_patch",
    "structured_price_deltas",
    "carried_from",
    "continuity",
)


def _truncate_str(value: str, max_len: int) -> str:
    if len(value) <= max_len:
        return value
    return value[:max_len] + "..."


def _slim_segment_body(body: dict[str, Any], char_budget: int) -> dict[str, Any]:
    """Compress one segment body for digest-subsection inputs under ``char_budget``."""
    working = dict(body)
    md = working.get("body")
    if not (isinstance(md, str) and md.strip()):
        composed = compose_legacy_research_body(working)
        if composed:
            working["body"] = composed
        if working.get("internal_bias") is None and working.get("bias") is not None:
            working["internal_bias"] = working["bias"]

    out: dict[str, Any] = {}
    for key in ("segment", "date", "internal_bias", "regime_label"):
        if key not in working:
            continue
        val = working[key]
        if isinstance(val, (str, int, float, bool)) or val is None:
            out[key] = val

    def _fits(candidate: dict[str, Any]) -> bool:
        return len(json.dumps(candidate, default=str, sort_keys=True)) <= char_budget

    memo = working.get("body")
    if isinstance(memo, str) and memo.strip():
        identity_chars = len(json.dumps(out, default=str, sort_keys=True))
        source_reserve = 180
        room = max(80, char_budget - identity_chars - source_reserve)
        out["body"] = _truncate_str(memo, min(_DIGEST_BODY_MAX, room))
        while not _fits(out) and len(out["body"]) > 80:
            out["body"] = _truncate_str(out["body"][:-3], max(80, len(out["body"]) // 2))

    sources = working.get("sources")
    if isinstance(sources, list):
        kept_sources: list[dict[str, Any]] = []
        for src in sources:
            if not isinstance(src, dict):
                continue
            trimmed_src = {k: src[k] for k in ("id", "title", "url") if k in src}
            if not _fits({**out, "sources": [*kept_sources, trimmed_src]}):
                break
            kept_sources.append(trimmed_src)
        if kept_sources:
            out["sources"] = kept_sources
    return out


def _count_today_segments(state: ResearchState) -> int:
    """Count freshly-generated (``source == "today"``) phase-1..5 segments."""
    total = 0
    for bag in (
        state.phase1_outputs,
        state.phase2_outputs,
        state.phase4_outputs,
        state.phase5_outputs,
    ):
        total += sum(1 for slot in bag.values() if slot.payload.source == "today")
    if state.phase3_output is not None and state.phase3_output.payload.source == "today":
        total += 1
    return total


def _per_segment_char_budget(segment_count: int) -> int:
    if segment_count <= 0:
        return _DIGEST_SEGMENT_INPUTS_BUDGET_CHARS
    return max(_DIGEST_SEGMENT_MIN_CHARS, _DIGEST_SEGMENT_INPUTS_BUDGET_CHARS // segment_count)


def _full_prior_digest_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep a full prior briefing body (not the #1559 300-char slim)."""
    body = payload.get("body")
    if not (isinstance(body, str) and body.strip()):
        body = compose_legacy_digest_body(payload)
    out: dict[str, Any] = {}
    date_s = payload.get("date")
    if date_s is not None and str(date_s).strip():
        out["date"] = str(date_s)
    regime = payload.get("regime_label")
    if isinstance(regime, str) and regime.strip():
        out["regime_label"] = regime
    if isinstance(body, str) and body.strip():
        out["body"] = _truncate_str(body.strip(), _DIGEST_PRIOR_BODY_MAX)
    return out


def _prior_digest_bodies(state: ResearchState, limit: int = 2) -> list[dict[str, Any]]:
    """Last ``limit`` full digest briefings, most recent first."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    run_iso = state.run_date.isoformat()

    def _consider(date_str: object, payload: object) -> None:
        if not isinstance(date_str, str) or not date_str or date_str in seen:
            return
        if date_str >= run_iso:
            return
        if not isinstance(payload, dict):
            return
        slim = _full_prior_digest_payload(payload)
        if not slim.get("body"):
            return
        slim["date"] = date_str
        seen.add(date_str)
        out.append(slim)

    for snap in state.prior_context.last_snapshots:
        if len(out) >= limit:
            break
        if isinstance(snap, dict):
            _consider(snap.get("date"), snap.get("snapshot") or {})
    for key in _DIGEST_CONTEXT_KEYS:
        if len(out) >= limit:
            break
        row = state.prior_context.latest_segments.get(key)
        if isinstance(row, dict):
            _consider(row.get("date"), row.get("payload") or {})
    return out[:limit]


def _digest_shared_context(state: ResearchState) -> dict[str, Any]:
    """Shared context for digest nodes — digest keys plus full prior briefing bodies."""
    shared = _shared_context(
        state,
        context_keys=_DIGEST_CONTEXT_KEYS,
        data_layer_scope="none",
        slim_snapshots=True,
    )
    latest = shared.get("prior_context", {}).get("latest_segments")
    if isinstance(latest, dict):
        for row in latest.values():
            if isinstance(row, dict) and isinstance(row.get("payload"), dict):
                row["payload"] = _full_prior_digest_payload(row["payload"])
    prior_block = shared.setdefault("prior_context", {})
    if isinstance(prior_block, dict):
        prior_block["prior_digests"] = _prior_digest_bodies(state, limit=2)
    return shared


def _subsection_payloads(state: ResearchState) -> dict[str, dict[str, Any]]:
    return {
        slug: dict(payload)
        for slug, payload in state.phase7_subsection_outputs.items()
        if isinstance(payload, dict)
    }


def _digest_phase_inputs(state: ResearchState) -> dict[str, Any]:
    """Stitcher inputs: subsections + two full prior briefings + bias row."""
    phase_inputs: dict[str, Any] = {
        "segment": "master-digest",
        "document_key": _digest_document_key(state),
        "bias_row": state.phase6_bias_row or {},
        "subsections": _subsection_payloads(state),
        "prior_digests": _prior_digest_bodies(state, limit=2),
    }
    if state.custom_prompt:
        phase_inputs["custom_prompt"] = state.custom_prompt
    return phase_inputs


def _subsection_phase_inputs(slug: str, state: ResearchState) -> dict[str, Any]:
    spec = next(s for s in DIGEST_SUBSECTION_SPECS if s.slug == slug)
    per_segment = _per_segment_char_budget(_count_today_segments(state))
    inputs: dict[str, Any] = {
        "segment": f"digest-{slug}",
        "subsection": slug,
        "prior_digests": _prior_digest_bodies(state, limit=2),
    }
    if spec.phase == "phase1":
        inputs["phase1"] = _bodies(state.phase1_outputs, per_segment)
    elif spec.phase == "phase2":
        inputs["phase2"] = _bodies(state.phase2_outputs, per_segment)
    elif spec.phase == "phase3":
        inputs["phase3"] = _body(state.phase3_output, per_segment)
    elif spec.phase == "phase4":
        inputs["phase4"] = _bodies(state.phase4_outputs, per_segment)
    else:
        inputs["phase5"] = _bodies(state.phase5_outputs, per_segment)
    if state.custom_prompt:
        inputs["custom_prompt"] = state.custom_prompt
    return inputs


def _published_digest_fields(merged: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {k: merged[k] for k in _PUBLISHED_DIGEST_KEYS if k in merged}
    for key in _DIGEST_PASSTHROUGH_KEYS:
        if key in merged:
            out[key] = merged[key]
    return out


def _fallback_stitch(state: ResearchState, date_str: str) -> str:
    parts = [f"# Daily Digest — {date_str}", ""]
    for spec in DIGEST_SUBSECTION_SPECS:
        sub = state.phase7_subsection_outputs.get(spec.slug) or {}
        body = str(sub.get("body") or "").strip() if isinstance(sub, dict) else ""
        if body:
            parts.extend([body, ""])
    return "\n".join(parts).strip() + "\n"


def _finalize_digest(state: ResearchState, body: dict[str, Any]) -> dict[str, Any]:
    result = DigestSnapshot.model_validate(body)
    overrides: dict[str, Any] = {
        "segment_freshness": _segment_freshness(state),
        "segment": "master-digest",
    }
    if not result.regime_label:
        overrides["regime_label"] = _regime_label_from_phase3(state)
    digest = _enforce_research_only_boundary(result.model_copy(update=overrides))
    merged = digest.model_dump(mode="json")
    merged["date"] = state.run_date.isoformat()
    if not str(merged.get("body") or "").strip():
        merged["body"] = _fallback_stitch(state, merged["date"])
    return _published_digest_fields(merged)


def _carry_prior_digest(state: ResearchState, prior: PriorPublished) -> dict[str, Any]:
    body = dict(prior.payload)
    return _finalize_digest(state, body)


def _prior_is_valid_digest(prior: PriorPublished) -> bool:
    try:
        DigestSnapshot.model_validate(prior.payload)
    except Exception:
        return False
    return True


def _carry_prior_digest_or_raise(
    state: ResearchState, document_key: str, exc: Exception
) -> dict[str, Any]:
    """Fail-soft degrade: carry a valid prior digest instead of aborting research."""
    prior = _DigestPriorLoader(state, document_key).load(("digest", document_key), state.run_date)
    if prior is not None and _prior_is_valid_digest(prior):
        logger.warning(
            "master-digest failed (%s: %s); carrying prior digest from %s",
            type(exc).__name__,
            exc,
            prior.date.isoformat(),
        )
        carried = _carry_prior_digest(state, prior)
        carried["carried_from"] = prior.date.isoformat()
        carried["continuity"] = f"carried_forward from {prior.date.isoformat()} (synthesis failed)"
        note = f"*Note: {carried['continuity']}*"
        existing = str(carried.get("body") or "").rstrip()
        if note not in existing:
            carried["body"] = f"{existing}\n\n{note}\n" if existing else f"{note}\n"
        return {
            "phase7_digest": carried,
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


def _digest_skips_llm(state: ResearchState) -> bool:
    """True when quiet-day / attention carry would skip the stitcher LLM."""
    document_key = _digest_document_key(state)
    rollout = resolve_research_attention_rollout_mode()
    if rollout is not AttentionRolloutMode.OFF and not state.custom_prompt:
        resolve_attention_plan_for_node(state)
    target_key = artifact_target_key("digest", document_key)
    enforce_path = research_attention_enforce_path(state, target_key=target_key)
    loader = _DigestPriorLoader(state, document_key)
    if enforce_path in {"carry", "metric_patch"}:
        prior = loader.load(("digest", document_key), state.run_date)
        return prior is not None and _prior_is_valid_digest(prior)
    mode = resolve_edit_mode(
        artifact_key=("digest", document_key),
        run_date=state.run_date,
        prior_loader=loader,
        triage=_digest_triage_signal(state),
        force_full_rewrite=refresh_scope_forces_full(state.refresh_scope, artifact="digest"),
    )
    if mode == "skip":
        prior = loader.load(("digest", document_key), state.run_date)
        return prior is not None and _prior_is_valid_digest(prior)
    return False


def _subsection_node(slug: str):
    def _run(state: ResearchState) -> dict[str, Any]:
        if _digest_skips_llm(state):
            return {}
        skill_text = load_skill("digest-subsection")
        try:
            result = run_research_agent(
                skill_text=skill_text,
                phase_inputs=_subsection_phase_inputs(slug, state),
                shared_context=_digest_shared_context(state),
                output_model=DigestSubsection,
                phase_slug=f"digest-{slug}",
            )
        except Exception as exc:  # observable degrade — stitcher can still fall back
            logger.warning("digest subsection %s failed (%s: %s)", slug, type(exc).__name__, exc)
            return {
                "errors": [
                    PhaseError(
                        phase="phase7_subsections",
                        node=f"digest-{slug}",
                        message=f"{type(exc).__name__}: {exc}"[:500],
                        retryable=True,
                    )
                ]
            }
        dumped = result.model_dump(mode="json")
        dumped["slug"] = slug
        dumped["date"] = state.run_date.isoformat()
        dumped["body"] = _strip_trade_verbs(str(dumped.get("body") or ""))
        return {"phase7_subsection_outputs": {slug: dumped}}

    return _run


def _stitch_node(state: ResearchState) -> dict[str, Any]:
    document_key = _digest_document_key(state)
    rollout = resolve_research_attention_rollout_mode()
    if rollout is not AttentionRolloutMode.OFF and not state.custom_prompt:
        resolve_attention_plan_for_node(state)
    target_key = artifact_target_key("digest", document_key)
    enforce_path = research_attention_enforce_path(state, target_key=target_key)
    if enforce_path == "carry":
        prior = _DigestPriorLoader(state, document_key).load(
            ("digest", document_key), state.run_date
        )
        if prior is not None and _prior_is_valid_digest(prior):
            return {"phase7_digest": _carry_prior_digest(state, prior)}
    if enforce_path == "metric_patch":
        prior = _DigestPriorLoader(state, document_key).load(
            ("digest", document_key), state.run_date
        )
        if prior is not None and _prior_is_valid_digest(prior):
            return {
                "phase7_digest": _finalize_digest(state, apply_digest_metric_patch(state, prior))
            }
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
            except Exception as exc:  # observable degrade, not a swallow
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
    except Exception as exc:  # observable degrade, not a swallow
        return _carry_prior_digest_or_raise(state, document_key, exc)
    return {"phase7_digest": _finalize_digest(state, result.model_dump(mode="json"))}


_synthesis_node = _stitch_node


def _regime_label_from_phase3(state: ResearchState) -> str:
    """Return the short regime token from phase3's macro body (fail-soft to empty string)."""
    if state.phase3_output is None or state.phase3_output.payload.source != "today":
        return ""
    return str(state.phase3_output.payload.body.get("regime_label") or "")  # type: ignore[union-attr]


def _body(slot: Any, char_budget: int) -> dict[str, Any]:
    if slot is None or slot.payload.source != "today":
        return {}
    return _slim_segment_body(dict(slot.payload.body), char_budget)


def _bodies(bag: dict[str, Any], char_budget: int) -> dict[str, dict[str, Any]]:
    """Return only today-source segment bodies (parity with ``_body``)."""
    return {
        slug: {
            **{k: v for k, v in slot.payload.model_dump(mode="json").items() if k != "body"},
            "body": _slim_segment_body(slot.payload.body, char_budget),
        }
        for slug, slot in bag.items()
        if slot.payload.source == "today"
    }


def build_phase7_subsections() -> PipelinePhase:
    return PipelinePhase(
        name="phase7_subsections",
        nodes=[
            NodeSpec(name=f"digest-{spec.slug}", run=_subsection_node(spec.slug))
            for spec in DIGEST_SUBSECTION_SPECS
        ],
    )


def build_phase7_stitch() -> PipelinePhase:
    return PipelinePhase(
        name="phase7_synthesis",
        nodes=[NodeSpec(name="master-digest", run=_stitch_node)],
    )


def build_phase7() -> list[PipelinePhase]:
    return [build_phase7_subsections(), build_phase7_stitch()]


__all__ = [
    "ActionableItem",
    "DIGEST_SUBSECTION_SPECS",
    "DigestSnapshot",
    "DigestSubsection",
    "RiskItem",
    "SegmentFreshness",
    "build_phase7",
    "_digest_phase_inputs",
    "_digest_shared_context",
    "_enforce_research_only_boundary",
    "_prior_digest_bodies",
    "_slim_segment_body",
    "_subsection_phase_inputs",
    "_synthesis_node",
]
