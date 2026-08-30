"""Fail-closed proof that the scheduled house GHA committed a book after main hotfixes.

``pipeline-olympus.yml`` checks out ``ref: main`` even when the schedule event
fires on default ``develop``. The 2026-08-31 schedule (``33426508863``) failed
before ledger-stamp [#3331](https://github.com/digithings-ai/digithings/pull/3331)
(20:10Z) and UUID stringify [#3334](https://github.com/digithings-ai/digithings/pull/3334)
(20:39Z). EPIC house-pipeline acceptance is a later **schedule** success — never
``workflow_dispatch``. This module only lists runs; it never dispatches.

A schedule that checks out UUID-hotfix ``3601f72df`` still misses Gemini
fail-softs [#3343](https://github.com/digithings-ai/digithings/pull/3343) →
[#3348](https://github.com/digithings-ai/digithings/pull/3348) →
[#3351](https://github.com/digithings-ai/digithings/pull/3351) →
[#3354](https://github.com/digithings-ai/digithings/pull/3354). While
``origin/main`` is that SHA the CLI exits 5 so operators merge those PRs
before the next ``0 12 * * *`` cron.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

WORKFLOW_FILE: str = "pipeline-olympus.yml"
CLI_PREFIX: str = "digiquant_house_pipeline_proof"
# Exclusive cutoff: runs at-or-before this instant are pre-#3334 main.
UUID_HOTFIX_MERGED_AT: datetime = datetime(2026, 8, 31, 20, 39, tzinfo=UTC)
UUID_HOTFIX_SHA_PREFIX: str = "3601f72df"
FAILSOFT_MAIN_PRS: tuple[int, ...] = (3343, 3348, 3351, 3354)
EXIT_PROVEN: int = 0
EXIT_SCHEDULE_FAILED: int = 2
EXIT_WAITING_SCHEDULE: int = 3
EXIT_LIST_FAILED: int = 4
EXIT_MAIN_MISSING_FAILSOFTS: int = 5

ListRunsFn = Callable[[], Sequence["HouseWorkflowRun"]]
ResolveOriginMainFn = Callable[[], "OriginMainRef"]


class HouseWorkflowRun(BaseModel):
    """Sanitized Actions run — ids and conclusions only, never logs or tokens."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    database_id: int
    event: str
    status: str
    conclusion: str | None = None
    created_at: datetime
    head_sha: str = Field(min_length=7)


class OriginMainRef(BaseModel):
    """``origin/main`` after fetch — SHA plus committer time, never the tree."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sha: str = Field(min_length=7)
    committed_at: datetime


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
        "main_missing_failsofts",
    ]
    main_sha: str | None = None


def sha_is_uuid_hotfix(sha: str) -> bool:
    """True when ``sha`` is the #3334 UUID-stringify commit on ``main``."""
    cleaned = sha.strip().lower()
    return bool(cleaned) and cleaned.startswith(UUID_HOTFIX_SHA_PREFIX)


def failsoft_pr_text() -> str:
    return " ".join(f"#{number}" for number in FAILSOFT_MAIN_PRS)


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


def counting_cutoff(
    *,
    hotfix_cutoff: datetime = UUID_HOTFIX_MERGED_AT,
    main_committed_at: datetime | None = None,
) -> datetime:
    """Exclusive floor: later of #3334 merge and current ``origin/main`` commit."""
    if main_committed_at is not None and main_committed_at > hotfix_cutoff:
        return main_committed_at
    return hotfix_cutoff


def evaluate_proof(
    runs: Sequence[HouseWorkflowRun],
    *,
    cutoff: datetime = UUID_HOTFIX_MERGED_AT,
    main_sha: str | None = None,
    main_committed_at: datetime | None = None,
) -> HousePipelineProof:
    """Map listed runs onto the EPIC house-pipeline gate. Never dispatches.

    ``gh run list`` ``headSha`` is the default-branch *trigger* (develop), not
    the job checkout (``ref: main``). Counting therefore uses ``created_at``
    vs ``origin/main`` committer time, never the trigger SHA.
    """
    if main_sha is not None and sha_is_uuid_hotfix(main_sha):
        return HousePipelineProof(
            cutoff=cutoff,
            selected=None,
            reason="main_missing_failsofts",
            main_sha=main_sha,
        )
    effective = counting_cutoff(hotfix_cutoff=cutoff, main_committed_at=main_committed_at)
    selected = select_proof_run(runs, cutoff=effective)
    if selected is None:
        return HousePipelineProof(
            cutoff=effective, selected=None, reason="waiting_next_schedule", main_sha=main_sha
        )
    if selected.status != "completed":
        return HousePipelineProof(
            cutoff=effective, selected=selected, reason="waiting_next_schedule", main_sha=main_sha
        )
    if selected.conclusion == "success":
        return HousePipelineProof(
            cutoff=effective,
            selected=selected,
            reason="proven_schedule_success",
            main_sha=main_sha,
        )
    return HousePipelineProof(
        cutoff=effective, selected=selected, reason="post_hotfix_schedule_failed", main_sha=main_sha
    )


