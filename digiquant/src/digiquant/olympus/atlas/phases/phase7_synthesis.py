"""Phase 7 — master digest synthesis (single LLM node)."""

from __future__ import annotations

from typing import Any, Literal  # noqa: F401 — used for JSON-derived dict shape

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase
from pydantic import BaseModel, Field

from digiquant.olympus.atlas.phases._node_factory import _shared_context
from digiquant.olympus.atlas.segments import SegmentReport
from digiquant.olympus.atlas.state import AtlasResearchState


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
    thesis_tracker: str = Field(default="")
    portfolio_recommendations: str = Field(default="")
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


def _thesis_tracker_from_state(state: AtlasResearchState) -> str:
    """Derive a thesis_tracker paragraph from active theses in prior_context (#814).

    Returns an empty string when no active theses are present so the field is
    omitted from the rendered digest (same as the LLM's default). This function
    is used as a post-generation fallback: when the LLM left thesis_tracker empty
    despite active theses being present, we fill it deterministically so the
    dashboard always reflects the real thesis state.
    """
    theses = state.prior_context.active_theses
    if not theses:
        return ""
    parts: list[str] = []
    for t in theses:
        name = t.get("thesis") or t.get("name") or t.get("ticker") or "Unknown"
        status = t.get("status") or "active"
        inv = t.get("invalidation") or ""
        line = f"{name}: {status}"
        if inv:
            line += f" — invalidation: {inv}"
        parts.append(line)
    return "; ".join(parts)


def _book_tickers(state: AtlasResearchState) -> list[str]:
    """Return the executed-book tickers from state.phase7d_rebalance (#814).

    Empty list when no rebalance decision is present (Atlas-only or monthly runs).
    """
    reb = state.phase7d_rebalance
    if not reb:
        return []
    return [row["ticker"] for row in (reb.get("recommended_portfolio") or []) if row.get("ticker")]


def _reconcile_portfolio_recommendations(text: str, book_tickers: list[str]) -> str:
    """Post-generation sanity check: ensure the narrative mentions only book tickers (#814).

    If the text contains tickers NOT in the book (e.g. XLK/QQQ/XLF when the book is
    SPY/IJR/XLP), append an explicit correction note so readers are never misled by
    the LLM hallucinating out-of-book names. This is a belt-and-suspenders guard,
    not a rewrite — the narrative prose is kept intact, only a correction suffix is
    added if needed.
    """
    if not book_tickers or not text:
        return text
    # Scan the text for any all-caps token of 1–5 letters that looks like a ticker but
    # is absent from the book. This is heuristic: it catches obvious fabrications (XLK,
    # QQQ, XLF) without penalising prose words like "US" or "ETF".
    import re

    book_set = set(book_tickers)
    # Common known non-ticker uppercase abbreviations to skip
    _NOT_TICKERS = frozenset(
        {
            "US",
            "ETF",
            "PM",
            "GDP",
            "CPI",
            "PCE",
            "FED",
            "FOMC",
            "USD",
            "EUR",
            "DXY",
            "EM",
            "DM",
            "HF",
            "YTD",
            "MOM",
            "QOQ",
            "YOY",
            "NAV",
            "AUM",
            "ESG",
            "EPS",
            "PE",
            "PB",
            "ROE",
            "ATH",
        }
    )
    found_off_book = [
        m
        for m in re.findall(r"\b([A-Z]{1,5})\b", text)
        if m not in book_set and m not in _NOT_TICKERS and len(m) >= 2
    ]
    if not found_off_book:
        return text
    # Distinct, order-preserving
    seen: set[str] = set()
    off_book_unique = [t for t in found_off_book if t not in seen and not seen.add(t)]  # type: ignore[func-returns-value]
    book_str = ", ".join(book_tickers) if book_tickers else "cash only"
    return (
        text + f" [Note: executed book is {book_str};"
        f" references to {', '.join(off_book_unique)} are not in the current portfolio.]"
    )


