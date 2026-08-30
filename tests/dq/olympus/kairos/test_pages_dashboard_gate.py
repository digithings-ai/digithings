"""Fail-closed Pages /dashboard gate — never deploy while the path 404s."""

from __future__ import annotations

from pathlib import Path

import pytest
from digiquant.olympus.kairos.pages_dashboard_gate import (
    DASHBOARD_PATHS,
    DASHBOARD_URL_FUNCTIONS,
    EXIT_APPLY_FAILED,
    EXIT_CHECKOUT_STALE,
    EXIT_LIVE_EF_STALE,
    EXIT_PAGES_DASHBOARD_NOT_READY,
    PROBE_USER_AGENT,
    LiveSettingsFetchError,
    fetch_live_settings_bundle,
    format_pages_dashboard_blocked,
    probe_pages_dashboard,
    run_pages_dashboard_gate,
    settings_bundle_ready,
)
from digiquant.olympus.kairos.vendor_secret_files import function_deploy_argv

pytestmark = pytest.mark.unit

ORIGIN = "https://digiquant.io"
READY_LIVE_BUNDLE = (
    '  if (method === "POST" && path === "/access/redeem-invite") {\n'
    'export const ALPACA_OAUTH_CALLBACK_PATH = "/dashboard/settings/brokers/callback/";\n'
    'export const SETTINGS_PATH = "/dashboard/settings/";\n'
)
V32_LIVE_BUNDLE = (
    "ESZIP2.3\x00// binary junk without the route\n"
    'export const ALPACA_OAUTH_CALLBACK_PATH = "/olympus/settings/brokers/callback/";\n'
    'export const SETTINGS_PATH = "/olympus/settings/";\n'
)


def _ready_live() -> str:
    return READY_LIVE_BUNDLE


def _ok_probe(url: str) -> tuple[int, str]:
    return 200, url


def _live_404_probe(url: str) -> tuple[int, str]:
    if "/dashboard" in url:
        return 404, url
    return 200, url


def _olympus_redirect_probe(url: str) -> tuple[int, str]:
    return 200, "https://digiquant.io/olympus/"


def test_default_probe_user_agent_is_not_python_urllib() -> None:
    assert "python-urllib" not in PROBE_USER_AGENT.lower()
    assert "kairos-pages-dashboard-gate" in PROBE_USER_AGENT


def test_probe_reports_all_required_paths() -> None:
    report = probe_pages_dashboard(origin=ORIGIN, probe=_ok_probe)
    assert report.ready is True
    assert tuple(item.path for item in report.results) == DASHBOARD_PATHS


def test_live_404_is_not_ready() -> None:
    report = probe_pages_dashboard(origin=ORIGIN, probe=_live_404_probe)
    assert report.ready is False
    msg = format_pages_dashboard_blocked(report)
    assert "do not redeploy settings EF" in msg
    assert "/dashboard/" in msg
    assert "http=404" in msg


def test_olympus_redirect_is_not_ready() -> None:
    report = probe_pages_dashboard(origin=ORIGIN, probe=_olympus_redirect_probe)
    assert report.ready is False


def test_check_exits_3_and_does_not_deploy() -> None:
    deployed: list[str] = []

    def run(argv: list[str] | tuple[str, ...]) -> None:
        deployed.append(" ".join(argv))

    code = run_pages_dashboard_gate(
        apply=False,
        log=lambda _msg: None,
        probe=_live_404_probe,
        run=run,
    )
    assert code == EXIT_PAGES_DASHBOARD_NOT_READY
    assert deployed == []


def test_apply_refuses_while_404() -> None:
    deployed: list[str] = []

    def run(argv: list[str] | tuple[str, ...]) -> None:
        deployed.append(" ".join(argv))

    code = run_pages_dashboard_gate(
        apply=True,
        log=lambda _msg: None,
        probe=_live_404_probe,
        run=run,
    )
    assert code == EXIT_PAGES_DASHBOARD_NOT_READY
    assert deployed == []


def test_apply_deploys_url_functions_when_ready() -> None:
    deployed: list[tuple[str, ...]] = []

    def run(argv: list[str] | tuple[str, ...]) -> None:
        deployed.append(tuple(argv))

    code = run_pages_dashboard_gate(
        apply=True,
        log=lambda _msg: None,
        probe=_ok_probe,
        run=run,
        live_source=_ready_live,
    )
    assert code == 0
    assert [row[4] for row in deployed] == list(DASHBOARD_URL_FUNCTIONS)
    assert "stripe-webhook" not in {row[4] for row in deployed}
    for function, argv in zip(DASHBOARD_URL_FUNCTIONS, deployed, strict=True):
        assert argv == tuple(function_deploy_argv(function))


