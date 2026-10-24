"""Unit tests for scripts/digichat_aca_secret_detector.py.

The detector is the only thing standing between "a digichat Container App secret
changed and nobody noticed" and silence, so the cases that matter are the ones
where it must exit non-zero: drift, a deleted secret, a binding renamed off its
env var, a secret migrated to a Key Vault, a lapsed expiry, and a malformed lock.

The `az` CLI is replaced by a fake that reads a fixture file, so no test touches
Azure and no test ever holds a real secret. One test pins the safety property the
whole design rests on: a secret value read by the detector never reaches stdout or
stderr, not even on the failure path.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
DETECTOR = REPO_ROOT / "scripts" / "digichat_aca_secret_detector.py"
LOCK = REPO_ROOT / "docs" / "ops" / "digichat-aca-secret-fingerprints.json"

CANARY = "canary-secret-value-must-never-be-printed-0123456789"

FAKE_AZ = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    import json, os, sys
    fixture = json.loads(os.environ["FAKE_AZ_FIXTURE"])
    argv = sys.argv[1:]
    if "secret" in argv and "list" in argv:
        group = argv[argv.index("-g") + 1]
        query = argv[argv.index("--query") + 1]
        name = query.split("'")[1]
        print(fixture["values"].get(f"{group}/{name}", ""))
        sys.exit(0)
    if "show" in argv:
        group = argv[argv.index("-g") + 1]
        print(json.dumps(fixture["env"][group]))
        sys.exit(0)
    sys.exit(3)
    """
)


def binding(resource_group: str, secret_name: str, value: str, **overrides: object) -> dict:
    import hashlib

    raw = value.encode("utf-8")
    entry = {
        "resource_group": resource_group,
        "environment": "prod" if resource_group == "datatap-rg" else "dev",
        "secret_name": secret_name,
        "env_var": {"auth-secret": "AUTH_SECRET", "embed-tenants": "DIGICHAT_EMBED_TENANTS"}[secret_name],
        "length_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "canonical_store": "the Container App itself",
        "owner": "Chris Stefan",
    }
    entry.update(overrides)
    return entry


def env_entry(env: str, secret_ref: str, key_vault_url: str | None = None) -> dict:
    return {"env": env, "secretRef": secret_ref, "keyVaultUrl": key_vault_url}


def lock_document(bindings: list[dict], expiry: str = "2027-01-04") -> dict:
    return {
        "subscription": "fc64972f-8c1e-46f1-a2b0-bd2407c0cdf0",
        "container_app": "digichat",
        "last_verified": "2026-10-06",
        "expiry": expiry,
        "bindings": bindings,
    }


@pytest.fixture()
def fake_az(tmp_path: Path) -> Path:
    path = tmp_path / "fake-az"
    path.write_text(FAKE_AZ)
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


