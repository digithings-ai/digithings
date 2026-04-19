"""Unit tests for the digibase bounded-timeout httpx helpers."""

from __future__ import annotations

import httpx
import pytest

from digibase import DEFAULT_TIMEOUT, async_client, sync_client


pytestmark = pytest.mark.unit


def test_default_timeout_envelope() -> None:
    """Default envelope matches the documented connect/read/write/pool values."""
    assert isinstance(DEFAULT_TIMEOUT, httpx.Timeout)
    assert DEFAULT_TIMEOUT.connect == 5.0
    assert DEFAULT_TIMEOUT.read == 30.0
    assert DEFAULT_TIMEOUT.write == 10.0
    assert DEFAULT_TIMEOUT.pool == 5.0


def test_sync_client_uses_default_timeout() -> None:
    with sync_client() as client:
        assert isinstance(client, httpx.Client)
        assert client.timeout == DEFAULT_TIMEOUT


def test_async_client_uses_default_timeout() -> None:
    # No ``aclose()`` — no request was dispatched, no sockets to release.
    client = async_client()
    assert isinstance(client, httpx.AsyncClient)
    assert client.timeout == DEFAULT_TIMEOUT


def test_async_client_timeout_override_scalar() -> None:
    """Passing ``timeout=60`` overrides every phase with the scalar value."""
    client = async_client(timeout=60)
    expected = httpx.Timeout(60)
    assert client.timeout == expected


def test_sync_client_timeout_override_scalar() -> None:
    with sync_client(timeout=2.5) as client:
        assert client.timeout == httpx.Timeout(2.5)


def test_async_client_timeout_override_envelope() -> None:
    override = httpx.Timeout(connect=1.0, read=2.0, write=3.0, pool=4.0)
    client = async_client(timeout=override)
    assert client.timeout == override


def test_async_client_accepts_standard_kwargs() -> None:
    """``async_client`` forwards standard httpx kwargs without error."""
    client = async_client(
        base_url="https://example.test",
        headers={"X-Trace": "unit"},
        auth=("user", "pass"),
    )
    assert str(client.base_url) == "https://example.test"
    assert client.headers["X-Trace"] == "unit"


def test_sync_client_accepts_standard_kwargs() -> None:
    with sync_client(
        base_url="https://example.test",
        headers={"X-Trace": "unit"},
    ) as client:
        assert str(client.base_url) == "https://example.test"
        assert client.headers["X-Trace"] == "unit"