def proof_exit_code(proof: HousePipelineProof) -> int:
    if proof.reason == "proven_schedule_success":
        return EXIT_PROVEN
    if proof.reason == "post_hotfix_schedule_failed":
        return EXIT_SCHEDULE_FAILED
    if proof.reason == "list_failed":
        return EXIT_LIST_FAILED
    if proof.reason == "main_missing_failsofts":
        return EXIT_MAIN_MISSING_FAILSOFTS
    return EXIT_WAITING_SCHEDULE


def format_proof_line(proof: HousePipelineProof) -> str:
    """Single-line status. Run ids only — never log bodies."""
    if proof.reason == "main_missing_failsofts":
        sha = (proof.main_sha or "")[:12]
        return (
            f"{CLI_PREFIX}: reason=main_missing_failsofts "
            f"main={sha} merge {failsoft_pr_text()} onto main before cron "
            "(do not workflow_dispatch)"
        )
    if proof.selected is None:
        return (
            f"{CLI_PREFIX}: waiting for next schedule after "
            f"{proof.cutoff.isoformat()} (do not workflow_dispatch)"
        )
    run = proof.selected
    return (
        f"{CLI_PREFIX}: "
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


def default_resolve_origin_main() -> OriginMainRef:
    """Fetch ``origin/main`` then read SHA + committer time. Never logs output."""
    fetch = subprocess.run(
        ["git", "fetch", "origin", "main"],
        check=False,
        capture_output=True,
        text=True,
    )
    if fetch.returncode != 0:
        raise OSError("git fetch origin main failed")
    sha_proc = subprocess.run(
        ["git", "rev-parse", "origin/main"],
        check=False,
        capture_output=True,
        text=True,
    )
    sha = (sha_proc.stdout or "").strip()
    if sha_proc.returncode != 0 or len(sha) < 7:
        raise OSError("git rev-parse origin/main failed")
    date_proc = subprocess.run(
        ["git", "log", "-1", "--format=%cI", "origin/main"],
        check=False,
        capture_output=True,
        text=True,
    )
    raw = (date_proc.stdout or "").strip()
    if date_proc.returncode != 0 or not raw:
        raise OSError("git log origin/main committer time failed")
    committed_at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if committed_at.tzinfo is None:
        committed_at = committed_at.replace(tzinfo=UTC)
    return OriginMainRef(sha=sha, committed_at=committed_at)


def main(
    argv: list[str] | None = None,
    *,
    list_runs: ListRunsFn | None = None,
    resolve_origin_main: ResolveOriginMainFn | None = None,
    log: Callable[[str], None] = print,
    log_err: Callable[[str], None] | None = None,
) -> int:
    """CLI used by ``scripts/digiquant_house_pipeline_proof.py``. Never dispatches."""
    err = log_err or log
    if argv:
        joined = " ".join(argv).lower()
        if "dispatch" in joined or "--apply" in joined:
            err(f"{CLI_PREFIX}: refuses workflow_dispatch / --apply")
            return EXIT_LIST_FAILED
    try:
        origin_main = (resolve_origin_main or default_resolve_origin_main)()
    except OSError as exc:
        err(f"{CLI_PREFIX}: origin/main failed ({exc})")
        return EXIT_LIST_FAILED
    if sha_is_uuid_hotfix(origin_main.sha):
        proof = evaluate_proof((), main_sha=origin_main.sha)
        log(format_proof_line(proof))
        err(
            "DIGIQUANT_HOUSE_PIPELINE: origin/main is still UUID-hotfix "
            f"{UUID_HOTFIX_SHA_PREFIX}; merge {failsoft_pr_text()} before cron "
            "(do not dispatch)"
        )
        return EXIT_MAIN_MISSING_FAILSOFTS
    try:
        runs = tuple(list_runs() if list_runs is not None else default_list_runs())
    except OSError as exc:
        err(f"{CLI_PREFIX}: list failed ({exc})")
        return EXIT_LIST_FAILED
    proof = evaluate_proof(
        runs, main_sha=origin_main.sha, main_committed_at=origin_main.committed_at
    )
    log(format_proof_line(proof))
    code = proof_exit_code(proof)
    if code == EXIT_SCHEDULE_FAILED:
        err("DIGIQUANT_HOUSE_PIPELINE: post-hotfix schedule failed (not a dispatch)")
    elif code == EXIT_WAITING_SCHEDULE:
        err("DIGIQUANT_HOUSE_PIPELINE: waiting for cron 0 12 * * * (do not dispatch)")
    return code


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CLI_PREFIX",
    "EXIT_LIST_FAILED",
    "EXIT_MAIN_MISSING_FAILSOFTS",
    "EXIT_PROVEN",
    "EXIT_SCHEDULE_FAILED",
    "EXIT_WAITING_SCHEDULE",
    "FAILSOFT_MAIN_PRS",
    "HousePipelineProof",
    "HouseWorkflowRun",
    "ListRunsFn",
    "OriginMainRef",
    "ResolveOriginMainFn",
    "UUID_HOTFIX_MERGED_AT",
    "UUID_HOTFIX_SHA_PREFIX",
    "WORKFLOW_FILE",
    "counting_cutoff",
    "default_list_runs",
    "default_resolve_origin_main",
    "evaluate_proof",
    "failsoft_pr_text",
    "format_proof_line",
    "main",
    "parse_github_runs",
    "proof_exit_code",
    "select_proof_run",
    "sha_is_uuid_hotfix",
]
