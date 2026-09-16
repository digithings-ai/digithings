"""Fail-first tests for the web_search pre-flight health check (#4198).

The daily book pipeline must learn that the web_search tool is dead *before*
running ~3h of research. These tests pin the health-check contract:

- healthy = ``ok: true`` envelope with a non-empty result set;
- a soft ``{"ok": false, ...}`` envelope, an HTTP 5xx surfaced through the hub,
  an empty result set, a malformed envelope, and a transport error all fail;
- the CLI exits non-zero and names the tool, endpoint, and underlying error.

They exercise the real call chain (``call_web_search_tool`` -> digigraph hub
envelope), patching only the HTTP boundary (:func:`invoke_digisearch_tool`) and
the service-JWT mint so no live search is needed.
"""

from __future__ import annotations

import httpx
import pytest
from click.testing import CliRunner
from digiquant.cli import main as digiquant_main
from digiquant.research.data.web_search_health import (
    WebSearchHealth,
    WebSearchHealthError,
    check_web_search_health,
)

pytestmark = pytest.mark.unit

_SEARCH_BASE = "https://search.digithings.ai"
_ENDPOINT = f"{_SEARCH_BASE}/v1/orchestrator_invoke"
_HIT = {
    "url": "https://example.com/python",
    "title": "Python",
    "snippet": "Python is a programming language.",
}


@pytest.fixture()
def digisearch_env(monkeypatch: pytest.MonkeyPatch) -> str:
    """Resolve the digisearch base and mute service-JWT minting for the test."""
    monkeypatch.setenv("DIGISEARCH_URL", _SEARCH_BASE)
    monkeypatch.setattr(
        "digiquant.research.data.web_grounding._pipeline_bearer",
        lambda: None,
    )
    return _ENDPOINT


def _out(result) -> str:
    """stdout+stderr as one string, across click CliRunner versions."""
    return result.output + (getattr(result, "stderr", None) or "")


def _patch_hub(monkeypatch: pytest.MonkeyPatch, result: dict, calls: list | None = None) -> None:
    """Patch the hub HTTP boundary; ``result`` is the envelope or an exception."""

    def fake_invoke(
        base_url: str,
        tool: str,
        arguments: dict,
        *,
        default_index_name: str,
        bearer_token: str | None,
        request_id: str | None,
        timeout: float = 120.0,
    ) -> dict:
        if isinstance(result, Exception):
            raise result
        if calls is not None:
            calls.append(
                {
                    "base_url": base_url,
                    "tool": tool,
                    "arguments": arguments,
                    "default_index_name": default_index_name,
                    "timeout": timeout,
                }
            )
        assert base_url == _SEARCH_BASE
        return result

    monkeypatch.setattr(
        "digigraph.vertical_orchestrator.digisearch_hub.invoke_digisearch_tool", fake_invoke
    )


def _invoke_cli(*args: str):
    return CliRunner().invoke(digiquant_main, ["web-search", "healthcheck", *args])


