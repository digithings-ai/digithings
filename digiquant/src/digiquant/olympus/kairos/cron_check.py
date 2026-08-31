"""Combined loud-fail probe for Kairos production cron CLIs.

Runs overlay store check, broker-sync store check, and Mailgun check.
Never prints secret values. Exit 2 if any probe fails.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from pydantic import BaseModel, ConfigDict

from digiquant.notify.mailgun import format_mailgun_not_configured, missing_mailgun_env_names


class CronCheckResult(BaseModel):
    """One CLI --check outcome (names only)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    exit_code: int


class CronCheckReport(BaseModel):
    """Sanitized summary of overlay + sync + Mailgun probes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    results: tuple[CronCheckResult, ...]
    failed: tuple[str, ...]


def run_cron_checks(
    *,
    overlay_rc: int,
    sync_rc: int,
    mailgun_rc: int,
) -> CronCheckReport:
    """Assemble --check outcomes. Does not dispatch jobs or send mail."""
    rows = (
        CronCheckResult(name="overlay", exit_code=overlay_rc),
        CronCheckResult(name="kairos_sync", exit_code=sync_rc),
        CronCheckResult(name="mailgun", exit_code=mailgun_rc),
    )
    failed = tuple(row.name for row in rows if row.exit_code != 0)
    return CronCheckReport(results=rows, failed=failed)


def cron_check_exit_code(report: CronCheckReport) -> int:
    return 2 if report.failed else 0


def format_cron_check_failure(failed: Sequence[str]) -> str:
    return "KAIROS_CRON_CHECK: " + ", ".join(failed)


def mailgun_check_exit_code(environ: Mapping[str, str] | None = None) -> int:
    missing = missing_mailgun_env_names(environ)
    return 2 if missing else 0


def main(
    argv: list[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    log: Callable[[str], None] = print,
    log_err: Callable[[str], None] | None = None,
) -> int:
    """CLI used by ``scripts/kairos_cron_check.py``."""
    del argv
    err = log_err or log
    from digiquant.olympus.kairos.sync_cron import main as sync_main
    from digiquant.olympus.overlay.cron import main as overlay_main

    overlay_rc = overlay_main(["--check"], environ=environ, log=log, log_err=err)
    sync_rc = sync_main(["--check"], environ=environ, log=log, log_err=err)
    mailgun_rc = mailgun_check_exit_code(environ)
    if mailgun_rc != 0:
        err(format_mailgun_not_configured(missing_mailgun_env_names(environ)))
    report = run_cron_checks(overlay_rc=overlay_rc, sync_rc=sync_rc, mailgun_rc=mailgun_rc)
    if report.failed:
        err(format_cron_check_failure(report.failed))
        return cron_check_exit_code(report)
    log("kairos cron check: overlay, sync, mailgun env present (names only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CronCheckReport",
    "CronCheckResult",
    "cron_check_exit_code",
    "format_cron_check_failure",
    "mailgun_check_exit_code",
    "main",
    "run_cron_checks",
]
