"""Scheduled house GHA proof — never treats workflow_dispatch as acceptance."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from digiquant.olympus.kairos.house_pipeline_proof import (
    EXIT_LIST_FAILED,
    EXIT_PROVEN,
    EXIT_SCHEDULE_FAILED,
    EXIT_WAITING_SCHEDULE,
    UUID_HOTFIX_MERGED_AT,
    HouseWorkflowRun,
    evaluate_proof,
    format_proof_line,
    main,
    parse_github_runs,
    proof_exit_code,
    select_proof_run,
)

pytestmark = pytest.mark.unit

_PRE = datetime(2026, 8, 31, 18, 42, 33, tzinfo=UTC)  # 33426508863
_POST = datetime(2026, 9, 1, 12, 0, 5, tzinfo=UTC)


def _run(
    *,
    database_id: int,
    event: str,
    status: str,
    conclusion: str | None,
    created_at: datetime,
    head_sha: str = "3601f72df05c",
) -> HouseWorkflowRun:
    return HouseWorkflowRun(
        database_id=database_id,
        event=event,
        status=status,
        conclusion=conclusion,
        created_at=created_at,
        head_sha=head_sha,
    )


def test_pre_hotfix_schedule_is_not_proof() -> None:
    failed = _run(
        database_id=33426508863,
        event="schedule",
        status="completed",
        conclusion="failure",
        created_at=_PRE,
    )
    assert select_proof_run((failed,)) is None
    proof = evaluate_proof((failed,))
    assert proof.reason == "waiting_next_schedule"
    assert proof_exit_code(proof) == EXIT_WAITING_SCHEDULE
    assert "do not workflow_dispatch" in format_proof_line(proof)
    assert failed.created_at < UUID_HOTFIX_MERGED_AT


def test_post_hotfix_schedule_success_is_proof() -> None:
    run = _run(
        database_id=99,
        event="schedule",
        status="completed",
        conclusion="success",
        created_at=_POST,
        head_sha="abcdef1234567890",
    )
    proof = evaluate_proof((run,))
    assert proof.reason == "proven_schedule_success"
    assert proof_exit_code(proof) == EXIT_PROVEN
    line = format_proof_line(proof)
    assert "run=99" in line
    assert "abcdef123456" in line


def test_post_hotfix_schedule_failure_exits_2() -> None:
    run = _run(
        database_id=100,
        event="schedule",
        status="completed",
        conclusion="failure",
        created_at=_POST,
    )
    proof = evaluate_proof((run,))
    assert proof.reason == "post_hotfix_schedule_failed"
    assert proof_exit_code(proof) == EXIT_SCHEDULE_FAILED


def test_workflow_dispatch_success_is_not_proof() -> None:
    run = _run(
        database_id=101,
        event="workflow_dispatch",
        status="completed",
        conclusion="success",
        created_at=_POST,
    )
    assert select_proof_run((run,)) is None
    assert evaluate_proof((run,)).reason == "waiting_next_schedule"


def test_in_progress_schedule_waits() -> None:
    run = _run(
        database_id=102,
        event="schedule",
        status="in_progress",
        conclusion=None,
        created_at=_POST,
    )
    proof = evaluate_proof((run,))
    assert proof.reason == "waiting_next_schedule"
    assert proof_exit_code(proof) == EXIT_WAITING_SCHEDULE


def test_latest_post_hotfix_schedule_wins() -> None:
    older = _run(
        database_id=1,
        event="schedule",
        status="completed",
        conclusion="failure",
        created_at=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
    )
    newer = _run(
        database_id=2,
        event="schedule",
        status="completed",
        conclusion="success",
        created_at=datetime(2026, 9, 2, 12, 0, tzinfo=UTC),
    )
    assert (
        select_proof_run(
            (
                older,
                newer,
            )
        )
        is newer
    )


def test_parse_github_runs_skips_malformed() -> None:
    parsed = parse_github_runs(
        [
            {
                "databaseId": 33426508863,
                "event": "schedule",
                "status": "completed",
                "conclusion": "failure",
                "createdAt": "2026-08-31T18:42:33Z",
                "headSha": "b363ea16beef",
            },
            {"databaseId": "nope"},
            "ignore",
        ]
    )
    assert len(parsed) == 1
    assert parsed[0].database_id == 33426508863
    assert parsed[0].created_at.tzinfo is not None


def test_main_uses_injected_list_and_refuses_dispatch() -> None:
    logs: list[str] = []
    rc = main(
        [],
        list_runs=lambda: (
            _run(
                database_id=33426508863,
                event="schedule",
                status="completed",
                conclusion="failure",
                created_at=_PRE,
            ),
        ),
        log=logs.append,
        log_err=logs.append,
    )
    assert rc == EXIT_WAITING_SCHEDULE
    assert any("KAIROS_HOUSE_PIPELINE" in line for line in logs)
    assert rc != EXIT_PROVEN
    refuse = main(["--dispatch"], list_runs=lambda: (), log=lambda _m: None, log_err=logs.append)
    assert refuse == EXIT_LIST_FAILED
    assert any("refuses workflow_dispatch" in line for line in logs)


def test_main_list_failure_exits_4() -> None:
    def _boom() -> tuple[HouseWorkflowRun, ...]:
        raise OSError("gh run list failed")

    err: list[str] = []
    rc = main([], list_runs=_boom, log=lambda _m: None, log_err=err.append)
    assert rc == EXIT_LIST_FAILED
    assert "list failed" in err[0]
