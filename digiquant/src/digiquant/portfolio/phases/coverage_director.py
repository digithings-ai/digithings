"""Coverage director (PM role, between H4 and H5) — #3739.

H4 builds the deterministic focus roster (held + thesis-mapped + technicals).
The director decides which rostered tickers actually get fresh analysis today:
refresh (reassessment needed), explore (new candidate worth analyzing), or skip
(rely on analysis history — downstream H5/H6 carry prior with 0 LLM).

The director proposes; ``apply_coverage`` disposes deterministically: it can
only narrow the H4 roster, never widen it. Unknown directive tickers are
dropped, and rostered tickers the directive omits are excluded.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import (  # score:allow untyped any — scored-lint: heterogeneous phase-input dicts
    Any,
    Literal,
)

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase
from pydantic import BaseModel, Field, field_validator, model_validator

from digiquant.dashboard.overlay.persist import portfolio_document_key
from digiquant.portfolio.candidates import holdings_from_prior_book
from digiquant.portfolio.skills import load_skill_full
from digiquant.portfolio.state import PortfolioState
from digiquant.research.phases._node_factory import _shared_context
from digiquant.research.state import ExcludedTicker, FocusRosterEntry, PhaseError
from digiquant.research.supabase_io import SupabaseClient, publish_document
from digiquant.tool_rounds import run_olympus_research_agent as run_research_agent

logger = logging.getLogger(__name__)

NODE_ID = "portfolio/coverage/director"
PHASE_NAME = "portfolio_h45_coverage_director"

DIRECTOR_REFRESH_REASON: Literal["director_refresh"] = "director_refresh"
DIRECTOR_EXPLORE_REASON: Literal["director_explore"] = "director_explore"


class CoverageSelection(BaseModel):
    """One ticker bucketed by the coverage director, with a reason (required)."""

    ticker: str
    reason: str = Field(min_length=1)

    @field_validator("ticker")
    @classmethod
    def _normalize_ticker(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("ticker must be non-empty")
        return normalized


class CoverageDirective(BaseModel):
    """Strict PM coverage decision: refresh + explore + skip (reasons required)."""

    refresh: list[CoverageSelection] = Field(default_factory=list)
    explore: list[CoverageSelection] = Field(default_factory=list)
    skip: list[CoverageSelection] = Field(default_factory=list)

    @model_validator(mode="after")
    def _no_ticker_in_two_buckets(self) -> CoverageDirective:
        seen: dict[str, str] = {}
        for bucket in ("refresh", "explore", "skip"):
            for selection in getattr(self, bucket):
                if selection.ticker in seen:
                    raise ValueError(
                        f"ticker {selection.ticker} in both {seen[selection.ticker]} and {bucket}"
                    )
                seen[selection.ticker] = bucket
        return self


def apply_coverage(
    roster: list[FocusRosterEntry],
    directive: CoverageDirective,
) -> tuple[list[FocusRosterEntry], list[ExcludedTicker]]:
    """Narrow the H4 *roster* per *directive*; never widen it.

    Returns ``(kept, excluded)`` in roster order. Directive tickers absent from
    the roster are dropped with a warning. Rostered tickers the directive omits
    are excluded (the gate defaults to skip, never to analyze).
    """
    reasons: dict[str, tuple[str, str]] = {}
    for selection in directive.refresh:
        reasons[selection.ticker] = (DIRECTOR_REFRESH_REASON, selection.reason)
    for selection in directive.explore:
        reasons[selection.ticker] = (DIRECTOR_EXPLORE_REASON, selection.reason)
    skip_reasons = {selection.ticker: selection.reason for selection in directive.skip}

    rostered = {entry.ticker.upper() for entry in roster}
    for bucket in (directive.refresh, directive.explore, directive.skip):
        for selection in bucket:
            if selection.ticker not in rostered:
                logger.warning(
                    "coverage director: directive ticker %s not on H4 roster; dropping",
                    selection.ticker,
                )

    kept: list[FocusRosterEntry] = []
    excluded: list[ExcludedTicker] = []
    for entry in roster:
        key = entry.ticker.upper()
        if key in reasons:
            roster_reason, rationale = reasons[key]
            kept.append(
                entry.model_copy(update={"roster_reason": roster_reason, "rationale": rationale})
            )
        else:
            reason = skip_reasons.get(key, "not selected by coverage director for fresh analysis")
            excluded.append(ExcludedTicker(ticker=entry.ticker, reason=reason))
    return kept, excluded


COVERAGE_DIRECTIVE_DOCUMENT_KEY = "coverage-directive"
COVERAGE_DIRECTIVE_PAYLOAD_DOC_TYPE = "coverage_directive"


def _director_phase_inputs(state: PortfolioState) -> dict[str, Any]:
    """Inputs the director judges on: H4 roster + book + market movement + prefs."""
    roster = state.phase_portfolio.focus_roster or []
    return {
        "h4_roster": [entry.model_dump(mode="json") for entry in roster],
        "held": sorted(holdings_from_prior_book(state.prior_context.prior_book)),
        "price_deltas": dict(getattr(state, "price_deltas", {}) or {}),
        "preferences": dict(state.config.preferences),
        "active_theses": list(state.prior_context.active_theses),
    }


def build_coverage_document(
    *,
    run_date: date,
    kept: list[FocusRosterEntry],
    excluded: list[ExcludedTicker],
) -> dict[str, Any]:
    """Envelope the coverage directive for the coverage-directive document view."""
    tickers = ", ".join(e.ticker for e in kept) or "none"
    return {
        "schema_version": "1.0",
        "doc_type": COVERAGE_DIRECTIVE_PAYLOAD_DOC_TYPE,
        "date": run_date.isoformat(),
        "body": {
            "summary": f"Coverage directive ({len(kept)} refresh/explore): {tickers}.",
            "selected": [entry.model_dump(mode="json") for entry in kept],
            "excluded": [row.model_dump(mode="json") for row in excluded],
        },
    }


def _coverage_markdown(document: dict[str, Any]) -> str:
    body = document.get("body") if isinstance(document.get("body"), dict) else {}
    date_str = str(document.get("date") or "")
    summary = str((body or {}).get("summary") or "").strip()
    selected = (body or {}).get("selected") or []
    lines = [f"# Coverage directive {date_str}", ""]
    if summary:
        lines.extend([summary, ""])
    if isinstance(selected, list) and selected:
        lines.extend(["| Ticker | Coverage | Rationale |", "| --- | --- | --- |"])
        for row in selected:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"| {row.get('ticker') or '—'} | {row.get('roster_reason') or '—'} | "
                f"{row.get('rationale') or '—'} |"
            )
        lines.append("")
    return "\n".join(lines)


def _coverage_director_node(
    state: PortfolioState, client: SupabaseClient | None = None
) -> dict[str, Any]:
    roster = list(state.phase_portfolio.focus_roster or [])
    if not roster:
        return {}
    try:
        directive = run_research_agent(
            skill_text=load_skill_full("coverage-director"),
            phase_inputs=_director_phase_inputs(state),
            shared_context=_shared_context(
                state,
                context_keys=("digest", "digest-delta"),
                data_layer_scope="portfolio",
            ),
            output_model=CoverageDirective,
            phase_slug=NODE_ID,
            tools=None,
        )
    except Exception as exc:  # LLM failure keeps H4's roster, never the chain (#3739)
        logger.warning(
            "H4.5 coverage-director LLM failed (%s: %s); keeping H4 roster", type(exc).__name__, exc
        )
        err = PhaseError(
            phase=PHASE_NAME,
            node=NODE_ID,
            message=f"coverage-director LLM failed, H4 roster kept: {exc}"[:500],
            retryable=False,
        )
        return {"errors": [err]}
    kept, excluded = apply_coverage(roster, directive)
    # Merge H4's exclusion ledger rows that still apply (tickers nobody selected).
    kept_tickers = {e.ticker for e in kept}
    merged_excluded = list(excluded) + [
        row
        for row in (state.phase_portfolio.focus_roster_excluded or [])
        if row.ticker not in kept_tickers and row.ticker not in {e.ticker for e in excluded}
    ]
    logger.info(
        "H4.5 coverage directive (%d refresh/explore, %d skip): %s",
        len(kept),
        len(merged_excluded),
        ", ".join(f"{e.ticker}:{e.roster_reason}" for e in kept),
    )
    phase_update = {
        "phase_portfolio": state.phase_portfolio.model_copy(
            update={"focus_roster": kept, "focus_roster_excluded": merged_excluded}
        ),
    }
    if client is not None:
        try:
            document = build_coverage_document(
                run_date=state.run_date, kept=kept, excluded=merged_excluded
            )
            date_str = state.run_date.isoformat()
            workspace_id = state.config.workspace_id
            publish_document(
                client=client,
                document_key=portfolio_document_key(COVERAGE_DIRECTIVE_DOCUMENT_KEY, workspace_id),
                payload=document,
                doc_type=None,
                run_type=state.run_type,
                title=f"Coverage directive {date_str}",
                date_str=date_str,
                category="portfolio",
                segment="coverage-director",
                content_markdown=_coverage_markdown(document),
                workspace_id=workspace_id,
            )
        except Exception:
            logger.exception(
                "H4.5: coverage-directive document publish failed for %s; continuing",
                state.run_date,
            )
    return phase_update


def build_coverage_director(*, client: SupabaseClient | None = None) -> PipelinePhase:
    """Build H4.5; optional ``client`` publishes the coverage-directive document."""

    def _bound(state: PortfolioState) -> dict[str, Any]:
        return _coverage_director_node(state, client=client)

    return PipelinePhase(
        name=PHASE_NAME,
        nodes=[NodeSpec(name=NODE_ID, run=_bound)],
    )


__all__ = [
    "NODE_ID",
    "PHASE_NAME",
    "CoverageDirective",
    "CoverageSelection",
    "apply_coverage",
    "build_coverage_director",
    "build_coverage_document",
]
