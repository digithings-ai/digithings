"""The digisearch hub call must not mask service failures as empty results (#4106).

`_call_digisearch_web_search` returned `{}` for *any* hub failure, and every
caller reports `{}` as "web_search returned no rows". On 2026-09-15 the hosted
digisearch rate limiter 429'd the daily book run, and the log said only
"returned no rows" — a day of debugging for a cause that was in the response
all along. A hub failure now raises `DigisearchHubError` carrying the hub's own
error text; a genuinely empty result set still returns `{}` (so callers keep
their no-synthesis, fail-hard contract, #3859).
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


def _invoke_with(monkeypatch: pytest.MonkeyPatch, response: Any) -> dict[str, Any]:
    # The service base is fail-loud when unconfigured (#4057); the hub call is
    # patched, so the URL only has to exist.
    monkeypatch.setenv("DIGISEARCH_URL", "https://search.example.test")
    monkeypatch.setattr(digisearch_hub, "invoke_digisearch_tool", lambda *a, **k: response)
    return web_search_tools.call_digisearch_web_search("news", context=_context())


class TestHubFailuresRaise:
    def test_rate_limit_message_reaches_the_caller(self, monkeypatch: pytest.MonkeyPatch) -> None:
        error = "digisearch invoke failed: Client error '429 Too Many Requests' for url 'https://search.digithings.ai/v1/orchestrator_invoke'"
        with pytest.raises(web_search_tools.DigisearchHubError) as excinfo:
            _invoke_with(monkeypatch, {"ok": False, "error": error})
        assert "429" in str(excinfo.value)
        assert "digisearch web_search failed" in str(excinfo.value)

    def test_circuit_open_reaches_the_caller(self, monkeypatch: pytest.MonkeyPatch) -> None:
        with pytest.raises(web_search_tools.DigisearchHubError) as excinfo:
            _invoke_with(
                monkeypatch,
                {"ok": False, "error": "digisearch circuit open; downstream unavailable"},
            )
        assert "circuit open" in str(excinfo.value)

    def test_non_object_response_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        with pytest.raises(web_search_tools.DigisearchHubError):
            _invoke_with(monkeypatch, ["not", "an", "object"])

    def test_envelope_without_a_data_object_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        with pytest.raises(web_search_tools.DigisearchHubError):
            _invoke_with(monkeypatch, {"ok": True, "data": "nope"})

    def test_error_is_named_in_the_exception_type(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A distinct type so callers can tell a broken service from an empty search."""
        with pytest.raises(web_search_tools.DigisearchHubError):
            _invoke_with(monkeypatch, {"ok": False, "error": "boom"})
        assert issubclass(web_search_tools.DigisearchHubError, RuntimeError)


class TestGenuineEmptyStillReturnsEmpty:
    def test_empty_results_do_not_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert _invoke_with(monkeypatch, {"ok": True, "data": {"results": []}}) == {}

    def test_missing_results_key_does_not_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert _invoke_with(monkeypatch, {"ok": True, "data": {}}) == {}

    def test_rows_are_normalized(self, monkeypatch: pytest.MonkeyPatch) -> None:
        out = _invoke_with(
            monkeypatch,
            {
                "ok": True,
                "data": {
                    "results": [
                        {"url": "https://a.com/1", "title": "t", "snippet": "s"},
                        {"url": "", "title": "skipped", "snippet": ""},
                    ]
                },
            },
        )
        assert [r["doc_id"] for r in out["results"]] == ["https://a.com/1"]
        assert out["results"][0]["metadata"]["evidence_tier"] == "External"
        assert out["content"] == "- [t](https://a.com/1) — s"