def test_apply_maps_deploy_failure() -> None:
    def run(_argv: list[str] | tuple[str, ...]) -> None:
        raise OSError("supabase missing")

    code = run_pages_dashboard_gate(
        apply=True,
        log=lambda _msg: None,
        probe=_ok_probe,
        run=run,
    )
    assert code == EXIT_APPLY_FAILED


def _write_ef_checkout(root: Path, *, redeem: bool, dashboard: bool) -> Path:
    handlers = root / "digiquant" / "supabase" / "functions" / "_shared" / "settings-handlers.ts"
    app_url = root / "digiquant" / "supabase" / "functions" / "_shared" / "app-url.ts"
    handlers.parent.mkdir(parents=True, exist_ok=True)
    redeem_line = '  if (method === "POST" && path === "/access/redeem-invite") {\n'
    handlers.write_text(
        ("export async function handleSettingsRequest() {}\n" + (redeem_line if redeem else "")),
        encoding="utf-8",
    )
    callback = (
        "/dashboard/settings/brokers/callback/"
        if dashboard
        else "/olympus/settings/brokers/callback/"
    )
    settings = "/dashboard/settings/" if dashboard else "/olympus/settings/"
    app_url.write_text(
        (
            f'export const ALPACA_OAUTH_CALLBACK_PATH = "{callback}";\n'
            f'export const SETTINGS_PATH = "{settings}";\n'
        ),
        encoding="utf-8",
    )
    return root


def test_apply_refuses_when_handlers_lack_redeem_invite(tmp_path: Path) -> None:
    deployed: list[str] = []

    def run(argv: list[str] | tuple[str, ...]) -> None:
        deployed.append(" ".join(argv))

    logs: list[str] = []
    code = run_pages_dashboard_gate(
        apply=True,
        log=logs.append,
        probe=_ok_probe,
        run=run,
        repo_root=_write_ef_checkout(tmp_path, redeem=False, dashboard=True),
    )
    assert code == EXIT_CHECKOUT_STALE
    assert deployed == []
    assert any("redeem-invite" in msg for msg in logs)


def test_apply_refuses_when_app_url_still_olympus(tmp_path: Path) -> None:
    deployed: list[str] = []

    def run(argv: list[str] | tuple[str, ...]) -> None:
        deployed.append(" ".join(argv))

    logs: list[str] = []
    code = run_pages_dashboard_gate(
        apply=True,
        log=logs.append,
        probe=_ok_probe,
        run=run,
        repo_root=_write_ef_checkout(tmp_path, redeem=True, dashboard=False),
    )
    assert code == EXIT_CHECKOUT_STALE
    assert deployed == []
    assert any("/olympus" in msg or "dashboard" in msg for msg in logs)


def test_check_does_not_require_redeem_invite_source(tmp_path: Path) -> None:
    deployed: list[str] = []

    def run(argv: list[str] | tuple[str, ...]) -> None:
        deployed.append(" ".join(argv))

    code = run_pages_dashboard_gate(
        apply=False,
        log=lambda _msg: None,
        probe=_ok_probe,
        run=run,
        repo_root=_write_ef_checkout(tmp_path, redeem=False, dashboard=False),
    )
    assert code == 0
    assert deployed == []


def test_apply_refuses_comment_only_redeem_invite(tmp_path: Path) -> None:
    deployed: list[str] = []

    def run(argv: list[str] | tuple[str, ...]) -> None:
        deployed.append(" ".join(argv))

    root = _write_ef_checkout(tmp_path, redeem=False, dashboard=True)
    handlers = root / "digiquant" / "supabase" / "functions" / "_shared" / "settings-handlers.ts"
    handlers.write_text(
        "// POST /access/redeem-invite — docs only\nexport async function handleSettingsRequest() {}\n",
        encoding="utf-8",
    )
    code = run_pages_dashboard_gate(
        apply=True,
        log=lambda _msg: None,
        probe=_ok_probe,
        run=run,
        repo_root=root,
    )
    assert code == EXIT_CHECKOUT_STALE
    assert deployed == []