def _synthesis_node(state: AtlasResearchState) -> dict[str, Any]:
    from digigraph.graph.research_agent import run_research_agent

    from digiquant.olympus.atlas.skills import load_skill

    skill_text = load_skill("digest")
    # Ground the digest prompt in the book (#814): inject the executed-book
    # tickers and active theses so the LLM has the raw facts it needs to write
    # accurate thesis_tracker and portfolio_recommendations sections.
    book_tickers = _book_tickers(state)
    phase_inputs: dict[str, Any] = {
        "segment": "master-digest",
        "bias_row": state.phase6_bias_row or {},
        "phase1": _bodies(state.phase1_outputs),
        "phase2": _bodies(state.phase2_outputs),
        "phase3": _body(state.phase3_output),
        "phase4": _bodies(state.phase4_outputs),
        "phase5": _bodies(state.phase5_outputs),
        # Executed book (tickers + target_pct) for portfolio_recommendations.
        # Empty list on Atlas-only / monthly runs.
        "executed_book": state.phase7d_rebalance.get("recommended_portfolio", [])
        if state.phase7d_rebalance
        else [],
        # Active theses for thesis_tracker. The LLM must ground its text in these.
        "active_theses": state.prior_context.active_theses,
    }
    # Custom research prompt threading (#313). Surfaced as an explicit
    # ``custom_prompt`` field rather than mixed into ``bias_row`` so the
    # digest skill can detect and prioritize it. Absent on routine runs.
    if state.custom_prompt:
        phase_inputs["custom_prompt"] = state.custom_prompt
    result = run_research_agent(
        skill_text=skill_text,
        phase_inputs=phase_inputs,
        shared_context=_shared_context(state),
        output_model=DigestSnapshot,
        phase_slug="master-digest",
    )
    # Overwrite the LLM-proposed freshness map with the deterministic one.
    # The LLM is prone to inferring freshness incorrectly on delta runs;
    # state is authoritative.
    overrides: dict[str, Any] = {"segment_freshness": _segment_freshness(state)}
    # Deterministically backfill regime_label when the LLM omitted it.
    # Phase 3's macro body carries the authoritative short regime token; the
    # digest skill is asked to copy it but may leave the field empty.
    if not result.regime_label:
        overrides["regime_label"] = _regime_label_from_phase3(state)
    # Post-generation reconciliation (#814):
    # (a) thesis_tracker — if the LLM left it empty but active theses are present,
    #     fill it deterministically from prior_context.active_theses.
    if not result.thesis_tracker and state.prior_context.active_theses:
        overrides["thesis_tracker"] = _thesis_tracker_from_state(state)
    # (b) portfolio_recommendations — assert the narrative only references book
    #     tickers; append a correction note if the LLM hallucinated out-of-book names.
    if result.portfolio_recommendations and book_tickers:
        reconciled = _reconcile_portfolio_recommendations(
            result.portfolio_recommendations, book_tickers
        )
        if reconciled != result.portfolio_recommendations:
            overrides["portfolio_recommendations"] = reconciled
    digest = result.model_copy(update=overrides)
    return {"phase7_digest": digest.model_dump(mode="json")}


def _regime_label_from_phase3(state: AtlasResearchState) -> str:
    """Return the short regime token from phase3's macro body (fail-soft to empty string)."""
    if state.phase3_output is None or state.phase3_output.payload.source != "today":
        return ""
    return str(state.phase3_output.payload.body.get("regime_label") or "")  # type: ignore[union-attr]


def _body(slot: Any) -> dict[str, Any]:
    if slot is None or slot.payload.source != "today":
        return {}
    return dict(slot.payload.body)


def _bodies(bag: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {slug: slot.payload.model_dump(mode="json") for slug, slot in bag.items()}


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
    "_book_tickers",
    "_reconcile_portfolio_recommendations",
    "_thesis_tracker_from_state",
]
