"""xAI Agent Tools x_search via the Responses API (#658).

x_search returns citations INLINE in output_text as [[n]](url) (not in
output[].action.sources like web_search), so sources are regex-extracted.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from digigraph.llm import x_search


@pytest.mark.unit
def test_x_search_returns_text_and_inline_sources_for_xai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XAI_API_KEY", "test-key")
    text = (
        "@theaiportfolios added $LLY[[1]](https://x.com/theaiportfolios/status/1) and "
        "trimmed $NVDA[[2]](https://x.com/grkportfolio/status/2)."
    )
    client = MagicMock()
    client.responses.create.return_value = SimpleNamespace(output_text=text, output=[])
    with patch("digigraph.llm.get_client_for_model", return_value=client):
        result = x_search("xai/grok-4.3", "latest holdings")
    assert result is not None
    out, sources = result
    assert "$LLY" in out
    assert sources == [
        "https://x.com/theaiportfolios/status/1",
        "https://x.com/grkportfolio/status/2",
    ]
    assert client.responses.create.call_args[1]["tools"][0]["type"] == "x_search"


@pytest.mark.unit
def test_x_search_none_for_non_xai():
    assert x_search("gpt-4o-mini", "q") is None


@pytest.mark.unit
def test_x_search_fails_soft_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XAI_API_KEY", "test-key")
    client = MagicMock()
    client.responses.create.side_effect = RuntimeError("boom")
    with patch("digigraph.llm.get_client_for_model", return_value=client):
        assert x_search("xai/grok-4.3", "q") is None