def test_apply_refuses_comment_only_dashboard_paths(tmp_path: Path) -> None:
    deployed: list[str] = []

    def run(argv: list[str] | tuple[str, ...]) -> None:
        deployed.append(" ".join(argv))

    root = _write_ef_checkout(tmp_path, redeem=True, dashboard=True)
    app_url = root / "digiquant" / "supabase" / "functions" / "_shared" / "app-url.ts"
    app_url.write_text(
        (
            '// export const ALPACA_OAUTH_CALLBACK_PATH = "/dashboard/settings/brokers/callback/";\n'
            '// export const SETTINGS_PATH = "/dashboard/settings/";\n'
            "export const ALPACA_OAUTH_CALLBACK_PATH = undefined;\n"
            "export const SETTINGS_PATH = undefined;\n"
        ),
        encoding="utf-8",
    )
    code = run_pages_dashboard_gate(
        apply=True,
        log=lambda _msg: None,
        probe=_ok_probe,
        run=run,
        repo_root=root,
    )
    assert code == EXIT_CHECKOUT_STALE
    assert deployed == []


def test_ready_live_bundle_passes_and_v32_fails() -> None:
    ok, _reason = settings_bundle_ready(READY_LIVE_BUNDLE)
    assert ok is True
    stale, reason = settings_bundle_ready(V32_LIVE_BUNDLE)
    assert stale is False
    assert "redeem-invite" in reason or "/olympus" in reason


def test_comment_only_markers_are_not_ready() -> None:
    blob = (
        '// if (method === "POST" && path === "/access/redeem-invite") {\n'
        '// export const ALPACA_OAUTH_CALLBACK_PATH = "/dashboard/settings/brokers/callback/";\n'
        '// export const SETTINGS_PATH = "/dashboard/settings/";\n'
    )
    ok, _reason = settings_bundle_ready(blob)
    assert ok is False


def test_apply_refuses_when_live_bundle_still_v32() -> None:
    deployed: list[str] = []

    def run(argv: list[str] | tuple[str, ...]) -> None:
        deployed.append(" ".join(argv))

    logs: list[str] = []
    code = run_pages_dashboard_gate(
        apply=True,
        log=logs.append,
        probe=_ok_probe,
        run=run,
        live_source=lambda: V32_LIVE_BUNDLE,
    )
    assert code == EXIT_LIVE_EF_STALE
    assert deployed  # deploy already ran; live proof is after
    assert any("live settings" in msg for msg in logs)


def test_apply_refuses_when_live_fetch_fails() -> None:
    deployed: list[str] = []

    def run(argv: list[str] | tuple[str, ...]) -> None:
        deployed.append(" ".join(argv))

    def boom() -> str:
        raise LiveSettingsFetchError("SUPABASE_ACCESS_TOKEN missing")

    logs: list[str] = []
    code = run_pages_dashboard_gate(
        apply=True,
        log=logs.append,
        probe=_ok_probe,
        run=run,
        live_source=boom,
    )
    assert code == EXIT_LIVE_EF_STALE
    assert deployed
    assert any("live settings" in msg or "ACCESS_TOKEN" in msg for msg in logs)


def test_check_does_not_fetch_live_bundle() -> None:
    def fail_live() -> str:
        raise AssertionError("check must not fetch live settings")

    code = run_pages_dashboard_gate(
        apply=False,
        log=lambda _msg: None,
        probe=_ok_probe,
        live_source=fail_live,
    )
    assert code == 0


def test_fetch_live_settings_bundle_decodes_eszip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SUPABASE_ACCESS_TOKEN", raising=False)
    payload = b"ESZIP2.3\x00" + READY_LIVE_BUNDLE.encode("utf-8")

    def http_bytes(url: str) -> bytes:
        assert url.endswith("/functions/settings/body")
        assert "rwagjbkvxkdwqmouagad" in url
        return payload

    text = fetch_live_settings_bundle(token="sbp_test", http_bytes=http_bytes)
    assert "redeem-invite" in text
    ok, _reason = settings_bundle_ready(text)
    assert ok is True


def test_fetch_live_settings_bundle_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SUPABASE_ACCESS_TOKEN", raising=False)
    with pytest.raises(LiveSettingsFetchError, match="SUPABASE_ACCESS_TOKEN"):
        fetch_live_settings_bundle(token="", http_bytes=lambda _url: b"nope")
