"""Combined loud-fail probe for execution production cron CLIs.

Runs overlay store check, broker-sync store check, route store check, and
notify check. Route ``--check`` never submits (kill switch still defaults
off). Never prints secret values. Exit 2 if any probe fails.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from pydantic import BaseModel, ConfigDict

from digiquant.dashboard.overlay.cron import main as overlay_main
from digiquant.execution.route_cron import main as route_main
from digiquant.execution.sync_cron import main as sync_main
from digiquant.notify.cloudflare_email import format_notify_not_configured, missing_notify_env_names


class CronCheckResult(BaseModel):
    """One CLI --check outcome (names only)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    exit_code: int


class CronCheckReport(BaseModel):
    """Sanitized summary of overlay + sync + route + notify probes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    results: tuple[CronCheckResult, ...]
    failed: tuple[str, ...]


def run_cron_checks(
    *,
    overlay_rc: int,
    sync_rc: int,
    route_rc: int,
    notify_rc: int,
) -> CronCheckReport:
    """Assemble --check outcomes. Does not dispatch jobs or send mail."""
    rows = (
        CronCheckResult(name="overlay", exit_code=overlay_rc),
        CronCheckResult(name="execution_sync", exit_code=sync_rc),
        CronCheckResult(name="execution_route", exit_code=route_rc),
        CronCheckResult(name="notify", exit_code=notify_rc),
    )
    failed = tuple(row.name for row in rows if row.exit_code != 0)
    return CronCheckReport(results=rows, failed=failed)


def cron_check_exit_code(report: CronCheckReport) -> int:
    return 2 if report.failed else 0


def format_cron_check_failure(failed: Sequence[str]) -> str:
    return "EXECUTION_CRON_CHECK: " + ", ".join(failed)


def notify_check_exit_code(environ: Mapping[str, str] | None = None) -> int:
    missing = missing_notify_env_names(environ)
    return 2 if missing else 0


def main(
    argv: list[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    log: Callable[[str], None] = print,
    log_err: Callable[[str], None] | None = None,
) -> int:
    """CLI used by ``scripts/execution_cron_check.py``."""
    del argv
    err = log_err or log
    overlay_rc = overlay_main(["--check"], environ=environ, log=log, log_err=err)
    sync_rc = sync_main(["--check"], environ=environ, log=log, log_err=err)
    route_rc = route_main(["--check"], environ=environ, log=log, log_err=err)
    notify_rc = notify_check_exit_code(environ)
    if notify_rc != 0:
        err(format_notify_not_configured(missing_notify_env_names(environ)))
    report = run_cron_checks(
        overlay_rc=overlay_rc,
        sync_rc=sync_rc,
        route_rc=route_rc,
        notify_rc=notify_rc,
    )
    if report.failed:
        err(format_cron_check_failure(report.failed))
        return cron_check_exit_code(report)
    log("execution cron check: overlay, sync, route, notify env present (names only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CronCheckReport",
    "CronCheckResult",
    "cron_check_exit_code",
    "format_cron_check_failure",
    "notify_check_exit_code",
    "main",
    "run_cron_checks",
]
