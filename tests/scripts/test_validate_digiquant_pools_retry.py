"""Unit tests for `_request` retry behaviour in scripts/validate_digiquant_pools.py (#1717).

The pool gate talks to a live OpenRouter API, so a slow upstream call must not fail the
sweep on its own. `_request` retried transient *statuses* but not timeouts: a timeout
raises out of `client.request` rather than returning a response, so it bypassed the status
check entirely and one slow `/models/{slug}/endpoints` call took the whole gate red after
seven slugs had already passed (run 30543907845).

These tests pin both halves of the retry contract without any network access.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any  # score:allow untyped any — dynamically loaded module + **kwargs passthrough

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = REPO_ROOT / "scripts" / "validate_digiquant_pools.py"

pytestmark = pytest.mark.unit


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("validate_digiquant_pools", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def vop() -> Any:
    return _load_module()


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch, vop: Any) -> None:
    """Retries sleep 5s each; tests assert on call counts, not wall time."""
    monkeypatch.setattr(vop.time, "sleep", lambda _s: None)


class _FakeClient:
    """Minimal httpx.Client stand-in that replays a scripted sequence of outcomes."""

    def __init__(self, outcomes: list[Any]) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _resp(status: int) -> httpx.Response:
    return httpx.Response(status_code=status, request=httpx.Request("GET", "https://x/y"))


def test_timeout_is_retried_once_and_succeeds(vop: Any) -> None:
    """A single ReadTimeout must be retried, not propagated — the regression this fixes."""
    client = _FakeClient([httpx.ReadTimeout("slow"), _resp(200)])
    resp = vop._request(client, "GET", "https://x/y")
    assert resp.status_code == 200
    assert client.calls == 2


def test_timeout_twice_still_raises(vop: Any) -> None:
    """One retry only: a persistently timing-out endpoint is a real failure."""
    client = _FakeClient([httpx.ReadTimeout("slow"), httpx.ReadTimeout("slow again")])
    with pytest.raises(httpx.ReadTimeout):
        vop._request(client, "GET", "https://x/y")
    assert client.calls == 2


def test_connect_timeout_also_retried(vop: Any) -> None:
    """The guard catches TimeoutException, so connect timeouts are covered too."""
    client = _FakeClient([httpx.ConnectTimeout("no route"), _resp(200)])
    assert vop._request(client, "GET", "https://x/y").status_code == 200
    assert client.calls == 2


@pytest.mark.parametrize("status", [429, 500, 502, 503])
def test_retryable_status_still_retried(vop: Any, status: int) -> None:
    """Pre-existing status retry must survive the timeout change."""
    client = _FakeClient([_resp(status), _resp(200)])
    assert vop._request(client, "GET", "https://x/y").status_code == 200
    assert client.calls == 2


def test_non_retryable_status_returned_as_is(vop: Any) -> None:
    """404 is a verdict, not a blip — returned without a second call."""
    client = _FakeClient([_resp(404)])
    assert vop._request(client, "GET", "https://x/y").status_code == 404
    assert client.calls == 1


def test_success_makes_exactly_one_call(vop: Any) -> None:
    """No retry storm on the happy path."""
    client = _FakeClient([_resp(200)])
    assert vop._request(client, "GET", "https://x/y").status_code == 200
    assert client.calls == 1


def test_timeout_then_retryable_status_retries_both(vop: Any) -> None:
    """The two retry paths compose: a timeout retry can still land on a 503 and retry again."""
    client = _FakeClient([httpx.ReadTimeout("slow"), _resp(503), _resp(200)])
    assert vop._request(client, "GET", "https://x/y").status_code == 200
    assert client.calls == 3
