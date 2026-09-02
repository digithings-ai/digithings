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
import os
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
    assert vp._CONNECTIVITY_PING_MODEL == "deepseek/deepseek-v4-flash"


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


def test_preflight_configures_bounded_digillm_env(vp: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """digillm reads timeout/retry env at import — preflight must set them first (#2528/#2531)."""
    monkeypatch.delenv("DIGILLM_REQUEST_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("DIGILLM_EMPTY_RETRY_MAX", raising=False)
    vp._configure_preflight_environment()
    assert os.environ["DIGILLM_REQUEST_TIMEOUT_SECONDS"] == str(
        vp._PREFLIGHT_REQUEST_TIMEOUT_SECONDS
    )
    assert os.environ["DIGILLM_EMPTY_RETRY_MAX"] == str(vp._PREFLIGHT_EMPTY_RETRY_MAX)


def test_preflight_applies_openrouter_allowed_models(
    vp: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preflight must call apply_olympus_openrouter_env so check 3 matches production (#2532)."""
    monkeypatch.delenv("OPENROUTER_ALLOWED_MODELS", raising=False)
    vp._configure_preflight_environment()
    assert os.environ.get("OPENROUTER_ALLOWED_MODELS", "").strip()


def test_structured_auto_router_request_shape_matches_production(
    vp: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """openrouter/auto with a constrained pool uses the auto-router plugin, not require_parameters."""
    monkeypatch.delenv("OPENROUTER_ALLOWED_MODELS", raising=False)
    vp._configure_preflight_environment()
    from digillm.client import _with_openrouter_cost_controls

    kwargs = {
        "model": "openrouter/openrouter/auto",
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "ping", "schema": {"type": "object"}},
        },
    }
    merged = _with_openrouter_cost_controls(kwargs, "openrouter")
    extra = merged["extra_body"]
    auto_plugins = [p for p in extra.get("plugins", []) if p.get("id") == "auto-router"]
    assert auto_plugins, "production constrains openrouter/auto via auto-router plugin"
    assert auto_plugins[0]["allowed_models"]
    provider = extra.get("provider") or {}
    assert "require_parameters" not in provider


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


def test_function_tools_pass_but_reports_substitution(vp: Any) -> None:
    """OpenRouter fallback routing (#2540) attaches to the PRIMARY request, not just retries,
    and can substitute a working pool member for reasons unrelated to tool-use capability
    (e.g. transient provider load-shedding — the exact scenario OPENROUTER_FALLBACK_MODELS
    exists to survive, and which the real pipeline run tolerates via the same env var). A
    substitution must NOT hard-fail the preflight, but must be visible in the detail text.

    Uses a real three-segment pool slug (``openrouter/deepseek/deepseek-v4-flash``, matching
    config/olympus_models.yaml) rather than a two-segment stand-in: a two-segment fixture
    can't distinguish a correct ``removeprefix("openrouter/")`` from a broken
    ``model.split("/")[-1]``-style implementation, since both happen to agree on two segments.
    """
    response = SimpleNamespace(
        model="anthropic/claude-sonnet-5",
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=None))],
    )
    with (
        patch("digigraph.model_config.get_olympus_tier", return_value="cheap"),
        patch(
            "digigraph.model_config._load_olympus_models",
            return_value=_fake_tier_config(["openrouter/deepseek/deepseek-v4-flash"]),
        ),
        patch("digillm.client.completion", return_value=response),
    ):
        assert vp.check_openrouter_function_tools() is True
    detail = vp.results[-1][2]
    assert "served by anthropic/claude-sonnet-5" in detail
    assert "substitution" in detail.lower()


def test_function_tools_reports_served_model_when_matching_requested(vp: Any) -> None:
    """The requested three-segment pool model (bare, ``openrouter/`` stripped) actually served
    the response — no substitution, and the served model is still surfaced for visibility."""
    response = SimpleNamespace(
        model="deepseek/deepseek-v4-flash",
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=None))],
    )
    with (
        patch("digigraph.model_config.get_olympus_tier", return_value="cheap"),
        patch(
            "digigraph.model_config._load_olympus_models",
            return_value=_fake_tier_config(["openrouter/deepseek/deepseek-v4-flash"]),
        ),
        patch("digillm.client.completion", return_value=response),
    ):
        assert vp.check_openrouter_function_tools() is True
    detail = vp.results[-1][2]
    assert "served by deepseek/deepseek-v4-flash" in detail
    assert "substitution" not in detail.lower()


def test_function_tools_pass_when_response_has_no_model_field(vp: Any) -> None:
    """Back-compat: a response object without a ``.model`` attribute has nothing to compare
    against, so substitution can't be detected — must not be treated as a mismatch."""
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=None))]
    )
    with (
        patch("digigraph.model_config.get_olympus_tier", return_value="cheap"),
        patch(
            "digigraph.model_config._load_olympus_models",
            return_value=_fake_tier_config(["openrouter/deepseek/deepseek-v4-flash"]),
        ),
        patch("digillm.client.completion", return_value=response),
    ):
        assert vp.check_openrouter_function_tools() is True


def test_function_tools_reports_substitution_on_unprefixed_house_slug(vp: Any) -> None:
    """House pins are unprefixed OpenRouter slugs (#3414); substitution still surfaces."""
    response = SimpleNamespace(
        model="anthropic/claude-sonnet-5",
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=None))],
    )
    with (
        patch("digigraph.model_config.get_olympus_tier", return_value="cheap"),
        patch(
            "digigraph.model_config._load_olympus_models",
            return_value=_fake_tier_config(["deepseek/deepseek-v4-flash"]),
        ),
        patch("digillm.client.completion", return_value=response),
    ):
        assert vp.check_openrouter_function_tools() is True
    detail = vp.results[-1][2]
    assert "served by anthropic/claude-sonnet-5" in detail
    assert "substitution" in detail.lower()


def test_function_tools_skips_substitution_check_for_non_openrouter_models(vp: Any) -> None:
    """A latent false positive: without gating on the ``openrouter/`` prefix, a differently-
    prefixed pool pin (e.g. a ``gemini/`` pin) would get a spurious substitution FAIL, since
    digillm's ``_parse_provider_prefix`` strips only registered provider prefixes — not the
    same thing a bare ``removeprefix("openrouter/")`` computes for a non-openrouter model."""
    response = SimpleNamespace(
        model="gemini-3.7-flash",
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=None))],
    )
    with (
        patch("digigraph.model_config.get_olympus_tier", return_value="cheap"),
        patch(
            "digigraph.model_config._load_olympus_models",
            return_value=_fake_tier_config(["gemini/gemini-3.7-flash"]),
        ),
        patch("digillm.client.completion", return_value=response),
    ):
        assert vp.check_openrouter_function_tools() is True
    detail = vp.results[-1][2]
    assert "substitution" not in detail.lower()
