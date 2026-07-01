"""Unit tests for digibase.audit.redact_mapping (recursive)."""

from __future__ import annotations

import pytest

from digibase.audit import redact_mapping


@pytest.mark.unit
def test_redacts_nested_secret_keys() -> None:
    payload = {"user": "alice", "nested": {"api_key": "sk-secret", "count": 1}}
    out = redact_mapping(payload)
    assert out["user"] == "alice"
    assert out["nested"]["api_key"] == "[REDACTED]"
    assert out["nested"]["count"] == 1


@pytest.mark.unit
def test_redacts_list_of_dicts() -> None:
    payload = {"items": [{"token": "abc"}, {"safe": True}]}
    out = redact_mapping(payload)
    assert out["items"][0]["token"] == "[REDACTED]"
    assert out["items"][1]["safe"] is True
