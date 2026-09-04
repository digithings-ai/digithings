"""WP16.9 — CLI for policy replay run/inspect/evaluate (recommendation/read only).

Never activates production policy. Human decision write is intentionally absent
from this unauthenticated surface — use the DigiAuth HTTP boundary instead.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import click

from digiquant.dashboard.replay.exposure import PolicyReplayExposureError
from digiquant.service import (
    service_evaluate_policy_gate,
    service_get_policy_comparison,
    service_get_policy_gate_evaluation,
    service_get_policy_replay,
    service_run_policy_replay,
)


@click.group("policy-replay")
def policy_replay() -> None:
    """Inspect offline policy replay evidence (summaries / artifact IDs only)."""


@policy_replay.command("run")
@click.option("--pair-content-hash", required=True, help="Stored pair content hash (64 hex)")
@click.option("--run-id", default=None, help="Optional stable run id")
def run_cmd(pair_content_hash: str, run_id: str | None) -> None:
    """Register a replay run against a stored pair."""
    try:
        summary = service_run_policy_replay(
            pair_content_hash=pair_content_hash,
            run_id=run_id,
            recorded_at=datetime.now(tz=UTC),
        )
    except (LookupError, PolicyReplayExposureError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(summary.model_dump(mode="json"), indent=2))


@policy_replay.command("get-replay")
@click.option("--run-id", required=True)
def get_replay_cmd(run_id: str) -> None:
    """Fetch a replay-run summary by id."""
    try:
        summary = service_get_policy_replay(run_id)
    except (LookupError, PolicyReplayExposureError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(summary.model_dump(mode="json"), indent=2))


@policy_replay.command("get-comparison")
@click.option("--comparison-id", required=True)
def get_comparison_cmd(comparison_id: str) -> None:
    """Fetch a comparison summary (IDs/status only)."""
    try:
        summary = service_get_policy_comparison(comparison_id)
    except (LookupError, PolicyReplayExposureError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(summary.model_dump(mode="json"), indent=2))


@policy_replay.command("evaluate-gate")
@click.option("--comparison-id", required=True)
@click.option("--criteria-version-id", required=True)
def evaluate_gate_cmd(comparison_id: str, criteria_version_id: str) -> None:
    """Evaluate immutable gate criteria (eligibility only)."""
    try:
        summary = service_evaluate_policy_gate(
            comparison_id=comparison_id,
            criteria_version_id=criteria_version_id,
            recorded_at=datetime.now(tz=UTC),
        )
    except (LookupError, PolicyReplayExposureError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(summary.model_dump(mode="json"), indent=2))


@policy_replay.command("get-evaluation")
@click.option("--evaluation-id", required=True)
def get_evaluation_cmd(evaluation_id: str) -> None:
    """Fetch a gate-evaluation summary by id."""
    try:
        summary = service_get_policy_gate_evaluation(evaluation_id)
    except (LookupError, PolicyReplayExposureError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(summary.model_dump(mode="json"), indent=2))


__all__ = ["policy_replay"]
