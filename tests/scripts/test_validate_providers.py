"""Unit tests for the OpenRouter connectivity retry in scripts/atlas/validate-providers.py (#1633).

Both the 2026-08-11 and 2026-08-12 daily olympus runs died at this single-shot, unretried
``openrouter/auto`` ping returning an empty completion — even though the real digillm-routed
checks in the same run (structured output, function tools, web search) passed cleanly, proving
the pipeline itself was healthy and only this preflight ping was flaky. These tests pin the
retry contract without touching OpenRouter.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any  # score:allow untyped any — dynamically loaded module + fake SDK stand-ins

import openai
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = REPO_ROOT / "digiquant" / "scripts" / "atlas" / "validate-providers.py"

pytestmark = pytest.mark.unit


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("validate_providers", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def vp() -> Any:
    return _load_module()


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch, vp: Any) -> list[float]:
    """Retries sleep 5s each; capture delays so tests can assert on them, not wall time."""
    delays: list[float] = []
    monkeypatch.setattr(vp.time, "sleep", delays.append)
    return delays


@pytest.fixture(autouse=True)
def _api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")


class _FakeCompletions:
    """Minimal chat.completions stand-in that replays a scripted sequence of contents."""

    def __init__(self, contents: list[str]) -> None:
        self._contents = list(contents)
        self.calls = 0
        self.request_kwargs: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls += 1
        self.request_kwargs.append(kwargs)
        content = self._contents.pop(0)
        message = type("Message", (), {"content": content})()
        choice = type("Choice", (), {"message": message})()
        return type("Completion", (), {"choices": [choice]})()


class _FakeClient:
    def __init__(self, contents: list[str]) -> None:
        self.chat = type("Chat", (), {"completions": _FakeCompletions(contents)})()


def _patch_client(monkeypatch: pytest.MonkeyPatch, contents: list[str]) -> _FakeClient:
    client = _FakeClient(contents)
    constructor_kwargs: dict[str, Any] = {}

    def _fake_openai(**kwargs: Any) -> _FakeClient:
        constructor_kwargs.update(kwargs)
        return client

    monkeypatch.setattr(openai, "OpenAI", _fake_openai)
    client.constructor_kwargs = constructor_kwargs  # type: ignore[attr-defined]
    return client


def test_immediate_success_makes_one_call_no_retry(
    monkeypatch: pytest.MonkeyPatch, vp: Any, _no_sleep: list[float]
) -> None:
    """No retry storm on the happy path."""
    client = _patch_client(monkeypatch, ["ok"])
    assert vp.check_openrouter("openrouter/auto") is True
    assert client.chat.completions.calls == 1
    assert _no_sleep == []


def test_empty_then_success_retries_once(
    monkeypatch: pytest.MonkeyPatch, vp: Any, _no_sleep: list[float]
) -> None:
    """A single empty completion is retried, not treated as a hard failure — the #1633 fix."""
    client = _patch_client(monkeypatch, ["", "ok"])
    assert vp.check_openrouter("openrouter/auto") is True
    assert client.chat.completions.calls == 2
    assert _no_sleep == [vp._OPENROUTER_PING_RETRY_DELAY]


def test_persistent_empty_exhausts_retries_and_fails(
    monkeypatch: pytest.MonkeyPatch, vp: Any, _no_sleep: list[float]
) -> None:
    """A genuinely dead provider still fails the preflight after a fixed, bounded retry budget."""
    client = _patch_client(monkeypatch, ["", "", "", ""])
    assert vp.check_openrouter("openrouter/auto") is False
    assert vp._OPENROUTER_PING_RETRY_MAX == 3
    assert client.chat.completions.calls == 4
    assert _no_sleep == [vp._OPENROUTER_PING_RETRY_DELAY] * 3


def test_client_is_bounded_and_does_not_stack_sdk_retries(
    monkeypatch: pytest.MonkeyPatch, vp: Any
) -> None:
    """The client must own a fixed timeout and not stack the SDK's own retry-on-error on top of
    our loop, or a single hung connection could blow well past the intended ~80s worst case."""
    client = _patch_client(monkeypatch, ["ok"])
    vp.check_openrouter("openrouter/auto")
    assert client.constructor_kwargs["timeout"] == vp._OPENROUTER_PING_TIMEOUT  # type: ignore[attr-defined]
    assert client.constructor_kwargs["max_retries"] == 0  # type: ignore[attr-defined]


def test_request_targets_the_given_model_with_a_short_deterministic_prompt(
    monkeypatch: pytest.MonkeyPatch, vp: Any
) -> None:
    """The ping must stay a cheap, deterministic 1-token check against the requested model."""
    client = _patch_client(monkeypatch, ["ok"])
    vp.check_openrouter("openrouter/some-model")
    request = client.chat.completions.request_kwargs[0]
    assert request["model"] == "openrouter/some-model"
    assert request["messages"] == [{"role": "user", "content": "Reply with the single word: ok"}]
    assert request["temperature"] == 0
