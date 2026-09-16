"""The hub payload must carry every request knob the caller set (#4165).

``recency_days`` is a real field on digisearch's ``WebSearchRequest`` (default 7),
but the hub call dropped it: an operator raising the config to 30 kept searching
7 days while the query text claimed otherwise. The key is omitted when unset so
digisearch's own default applies — never sent as an explicit ``None``, which the
model reads as "no recency window" and would silently widen every search.
"""

from __future__ import annotations

from typing import Any

import pytest
from digigraph.orchestration import web_search_tools
from digigraph.orchestration.registry import ToolContext
from digigraph.vertical_orchestrator import digisearch_hub

pytestmark = pytest.mark.unit


def _context() -> ToolContext:
    return ToolContext(
        session_id=None,
        run_data_dir=None,
        index_name="default",
        index_config={},
        state={"digi_bearer": "svc-jwt"},
    )


def _capture_arguments(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Patch the hub call and capture the outbound tool ``arguments``."""
    monkeypatch.setenv("DIGISEARCH_URL", "https://search.example.test")
    captured: dict[str, Any] = {}

    def _invoke(
        base_url: str, tool: str, arguments: dict[str, Any], **kwargs: Any
    ) -> dict[str, Any]:
        captured.update(arguments)
        return {
            "ok": True,
            "data": {"results": [{"url": "https://a.com/1", "title": "t", "snippet": "s"}]},
        }

    monkeypatch.setattr(digisearch_hub, "invoke_digisearch_tool", _invoke)
    return captured


def test_recency_days_reaches_the_hub_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_arguments(monkeypatch)
    web_search_tools.call_digisearch_web_search("news", recency_days=30, context=_context())
    assert captured["recency_days"] == 30


def test_recency_days_is_omitted_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Absent means "digisearch default (7)"; an explicit None would drop the window."""
    captured = _capture_arguments(monkeypatch)
    web_search_tools.call_digisearch_web_search("news", context=_context())
    assert "recency_days" not in captured
