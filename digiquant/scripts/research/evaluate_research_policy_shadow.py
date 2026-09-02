#!/usr/bin/env python3
"""WP13.5 — file-only research attention shadow evaluation CLI (#2934).

Loads an attention store snapshot, per-target WP1 attempt details, and downstream
artifact outcomes; writes an immutable evaluation report. Never activates enforcement
or contacts production booking paths.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from digiquant.olympus.research_retrieval.planner import AttentionPlan, attention_decision_id
from digiquant.olympus.research_retrieval.shadow_evaluation import (
    AttentionDownstreamOutcomes,
    ShadowProviderAttemptDetail,
    evaluate_research_policy_shadow,
    write_shadow_evaluation_report,
)
from digiquant.olympus.research_retrieval.store import AttentionStore


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_store_snapshot(path: Path) -> tuple[AttentionStore, UUID]:
    raw = _load_json(path)
    if not isinstance(raw, dict):
        raise ValueError("store snapshot must be a JSON object")
    plan_id_raw = raw.get("plan_id")
    if plan_id_raw is None:
        raise ValueError("store snapshot requires plan_id")
    plan_id = UUID(str(plan_id_raw))
    plan = AttentionPlan.model_validate(raw["plan"])
    attempt_id = str(raw.get("attempt_id") or "attempt-1")
    recorded_at = datetime.fromisoformat(str(raw.get("recorded_at")))
    if recorded_at.tzinfo is None:
        recorded_at = recorded_at.replace(tzinfo=UTC)

    store = AttentionStore()
    store.append_plan(plan, attempt_id=attempt_id, recorded_at=recorded_at)
    links = raw.get("provider_attempt_links") or {}
    if isinstance(links, dict):
        for target_key, attempt_ids in links.items():
            decision_id = attention_decision_id(plan_id=plan_id, target_key=str(target_key))
            if not isinstance(attempt_ids, list):
                continue
            for attempt_id_raw in attempt_ids:
                store.link_provider_attempt(
                    decision_id=decision_id,
                    provider_attempt_id=UUID(str(attempt_id_raw)),
                )
    return store, plan_id


def _load_attempt_details(path: Path) -> dict[str, tuple[ShadowProviderAttemptDetail, ...]]:
    raw = _load_json(path)
    if not isinstance(raw, dict):
        raise ValueError("attempt details must be a JSON object keyed by target_key")
    result: dict[str, tuple[ShadowProviderAttemptDetail, ...]] = {}
    for target_key, group in raw.items():
        if not isinstance(group, list):
            raise ValueError(f"attempt details for {target_key!r} must be a list")
        result[str(target_key)] = tuple(
            ShadowProviderAttemptDetail.model_validate(item) for item in group
        )
    return result


def _load_downstream(path: Path) -> dict[str, AttentionDownstreamOutcomes]:
    raw = _load_json(path)
    if not isinstance(raw, dict):
        raise ValueError("downstream outcomes must be a JSON object keyed by target_key")
    return {
        str(target_key): AttentionDownstreamOutcomes.model_validate(value)
        for target_key, value in raw.items()
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate research attention policy in shadow mode (evidence only)."
    )
    parser.add_argument(
        "--store-snapshot",
        type=Path,
        required=True,
        help="Attention plan snapshot JSON (plan + provider_attempt_links).",
    )
    parser.add_argument(
        "--attempt-details",
        type=Path,
        required=True,
        help="Per-target WP1 attempt detail JSON keyed by target_key.",
    )
    parser.add_argument(
        "--downstream",
        type=Path,
        required=True,
        help="Per-target downstream outcomes JSON keyed by target_key.",
    )
    parser.add_argument(
        "--recorded-at",
        default=None,
        help="Evaluation timestamp (ISO-8601 UTC). Defaults to now().",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="File-only output path for ResearchPolicyShadowEvaluationReport JSON.",
    )
    args = parser.parse_args(argv)

    store, plan_id = _load_store_snapshot(args.store_snapshot)
    attempt_details = _load_attempt_details(args.attempt_details)
    downstream = _load_downstream(args.downstream)
    if args.recorded_at:
        recorded_at = datetime.fromisoformat(args.recorded_at)
        if recorded_at.tzinfo is None:
            recorded_at = recorded_at.replace(tzinfo=UTC)
    else:
        recorded_at = datetime.now(tz=UTC)

    report = evaluate_research_policy_shadow(
        store,
        plan_id=plan_id,
        attempt_details=attempt_details,
        downstream_by_target=downstream,
        recorded_at=recorded_at,
    )
    write_shadow_evaluation_report(report, str(args.output))
    print(
        json.dumps(
            {
                "eligible": report.eligible,
                "complete": report.complete,
                "reconciliation_rate": str(report.reconciliation_rate),
                "telemetry_complete": report.telemetry_complete,
                "downstream_complete": report.downstream_complete,
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )
    return 0 if report.complete or not report.eligible else 1


if __name__ == "__main__":
    sys.exit(main())
