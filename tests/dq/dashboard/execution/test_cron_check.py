"""Combined execution cron --check probe."""

from __future__ import annotations

import pytest
from digiquant.dashboard.overlay.cron import missing_overlay_cron_env_names
from digiquant.execution.cron_check import (
    cron_check_exit_code,
    format_cron_check_failure,
    main,
    notify_check_exit_code,
    run_cron_checks,
)
from digiquant.execution.sync_cron import missing_execution_sync_env_names
from digiquant.notify.cloudflare_email import missing_notify_env_names

pytestmark = pytest.mark.unit

_STORE = {
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "service-role",
}
_NOTIFY = {
    "CLOUDFLARE_EMAIL_API_TOKEN": "token-placeholder",
    "CLOUDFLARE_ACCOUNT_ID": "acct.example.test",
    "NOTIFY_FROM": "ops@example.test",
}


def test_run_cron_checks_all_green() -> None:
    report = run_cron_checks(overlay_rc=0, sync_rc=0, route_rc=0, notify_rc=0)
    assert report.failed == ()
    assert cron_check_exit_code(report) == 0


def test_run_cron_checks_names_failures() -> None:
    report = run_cron_checks(overlay_rc=2, sync_rc=0, route_rc=3, notify_rc=2)
    assert report.failed == ("overlay", "execution_route", "notify")
    assert cron_check_exit_code(report) == 2
    msg = format_cron_check_failure(report.failed)
    assert msg == "EXECUTION_CRON_CHECK: overlay, execution_route, notify"
    assert "token-placeholder" not in msg


def test_main_empty_env_exits_2() -> None:
    err: list[str] = []
    rc = main([], environ={}, log=lambda _m: None, log_err=err.append)
    assert rc == 2
    blob = "\n".join(err)
    assert "EXECUTION_CRON_CHECK:" in blob
    assert "overlay" in blob
    assert "execution_sync" in blob
    assert "execution_route" in blob
    assert "notify" in blob
    assert "OVERLAY_STORE_NOT_CONFIGURED" in blob
    assert "KAIROS_SYNC_NOT_CONFIGURED" in blob
    assert "KAIROS_ROUTING_DISABLED" not in blob
    assert "NOTIFY_NOT_CONFIGURED" in blob
    assert missing_overlay_cron_env_names({})
    assert missing_execution_sync_env_names({})
    assert missing_notify_env_names({})


def test_main_complete_env_exits_0() -> None:
    logs: list[str] = []
    rc = main(
        [],
        environ={**_STORE, **_NOTIFY},
        log=logs.append,
        log_err=lambda _m: None,
    )
    assert rc == 0
    assert logs
    blob = "\n".join(logs)
    assert "names only" in blob
    assert "route" in blob
    assert notify_check_exit_code(_NOTIFY) == 0
    assert "token-placeholder" not in blob
    assert "submit_order" not in blob
