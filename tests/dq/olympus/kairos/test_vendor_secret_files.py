"""Vendor secret file load/apply — names only, never values in assertions."""

from __future__ import annotations

from pathlib import Path

import pytest
from digiquant.olympus.kairos.staging_secrets import KAIROS_STAGING_REQUIRED_SECRETS
from digiquant.olympus.kairos.vendor_secret_apply import run_vendor_secret_apply
from digiquant.olympus.kairos.vendor_secret_files import (
    EXIT_VENDOR_FILES_OR_KEYS_MISSING,
    VENDOR_SECRET_FILENAMES,
    format_vendor_apply_blocked,
    function_deploy_argv,
    inspect_vendor_secret_files,
    secrets_set_argv,
    write_vendor_secret_env_file,
)

pytestmark = pytest.mark.unit

_FAKE = {
    "STRIPE_SECRET_KEY": "sk_test_not_a_real_key",
    "STRIPE_WEBHOOK_SECRET": "whsec_not_a_real_secret",
    "STRIPE_PRICE_BASELINE_MONTHLY": "price_baseline",
    "STRIPE_PRICE_CUSTOM_MONTHLY": "price_custom",
    "MAILGUN_API_KEY": "key-not-real",
    "MAILGUN_DOMAIN": "mg.example.test",
    "NOTIFY_FROM": "Kairos <noreply@example.test>",
    "ALPACA_OAUTH_CLIENT_ID": "alpaca-client",
    "ALPACA_OAUTH_CLIENT_SECRET": "alpaca-secret",
}


def _write_complete(root: Path) -> None:
    secrets = root / ".local" / "secrets"
    secrets.mkdir(parents=True)
    (secrets / "digithings-stripe.env").write_text(
        "\n".join(
            f"{k}={_FAKE[k]}"
            for k in (
                "STRIPE_SECRET_KEY",
                "STRIPE_WEBHOOK_SECRET",
                "STRIPE_PRICE_BASELINE_MONTHLY",
                "STRIPE_PRICE_CUSTOM_MONTHLY",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (secrets / "digithings-mailgun.env").write_text(
        "MAILGUN_API_KEY={MAILGUN_API_KEY}\n"
        "MAILGUN_DOMAIN={MAILGUN_DOMAIN}\n"
        "NOTIFY_FROM={NOTIFY_FROM}\n".format(**_FAKE),
        encoding="utf-8",
    )
    (secrets / "digithings-alpaca.env").write_text(
        "ALPACA_OAUTH_CLIENT_ID={ALPACA_OAUTH_CLIENT_ID}\n"
        "ALPACA_OAUTH_CLIENT_SECRET={ALPACA_OAUTH_CLIENT_SECRET}\n".format(**_FAKE),
        encoding="utf-8",
    )


def test_inspect_reports_missing_files_by_name(tmp_path: Path) -> None:
    report = inspect_vendor_secret_files(tmp_path)
    assert report.missing_files == VENDOR_SECRET_FILENAMES
    assert report.missing_keys == KAIROS_STAGING_REQUIRED_SECRETS
    msg = format_vendor_apply_blocked(report)
    assert "digithings-stripe.env" in msg
    assert "STRIPE_SECRET_KEY" in msg
    assert "sk_test" not in msg
    assert "whsec_" not in msg


def test_inspect_complete_files_is_apply_ready(tmp_path: Path) -> None:
    _write_complete(tmp_path)
    report = inspect_vendor_secret_files(tmp_path)
    assert report.missing_files == ()
    assert report.missing_keys == ()
    assert "STRIPE_SECRET_KEY" in report.present_key_names
    assert "sk_test" not in "".join(report.present_key_names)


def test_check_exits_2_when_files_missing(tmp_path: Path) -> None:
    logs: list[str] = []
    code = run_vendor_secret_apply(
        repo_root=tmp_path,
        apply=False,
        log=logs.append,
        run=lambda _argv: pytest.fail("check must not invoke supabase"),
    )
    assert code == EXIT_VENDOR_FILES_OR_KEYS_MISSING
    assert any("missing files" in line for line in logs)
    assert not any("sk_test" in line for line in logs)


def test_apply_refuses_without_files(tmp_path: Path) -> None:
    called: list[object] = []
    code = run_vendor_secret_apply(
        repo_root=tmp_path,
        apply=True,
        log=lambda _msg: None,
        run=called.append,
    )
    assert code == EXIT_VENDOR_FILES_OR_KEYS_MISSING
    assert called == []


def test_apply_runs_secrets_set_and_deploys(tmp_path: Path) -> None:
    _write_complete(tmp_path)
    captured: list[list[str]] = []
    logs: list[str] = []
    code = run_vendor_secret_apply(
        repo_root=tmp_path,
        apply=True,
        log=logs.append,
        run=lambda argv: captured.append(list(argv)),
    )
    assert code == 0
    assert captured[0][:4] == ["npx", "supabase", "secrets", "set"]
    assert any(item.startswith("--env-file=") for item in captured[0])
    assert not any("sk_test_not_a_real_key" in item for item in captured[0])
    names = [cmd[4] for cmd in captured[1:] if len(cmd) > 4]
    assert "stripe-webhook" in names
    assert "settings" in names
    webhook = next(cmd for cmd in captured if "stripe-webhook" in cmd)
    assert "--no-verify-jwt" in webhook
    joined_logs = "\n".join(logs)
    assert "sk_test_not_a_real_key" not in joined_logs
    assert "whsec_not_a_real_secret" not in joined_logs


def test_argv_builders_pin_core_project(tmp_path: Path) -> None:
    env_file = tmp_path / "vendor.env"
    write_vendor_secret_env_file({"STRIPE_SECRET_KEY": "x"}, env_file)
    argv = secrets_set_argv(env_file)
    assert "--project-ref=rwagjbkvxkdwqmouagad" in argv
    assert f"--env-file={env_file}" in argv
    assert "STRIPE_SECRET_KEY=x" not in argv
    assert env_file.stat().st_mode & 0o777 == 0o600
    deploy = function_deploy_argv("settings")
    assert "--no-verify-jwt" not in deploy
    assert function_deploy_argv("stripe-webhook")[-1] == "--no-verify-jwt"
