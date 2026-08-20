"""Unit tests for OpenRouter connectivity check in scripts/atlas/validate-providers.py (#2374).

The 2026-08-11/12/15/18/19/20 daily olympus runs all died at this preflight ping: a bare,
unconstrained ``openrouter/auto`` call made through a standalone OpenAI client with its own
ad-hoc retry loop — bypassing every protection (empty-completion self-heal, provider fallback
swap) that digillm gives every other call in the codebase, and pinging a model no real phase
ever uses. The fix routes this ping through ``digillm.client.completion`` (same self-heal path
production gets) and pins it to a known-good model instead of bare auto. These tests pin that
contract without touching OpenRouter.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any  # score:allow untyped any — dynamically loaded module + fake SDK stand-ins
from unittest.mock import patch

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
def _api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")


def _fake_response(content: str | None) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def test_default_model_is_pinned_not_bare_auto(vp: Any) -> None:
    """The regression: the ping must pin to a known-good model, never bare openrouter/auto."""
    assert vp._CONNECTIVITY_PING_MODEL == "openrouter/deepseek/deepseek-v4-flash"


def test_success_routes_through_digillm_and_passes(vp: Any) -> None:
    calls: list[dict[str, Any]] = []

    def fake_completion(model: str, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        calls.append({"model": model, "messages": messages, **kwargs})
        return _fake_response("ok")

    with patch("digillm.client.completion", side_effect=fake_completion):
        assert vp.check_openrouter() is True

    assert len(calls) == 1
    request = calls[0]
    assert request["model"] == vp._CONNECTIVITY_PING_MODEL
    assert request["messages"] == [{"role": "user", "content": "Reply with the single word: ok"}]
    assert request["temperature"] == 0
    assert "max_tokens" not in request


def test_empty_completion_fails_after_digillm_self_heal(vp: Any) -> None:
    """digillm owns the empty-retry self-heal now; a still-empty result is a hard failure here."""
    with patch("digillm.client.completion", return_value=_fake_response("")):
        assert vp.check_openrouter() is False


def test_none_response_fails(vp: Any) -> None:
    with patch("digillm.client.completion", return_value=None):
        assert vp.check_openrouter() is False


def test_exception_is_caught_and_reported_as_failure(vp: Any) -> None:
    with patch("digillm.client.completion", side_effect=RuntimeError("boom")):
        assert vp.check_openrouter() is False


def test_missing_api_key_fails_without_calling_digillm(
    vp: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with patch("digillm.client.completion") as completion:
        assert vp.check_openrouter() is False
    completion.assert_not_called()


def test_accepts_an_explicit_model_override(vp: Any) -> None:
    """Callers (e.g. a future targeted diagnostic) can still ping a specific model."""
    calls: list[dict[str, Any]] = []

    def fake_completion(model: str, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        calls.append({"model": model, **kwargs})
        return _fake_response("ok")

    with patch("digillm.client.completion", side_effect=fake_completion):
        assert vp.check_openrouter("openrouter/some-model") is True

    assert calls[0]["model"] == "openrouter/some-model"


def _fake_tier_config(models: list[str]) -> Any:
    tier_cfg = SimpleNamespace(allowed_models={"phase": models})
    return SimpleNamespace(tiers={"cheap": tier_cfg})


def test_function_tools_pass_on_text_content(vp: Any) -> None:
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=None))]
    )
    with (
        patch("digigraph.model_config.get_olympus_tier", return_value="cheap"),
        patch(
            "digigraph.model_config._load_olympus_models",
            return_value=_fake_tier_config(["openrouter/some-model"]),
        ),
        patch("digillm.client.completion", return_value=response),
    ):
        assert vp.check_openrouter_function_tools() is True


def test_function_tools_pass_on_tool_calls_with_no_content(vp: Any) -> None:
    """A tool-call-only response has no text content but isn't empty — must still PASS."""
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[SimpleNamespace()]))
        ]
    )
    with (
        patch("digigraph.model_config.get_olympus_tier", return_value="cheap"),
        patch(
            "digigraph.model_config._load_olympus_models",
            return_value=_fake_tier_config(["openrouter/some-model"]),
        ),
        patch("digillm.client.completion", return_value=response),
    ):
        assert vp.check_openrouter_function_tools() is True


def test_function_tools_fail_on_truly_empty_response(vp: Any) -> None:
    """The regression this check exists for: resp is not None but carries no content or tool_calls."""
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="", tool_calls=None))]
    )
    with (
        patch("digigraph.model_config.get_olympus_tier", return_value="cheap"),
        patch(
            "digigraph.model_config._load_olympus_models",
            return_value=_fake_tier_config(["openrouter/some-model"]),
        ),
        patch("digillm.client.completion", return_value=response),
    ):
        assert vp.check_openrouter_function_tools() is False
