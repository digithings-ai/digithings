"""The ephemeral digikey signing key stays in process memory only."""

from __future__ import annotations

import os

import pytest

from digikey import crypto_keys

pytestmark = pytest.mark.unit


@pytest.fixture
def ephemeral_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGIKEY_PRIVATE_KEY_PEM", raising=False)
    monkeypatch.delenv("_DIGIKEY_EPHEMERAL_PEM", raising=False)
    monkeypatch.setenv("DIGIKEY_ALLOW_EPHEMERAL_KEY", "1")
    monkeypatch.delenv("WEB_CONCURRENCY", raising=False)


def _pem_in_environ() -> list[str]:
    return [
        k
        for k, v in os.environ.items()
        if "PRIVATE KEY-----" in v and k != "_PYTEST_DIGIKEY_PRIVATE_PEM"
    ]


def test_no_private_key_reaches_the_environment(ephemeral_env: None) -> None:
    before = _pem_in_environ()
    key, _kid = crypto_keys.load_or_create_signing_key()
    assert "_DIGIKEY_EPHEMERAL_PEM" not in os.environ
    assert _pem_in_environ() == before
    pem = crypto_keys.private_key_to_pem(key)
    assert pem not in os.environ.values()


def test_ephemeral_key_is_stable_within_the_process(ephemeral_env: None) -> None:
    first, _ = crypto_keys.load_or_create_signing_key()
    second, _ = crypto_keys.load_or_create_signing_key()
    assert first is second
    assert crypto_keys.public_key_to_pem(first.public_key()) == crypto_keys.public_key_to_pem(
        second.public_key()
    )


def test_a_stable_pem_still_wins(ephemeral_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    stable = crypto_keys.generate_rsa_private_key()
    monkeypatch.setenv("DIGIKEY_PRIVATE_KEY_PEM", crypto_keys.private_key_to_pem(stable))
    key, _ = crypto_keys.load_or_create_signing_key()
    assert crypto_keys.public_key_to_pem(key.public_key()) == crypto_keys.public_key_to_pem(
        stable.public_key()
    )


def test_refusal_without_the_flag_is_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGIKEY_PRIVATE_KEY_PEM", raising=False)
    monkeypatch.setenv("DIGIKEY_ALLOW_EPHEMERAL_KEY", "0")
    with pytest.raises(RuntimeError, match="DIGIKEY_PRIVATE_KEY_PEM"):
        crypto_keys.load_or_create_signing_key()


def test_concurrent_first_loads_share_one_key(
    ephemeral_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading

    monkeypatch.setattr(crypto_keys, "_ephemeral_key", None)
    barrier = threading.Barrier(8)
    keys: list[object] = []

    def load() -> None:
        barrier.wait()
        keys.append(crypto_keys.load_or_create_signing_key()[0])

    threads = [threading.Thread(target=load) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(keys) == 8
    assert all(k is keys[0] for k in keys)


@pytest.mark.parametrize("workers", ["2", "4", "+2", "abc", "\u0662", " 2 "])
def test_ephemeral_mode_refuses_multiple_workers(
    ephemeral_env: None, monkeypatch: pytest.MonkeyPatch, workers: str
) -> None:
    monkeypatch.setenv("WEB_CONCURRENCY", workers)
    with pytest.raises(RuntimeError, match="single digikey process"):
        crypto_keys.load_or_create_signing_key()


@pytest.mark.parametrize("workers", ["", "1"])
def test_ephemeral_mode_allows_one_worker(
    ephemeral_env: None, monkeypatch: pytest.MonkeyPatch, workers: str
) -> None:
    monkeypatch.setenv("WEB_CONCURRENCY", workers)
    crypto_keys.load_or_create_signing_key()


def test_a_stable_pem_allows_multiple_workers(
    ephemeral_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WEB_CONCURRENCY", "4")
    stable = crypto_keys.generate_rsa_private_key()
    monkeypatch.setenv("DIGIKEY_PRIVATE_KEY_PEM", crypto_keys.private_key_to_pem(stable))
    crypto_keys.load_or_create_signing_key()
