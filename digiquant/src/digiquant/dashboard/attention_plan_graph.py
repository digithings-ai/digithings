"""Daily-graph wiring for AttentionPlan shadow publish (#2622 / #1945).

Computes a WP13-class shadow plan beside incumbent edit modes and upserts
``document_key='attention-plan'`` during the research publish phase so Pipeline
can inspect refresh reasons. Never actuates alternate routing.
"""

from __future__ import annotations

import logging
from datetime import date

from digiquant.dashboard.attention_plan import PlannerMode, plan_attention_shadow
from digiquant.dashboard.attention_plan_io import (
    AttentionPlanPublishError,
    publish_attention_plan_shadow,
)
from digiquant.dashboard.edit_mode.content_identity import prior_content_date
from digiquant.dashboard.edit_mode.models import ArtifactKey, PriorPublished, TriageSignal
from digiquant.dashboard.edit_mode.prior import artifact_document_key
from digiquant.dashboard.envcompat import PLANNER_MODE, env_lookup
from digiquant.research.state import PublishedArtifact, ResearchState
from digiquant.research.supabase_io import SupabaseClient
from digiquant.research.triage import triage_decision_to_signal

logger = logging.getLogger(__name__)

OLYMPUS_PLANNER_MODE_ENV = "OLYMPUS_PLANNER_MODE"


class _StatePriorLoader:
    """Resolve segment priors from ``state.prior_context.latest_segments``."""

    def __init__(self, state: ResearchState) -> None:
        self._state = state

    def load(self, artifact_key: ArtifactKey, run_date: date) -> PriorPublished | None:
        doc_key = artifact_document_key(artifact_key)
        row = self._state.prior_context.latest_segments.get(doc_key)
        if not isinstance(row, dict):
            return None
        row_date = row.get("date")
        payload = row.get("payload")
        if not isinstance(row_date, str) or not isinstance(payload, dict):
            return None
        published = date.fromisoformat(row_date)
        if published >= run_date:
            return None
        return PriorPublished(
            date=published,
            document_key=doc_key,
            payload=dict(payload),
            content_date=prior_content_date(payload, published),
        )


def planner_mode_from_env() -> PlannerMode:
    """Return ``off``|``shadow`` from env; unknown values fall back to ``shadow``."""
    raw = env_lookup(PLANNER_MODE, default="shadow").strip().lower()
    if raw in ("off", "shadow"):
        return raw  # type: ignore[return-value]
    logger.warning(
        "invalid %s=%r; using shadow (enforce is not available)",
        OLYMPUS_PLANNER_MODE_ENV,
        raw,
    )
    return "shadow"


def _segment_artifact_keys(state: ResearchState) -> list[ArtifactKey]:
    if state.triage is None or not state.triage.decisions:
        return []
    return [("segment", decision.segment) for decision in state.triage.decisions]


def _triage_map(state: ResearchState) -> dict[ArtifactKey, TriageSignal | None]:
    if state.triage is None:
        return {}
    out: dict[ArtifactKey, TriageSignal | None] = {}
    for decision in state.triage.decisions:
        out[("segment", decision.segment)] = triage_decision_to_signal(decision)
    return out


def _h4_roster(state: ResearchState) -> list[str]:
    portfolio = state.phase_portfolio
    if portfolio is None or not portfolio.focus_roster:
        return []
    return [entry.ticker for entry in portfolio.focus_roster if entry.ticker]


def _documents_run_type(state: ResearchState) -> str:
    if state.run_type in ("baseline", "delta"):
        return state.run_type
    return "baseline"


def maybe_publish_attention_plan_shadow(
    *,
    client: SupabaseClient,
    state: ResearchState,
) -> PublishedArtifact | None:
    """Plan + publish AttentionPlan when triage ran and planner mode is shadow.

    Returns ``None`` when skipped (custom research, planner off, or no triage).
    Raises only for unexpected publish failures — callers may catch to fail-soft.
    """
    if state.custom_prompt:
        return None
    mode = planner_mode_from_env()
    if mode == "off":
        return None
    artifacts = _segment_artifact_keys(state)
    if not artifacts:
        logger.info(
            "attention-plan: skip publish for %s (no triage decisions)",
            state.run_date.isoformat(),
        )
        return None

    result = plan_attention_shadow(
        run_date=state.run_date,
        artifacts=artifacts,
        prior_loader=_StatePriorLoader(state),
        triages=_triage_map(state),
        h4_roster=_h4_roster(state),
        planner_mode=mode,
    )
    try:
        return publish_attention_plan_shadow(
            client=client,
            result=result,
            run_type=_documents_run_type(state),
            run_date=state.run_date,
        )
    except AttentionPlanPublishError as exc:
        logger.warning("attention-plan: skip publish for %s: %s", state.run_date, exc)
        return None


__all__ = [
    "OLYMPUS_PLANNER_MODE_ENV",
    "maybe_publish_attention_plan_shadow",
    "planner_mode_from_env",
]
