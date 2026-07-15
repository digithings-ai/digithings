"""On-demand beliefs blob distillation (Olympus #930, spec §11.1).

Phase 9 evolution LLM (9A–9C) is **not** on the daily Hermes graph — H9
``commit_run`` owns terminal persist. This module folds resolved ``decision_log``
lessons into a single ``documents`` row (``document_key=beliefs``,
``doc_type=Beliefs``) when:

1. ``refresh_scope=beliefs`` (operator), or
2. unfolded resolved backlog exceeds ``OLYMPUS_BELIEFS_BACKLOG`` (default 20).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Literal  # noqa  # scored-lint suppression: heterogeneous graph / dict shapes
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from digigraph.graph.pipeline_builder import PipelinePhase

from digiquant.olympus.atlas.decision_log import fetch_recent_lessons
from digiquant.olympus.atlas.graph import AtlasInput
from digiquant.olympus.atlas.state import RefreshScope
from digiquant.olympus.atlas.supabase_io import (
    SupabaseClient,
    load_active_theses_rows,
    mark_decisions_beliefs_folded,
    publish_document,
    query_unfolded_resolved_decisions,
)
from digiquant.olympus.hermes.state import HermesState

logger = logging.getLogger(__name__)

DEFAULT_BELIEFS_BACKLOG = 20
BELIEFS_DOCUMENT_KEY = "beliefs"
BELIEFS_DOC_TYPE_COLUMN = "Beliefs"
# Must be allow-listed in chk_documents_category (migration 053); see #1383.
BELIEFS_CATEGORY = "learning"

__all__ = [
    "DEFAULT_BELIEFS_BACKLOG",
    "BeliefsBlob",
    "BeliefsDistillationDeps",
    "beliefs_backlog_threshold",
    "build_beliefs_distillation_phase",
    "count_unfolded_resolved_decisions",
    "distill_beliefs",
    "run_beliefs_distillation_if_triggered",
    "should_distill_beliefs",
]


class BeliefsBlob(BaseModel):
    """Distilled beliefs document payload (``payload.doc_type=beliefs``)."""

    schema_version: str = "1.0"
    doc_type: Literal["beliefs"] = "beliefs"
    date: date
    body: str = Field(min_length=1, max_length=12000)


def beliefs_backlog_threshold() -> int:
    """``OLYMPUS_BELIEFS_BACKLOG`` env override; default 20."""
    raw = os.environ.get("OLYMPUS_BELIEFS_BACKLOG", "").strip()
    if not raw:
        return DEFAULT_BELIEFS_BACKLOG
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_BELIEFS_BACKLOG


def should_distill_beliefs(*, refresh_scope: RefreshScope, backlog_count: int) -> bool:
    """Return whether beliefs distillation should run this invocation."""
    if refresh_scope == "beliefs":
        return True
    return backlog_count > beliefs_backlog_threshold()


def count_unfolded_resolved_decisions(client: SupabaseClient) -> int:
    """Count resolved ``decision_log`` rows not yet folded into beliefs."""
    return len(query_unfolded_resolved_decisions(client=client))


def _run_beliefs_llm(
    *,
    run_date: date,
    lessons: list[dict[str, Any]],
    active_theses: list[dict[str, Any]],
) -> BeliefsBlob:
    from digigraph.graph.research_agent import run_research_agent
    from digigraph.model_config import get_grounding_model

    from digiquant.olympus.atlas.data.web_grounding import fetch_web_grounding
    from digiquant.olympus.atlas.phases._node_factory import apply_web_grounding_to_inputs
    from digiquant.olympus.atlas.skills import load_skill

    skill_text = load_skill("beliefs-distillation")
    grounding_model = get_grounding_model(segment="beliefs-distillation")
    web_grounding = None
    if grounding_model:
        web_grounding = fetch_web_grounding(
            model=grounding_model,
            segment="beliefs-distillation",
            run_date=run_date,
            scope="portfolio lessons and active theses",
        )
    phase_inputs = apply_web_grounding_to_inputs(
        {
            "segment": "learning/beliefs-distillation",
            "resolved_lessons": lessons,
            "active_theses": active_theses,
        },
        web_grounding=web_grounding,
        segment="beliefs-distillation",
        live_search=True,
    )
    result = run_research_agent(
        skill_text=skill_text,
        phase_inputs=phase_inputs,
        shared_context={"run_date": run_date.isoformat()},
        output_model=BeliefsBlob,
        phase_slug="beliefs-distillation",
    )
    return result.model_copy(update={"date": run_date})


def distill_beliefs(
    *,
    client: SupabaseClient,
    run_date: date,
    run_type: str,
    lessons: list[dict[str, Any]] | None = None,
    active_theses: list[dict[str, Any]] | None = None,
    llm_runner: Callable[..., BeliefsBlob] | None = None,
) -> bool:
    """Run one beliefs distillation call and persist the document.

    Returns ``True`` when a document was written; ``False`` when there was
    nothing to fold (no unfolded resolved rows).
    """
    unfolded = query_unfolded_resolved_decisions(client=client)
    if not unfolded:
        return False

    lesson_rows = lessons if lessons is not None else unfolded
    theses = active_theses
    if theses is None:
        try:
            theses = load_active_theses_rows(client, run_date)
        except Exception as exc:  # noqa: BLE001 — optional context must not block beliefs fold
            logger.warning("beliefs: active_theses unavailable (%s); continuing", exc)
            theses = []

    runner = llm_runner or _run_beliefs_llm
    blob = runner(run_date=run_date, lessons=lesson_rows, active_theses=theses)
    payload = blob.model_dump(mode="json")
    publish_document(
        client=client,
        document_key=BELIEFS_DOCUMENT_KEY,
        payload=payload,
        doc_type=BELIEFS_DOC_TYPE_COLUMN,
        run_type=run_type,
        title=f"Beliefs {run_date.isoformat()}",
        date_str=run_date.isoformat(),
        category=BELIEFS_CATEGORY,
        segment="beliefs",
    )
    mark_decisions_beliefs_folded(
        client=client,
        row_ids=[str(row["id"]) for row in lesson_rows if row.get("id")],
        folded_at=datetime.now(tz=timezone.utc),
    )
    return True


@dataclass(frozen=True)
class BeliefsDistillationDeps:
    """Optional wiring for the on-demand beliefs graph node."""

    client: SupabaseClient


def _beliefs_node_factory(
    deps: BeliefsDistillationDeps,
) -> Callable[[HermesState], dict[str, Any]]:
    def _node(state: HermesState) -> dict[str, Any]:
        if not should_distill_beliefs(
            refresh_scope=state.refresh_scope,
            backlog_count=count_unfolded_resolved_decisions(deps.client),
        ):
            return {}
        distill_beliefs(
            client=deps.client,
            run_date=state.run_date,
            run_type=state.run_type,
        )
        return {}

    return _node


def build_beliefs_distillation_phase(
    deps: BeliefsDistillationDeps | None = None,
) -> "PipelinePhase":
    """Optional Hermes phase — only runs when trigger conditions hold."""
    from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase

    if deps is None:

        def _noop(_state: HermesState) -> dict[str, Any]:
            return {}

        return PipelinePhase(
            name="beliefs_distillation",
            nodes=[NodeSpec(name="learning/beliefs-distillation-noop", run=_noop)],
        )

    return PipelinePhase(
        name="beliefs_distillation",
        nodes=[
            NodeSpec(
                name="learning/beliefs-distillation",
                run=_beliefs_node_factory(deps),
            )
        ],
    )


def run_beliefs_distillation_if_triggered(
    *,
    client: SupabaseClient,
    atlas_input: AtlasInput,
    run_type: str,
) -> bool:
    """Chain-level entry: distill when operator scope or backlog demands it."""
    backlog = count_unfolded_resolved_decisions(client)
    if not should_distill_beliefs(refresh_scope=atlas_input.refresh_scope, backlog_count=backlog):
        return False

    try:
        lessons = fetch_recent_lessons(
            client=client,
            run_date=atlas_input.run_date,
            watchlist=atlas_input.watchlist,
            same_ticker_limit=50,
            cross_ticker_limit=50,
        )
    except Exception as exc:  # noqa: BLE001 — optional context must not block beliefs fold
        logger.warning("beliefs: lessons fetch failed (%s); using unfolded rows", exc)
        lessons = query_unfolded_resolved_decisions(client=client)

    return distill_beliefs(
        client=client,
        run_date=atlas_input.run_date,
        run_type=run_type,
        lessons=lessons,
    )