def test_healthcheck_passes_on_ok_envelope_with_results(
    digisearch_env: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list = []
    _patch_hub(monkeypatch, {"ok": True, "data": {"results": [_HIT]}}, calls)

    result = _invoke_cli()

    assert result.exit_code == 0, _out(result)
    assert "ok" in _out(result).lower()
    assert _ENDPOINT in _out(result)


def test_healthcheck_sends_minimal_deterministic_query(
    digisearch_env: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list = []
    _patch_hub(monkeypatch, {"ok": True, "data": {"results": [_HIT]}}, calls)

    result = _invoke_cli("--timeout", "5")

    assert result.exit_code == 0, _out(result)
    assert len(calls) == 1
    call = calls[0]
    assert call["tool"] == "web_search"
    assert call["arguments"]["include_domains"] == []
    assert call["arguments"]["max_results"] == 1
    assert isinstance(call["arguments"]["query"], str) and call["arguments"]["query"]
    assert call["timeout"] == 5.0


def test_healthcheck_fails_on_http_500_envelope(
    digisearch_env: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_hub(
        monkeypatch,
        {
            "ok": False,
            "error": (
                "digisearch invoke failed: Server error '500 Internal Server Error' "
                f"for url '{_ENDPOINT}'"
            ),
        },
    )

    result = _invoke_cli()

    assert result.exit_code != 0
    assert "500" in _out(result)
    assert _ENDPOINT in _out(result)


def test_healthcheck_fails_on_soft_ok_false_envelope(
    digisearch_env: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_hub(monkeypatch, {"ok": False, "error": "provider backend unavailable"})

    result = _invoke_cli()

    assert result.exit_code != 0
    assert "provider backend unavailable" in _out(result)


def test_healthcheck_fails_on_empty_result_set(
    digisearch_env: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_hub(monkeypatch, {"ok": True, "data": {"results": []}})

    result = _invoke_cli()

    assert result.exit_code != 0
    assert "no rows" in _out(result)


def test_healthcheck_fails_on_malformed_envelope(
    digisearch_env: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_hub(monkeypatch, {"ok": True})

    result = _invoke_cli()

    assert result.exit_code != 0
    assert "no data object" in _out(result)


def test_healthcheck_fails_on_connection_error(
    digisearch_env: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_hub(monkeypatch, httpx.ConnectError("connection refused"))

    result = _invoke_cli()

    assert result.exit_code != 0
    assert "connection refused" in _out(result)
    assert _ENDPOINT in _out(result)


def test_healthcheck_fails_on_timeout(digisearch_env: str, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_hub(monkeypatch, httpx.ReadTimeout("read timed out"))

    result = _invoke_cli()

    assert result.exit_code != 0
    assert "read timed out" in _out(result)


def test_web_search_group_is_registered_on_main() -> None:
    result = CliRunner().invoke(digiquant_main, ["web-search", "--help"])

    assert result.exit_code == 0, _out(result)
    assert "healthcheck" in _out(result)


def test_check_web_search_health_returns_health_on_success(
    digisearch_env: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "digiquant.research.data.web_grounding.call_web_search_tool",
        lambda **kwargs: {
            "summary": "- [Python](https://example.com/python)",
            "sources": ["https://example.com/python"],
        },
    )

    health = check_web_search_health(timeout_s=5.0)

    assert isinstance(health, WebSearchHealth)
    assert health.ok is True
    assert health.results == 1
    assert health.endpoint == _ENDPOINT
    assert health.elapsed_s >= 0.0
    assert health.error == ""


def test_check_web_search_health_raises_with_endpoint_and_error(
    digisearch_env: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(**kwargs):
        raise httpx.TimeoutException("handshake timed out")

    monkeypatch.setattr("digiquant.research.data.web_grounding.call_web_search_tool", _boom)

    with pytest.raises(WebSearchHealthError) as excinfo:
        check_web_search_health(timeout_s=5.0)

    message = str(excinfo.value)
    assert "web_search" in message
    assert _ENDPOINT in message
    assert "handshake timed out" in message


def test_check_web_search_health_raises_on_no_rows(
    digisearch_env: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _empty(**kwargs):
        raise RuntimeError("digisearch web_search returned no rows (unscoped)")

    monkeypatch.setattr("digiquant.research.data.web_grounding.call_web_search_tool", _empty)

    with pytest.raises(WebSearchHealthError, match="no rows"):
        check_web_search_health()


def test_chain_guard_fails_hard_when_web_search_is_unhealthy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The research-stage guard is the one deliberate fail-hard gate (#4198)."""
    from digiquant.portfolio import chain

    def _unhealthy(*, timeout_s: float = 25.0) -> WebSearchHealth:
        raise WebSearchHealthError(
            "web_search pre-flight failed: tool=web_search "
            f"endpoint={_ENDPOINT} elapsed=0.10s error=provider down"
        )

    monkeypatch.setattr(
        "digiquant.research.data.web_search_health.check_web_search_health", _unhealthy
    )

    with pytest.raises(WebSearchHealthError):
        chain._guard_web_search_health()
