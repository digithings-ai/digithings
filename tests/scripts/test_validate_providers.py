"""Unit tests for the OpenRouter connectivity retry in scripts/atlas/validate-providers.py (#1633).

Both the 2026-08-11 and 2026-08-12 daily Olympus runs died at this single-shot, unretried
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
def _no_sleep(monkeypatch: pytest.MonkeyPatch, vp: Any) -> None:
    """Retries sleep 5s each; tests assert on call counts, not wall time."""
    monkeypatch.setattr(vp.time, "sleep", lambda _s: None)


@pytest.fixture(autouse=True)
def _api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")


class _FakeCompletions:
    """Minimal chat.completions stand-in that replays a scripted sequence of contents."""

    def __init__(self, contents: list[str]) -> None:
        self._contents = list(contents)
        self.calls = 0

    def create(self, **_kwargs: Any) -> Any:
        self.calls += 1
        content = self._contents.pop(0)
        message = type("Message", (), {"content": content})()
        choice = type("Choice", (), {"message": message})()
        return type("Completion", (), {"choices": [choice]})()


class _FakeClient:
    def __init__(self, contents: list[str]) -> None:
        self.chat = type("Chat", (), {"completions": _FakeCompletions(contents)})()


def _patch_client(monkeypatch: pytest.MonkeyPatch, contents: list[str]) -> _FakeClient:
    client = _FakeClient(contents)
    monkeypatch.setattr(openai, "OpenAI", lambda **_kwargs: client)
    return client


def test_immediate_success_makes_one_call_no_retry(
    monkeypatch: pytest.MonkeyPatch, vp: Any
) -> None:
    """No retry storm on the happy path."""
    client = _patch_client(monkeypatch, ["ok"])
    assert vp.check_openrouter("openrouter/auto") is True
    assert client.chat.completions.calls == 1


def test_empty_then_success_retries_once(monkeypatch: pytest.MonkeyPatch, vp: Any) -> None:
    """A single empty completion is retried, not treated as a hard failure — the #1633 fix."""
    client = _patch_client(monkeypatch, ["", "ok"])
    assert vp.check_openrouter("openrouter/auto") is True
    assert client.chat.completions.calls == 2


def test_persistent_empty_exhausts_retries_and_fails(
    monkeypatch: pytest.MonkeyPatch, vp: Any
) -> None:
    """A genuinely dead provider still fails the preflight after bounded retries."""
    client = _patch_client(monkeypatch, ["", "", "", ""])
    assert vp.check_openrouter("openrouter/auto") is False
    assert client.chat.completions.calls == 1 + vp._OPENROUTER_PING_RETRY_MAX
