"""Checkpointer acquisition is best-effort (#667) — a bad URI must not crash the run."""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytest.importorskip("openai")  # chain -> atlas.graph -> digigraph.llm needs openai

from digiquant.olympus.hermes import chain  # noqa: E402


@pytest.mark.unit
def test_acquire_none_when_env_unset(monkeypatch):
    monkeypatch.delenv("DIGI_CHECKPOINTER", raising=False)
    assert chain._acquire_checkpointer() is None


@pytest.mark.unit
def test_acquire_returns_saver_when_available(monkeypatch):
    monkeypatch.setenv("DIGI_CHECKPOINTER", "postgres")
    sentinel = object()
    with patch("digigraph.graph.graph.get_checkpointer", return_value=sentinel):
        assert chain._acquire_checkpointer() is sentinel


@pytest.mark.unit
def test_acquire_degrades_to_none_on_init_failure(monkeypatch):
    # Bad URI / unreachable Postgres → setup() raises → must degrade to None, not crash.
    monkeypatch.setenv("DIGI_CHECKPOINTER", "postgres")
    with patch(
        "digigraph.graph.graph.get_checkpointer",
        side_effect=RuntimeError("could not connect to server"),
    ):
        assert chain._acquire_checkpointer() is None
