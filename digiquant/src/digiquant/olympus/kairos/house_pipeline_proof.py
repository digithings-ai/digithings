"""Fail-closed proof that the scheduled house GHA committed a book after main hotfixes.

``pipeline-olympus.yml`` checks out ``ref: main`` even when the schedule event
fires on default ``develop``. The 2026-08-31 schedule (``33426508863``) failed
before ledger-stamp [#3331](https://github.com/digithings-ai/digithings/pull/3331)
(20:10Z) and UUID stringify [#3334](https://github.com/digithings-ai/digithings/pull/3334)
(20:39Z). EPIC house-pipeline acceptance is a later **schedule** success — never
``workflow_dispatch``. This module only lists runs; it never dispatches.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

WORKFLOW_FILE: str = "pipeline-olympus.yml"
# Exclusive cutoff: runs at-or-before this instant are pre-#3334 main.
UUID_HOTFIX_MERGED_AT: datetime = datetime(2026, 8, 31, 20, 39, tzinfo=UTC)
EXIT_PROVEN: int = 0
EXIT_SCHEDULE_FAILED: int = 2
EXIT_WAITING_SCHEDULE: int = 3
EXIT_LIST_FAILED: int = 4

ListRunsFn = Callable[[], Sequence["HouseWorkflowRun"]]


class HouseWorkflowRun(BaseModel):
    """Sanitized Actions run — ids and conclusions only, never logs or tokens."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    database_id: int
    event: str
    status: str
    conclusion: str | None = None
    created_at: datetime
    head_sha: str = Field(min_length=7)


class HousePipelineProof(BaseModel):
    """Which schedule (if any) counts as the post-hotfix proof."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cutoff: datetime
    selected: HouseWorkflowRun | None = None
    reason: Literal[
        "proven_schedule_success",
        "post_hotfix_schedule_failed",
        "waiting_next_schedule",
        "list_failed",
    ]


def parse_github_runs(raw: object) -> tuple[HouseWorkflowRun, ...]:
    """Build runs from ``gh run list --json`` output. Never logs the payload."""
    if not isinstance(raw, list):
        return ()
    rows: list[HouseWorkflowRun] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        created = item.get("createdAt")
        sha = item.get("headSha")
        run_id = item.get("databaseId")
        event = item.get("event")
        status = item.get("status")
        if not isinstance(created, str) or not isinstance(sha, str):
            continue
        if not isinstance(run_id, int) or not isinstance(event, str) or not isinstance(status, str):
            continue
        conclusion = item.get("conclusion")
        rows.append(
            HouseWorkflowRun(
                database_id=run_id,
                event=event,
                status=status,
                conclusion=conclusion if isinstance(conclusion, str) else None,
                created_at=datetime.fromisoformat(created.replace("Z", "+00:00")),
                head_sha=sha,
            )
        )
    return tuple(rows)


def select_proof_run(
    runs: Sequence[HouseWorkflowRun],
    *,
    cutoff: datetime = UUID_HOTFIX_MERGED_AT,
) -> HouseWorkflowRun | None:
    """Latest **schedule** run strictly after the UUID-stringify hotfix on main."""
    candidates = [row for row in runs if row.event == "schedule" and row.created_at > cutoff]
    if not candidates:
        return None
    return max(candidates, key=lambda row: row.created_at)


def evaluate_proof(
    runs: Sequence[HouseWorkflowRun],
    *,
    cutoff: datetime = UUID_HOTFIX_MERGED_AT,
) -> HousePipelineProof:
    """Map listed runs onto the EPIC house-pipeline gate. Never dispatches."""
    selected = select_proof_run(runs, cutoff=cutoff)
    if selected is None:
        return HousePipelineProof(cutoff=cutoff, selected=None, reason="waiting_next_schedule")
    if selected.status != "completed":
        return HousePipelineProof(cutoff=cutoff, selected=selected, reason="waiting_next_schedule")
    if selected.conclusion == "success":
        return HousePipelineProof(
            cutoff=cutoff, selected=selected, reason="proven_schedule_success"
        )
    return HousePipelineProof(
        cutoff=cutoff, selected=selected, reason="post_hotfix_schedule_failed"
    )


def proof_exit_code(proof: HousePipelineProof) -> int:
    if proof.reason == "proven_schedule_success":
        return EXIT_PROVEN
    if proof.reason == "post_hotfix_schedule_failed":
        return EXIT_SCHEDULE_FAILED
    if proof.reason == "list_failed":
        return EXIT_LIST_FAILED
    return EXIT_WAITING_SCHEDULE


def format_proof_line(proof: HousePipelineProof) -> str:
    """Single-line status. Run ids only — never log bodies."""
    if proof.selected is None:
        return (
            "kairos_house_pipeline_proof: waiting for next schedule after "
            f"{proof.cutoff.isoformat()} (do not workflow_dispatch)"
        )
    run = proof.selected
    return (
        "kairos_house_pipeline_proof: "
        f"reason={proof.reason} run={run.database_id} "
        f"event={run.event} status={run.status} conclusion={run.conclusion or ''} "
        f"sha={run.head_sha[:12]}"
    )


def default_list_runs() -> tuple[HouseWorkflowRun, ...]:
    """``gh run list`` for the house workflow. Never dispatches a run."""
    proc = subprocess.run(
        [
            "gh",
            "run",
            "list",
            "--workflow",
            WORKFLOW_FILE,
            "--limit",
            "20",
            "--json",
            "databaseId,conclusion,status,event,createdAt,headSha",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise OSError("gh run list failed")
    try:
        payload: object = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise OSError("gh run list returned non-JSON") from exc
    return parse_github_runs(payload)


def main(
    argv: list[str] | None = None,
    *,
    list_runs: ListRunsFn | None = None,
    log: Callable[[str], None] = print,
    log_err: Callable[[str], None] | None = None,
) -> int:
    """CLI used by ``scripts/kairos_house_pipeline_proof.py``. Never dispatches."""
    err = log_err or log
    if argv:
        joined = " ".join(argv).lower()
        if "dispatch" in joined or "--apply" in joined:
            err("kairos_house_pipeline_proof: refuses workflow_dispatch / --apply")
            return EXIT_LIST_FAILED
    try:
        runs = tuple(list_runs() if list_runs is not None else default_list_runs())
    except OSError as exc:
        err(f"kairos_house_pipeline_proof: list failed ({exc})")
        return EXIT_LIST_FAILED
    proof = evaluate_proof(runs)
    log(format_proof_line(proof))
    code = proof_exit_code(proof)
    if code == EXIT_SCHEDULE_FAILED:
        err("KAIROS_HOUSE_PIPELINE: post-hotfix schedule failed (not a dispatch)")
    elif code == EXIT_WAITING_SCHEDULE:
        err("KAIROS_HOUSE_PIPELINE: waiting for cron 0 12 * * * (do not dispatch)")
    return code


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "EXIT_LIST_FAILED",
    "EXIT_PROVEN",
    "EXIT_SCHEDULE_FAILED",
    "EXIT_WAITING_SCHEDULE",
    "HousePipelineProof",
    "HouseWorkflowRun",
    "ListRunsFn",
    "UUID_HOTFIX_MERGED_AT",
    "WORKFLOW_FILE",
    "default_list_runs",
    "evaluate_proof",
    "format_proof_line",
    "main",
    "parse_github_runs",
    "proof_exit_code",
    "select_proof_run",
]
