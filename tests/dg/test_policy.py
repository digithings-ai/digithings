"""digigraph policy env gates (debug / thread API / hub mode)."""

from __future__ import annotations

import pytest
from digigraph.policy import (
    debug_endpoints_enabled,
    federated_hub_enabled,
    hub_mode,
    thread_api_enabled,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1", True),
        ("true", True),
        ("YES", True),
        ("0", False),
        ("", False),
        ("no", False),
    ],
)
def test_debug_endpoints_enabled_truthy_matrix(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: bool
) -> None:
    if raw == "":
        monkeypatch.delenv("DIGI_ENABLE_DEBUG_ENDPOINTS", raising=False)
    else:
        monkeypatch.setenv("DIGI_ENABLE_DEBUG_ENDPOINTS", raw)
    assert debug_endpoints_enabled() is expected


@pytest.mark.unit
def test_thread_api_enabled_defaults_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGI_ENABLE_THREAD_API", raising=False)
    assert thread_api_enabled() is False
    monkeypatch.setenv("DIGI_ENABLE_THREAD_API", "1")
    assert thread_api_enabled() is True


@pytest.mark.unit
def test_hub_mode_defaults_legacy_and_federated_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DIGI_HUB_MODE", raising=False)
    assert hub_mode() == "legacy"
    assert federated_hub_enabled() is False
    monkeypatch.setenv("DIGI_HUB_MODE", " Federated ")
    assert hub_mode() == "federated"
    assert federated_hub_enabled() is True
