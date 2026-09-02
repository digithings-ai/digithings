"""AttentionPlan document persistence for Pipeline glass-box (#1945).

Typed contract for publishing WP13-class shadow plans under
``document_key='attention-plan'``. Daily graph call-site:
``digiquant.dashboard.attention_plan_graph.maybe_publish_attention_plan_shadow``
(invoked from research ``publish_phase``).
"""

from __future__ import annotations

from datetime import date
from typing import Any  # score:allow untyped any — documents.payload jsonb shape

from digiquant.dashboard.attention_plan import AttentionPlanShadowResult
from digiquant.research.supabase_io import (
    PublishedArtifact,
    SupabaseClient,
    publish_document,
)

ATTENTION_PLAN_DOCUMENT_KEY = "attention-plan"
ATTENTION_PLAN_DOC_TYPE_COLUMN = "Attention Plan"
ATTENTION_PLAN_PAYLOAD_DOC_TYPE = "attention_plan"
ATTENTION_PLAN_CATEGORY = "planner"

REFRESH_REASON_LABELS: dict[str, str] = {
    "no_prior": "No prior published document",
    "stale_content": "Content past the stale-full window",
    "triage_stale": "Triage marked the artifact stale",
    "triage_quiet": "Triage marked the artifact quiet",
    "force_full": "Forced full rewrite",
    "incumbent_edit": "Incumbent edit mode",
    "incumbent_skip": "Incumbent skip / carry",
    "incumbent_full": "Incumbent full rewrite",
}


class AttentionPlanPublishError(ValueError):
    """Raised when a shadow result cannot be published as a glass-box document."""


def attention_plan_document_payload(
    result: AttentionPlanShadowResult,
    *,
    run_date: date | None = None,
) -> dict[str, Any]:
    """Serialize a shadow result into a documents.payload glass-box shape.

    Never fabricates a plan when ``planner_mode=off``. Includes human-readable
    refresh reason labels for Pipeline rendering without exposing chain-of-thought.
    """
    if result.actuated:
        raise AttentionPlanPublishError("refusing to publish actuated AttentionPlan (shadow only)")
    if result.planner_mode == "off":
        raise AttentionPlanPublishError("planner_mode=off produces no AttentionPlan document")
    if result.plan is None:
        raise AttentionPlanPublishError("planner_mode=shadow requires a plan")

    plan = result.plan
    date_str = (run_date or plan.run_date).isoformat()
    decisions: list[dict[str, Any]] = []
    for decision in plan.decisions:
        reason_codes = [code.value for code in decision.refresh_reasons]
        decisions.append(
            {
                "artifact_key": decision.artifact_key,
                "action": decision.action,
                "proposed_edit_mode": decision.proposed_edit_mode,
                "refresh_reasons": reason_codes,
                "refresh_reason_labels": [
                    REFRESH_REASON_LABELS.get(code, code.replace("_", " ")) for code in reason_codes
                ],
            }
        )

    return {
        "doc_type": ATTENTION_PLAN_PAYLOAD_DOC_TYPE,
        "date": date_str,
        "planner_mode": result.planner_mode,
        "actuated": False,
        "shadow": True,
        "profile_pin": {
            "profile_key": plan.profile_key,
            "profile_config_version_id": str(plan.profile_config_version_id),
            "is_house_default": plan.is_house_default,
            "label": "digithings house" if plan.is_house_default else plan.profile_key,
        },
        "plan": {
            "plan_id": str(plan.plan_id),
            "schema_version": plan.schema_version,
            "run_date": plan.run_date.isoformat(),
            "h4_roster": list(plan.h4_roster),
            "h4_roster_fingerprint": plan.h4_roster_fingerprint,
            "decisions": decisions,
        },
        "incumbent_edit_modes": dict(result.incumbent_edit_modes),
    }


def publish_attention_plan_shadow(
    *,
    client: SupabaseClient,
    result: AttentionPlanShadowResult,
    run_type: str = "baseline",
    run_date: date | None = None,
) -> PublishedArtifact:
    """Upsert the AttentionPlan shadow document for Pipeline inspection.

    ``run_type`` must satisfy ``chk_documents_run_type`` (``baseline``|``delta``).
    ``category='planner'`` requires migration ``078``.
    """
    if run_type not in ("baseline", "delta"):
        raise AttentionPlanPublishError(
            f"documents.run_type must be baseline|delta, got {run_type!r}"
        )
    payload = attention_plan_document_payload(result, run_date=run_date)
    date_str = str(payload["date"])
    return publish_document(
        client=client,
        document_key=ATTENTION_PLAN_DOCUMENT_KEY,
        payload=payload,
        doc_type=ATTENTION_PLAN_DOC_TYPE_COLUMN,
        run_type=run_type,
        title=f"Attention plan {date_str}",
        date_str=date_str,
        category=ATTENTION_PLAN_CATEGORY,
        segment="attention_plan",
    )


__all__ = [
    "ATTENTION_PLAN_CATEGORY",
    "ATTENTION_PLAN_DOC_TYPE_COLUMN",
    "ATTENTION_PLAN_DOCUMENT_KEY",
    "ATTENTION_PLAN_PAYLOAD_DOC_TYPE",
    "REFRESH_REASON_LABELS",
    "AttentionPlanPublishError",
    "attention_plan_document_payload",
    "publish_attention_plan_shadow",
]
