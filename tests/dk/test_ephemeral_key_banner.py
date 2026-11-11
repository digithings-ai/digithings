"""digikey's startup warning when it signs with an ephemeral key."""

from __future__ import annotations

import logging
import os

# Signing key loads at digikey.server import — allow ephemeral RS256 for unit tests.
if not (os.environ.get("DIGIKEY_PRIVATE_KEY_PEM") or "").strip():
    os.environ.setdefault("DIGIKEY_ALLOW_EPHEMERAL_KEY", "1")

import pytest

from digikey import crypto_keys, server

pytestmark = pytest.mark.unit


def _warnings(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [
        r for r in caplog.records if r.name == server.logger.name and r.levelno == logging.WARNING
    ]


@pytest.mark.parametrize("flag", ["1", "true", "YES", " yes "])
def test_crypto_keys_records_an_ephemeral_key(monkeypatch: pytest.MonkeyPatch, flag: str) -> None:
    monkeypatch.delenv("DIGIKEY_PRIVATE_KEY_PEM", raising=False)
    monkeypatch.setenv("DIGIKEY_ALLOW_EPHEMERAL_KEY", flag)
    crypto_keys.load_or_create_signing_key()
    assert crypto_keys.ephemeral_key_in_use() is True


def test_crypto_keys_records_a_stable_key(monkeypatch: pytest.MonkeyPatch) -> None:
    pem = crypto_keys.private_key_to_pem(crypto_keys.generate_rsa_private_key())
    monkeypatch.setenv("DIGIKEY_PRIVATE_KEY_PEM", pem)
    monkeypatch.setenv("DIGIKEY_ALLOW_EPHEMERAL_KEY", "1")  # a PEM always wins
    crypto_keys.load_or_create_signing_key()
    assert crypto_keys.ephemeral_key_in_use() is False


@pytest.mark.parametrize("flag", ["0", "", "on", "2"])
def test_crypto_keys_still_refuses_without_a_truthy_flag(
    monkeypatch: pytest.MonkeyPatch, flag: str
) -> None:
    monkeypatch.delenv("DIGIKEY_PRIVATE_KEY_PEM", raising=False)
    monkeypatch.setenv("DIGIKEY_ALLOW_EPHEMERAL_KEY", flag)
    with pytest.raises(RuntimeError, match="DIGIKEY_PRIVATE_KEY_PEM"):
        crypto_keys.load_or_create_signing_key()


def test_refusal_clears_an_earlier_ephemeral_record(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGIKEY_PRIVATE_KEY_PEM", raising=False)
    monkeypatch.setenv("DIGIKEY_ALLOW_EPHEMERAL_KEY", "1")
    crypto_keys.load_or_create_signing_key()
    assert crypto_keys.ephemeral_key_in_use() is True

    monkeypatch.setenv("DIGIKEY_ALLOW_EPHEMERAL_KEY", "0")
    with pytest.raises(RuntimeError, match="DIGIKEY_PRIVATE_KEY_PEM"):
        crypto_keys.load_or_create_signing_key()
    assert crypto_keys.ephemeral_key_in_use() is False


def _load_ephemeral_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGIKEY_PRIVATE_KEY_PEM", raising=False)
    monkeypatch.setenv("DIGIKEY_ALLOW_EPHEMERAL_KEY", "1")
    crypto_keys.load_or_create_signing_key()
    assert crypto_keys.ephemeral_key_in_use() is True


def test_bad_pem_clears_an_earlier_ephemeral_record(monkeypatch: pytest.MonkeyPatch) -> None:
    _load_ephemeral_once(monkeypatch)
    monkeypatch.setenv("DIGIKEY_PRIVATE_KEY_PEM", "not a pem")
    with pytest.raises(ValueError):
        crypto_keys.load_or_create_signing_key()
    assert crypto_keys.ephemeral_key_in_use() is False


def test_failed_generate_clears_an_earlier_ephemeral_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _load_ephemeral_once(monkeypatch)

    def boom() -> None:
        raise OSError("no entropy")

    # Once the loader caches its ephemeral key in a module variable, drop the
    # cached key so the next load really generates (no-op until then).
    monkeypatch.setattr(crypto_keys, "_ephemeral_key", None, raising=False)
    monkeypatch.setattr(crypto_keys, "generate_rsa_private_key", boom)
    with pytest.raises(OSError, match="no entropy"):
        crypto_keys.load_or_create_signing_key()
    assert crypto_keys.ephemeral_key_in_use() is False


def test_server_captures_the_flag_for_its_own_key() -> None:
    expected = not (os.environ.get("DIGIKEY_PRIVATE_KEY_PEM") or "").strip()
    assert server._ephemeral_key is expected


def test_ephemeral_key_logs_a_loud_multiline_banner(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(server, "_ephemeral_key", True)
    with caplog.at_level(logging.WARNING, logger=server.logger.name):
        server.warn_if_ephemeral_key()
    records = _warnings(caplog)
    assert len(records) == 1
    text = records[0].getMessage()
    assert text.count("\n") >= 5
    assert "EVERY digikey restart" in text
    assert "NOT FOR PRODUCTION" in text
    assert "DIGIKEY_PRIVATE_KEY_PEM" in text


def test_banner_follows_the_recorded_key_not_the_environment(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The banner must not drift from what was loaded when the env changes later."""
    monkeypatch.setattr(server, "_ephemeral_key", True)
    monkeypatch.setenv("DIGIKEY_PRIVATE_KEY_PEM", "-----BEGIN PRIVATE KEY-----\nx\n")
    monkeypatch.setenv("DIGIKEY_ALLOW_EPHEMERAL_KEY", "0")
    with caplog.at_level(logging.WARNING, logger=server.logger.name):
        server.warn_if_ephemeral_key()
    assert len(_warnings(caplog)) == 1

    caplog.clear()
    monkeypatch.setattr(server, "_ephemeral_key", False)
    monkeypatch.delenv("DIGIKEY_PRIVATE_KEY_PEM", raising=False)
    monkeypatch.setenv("DIGIKEY_ALLOW_EPHEMERAL_KEY", "1")
    with caplog.at_level(logging.WARNING, logger=server.logger.name):
        server.warn_if_ephemeral_key()
    assert _warnings(caplog) == []
