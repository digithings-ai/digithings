"""Combined Kairos cron --check probe."""

from __future__ import annotations

import pytest
from digiquant.notify.mailgun import missing_mailgun_env_names
from digiquant.execution.cron_check import (
    cron_check_exit_code,
    format_cron_check_failure,
    mailgun_check_exit_code,
    main,
    run_cron_checks,
)
from digiquant.execution.sync_cron import missing_kairos_sync_env_names
from digiquant.dashboard.overlay.cron import missing_overlay_cron_env_names

pytestmark = pytest.mark.unit

_STORE = {
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "service-role",
}
_MAILGUN = {
    "MAILGUN_API_KEY": "key-placeholder",
    "MAILGUN_DOMAIN": "mg.example.test",
    "NOTIFY_FROM": "ops@example.test",
}


def test_run_cron_checks_all_green() -> None:
    report = run_cron_checks(overlay_rc=0, sync_rc=0, route_rc=0, mailgun_rc=0)
    assert report.failed == ()
    assert cron_check_exit_code(report) == 0


def test_run_cron_checks_names_failures() -> None:
    report = run_cron_checks(overlay_rc=2, sync_rc=0, route_rc=3, mailgun_rc=2)
    assert report.failed == ("overlay", "kairos_route", "mailgun")
    assert cron_check_exit_code(report) == 2
    msg = format_cron_check_failure(report.failed)
    assert msg == "KAIROS_CRON_CHECK: overlay, kairos_route, mailgun"
    assert "key-placeholder" not in msg


def test_main_empty_env_exits_2() -> None:
    err: list[str] = []
    rc = main([], environ={}, log=lambda _m: None, log_err=err.append)
    assert rc == 2
    blob = "\n".join(err)
    assert "KAIROS_CRON_CHECK:" in blob
    assert "overlay" in blob
    assert "kairos_sync" in blob
    assert "kairos_route" in blob
    assert "mailgun" in blob
    assert "OVERLAY_STORE_NOT_CONFIGURED" in blob
    assert "KAIROS_SYNC_NOT_CONFIGURED" in blob
    assert "KAIROS_ROUTING_DISABLED" not in blob
    assert "MAILGUN_NOT_CONFIGURED" in blob
    assert missing_overlay_cron_env_names({})
    assert missing_kairos_sync_env_names({})
    assert missing_mailgun_env_names({})


def test_main_complete_env_exits_0() -> None:
    logs: list[str] = []
    rc = main(
        [],
        environ={**_STORE, **_MAILGUN},
        log=logs.append,
        log_err=lambda _m: None,
    )
    assert rc == 0
    assert logs
    blob = "\n".join(logs)
    assert "names only" in blob
    assert "route" in blob
    assert mailgun_check_exit_code(_MAILGUN) == 0
    assert "key-placeholder" not in blob
    assert "submit_order" not in blob