def run_detector(tmp_path: Path, lock: dict, fixture: dict | None = None, *args: str,
                 fake_az: Path | None = None, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    lock_path = tmp_path / "lock.json"
    lock_path.write_text(json.dumps(lock))
    env = dict(os.environ)
    env.pop("AZURE_CLI", None)
    if fixture is not None:
        env["FAKE_AZ_FIXTURE"] = json.dumps(fixture)
    if env_extra:
        env.update(env_extra)
    argv = [sys.executable, str(DETECTOR), "--lock", str(lock_path), *args]
    if fake_az is not None:
        argv += ["--az-bin", str(fake_az)]
    return subprocess.run(argv, capture_output=True, text=True, env=env, cwd=REPO_ROOT)


def codes(result: subprocess.CompletedProcess) -> set[str]:
    return {line.split()[1] for line in result.stdout.splitlines() if line.startswith(("FAIL", "OK "))}


def two_bindings() -> list[dict]:
    return [
        binding("datatap-rg", "auth-secret", CANARY),
        binding("datatap-rg", "embed-tenants", '{"acme":{"token":"other"}}'),
    ]


def two_env() -> dict:
    return {
        "datatap-rg": [
            env_entry("AUTH_SECRET", "auth-secret"),
            env_entry("DIGICHAT_EMBED_TENANTS", "embed-tenants"),
        ]
    }


# --------------------------------------------------------------------------- clean


def test_matching_fingerprints_exit_zero(tmp_path: Path, fake_az: Path) -> None:
    fixture = {"values": {"datatap-rg/auth-secret": CANARY, "datatap-rg/embed-tenants": '{"acme":{"token":"other"}}'}, "env": two_env()}
    result = run_detector(tmp_path, lock_document(two_bindings()), fixture, fake_az=fake_az)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FAIL" not in result.stdout


def test_offline_never_calls_az(tmp_path: Path, fake_az: Path) -> None:
    # No fixture env var at all: the fake would exit 3 if it were ever invoked.
    result = run_detector(tmp_path, lock_document(two_bindings()), None, "--offline", fake_az=fake_az)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "skipped the live read" in result.stdout


def test_json_output_reports_pass(tmp_path: Path, fake_az: Path) -> None:
    fixture = {"values": {"datatap-rg/auth-secret": CANARY, "datatap-rg/embed-tenants": '{"acme":{"token":"other"}}'}, "env": two_env()}
    result = run_detector(tmp_path, lock_document(two_bindings()), fixture, "--json", fake_az=fake_az)
    payload = json.loads(result.stdout)
    assert payload["status"] == "pass"
    assert result.returncode == 0


# --------------------------------------------------------------------------- findings


def test_drift_in_one_binding_fails_and_names_it(tmp_path: Path, fake_az: Path) -> None:
    fixture = {
        "values": {"datatap-rg/auth-secret": "a-different-value", "datatap-rg/embed-tenants": '{"acme":{"token":"other"}}'},
        "env": two_env(),
    }
    result = run_detector(tmp_path, lock_document(two_bindings()), fixture, fake_az=fake_az)
    assert result.returncode == 1
    assert "drift" in codes(result)
    assert "datatap-rg/auth-secret" in result.stdout


def test_deleted_secret_fails_as_missing(tmp_path: Path, fake_az: Path) -> None:
    fixture = {"values": {"datatap-rg/embed-tenants": '{"acme":{"token":"other"}}'}, "env": two_env()}
    result = run_detector(tmp_path, lock_document(two_bindings()), fixture, fake_az=fake_az)
    assert result.returncode == 1
    assert "missing" in codes(result)


def test_key_vault_migration_fails_so_the_lock_row_is_retired(tmp_path: Path, fake_az: Path) -> None:
    fixture = {
        "values": {"datatap-rg/auth-secret": CANARY, "datatap-rg/embed-tenants": '{"acme":{"token":"other"}}'},
        "env": {
            "datatap-rg": [
                env_entry("AUTH_SECRET", "auth-secret", key_vault_url="https://kv-prod.vault.azure.net/secrets/auth-secret"),
                env_entry("DIGICHAT_EMBED_TENANTS", "embed-tenants"),
            ]
        },
    }
    result = run_detector(tmp_path, lock_document(two_bindings()), fixture, fake_az=fake_az)
    assert result.returncode == 1
    assert "migrated" in codes(result)
    assert "Delete this fingerprint row" in result.stdout


def test_renamed_env_var_fails_as_unbound(tmp_path: Path, fake_az: Path) -> None:
    fixture = {
        "values": {"datatap-rg/auth-secret": CANARY, "datatap-rg/embed-tenants": '{"acme":{"token":"other"}}'},
        "env": {"datatap-rg": [env_entry("AUTH_SECRET_V2", "auth-secret"), env_entry("DIGICHAT_EMBED_TENANTS", "embed-tenants")]},
    }
    result = run_detector(tmp_path, lock_document(two_bindings()), fixture, fake_az=fake_az)
    assert result.returncode == 1
    assert "unbound" in codes(result)


def test_a_secret_added_without_an_owner_fails_as_unrecorded(tmp_path: Path, fake_az: Path) -> None:
    # The exact gap this issue exists to close: a new inline secret on the app that
    # nobody owns and nobody fingerprinted.
    fixture = {
        "values": {"datatap-rg/auth-secret": CANARY, "datatap-rg/embed-tenants": '{"acme":{"token":"other"}}'},
        "env": {
            "datatap-rg": [
                env_entry("AUTH_SECRET", "auth-secret"),
                env_entry("DIGICHAT_EMBED_TENANTS", "embed-tenants"),
                env_entry("STRIPE_WEBHOOK_SECRET", "stripe-webhook-secret"),
            ]
        },
    }
    result = run_detector(tmp_path, lock_document(two_bindings()), fixture, fake_az=fake_az)
    assert result.returncode == 1
    assert "unrecorded" in codes(result)
    assert "datatap-rg/stripe-webhook-secret" in result.stdout
    assert "STRIPE_WEBHOOK_SECRET" in result.stdout
    assert "no owner, no fingerprint" in result.stdout


def test_plain_env_values_are_not_mistaken_for_unrecorded_secrets(tmp_path: Path, fake_az: Path) -> None:
    # An env entry bound with `value` rather than `secretRef` is ordinary config, not a
    # credential, so it must not trip the unrecorded check.
    fixture = {
        "values": {"datatap-rg/auth-secret": CANARY, "datatap-rg/embed-tenants": '{"acme":{"token":"other"}}'},
        "env": {
            "datatap-rg": [
                env_entry("AUTH_SECRET", "auth-secret"),
                env_entry("DIGICHAT_EMBED_TENANTS", "embed-tenants"),
                {"env": "PORT", "secretRef": None, "keyVaultUrl": None},
            ]
        },
    }
    result = run_detector(tmp_path, lock_document(two_bindings()), fixture, fake_az=fake_az)
    assert result.returncode == 0
    assert "unrecorded" not in codes(result)


def test_az_refusal_is_reported_not_swallowed(tmp_path: Path) -> None:
    # A fake that always fails stands in for a lapsed Azure session.
    dead = tmp_path / "dead-az"
    dead.write_text("#!/bin/sh\nexit 1\n")
    dead.chmod(dead.stat().st_mode | stat.S_IEXEC)
    result = run_detector(tmp_path, lock_document(two_bindings()), None, fake_az=dead)
    assert result.returncode == 1
    assert "unreadable" in codes(result)


def test_lapsed_expiry_fails(tmp_path: Path, fake_az: Path) -> None:
    result = run_detector(
        tmp_path, lock_document(two_bindings(), expiry="2026-01-04"), None, "--offline", "--today", "2026-10-06",
        fake_az=fake_az,
    )
    assert result.returncode == 1
    assert "expired" in codes(result)


def test_expiry_inside_the_window_passes(tmp_path: Path, fake_az: Path) -> None:
    result = run_detector(
        tmp_path, lock_document(two_bindings(), expiry="2026-10-06"), None, "--offline", "--today", "2026-10-06",
        fake_az=fake_az,
    )
    assert result.returncode == 0, result.stdout


def test_bad_today_is_usage_error(tmp_path: Path, fake_az: Path) -> None:
    result = run_detector(tmp_path, lock_document(two_bindings()), None, "--offline", "--today", "yesterday",
                          fake_az=fake_az)
    assert result.returncode == 2


# --------------------------------------------------------------------------- lock shape


@pytest.mark.parametrize(
    "mutate, expected",
    [
        (lambda b: b[0].pop("owner"), "missing field"),
        (lambda b: b[0].update(sha256="nope"), "not 64 hex"),
        (lambda b: b[0].update(length_bytes=0), "positive integer"),
        (lambda b: b.append(dict(b[0])), "duplicate"),
    ],
)
def test_malformed_lock_fails_loudly(tmp_path: Path, fake_az: Path, mutate, expected) -> None:
    bindings = two_bindings()
    mutate(bindings)
    result = run_detector(tmp_path, lock_document(bindings), None, "--offline", fake_az=fake_az)
    assert result.returncode == 1
    assert expected in result.stdout


def test_missing_lock_file_is_an_infra_error(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(DETECTOR), "--lock", str(tmp_path / "nope.json"), "--offline"],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert result.returncode == 2
    assert "lock file not found" in result.stderr


# --------------------------------------------------------------------------- safety


def test_secret_never_reaches_the_output_on_any_path(tmp_path: Path, fake_az: Path) -> None:
    """The design rests on this: a read value never appears in stdout or stderr."""
    drifted = {
        "values": {"datatap-rg/auth-secret": CANARY + "-rotated", "datatap-rg/embed-tenants": '{"acme":{"token":"other"}}'},
        "env": {"datatap-rg": [env_entry("SOMETHING_ELSE", "auth-secret"), env_entry("DIGICHAT_EMBED_TENANTS", "embed-tenants")]},
    }
    result = run_detector(tmp_path, lock_document(two_bindings()), drifted, "--json", fake_az=fake_az)
    assert result.returncode == 1
    assert CANARY not in result.stdout
    assert CANARY not in result.stderr


def test_committed_lock_file_is_self_consistent_and_offline_clean() -> None:
    """Guards the lock we actually ship: complete, fingerprint-shaped, not expired."""
    result = subprocess.run(
        [sys.executable, str(DETECTOR), "--offline", "--today", "2026-10-06"],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    assert {b["environment"] for b in lock["bindings"]} == {"prod", "dev"}
    assert {b["secret_name"] for b in lock["bindings"]} == {"auth-secret", "embed-tenants"}
    # prod and dev must not share a value, or one app was copied over the other
    by_env = {(b["resource_group"], b["secret_name"]): b["sha256"] for b in lock["bindings"]}
    assert len(set(by_env.values())) == len(by_env)