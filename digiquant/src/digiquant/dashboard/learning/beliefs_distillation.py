"""Daily beliefs blob distillation (dashboard WP-I / spec §11.1).

Phase 9 evolution LLM (9A–9C) is **not** on the daily portfolio graph — H9
``commit_run`` owns terminal persist. This module folds resolved ``decision_log``
lessons into a same-date ``documents`` row (``document_key=beliefs``,
``doc_type=Beliefs``) on every house chain:

* **short** (default daily) — today's unfolded lessons + yesterday's beliefs body,
  cheap model, tight token budget; empty-lesson days carry prior with one paragraph.
* **full** — ``refresh_scope=beliefs`` operator rewrite, or unfolded backlog above
  ``OLYMPUS_BELIEFS_BACKLOG`` (default 20).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import (  # scored-lint suppression: heterogeneous graph / dict shapes
    TYPE_CHECKING,
    Any,
    Callable,
    Literal,
)
from uuid import UUID

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from digigraph.graph.pipeline_builder import PipelinePhase

from digiquant.dashboard.envcompat import BELIEFS_BACKLOG, env_lookup
from digiquant.dashboard.overlay.persist import skip_overlay_shared_register
from digiquant.portfolio.state import PortfolioState
from digiquant.research.decision_log import fetch_recent_lessons
from digiquant.research.graph import ResearchInput
from digiquant.research.state import RefreshScope
from digiquant.research.supabase_io import (
    SupabaseClient,
    load_active_theses_rows,
    load_latest_beliefs_document,
    mark_decisions_beliefs_folded,
    publish_document,
    query_unfolded_resolved_decisions,
)

logger = logging.getLogger(__name__)

DEFAULT_BELIEFS_BACKLOG = 20
DAILY_BELIEFS_MAX_TOKENS = 800
BELIEFS_DOCUMENT_KEY = "beliefs"
BELIEFS_DOC_TYPE_COLUMN = "Beliefs"
# Must be allow-listed in chk_documents_category (migration 053); see #1383.
BELIEFS_CATEGORY = "learning"
BeliefsFoldMode = Literal["short", "full"]

__all__ = [
    "DAILY_BELIEFS_MAX_TOKENS",
    "DEFAULT_BELIEFS_BACKLOG",
    "BeliefsBlob",
    "BeliefsDistillationDeps",
    "BeliefsFoldMode",
    "beliefs_backlog_threshold",
    "build_beliefs_distillation_phase",
    "count_unfolded_resolved_decisions",
    "distill_beliefs",
    "resolve_beliefs_fold_mode",
    "run_beliefs_distillation_if_triggered",
    "should_distill_beliefs",
]


class BeliefsBlob(BaseModel):
    """Distilled beliefs document payload (``payload.doc_type=beliefs``)."""

    schema_version: str = "1.0"
    doc_type: Literal["beliefs"] = "beliefs"
    date: date
    body: str = Field(min_length=1)


def beliefs_backlog_threshold() -> int:
    """``OLYMPUS_BELIEFS_BACKLOG`` env override; default 20."""
    raw = env_lookup(BELIEFS_BACKLOG).strip()
    if not raw:
        return DEFAULT_BELIEFS_BACKLOG
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_BELIEFS_BACKLOG


def resolve_beliefs_fold_mode(
    *, refresh_scope: RefreshScope, backlog_count: int
) -> BeliefsFoldMode:
    """Choose short daily fold vs full rewrite.

    ``refresh_scope=beliefs`` is the operator full rewrite. An unfolded resolved
    backlog above ``OLYMPUS_BELIEFS_BACKLOG`` is the additional full-fold trigger
    (catch-up after missed daily folds). Every other house invocation is short.
    """
    if refresh_scope == "beliefs":
        return "full"
    if backlog_count > beliefs_backlog_threshold():
        return "full"
    return "short"


def should_distill_beliefs(*, refresh_scope: RefreshScope, backlog_count: int) -> bool:
    """Return True for every house invocation (WP-I daily fold).

    Overlay skip is a separate gate. ``refresh_scope`` / ``backlog_count`` still
    select short vs full via :func:`resolve_beliefs_fold_mode`.
    """
    del refresh_scope, backlog_count
    return True


def _prior_beliefs_body(row: dict[str, Any] | None) -> str | None:
    if not row:
        return None
    payload = row.get("payload") or {}
    body = payload.get("body")
    if isinstance(body, str) and body.strip():
        return body
    return None


def _carry_forward_body(*, run_date: date, prior_body: str | None) -> str:
    header = f"No new resolved lessons on {run_date.isoformat()}. Prior beliefs carried forward."
    if prior_body and prior_body.strip():
        return f"{header}\n\n{prior_body.strip()}"
    return f"No new resolved lessons on {run_date.isoformat()}. No prior beliefs document to carry."


def count_unfolded_resolved_decisions(client: SupabaseClient) -> int:
    """Count resolved ``decision_log`` rows not yet folded into beliefs."""
    return len(query_unfolded_resolved_decisions(client=client))


def _run_beliefs_llm(
    *,
    run_date: date,
    lessons: list[dict[str, Any]],
    active_theses: list[dict[str, Any]],
    fold_mode: BeliefsFoldMode = "full",
    prior_body: str | None = None,
    max_tokens: int | None = None,
) -> BeliefsBlob:
    from digigraph.graph.research_agent import run_research_agent
    from digigraph.model_config import get_grounding_model

    from digiquant.research.data.web_grounding import fetch_web_grounding
    from digiquant.research.phases._node_factory import apply_web_grounding_to_inputs
    from digiquant.research.skills import load_skill

    skill_slug = "beliefs-distillation-daily" if fold_mode == "short" else "beliefs-distillation"
    skill_text = load_skill(skill_slug)
    web_grounding = None
    if fold_mode == "full":
        grounding_model = get_grounding_model(segment="beliefs-distillation")
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
            "fold_mode": fold_mode,
            "resolved_lessons": lessons,
            "active_theses": active_theses,
            "prior_beliefs_body": prior_body or "",
        },
        web_grounding=web_grounding,
        segment="beliefs-distillation",
        live_search=fold_mode == "full",
    )
    result = run_research_agent(
        skill_text=skill_text,
        phase_inputs=phase_inputs,
        shared_context={"run_date": run_date.isoformat(), "fold_mode": fold_mode},
        output_model=BeliefsBlob,
        phase_slug="beliefs-distillation",
        max_tokens=max_tokens,
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
    workspace_id: UUID | str | None = None,
    fold_mode: BeliefsFoldMode = "short",
) -> bool:
    """Run one beliefs fold and persist a same-date ``beliefs`` document.

    Returns ``True`` when a document was written. Overlay workspaces skip:
    ``decision_log`` has no ``workspace_id`` and ``beliefs_folded_at`` would
    stamp house lessons by id. Short mode with no unfolded rows still publishes
    a carry-forward body so Learning is never empty on a house run date.
    """
    if skip_overlay_shared_register(workspace_id):
        logger.info("beliefs: overlay workspace skips house decision_log fold")
        return False
    unfolded = query_unfolded_resolved_decisions(client=client)
    lesson_rows = lessons if lessons is not None else unfolded
    try:
        prior_row = load_latest_beliefs_document(
            client=client, run_date=run_date, workspace_id=workspace_id
        )
    except Exception as exc:  # prior body is optional context
        logger.warning("beliefs: prior document unavailable (%s); continuing", exc)
        prior_row = None
    prior_body = _prior_beliefs_body(prior_row)

    if fold_mode == "short" and not lesson_rows:
        blob = BeliefsBlob(
            date=run_date,
            body=_carry_forward_body(run_date=run_date, prior_body=prior_body),
        )
    else:
        theses = active_theses
        if theses is None:
            try:
                theses = load_active_theses_rows(client, run_date)
            except Exception as exc:  # optional context must not block beliefs fold
                logger.warning("beliefs: active_theses unavailable (%s); continuing", exc)
                theses = []
        runner = llm_runner or _run_beliefs_llm
        token_budget = DAILY_BELIEFS_MAX_TOKENS if fold_mode == "short" else None
        blob = runner(
            run_date=run_date,
            lessons=lesson_rows,
            active_theses=theses,
            fold_mode=fold_mode,
            prior_body=prior_body,
            max_tokens=token_budget,
        )

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
    """Optional wiring for the post-publish beliefs graph node."""

    client: SupabaseClient


def _beliefs_node_factory(
    deps: BeliefsDistillationDeps,
) -> Callable[[PortfolioState], dict[str, Any]]:
    def _node(state: PortfolioState) -> dict[str, Any]:
        if skip_overlay_shared_register(state.config.workspace_id):
            return {}
        fold_mode = resolve_beliefs_fold_mode(
            refresh_scope=state.refresh_scope,
            backlog_count=count_unfolded_resolved_decisions(deps.client),
        )
        distill_beliefs(
            client=deps.client,
            run_date=state.run_date,
            run_type=state.run_type,
            workspace_id=state.config.workspace_id,
            fold_mode=fold_mode,
        )
        return {}

    return _node


def build_beliefs_distillation_phase(
    deps: BeliefsDistillationDeps | None = None,
) -> "PipelinePhase":
    """Optional portfolio phase — daily short fold; full rewrite on trigger."""
    from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase

    if deps is None:

        def _noop(_state: PortfolioState) -> dict[str, Any]:
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
    research_input: ResearchInput,
    run_type: str,
    workspace_id: UUID | str | None = None,
) -> bool:
    """Chain-level entry: daily short fold, or full rewrite on operator/backlog."""
    if skip_overlay_shared_register(workspace_id):
        return False
    backlog = count_unfolded_resolved_decisions(client)
    fold_mode = resolve_beliefs_fold_mode(
        refresh_scope=research_input.refresh_scope, backlog_count=backlog
    )

    lessons: list[dict[str, Any]] | None = None
    if fold_mode == "full":
        try:
            lessons = fetch_recent_lessons(
                client=client,
                run_date=research_input.run_date,
                watchlist=research_input.watchlist,
                same_ticker_limit=50,
                cross_ticker_limit=50,
            )
        except Exception as exc:  # optional context must not block beliefs fold
            logger.warning("beliefs: lessons fetch failed (%s); using unfolded rows", exc)
            lessons = query_unfolded_resolved_decisions(client=client)

    return distill_beliefs(
        client=client,
        run_date=research_input.run_date,
        run_type=run_type,
        lessons=lessons,
        workspace_id=workspace_id,
        fold_mode=fold_mode,
    )
