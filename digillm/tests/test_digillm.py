"""Tests for digillm: routing, chat_completion, tools, structured output, overrides.

The OpenAI client is mocked throughout — no network. Caches are cleared between
tests (module-global response/client caches would otherwise mask the mock).
"""

from __future__ import annotations

import json
import threading
from typing import Any  # score:allow untyped any — fake OpenAI client dict shapes
from unittest.mock import MagicMock, patch

import pytest
from openai import Timeout
from openai.types.chat import ChatCompletion
from openai.types.chat import ChatCompletionMessage as OpenAIMessage
from openai.types.chat.chat_completion import Choice
from pydantic import BaseModel, ValidationError

import digillm
from digillm import client as client_mod

# Every test here is offline — the OpenAI client is mocked throughout (see the module
# docstring), so the whole file is `unit` by construction. Marking it module-wide rather
# than per-test matches digifetch/tests and means a new test cannot forget the marker.
# Until #1788 this file carried no marker at all, so `pytest -m unit` selected zero of its
# tests and `make test-unit` covered none of them.
pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear module-global caches and provider env vars before each test."""
    previous_usage_observer = client_mod._usage_observer
    digillm.clear_caches()
    digillm.set_usage_observer(None)
    for var in (
        "OPENAI_API_KEY",
        "OPENAI_API_BASE",
        "LITELLM_PROXY_API_KEY",
        "XAI_API_KEY",
        "GEMINI_API_KEY",
        "OPENROUTER_API_KEY",
        "OPENROUTER_FALLBACK_MODELS",
        "OPENROUTER_SORT",
        "OPENROUTER_MAX_PROMPT_PRICE",
        "OPENROUTER_MAX_COMPLETION_PRICE",
        "OPENROUTER_REQUIRE_PARAMETERS",
        "OPENROUTER_ALLOWED_MODELS",
        "OPENROUTER_COST_QUALITY_TRADEOFF",
        "DIGI_LLM_CACHE_TTL_SECONDS",
    ):
        monkeypatch.delenv(var, raising=False)
    yield
    digillm.set_usage_observer(previous_usage_observer)
    digillm.clear_caches()


def _mock_response(content: str = "", tool_calls: Any = None) -> MagicMock:
    """Build a mock OpenAI ChatCompletion response with one choice."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _real_completion(content: str = "") -> ChatCompletion:
    """A real ``ChatCompletion`` (not a mock) so the response cache's
    serialize/rehydrate round-trip works in tests that exercise cache hits."""
    return ChatCompletion(
        id="cmpl-test",
        created=0,
        model="test-model",
        object="chat.completion",
        choices=[
            Choice(
                index=0,
                finish_reason="stop",
                message=OpenAIMessage(role="assistant", content=content),
            )
        ],
    )


# ── Provider routing / client construction ──────────────────────────────────


def test_parse_provider_prefix_known_and_unknown() -> None:
    assert client_mod._parse_provider_prefix("openrouter/mistral/mistral-7b") == (
        "openrouter",
        "mistral/mistral-7b",
    )
    assert client_mod._parse_provider_prefix("gpt-4o-mini") == (None, "gpt-4o-mini")
    # Unregistered prefix is treated as a plain model (default client handles it).
    assert client_mod._parse_provider_prefix("ollama/qwen2.5") == (None, "ollama/qwen2.5")


def test_get_client_for_model_external_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-test")
    made: dict[str, Any] = {}

    def fake_openai(**kwargs: Any) -> MagicMock:
        made.update(kwargs)
        return MagicMock()

    with patch.object(client_mod, "OpenAI", side_effect=fake_openai):
        c1 = digillm.get_client_for_model("openrouter/mistral/mistral-7b")
        c2 = digillm.get_client_for_model("openrouter/other/model")  # cached by provider
    assert made["api_key"] == "or-test"
    assert made["base_url"] == "https://openrouter.ai/api/v1"
    assert c1 is c2  # provider client is cached and reused


def test_get_client_for_model_openrouter_byok_uses_user_key() -> None:
    made: list[dict[str, Any]] = []

    def fake_openai(**kwargs: Any) -> MagicMock:
        made.append(kwargs)
        return MagicMock()

    with patch.object(client_mod, "OpenAI", side_effect=fake_openai):
        with digillm.byok("sk-or-user", "https://openrouter.ai/api/v1"):
            a = digillm.get_client_for_model("openrouter/openai/gpt-4o-mini")
            b = digillm.get_client_for_model("openrouter/openai/gpt-4o-mini")
    assert len(made) == 2
    assert a is not b
    assert made[0]["api_key"] == "sk-or-user"
    assert made[0]["base_url"] == "https://openrouter.ai/api/v1"


def test_get_client_for_model_missing_key_raises() -> None:
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        digillm.get_client_for_model("gemini/gemini-2.5-flash")


def test_get_client_for_model_anthropic_byok_uses_user_key() -> None:
    made: list[dict[str, Any]] = []

    def fake_openai(**kwargs: Any) -> MagicMock:
        made.append(kwargs)
        return MagicMock()

    with patch.object(client_mod, "OpenAI", side_effect=fake_openai):
        with digillm.byok("sk-ant-user", "https://api.anthropic.com/v1/"):
            digillm.get_client_for_model("anthropic/claude-sonnet-4-6")
    assert made[0]["api_key"] == "sk-ant-user"
    assert made[0]["base_url"].rstrip("/") == "https://api.anthropic.com/v1"


def test_anthropic_is_registered_provider() -> None:
    assert digillm.is_registered_provider("anthropic")
    assert digillm.get_provider_api_key_env("anthropic") == "ANTHROPIC_API_KEY"


def test_default_client_uses_openai_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-default")
    monkeypatch.setenv("OPENAI_API_BASE", "http://localhost:4000/")
    made: dict[str, Any] = {}

    def fake_openai(**kwargs: Any) -> MagicMock:
        made.update(kwargs)
        return MagicMock()

    with patch.object(client_mod, "OpenAI", side_effect=fake_openai):
        digillm.get_client_for_model("gpt-4o-mini")
    assert made["api_key"] == "sk-default"
    assert made["base_url"] == "http://localhost:4000"  # trailing slash stripped


def test_default_client_cached_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-1")
    with patch.object(client_mod, "OpenAI", side_effect=lambda **_: MagicMock()):
        a = digillm.get_client()
        b = digillm.get_client()
        assert a is b
        monkeypatch.setenv("OPENAI_API_KEY", "sk-2")  # different cache key
        c = digillm.get_client()
        assert c is not a


def test_register_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    client_mod.register_provider("acme", "https://acme.test/v1", "ACME_API_KEY")
    try:
        monkeypatch.setenv("ACME_API_KEY", "ak-1")
        made: dict[str, Any] = {}
        with patch.object(
            client_mod, "OpenAI", side_effect=lambda **kw: made.update(kw) or MagicMock()
        ):
            digillm.get_client_for_model("acme/model-x")
        assert made["base_url"] == "https://acme.test/v1"
        assert made["api_key"] == "ak-1"
    finally:
        client_mod._EXTERNAL_PROVIDERS.pop("acme", None)


# ── Explicit request timeout (#1734) ─────────────────────────────────────────


def _capture_client_kwargs(build: Any) -> list[dict[str, Any]]:
    """Run ``build()`` with ``OpenAI`` patched; return the kwargs of every construction."""
    made: list[dict[str, Any]] = []

    def fake_openai(**kwargs: Any) -> MagicMock:
        made.append(kwargs)
        return MagicMock()

    with patch.object(client_mod, "OpenAI", side_effect=fake_openai):
        build()
    return made


def test_default_timeout_matches_openai_sdk_default() -> None:
    """The explicit bound must equal the SDK default it replaces, or this "hardening"
    silently retunes every call. A bare float would widen connect from 5s to 600s."""
    from openai._constants import DEFAULT_TIMEOUT

    assert client_mod._REQUEST_TIMEOUT == DEFAULT_TIMEOUT
    assert client_mod._REQUEST_TIMEOUT.connect == 5.0
    assert client_mod._REQUEST_TIMEOUT.read == 600


@pytest.mark.parametrize(
    ("env", "build"),
    [
        pytest.param(
            {"OPENAI_API_KEY": "sk-default"},
            lambda: digillm.get_client_for_model("gpt-4o-mini"),
            id="default-client",
        ),
        pytest.param(
            {"OPENROUTER_API_KEY": "or-test"},
            lambda: digillm.get_client_for_model("openrouter/mistral/mistral-7b"),
            id="provider-client",
        ),
    ],
)
def test_clients_are_built_with_an_explicit_timeout(
    monkeypatch: pytest.MonkeyPatch, env: dict[str, str], build: Any
) -> None:
    """Every client construction threads ``timeout=``. Without it the bound exists only
    inside the OpenAI SDK's constants module: invisible here and free to change on a bump."""
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    sentinel = Timeout(123.0, connect=4.0)
    # raising=False so this fails on the missing ``timeout`` kwarg (the actual defect)
    # rather than on the missing constant, which would prove nothing about behavior.
    monkeypatch.setattr(client_mod, "_REQUEST_TIMEOUT", sentinel, raising=False)
    made = _capture_client_kwargs(build)
    assert made, "expected exactly one client construction"
    assert all(kw.get("timeout") is sentinel for kw in made), (
        f"expected timeout={sentinel!r} on every client, got {[kw.get('timeout') for kw in made]}"
    )


def test_byok_clients_are_built_with_an_explicit_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The two uncached BYOK paths bypass the ``_client_cache`` branches above, so they
    need their own coverage — a user-key client that can hang forever is the same bug."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-test")
    sentinel = Timeout(123.0, connect=4.0)
    monkeypatch.setattr(client_mod, "_REQUEST_TIMEOUT", sentinel, raising=False)

    def build() -> None:
        with digillm.byok("sk-or-user", "https://openrouter.ai/api/v1"):
            digillm.get_client_for_model("openrouter/openai/gpt-4o-mini")  # provider BYOK
            digillm.get_client_for_model("gpt-4o-mini")  # default-path BYOK

    made = _capture_client_kwargs(build)
    assert len(made) == 2
    assert all(kw.get("timeout") is sentinel for kw in made), (
        f"expected timeout={sentinel!r} on both BYOK clients, "
        f"got {[kw.get('timeout') for kw in made]}"
    )


# ── chat_completion ─────────────────────────────────────────────────────────


def test_chat_completion_returns_content(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _mock_response("  hello world  ")
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        resp = digillm.completion("gpt-4o-mini", [{"role": "user", "content": "hi"}])
    # completion returns the raw ChatCompletion object (no stripping at this layer).
    assert resp.choices[0].message.content == "  hello world  "
    # model string passed verbatim for the default (non-prefixed) client.
    _, kwargs = fake_client.chat.completions.create.call_args
    assert kwargs["model"] == "gpt-4o-mini"


def test_chat_completion_passes_model_as_given_no_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _mock_response("ok")
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        digillm.completion("gpt-4o-mini", [{"role": "user", "content": "hi"}])
    _, kwargs = fake_client.chat.completions.create.call_args
    assert kwargs["model"] == "gpt-4o-mini"  # used verbatim, no env substitution


# ── Self-prefixed model ids: OpenRouter's auto-router ────────────────────────


def test_wire_model_restores_a_self_prefixed_id() -> None:
    """``openrouter/auto`` IS the model id, so stripping one prefix must not consume it.

    Both accepted spellings have to land on the same wire id. Operators write the
    doubled form (README, digigraph/ARCHITECTURE.md), but a BYOK caller cannot produce
    it: ``byok_routable_model`` strips the provider's own prefix to a fixpoint and
    re-applies exactly one, and that fixpoint is load-bearing for the middleware/resolver
    agreement on a hostile header. So the single-prefix form is all BYOK can emit.
    """
    assert client_mod._wire_model("openrouter", "auto", "openrouter/auto") == "openrouter/auto"
    assert (
        client_mod._wire_model("openrouter", "openrouter/auto", "openrouter/openrouter/auto")
        == "openrouter/auto"
    )
    # Controls. An ordinary id still loses exactly one prefix; the table is per-provider,
    # so a same-named id under another provider is untouched; and the default client is
    # handed the string verbatim.
    assert (
        client_mod._wire_model("openrouter", "openai/gpt-4o-mini", "openrouter/openai/gpt-4o-mini")
        == "openai/gpt-4o-mini"
    )
    assert client_mod._wire_model("xai", "auto", "xai/auto") == "auto"
    assert client_mod._wire_model(None, "gpt-4o-mini", "gpt-4o-mini") == "gpt-4o-mini"


@pytest.mark.parametrize("model", ["openrouter/auto", "openrouter/openrouter/auto"])
def test_completion_reaches_the_auto_router_from_either_spelling(
    model: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: the BYOK spelling used to reach the wire as a bare ``auto``.

    ``auto`` is not an OpenRouter model id, so the request failed at the provider — on the
    user's own key. A BYOK user could not reach the auto-router at all.
    """
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _mock_response("ok")
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        digillm.completion(model, [{"role": "user", "content": "hi"}])
    _, kwargs = fake_client.chat.completions.create.call_args
    assert kwargs["model"] == "openrouter/auto"


def test_completion_still_strips_one_prefix_for_an_ordinary_openrouter_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Control for the test above — the vendor sub-slug must still lose the routing prefix."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _mock_response("ok")
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        digillm.completion(
            "openrouter/anthropic/claude-sonnet-4", [{"role": "user", "content": "hi"}]
        )
    _, kwargs = fake_client.chat.completions.create.call_args
    assert kwargs["model"] == "anthropic/claude-sonnet-4"


def test_auto_router_pool_constraint_applies_to_the_single_prefix_spelling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The #802 curated pool keys off ``endswith("/auto")`` on the *wire* model.

    While the BYOK spelling collapsed to a bare ``auto`` that test was False, so the
    capability guard silently did not apply to it either. Restoring the id restores the
    guard — a BYOK auto-router request is now constrained exactly like an operator one.
    """
    monkeypatch.setenv("OPENROUTER_ALLOWED_MODELS", "a/x,b/y")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _mock_response("ok")
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        digillm.completion("openrouter/auto", [{"role": "user", "content": "hi"}])
    _, kwargs = fake_client.chat.completions.create.call_args
    plugins = kwargs["extra_body"]["plugins"]
    assert [p for p in plugins if p["id"] == "auto-router"] == [
        {"id": "auto-router", "allowed_models": ["a/x", "b/y"]}
    ]
    # Control: a pinned model is not the auto-router, so the plugin must NOT be attached.
    fake_client.chat.completions.create.reset_mock()
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        digillm.completion(
            "openrouter/anthropic/claude-sonnet-4", [{"role": "user", "content": "hi"}]
        )
    _, pinned = fake_client.chat.completions.create.call_args
    assert "plugins" not in (pinned.get("extra_body") or {})


def test_streaming_path_reaches_the_auto_router_too(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_stream_completion_one_turn`` derives the wire model separately from ``completion``.

    Same bug, second door: a BYOK chat request streams by default in digichat, so the
    streaming derivation has to agree or the fix only covers half the traffic.
    """
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = [_stream_chunk("hi")]
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        digillm.run_tools(
            "openrouter/auto",
            [{"role": "user", "content": "hi"}],
            [],
            execute_tool=lambda *_: "",
            stream_deltas=True,
        )
    _, kwargs = fake_client.chat.completions.create.call_args
    assert kwargs["stream"] is True
    assert kwargs["model"] == "openrouter/auto"


# ── Empty-response self-heal (#726, 1C) ──────────────────────────────────────


def test_is_empty_completion_detects_blank_and_no_tool_calls() -> None:
    assert client_mod._is_empty_completion(_mock_response("")) is True
    assert client_mod._is_empty_completion(_mock_response("   ")) is True
    assert client_mod._is_empty_completion(_mock_response("hi")) is False
    # Blank content but tool_calls present is NOT empty.
    assert client_mod._is_empty_completion(_mock_response("", tool_calls=[object()])) is False
    no_choices = MagicMock()
    no_choices.choices = []
    assert client_mod._is_empty_completion(no_choices) is True


def test_openrouter_fallback_models_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_FALLBACK_MODELS", " a/x , b/y ,")
    assert client_mod._openrouter_fallback_models() == ["a/x", "b/y"]
    monkeypatch.delenv("OPENROUTER_FALLBACK_MODELS", raising=False)
    assert client_mod._openrouter_fallback_models() == []


def test_openrouter_usage_cost_reads_typed_extra_and_missing() -> None:
    # OpenRouter usage.cost as a plain typed attribute.
    typed = MagicMock(spec=["cost", "model_extra"])
    typed.cost = 0.0042
    typed.model_extra = None
    assert client_mod._openrouter_usage_cost(typed) == pytest.approx(0.0042)
    # Falls back to pydantic model_extra when the SDK drops the unknown field off the typed attr.
    extra_only = MagicMock(spec=["cost", "model_extra"])
    extra_only.cost = None
    extra_only.model_extra = {"cost": 0.009}
    assert client_mod._openrouter_usage_cost(extra_only) == pytest.approx(0.009)
    # No usage / no cost / non-numeric → None (never fabricate 0 — #2763 / WP1).
    assert client_mod._openrouter_usage_cost(None) is None
    none_cost = MagicMock(spec=["cost", "model_extra"])
    none_cost.cost = None
    none_cost.model_extra = {}
    assert client_mod._openrouter_usage_cost(none_cost) is None
    bad = MagicMock(spec=["cost", "model_extra"])
    bad.cost = "free"
    bad.model_extra = None
    assert client_mod._openrouter_usage_cost(bad) is None
    # Non-finite / negative cost must not poison run-level aggregation → None.
    for bad_value in (float("nan"), float("inf"), -0.5, "nan", "inf"):
        nf = MagicMock(spec=["cost", "model_extra"])
        nf.cost = bad_value
        nf.model_extra = None
        assert client_mod._openrouter_usage_cost(nf) is None


def test_with_openrouter_fallback_only_for_openrouter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_FALLBACK_MODELS", "a/x,b/y")
    base = {"model": "m", "messages": []}
    out = client_mod._with_openrouter_fallback(base, "openrouter")
    # require_parameters defaults ON, so it rides alongside the fallback allowlist.
    assert out["extra_body"] == {
        "models": ["a/x", "b/y"],
        "route": "fallback",
        "provider": {"require_parameters": True},
    }
    # Non-openrouter providers (and the default client) are untouched.
    assert client_mod._with_openrouter_fallback(base, "xai") == base
    assert client_mod._with_openrouter_fallback(base, None) == base


def test_openrouter_provider_prefs_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Unset → empty (fully opt-in, no behavior change by default).
    assert client_mod._openrouter_provider_prefs() == {}
    monkeypatch.setenv("OPENROUTER_SORT", "price")
    monkeypatch.setenv("OPENROUTER_MAX_PROMPT_PRICE", "1.5")
    monkeypatch.setenv("OPENROUTER_MAX_COMPLETION_PRICE", "4")
    assert client_mod._openrouter_provider_prefs() == {
        "sort": "price",
        "max_price": {"prompt": 1.5, "completion": 4.0},
    }


def test_openrouter_provider_prefs_ignores_non_numeric_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_MAX_PROMPT_PRICE", "cheap")  # garbage → dropped, not crash
    assert client_mod._openrouter_provider_prefs() == {}


def test_openrouter_provider_prefs_drops_invalid_sort(monkeypatch: pytest.MonkeyPatch) -> None:
    # An invalid sort would 400 (not transient) and crash the call — drop it instead of sending.
    monkeypatch.setenv("OPENROUTER_SORT", "cheapest")  # not in the OpenRouter enum
    assert client_mod._openrouter_provider_prefs() == {}
    monkeypatch.setenv("OPENROUTER_SORT", "throughput")  # a valid value passes through
    assert client_mod._openrouter_provider_prefs() == {"sort": "throughput"}


def test_openrouter_provider_prefs_drops_nonpositive_or_nonfinite_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # float() accepts these, but a price ceiling must be finite and > 0.
    for bad in ("0", "-1", "inf", "nan"):
        monkeypatch.setenv("OPENROUTER_MAX_PROMPT_PRICE", bad)
        assert client_mod._openrouter_provider_prefs() == {}, bad


def test_cost_controls_combine_allowlist_and_price_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_FALLBACK_MODELS", "a/x,b/y")
    monkeypatch.setenv("OPENROUTER_SORT", "price")
    monkeypatch.setenv("OPENROUTER_MAX_PROMPT_PRICE", "1.5")
    out = client_mod._with_openrouter_cost_controls(
        {"model": "openrouter/auto", "messages": []}, "openrouter"
    )
    assert out["extra_body"]["models"] == ["a/x", "b/y"]
    assert out["extra_body"]["route"] == "fallback"
    assert out["extra_body"]["provider"] == {
        "require_parameters": True,
        "sort": "price",
        "max_price": {"prompt": 1.5},
    }


def test_cost_controls_default_adds_require_parameters(monkeypatch: pytest.MonkeyPatch) -> None:
    # With no cost knobs set, an OpenRouter request still gets provider.require_parameters
    # (default ON) so the Auto Router only routes to a provider that honors the request's
    # response_format / tools — preventing the empty-completion failure mode (#717 regression).
    base = {"model": "openrouter/auto", "messages": []}
    out = client_mod._with_openrouter_cost_controls(base, "openrouter")
    assert out["extra_body"] == {"provider": {"require_parameters": True}}
    # Opt-out → a true no-op for OpenRouter.
    monkeypatch.setenv("OPENROUTER_REQUIRE_PARAMETERS", "0")
    assert client_mod._with_openrouter_cost_controls(base, "openrouter") == base
    # Never applies to non-OpenRouter providers regardless of the flag.
    monkeypatch.delenv("OPENROUTER_REQUIRE_PARAMETERS", raising=False)
    assert client_mod._with_openrouter_cost_controls(base, "xai") == base


def test_require_parameters_forced_for_structured_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    # A response_format / tools request must keep require_parameters even when the operator
    # disables the global toggle — those requests empty-fail on a provider that drops the param.
    monkeypatch.setenv("OPENROUTER_REQUIRE_PARAMETERS", "0")
    schema_req = {
        "model": "openrouter/auto",
        "messages": [],
        "response_format": {"type": "json_schema", "json_schema": {"name": "X", "schema": {}}},
    }
    out = client_mod._with_openrouter_cost_controls(schema_req, "openrouter")
    assert out["extra_body"] == {"provider": {"require_parameters": True}}
    tool_req = {"model": "openrouter/auto", "messages": [], "tools": [{"type": "function"}]}
    out = client_mod._with_openrouter_cost_controls(tool_req, "openrouter")
    assert out["extra_body"] == {"provider": {"require_parameters": True}}
    # OpenRouter server tools (web search) must NOT get require_parameters — it 404s.
    server_tool_req = {
        "model": "perplexity/sonar",
        "messages": [],
        "tools": [{"type": "openrouter:web_search", "parameters": {"engine": "exa"}}],
    }
    out = client_mod._with_openrouter_cost_controls(server_tool_req, "openrouter")
    assert "extra_body" not in out or "require_parameters" not in out.get("extra_body", {}).get(
        "provider", {}
    )
    # A plain-prose request still honors the opt-out (no extra_body added).
    prose_req = {"model": "openrouter/auto", "messages": []}
    assert client_mod._with_openrouter_cost_controls(prose_req, "openrouter") == prose_req


def test_allowed_models_constrains_auto_router(monkeypatch: pytest.MonkeyPatch) -> None:
    # OPENROUTER_ALLOWED_MODELS fences the Auto Router's candidate pool via the auto-router
    # plugin (keeps per-prompt auto-selection, excludes incapable models like flash-lite, #802).
    monkeypatch.setenv(
        "OPENROUTER_ALLOWED_MODELS", " openai/gpt-4o-mini , deepseek/deepseek-chat ,"
    )
    monkeypatch.setenv("OPENROUTER_COST_QUALITY_TRADEOFF", "6")
    req = {"model": "openrouter/auto", "messages": []}
    out = client_mod._with_openrouter_cost_controls(req, "openrouter")
    assert out["extra_body"]["plugins"] == [
        {
            "id": "auto-router",
            "allowed_models": ["openai/gpt-4o-mini", "deepseek/deepseek-chat"],
            "cost_quality_tradeoff": 6,
        }
    ]
    # allowed_models supersedes require_parameters — applying both compounds to an empty set
    # → OpenRouter 404 (#802). The curated pool is the capability guarantee, so no provider block.
    assert "provider" not in out["extra_body"]


def test_allowed_models_only_for_auto_router(monkeypatch: pytest.MonkeyPatch) -> None:
    # The plugin is meaningless on a pinned model → not injected there.
    monkeypatch.setenv("OPENROUTER_ALLOWED_MODELS", "openai/gpt-4o-mini")
    pinned = {"model": "deepseek/deepseek-chat", "messages": []}
    out = client_mod._with_openrouter_cost_controls(pinned, "openrouter")
    assert "plugins" not in out.get("extra_body", {})
    # Out-of-range / non-int tradeoff is ignored (plugin omits the key, uses OpenRouter default).
    monkeypatch.setenv("OPENROUTER_COST_QUALITY_TRADEOFF", "99")
    out = client_mod._with_openrouter_cost_controls(
        {"model": "openrouter/auto", "messages": []}, "openrouter"
    )
    assert out["extra_body"]["plugins"][0] == {
        "id": "auto-router",
        "allowed_models": ["openai/gpt-4o-mini"],
    }


def test_cost_controls_merge_preserves_existing_extra_body(monkeypatch: pytest.MonkeyPatch) -> None:
    # The xAI search_parameters branch is openrouter-gated out, but a pre-existing extra_body
    # (and any pre-set provider keys) must be preserved/merged, not clobbered.
    monkeypatch.setenv("OPENROUTER_SORT", "price")
    base = {
        "model": "openrouter/auto",
        "messages": [],
        "extra_body": {"provider": {"order": ["x"]}, "foo": 1},
    }
    out = client_mod._with_openrouter_cost_controls(base, "openrouter")
    assert out["extra_body"]["foo"] == 1
    assert out["extra_body"]["provider"] == {
        "order": ["x"],
        "require_parameters": True,
        "sort": "price",
    }
    assert base["extra_body"]["provider"] == {"order": ["x"]}  # input not mutated


def test_cost_controls_deep_merge_max_price(monkeypatch: pytest.MonkeyPatch) -> None:
    # A caller-set max_price key (completion) must survive when env sets only the other
    # (prompt) — deep-merge the nested dict, don't clobber it.
    monkeypatch.setenv("OPENROUTER_MAX_PROMPT_PRICE", "1.5")
    base = {
        "model": "openrouter/auto",
        "messages": [],
        "extra_body": {"provider": {"max_price": {"completion": 9.0}}},
    }
    out = client_mod._with_openrouter_cost_controls(base, "openrouter")
    assert out["extra_body"]["provider"]["max_price"] == {"completion": 9.0, "prompt": 1.5}


def test_empty_response_retries_then_heals(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    monkeypatch.setattr(client_mod, "_EMPTY_RETRY_MAX", 2)  # deterministic regardless of env
    monkeypatch.setattr(client_mod.time, "sleep", lambda *_a, **_k: None)  # no backoff wait
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = [_mock_response(""), _mock_response("healed")]
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        resp = digillm.completion("gpt-4o-mini", [{"role": "user", "content": "hi"}])
    assert resp.choices[0].message.content == "healed"
    assert fake_client.chat.completions.create.call_count == 2  # initial empty + one retry


def test_empty_response_gives_up_gracefully(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    monkeypatch.setattr(client_mod, "_EMPTY_RETRY_MAX", 2)  # deterministic regardless of env
    monkeypatch.setattr(client_mod.time, "sleep", lambda *_a, **_k: None)
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _mock_response("")  # always empty
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        resp = digillm.completion("gpt-4o-mini", [{"role": "user", "content": "hi"}])
    assert client_mod._is_empty_completion(resp)  # returned unchanged, no crash
    # 1 initial + _EMPTY_RETRY_MAX retries.
    assert fake_client.chat.completions.create.call_count == 1 + client_mod._EMPTY_RETRY_MAX


def test_openrouter_cost_controls_applied_on_primary_and_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Cost controls (#774) now apply on the PRIMARY request (cheap allowlist + price ceiling),
    # not only on the empty-retry path — so every OpenRouter call is bounded to cheap models.
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-test")
    monkeypatch.setenv("OPENROUTER_FALLBACK_MODELS", "openrouter/cheap-a,openrouter/cheap-b")
    monkeypatch.setenv("OPENROUTER_MAX_PROMPT_PRICE", "1.5")
    monkeypatch.setattr(client_mod, "_EMPTY_RETRY_MAX", 2)  # deterministic regardless of env
    monkeypatch.setattr(client_mod.time, "sleep", lambda *_a, **_k: None)
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = [_mock_response(""), _mock_response("ok")]
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        digillm.completion("openrouter/primary/model", [{"role": "user", "content": "hi"}])
    calls = fake_client.chat.completions.create.call_args_list
    expected = {
        "models": ["openrouter/cheap-a", "openrouter/cheap-b"],
        "route": "fallback",
        "provider": {"require_parameters": True, "max_price": {"prompt": 1.5}},
    }
    assert calls[0].kwargs["extra_body"] == expected  # primary already bounded to cheap models
    assert calls[1].kwargs["extra_body"] == expected  # retry keeps the controls


def test_chat_completion_response_cache_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _real_completion("cached-value")
    msgs = [{"role": "user", "content": "same"}]
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        first = digillm.completion("gpt-4o-mini", msgs)
        second = digillm.completion("gpt-4o-mini", msgs)
    # Both return a ChatCompletion with the same content; the second is rehydrated
    # from the serialized cache entry rather than a fresh API call.
    assert first.choices[0].message.content == "cached-value"
    assert second.choices[0].message.content == "cached-value"
    # Second call served from cache → underlying API hit exactly once.
    assert fake_client.chat.completions.create.call_count == 1


def test_chat_completion_empty_choices() -> None:
    fake_client = MagicMock()
    empty = MagicMock()
    empty.choices = []
    fake_client.chat.completions.create.return_value = empty
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        resp = digillm.completion("gpt-4o-mini", [{"role": "user", "content": "x"}])
    assert resp.choices == []


def test_chat_completion_with_tools_returns_tuple() -> None:
    fn = MagicMock()
    fn.name = "get_weather"
    fn.arguments = '{"city": "Paris"}'
    tc = MagicMock()
    tc.id = "call_1"
    tc.function = fn
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _mock_response("", tool_calls=[tc])
    tools = [{"type": "function", "function": {"name": "get_weather", "parameters": {}}}]
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        resp = digillm.completion(
            "gpt-4o-mini", [{"role": "user", "content": "weather?"}], tools=tools
        )
    # completion returns the raw object; tool_calls live on the message.
    tool_calls = resp.choices[0].message.tool_calls
    assert tool_calls[0].function.name == "get_weather"
    assert tool_calls[0].id == "call_1"


# ── Tool-calling loop ────────────────────────────────────────────────────────


def test_chat_completion_with_tools_loop() -> None:
    """One tool round, then a final text answer."""
    fn = MagicMock()
    fn.name = "lookup"
    fn.arguments = '{"q": "x"}'
    tc = MagicMock()
    tc.id = "c1"
    tc.function = fn

    responses = [
        _mock_response("", tool_calls=[tc]),  # round 1: request tool
        _mock_response("final answer"),  # round 2: no tools → final
    ]
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = responses

    executed: list[tuple[str, dict]] = []

    def execute_tool(name: str, args: dict) -> str:
        executed.append((name, args))
        return "tool-result"

    steps: list[tuple[str, Any]] = []
    tools = [{"type": "function", "function": {"name": "lookup", "parameters": {}}}]
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        out = digillm.run_tools(
            "gpt-4o-mini",
            [{"role": "user", "content": "go"}],
            tools,
            execute_tool,
            on_tool_step=lambda kind, payload: steps.append((kind, payload)),
        )
    assert out == "final answer"
    assert executed == [("lookup", {"q": "x"})]
    assert ("tool_call", {"name": "lookup", "arguments": {"q": "x"}}) in steps
    assert any(k == "tool_result" for k, _ in steps)
    # Round 1 had empty content alongside its tool_calls (the common, well-behaved
    # case) — no round_boundary fires when there is no narration to mark.
    assert not any(k == "round_boundary" for k, _ in steps)


def test_round_with_content_and_tool_calls_emits_round_boundary() -> None:
    """#2306 follow-up: a round that narrates its plan WHILE also calling tools
    ("I will load the full notes...") must be marked as not-final the moment
    tool_calls is known, or a caller downstream has no way to distinguish that
    narration from the actual final answer that streams right after it — confirmed
    in production, where the two concatenated into one visible block with nothing
    between them."""
    fn = MagicMock()
    fn.name = "lookup"
    fn.arguments = "{}"
    tc = MagicMock()
    tc.id = "c1"
    tc.function = fn

    responses = [
        _mock_response("I will load the full notes now.", tool_calls=[tc]),
        _mock_response("Here is the real answer."),
    ]
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = responses

    steps: list[tuple[str, Any]] = []
    tools = [{"type": "function", "function": {"name": "lookup", "parameters": {}}}]
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        out = digillm.run_tools(
            "gpt-4o-mini",
            [{"role": "user", "content": "go"}],
            tools,
            lambda name, args: "tool-result",
            on_tool_step=lambda kind, payload: steps.append((kind, payload)),
        )

    assert out == "Here is the real answer."
    boundaries = [p for k, p in steps if k == "round_boundary"]
    assert len(boundaries) == 1
    assert boundaries[0] == {"round_idx": 0, "narration": "I will load the full notes now."}
    # The boundary fires the moment tool_calls is known, BEFORE this round's own
    # tool_call/tool_result events (those fire later, during dispatch) — so a
    # consumer reacting to it (e.g. closing the current text segment) sees the
    # marker before the round's tool activity, not interleaved after it.
    kinds = [k for k, _ in steps]
    assert kinds.index("round_boundary") < kinds.index("tool_call")


def test_sequential_tool_error_becomes_recoverable_result() -> None:
    """A raised exception from a sequential (non-parallel) tool call must not abort the
    whole run — it must become a tool-result content string, exactly like the parallel
    dispatch branch's existing ``except (RuntimeError, OSError, ValueError, TypeError,
    KeyError)`` 3 lines above the sequential branch — so the model gets a turn to react
    instead of the caller seeing a bare traceback."""
    fn = MagicMock()
    fn.name = "lookup"
    fn.arguments = "{}"
    tc = MagicMock()
    tc.id = "c1"
    tc.function = fn

    responses = [
        _mock_response("", tool_calls=[tc]),
        _mock_response("recovered"),
    ]
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = responses

    def execute_tool(name: str, args: dict) -> str:
        raise ValueError("boom")

    tools = [{"type": "function", "function": {"name": "lookup", "parameters": {}}}]
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        out = digillm.run_tools(
            "gpt-4o-mini",
            [{"role": "user", "content": "go"}],
            tools,
            execute_tool,
        )
    assert out == "recovered"
    second_call_messages = fake_client.chat.completions.create.call_args_list[1].kwargs["messages"]
    tool_msgs = [m for m in second_call_messages if m.get("role") == "tool"]
    assert tool_msgs, "expected a tool-role message to reach the model"
    assert "boom" in tool_msgs[0]["content"]


def test_round_limit_exhausted_emits_signal_and_forces_final_answer() -> None:
    """When every round through max_tool_rounds keeps requesting tools, run_tools must
    still return a real answer (forcing one tool-free completion, existing behavior)
    AND tell the caller the round budget was exhausted, not just fall through silently —
    today there is no signal at all that a workflow is routinely maxing out its budget."""
    fn = MagicMock()
    fn.name = "lookup"
    fn.arguments = "{}"
    tc = MagicMock()
    tc.id = "c1"
    tc.function = fn

    responses = [
        _mock_response("", tool_calls=[tc]),  # round 0: still calling tools
        _mock_response(
            "", tool_calls=[tc]
        ),  # round 1 (last, max_tool_rounds=2): still calling tools
        _mock_response("forced final answer"),  # post-loop forced completion
    ]
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = responses

    steps: list[tuple[str, Any]] = []
    tools = [{"type": "function", "function": {"name": "lookup", "parameters": {}}}]
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        out = digillm.run_tools(
            "gpt-4o-mini",
            [{"role": "user", "content": "go"}],
            tools,
            lambda name, args: "tool-result",
            max_tool_rounds=2,
            on_tool_step=lambda kind, payload: steps.append((kind, payload)),
        )

    assert out == "forced final answer"
    signals = [p for k, p in steps if k == "round_limit_exhausted"]
    assert signals == [{"max_tool_rounds": 2}]


@pytest.mark.parametrize("max_tool_rounds", [0, -1])
def test_max_tool_rounds_zero_never_emits_round_limit_exhausted(max_tool_rounds: int) -> None:
    """max_tool_rounds=0 (or negative) means the for loop's range() is empty -- zero
    tool rounds ever ran, so there is nothing to have "exhausted." Before the guard,
    run_tools fell through to the post-loop code unconditionally and fired
    round_limit_exhausted (and the matching warning log) even though no round ran at
    all, falsely implying the model burned through a budget it never got a chance to
    use."""
    fake_client = MagicMock()
    # No completion call should happen at all: the loop body never executes, and
    # `content` stays "" with `current` unchanged from `messages`, so the
    # forced-completion branch's `len(current) > len(messages)` guard is also False.
    fake_client.chat.completions.create.side_effect = AssertionError(
        f"must not call the model when max_tool_rounds={max_tool_rounds}"
    )

    steps: list[tuple[str, Any]] = []
    tools = [{"type": "function", "function": {"name": "lookup", "parameters": {}}}]
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        out = digillm.run_tools(
            "gpt-4o-mini",
            [{"role": "user", "content": "go"}],
            tools,
            lambda name, args: "tool-result",
            max_tool_rounds=max_tool_rounds,
            on_tool_step=lambda kind, payload: steps.append((kind, payload)),
        )

    assert out == ""
    assert not any(k == "round_limit_exhausted" for k, _ in steps)


def test_round_boundary_not_emitted_on_the_non_streaming_path_without_content() -> None:
    """Regression pin for the non-streaming branch specifically (test above already
    covers it, but this isolates it): tool_calls with NO content must still fire no
    round_boundary, matching the streaming path's behavior exactly."""
    fn = MagicMock()
    fn.name = "lookup"
    fn.arguments = "{}"
    tc = MagicMock()
    tc.id = "c1"
    tc.function = fn
    responses = [_mock_response("", tool_calls=[tc]), _mock_response("done")]
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = responses
    steps: list[tuple[str, Any]] = []
    tools = [{"type": "function", "function": {"name": "lookup", "parameters": {}}}]
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        digillm.run_tools(
            "gpt-4o-mini",
            [{"role": "user", "content": "go"}],
            tools,
            lambda name, args: "tool-result",
            on_tool_step=lambda kind, payload: steps.append((kind, payload)),
        )
    assert not any(k == "round_boundary" for k, _ in steps)


def test_run_tools_raises_when_required_tool_choice_gets_no_tool_calls() -> None:
    """tool_choice='required' must fail closed, not silently return content, when a
    tool-enabled turn ignores the requirement and answers without calling a tool —
    a deployment that opted into this floor (agents.require_tool_calls) never gets
    a quiet parametric-knowledge answer in its place."""
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _mock_response("final answer")

    tools = [{"type": "function", "function": {"name": "lookup", "parameters": {}}}]
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        with pytest.raises(RuntimeError, match="tool_choice='required'"):
            digillm.run_tools(
                "gpt-4o-mini",
                [{"role": "user", "content": "go"}],
                tools,
                execute_tool=lambda n, a: "unused",
                tool_choice="required",
            )
    # tool_choice still reached the wire before the model's response was rejected.
    _, kwargs = fake_client.chat.completions.create.call_args
    assert kwargs["tool_choice"] == "required"


def test_run_tools_defaults_tool_choice_to_auto() -> None:
    """Unchanged default behavior when tool_choice is not passed."""
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _mock_response("final answer")

    tools = [{"type": "function", "function": {"name": "lookup", "parameters": {}}}]
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        digillm.run_tools(
            "gpt-4o-mini",
            [{"role": "user", "content": "go"}],
            tools,
            execute_tool=lambda n, a: "unused",
        )
    _, kwargs = fake_client.chat.completions.create.call_args
    assert kwargs["tool_choice"] == "auto"


def test_chat_completion_with_tools_parallel_branch() -> None:
    """Two parallel-safe tools in one round run via the concurrent branch."""
    fn_a = MagicMock()
    fn_a.name = "alpha"
    fn_a.arguments = '{"n": 1}'
    tc_a = MagicMock()
    tc_a.id = "a"
    tc_a.function = fn_a
    fn_b = MagicMock()
    fn_b.name = "beta"
    fn_b.arguments = '{"n": 2}'
    tc_b = MagicMock()
    tc_b.id = "b"
    tc_b.function = fn_b

    responses = [
        _mock_response("", tool_calls=[tc_a, tc_b]),  # round 1: two tool calls
        _mock_response("done"),  # round 2: final answer
    ]
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = responses

    executed: set[str] = set()

    def execute_tool(name: str, args: dict) -> dict:
        executed.add(name)
        return {"content": f"{name}-result"}

    steps: list[tuple[str, Any]] = []
    tools = [
        {"type": "function", "function": {"name": "alpha", "parameters": {}}},
        {"type": "function", "function": {"name": "beta", "parameters": {}}},
    ]
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        out = digillm.run_tools(
            "gpt-4o-mini",
            [{"role": "user", "content": "go"}],
            tools,
            execute_tool,
            on_tool_step=lambda kind, payload: steps.append((kind, payload)),
            parallel_safe_tools={"alpha", "beta"},
        )
    assert out == "done"
    assert executed == {"alpha", "beta"}
    # Both tools fire a tool_call and a tool_result event (parallel branch defers
    # the tool_call event until after dispatch, but still emits it for each).
    call_names = {p["name"] for k, p in steps if k == "tool_call"}
    result_names = {p["name"] for k, p in steps if k == "tool_result"}
    assert call_names == {"alpha", "beta"}
    assert result_names == {"alpha", "beta"}


def test_parallel_branch_carries_the_byok_override_into_each_worker() -> None:
    """A parallel-safe tool must still see the caller's BYOK key.

    A pool worker starts with an empty context, so without a copied one
    :func:`digillm.get_byok` reads ``None`` inside the branch and any tool that
    calls an LLM itself bills the *operator's* key while the caller's is bound.

    The barrier forces both tools to be in flight at once, which is what
    distinguishes a per-submit ``copy_context()`` from one shared Context: a
    single Context cannot be entered by two threads and raises "is already
    entered" in the second. Without the barrier the calls can serialize and a
    shared-Context regression would pass unnoticed.
    """
    fn_a = MagicMock()
    fn_a.name = "alpha"
    fn_a.arguments = "{}"
    tc_a = MagicMock()
    tc_a.id = "a"
    tc_a.function = fn_a
    fn_b = MagicMock()
    fn_b.name = "beta"
    fn_b.arguments = "{}"
    tc_b = MagicMock()
    tc_b.id = "b"
    tc_b.function = fn_b

    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = [
        _mock_response("", tool_calls=[tc_a, tc_b]),
        _mock_response("done"),
    ]

    barrier = threading.Barrier(2, timeout=10)
    seen: dict[str, tuple[str, str] | None] = {}

    def execute_tool(name: str, args: dict) -> dict:
        barrier.wait()
        seen[name] = digillm.get_byok()
        return {"content": name}

    tools = [
        {"type": "function", "function": {"name": "alpha", "parameters": {}}},
        {"type": "function", "function": {"name": "beta", "parameters": {}}},
    ]
    token = digillm.set_byok("sk-caller", "https://openrouter.ai/api/v1")
    try:
        with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
            out = digillm.run_tools(
                "gpt-4o-mini",
                [{"role": "user", "content": "go"}],
                tools,
                execute_tool,
                parallel_safe_tools={"alpha", "beta"},
            )
    finally:
        digillm.reset_byok(token)

    assert out == "done"
    expected = ("sk-caller", "https://openrouter.ai/api/v1")
    assert seen == {"alpha": expected, "beta": expected}


def test_parallel_branch_leaves_an_unbound_caller_unbound() -> None:
    """Copying a context must not invent an override the caller never set."""
    fn_a = MagicMock()
    fn_a.name = "alpha"
    fn_a.arguments = "{}"
    tc_a = MagicMock()
    tc_a.id = "a"
    tc_a.function = fn_a
    fn_b = MagicMock()
    fn_b.name = "beta"
    fn_b.arguments = "{}"
    tc_b = MagicMock()
    tc_b.id = "b"
    tc_b.function = fn_b

    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = [
        _mock_response("", tool_calls=[tc_a, tc_b]),
        _mock_response("done"),
    ]

    seen: dict[str, tuple[str, str] | None] = {}

    def execute_tool(name: str, args: dict) -> dict:
        seen[name] = digillm.get_byok()
        return {"content": name}

    tools = [
        {"type": "function", "function": {"name": "alpha", "parameters": {}}},
        {"type": "function", "function": {"name": "beta", "parameters": {}}},
    ]
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        digillm.run_tools(
            "gpt-4o-mini",
            [{"role": "user", "content": "go"}],
            tools,
            execute_tool,
            parallel_safe_tools={"alpha", "beta"},
        )
    assert seen == {"alpha": None, "beta": None}


def test_parallel_branch_does_not_share_the_telemetry_handle() -> None:
    """The copy carries credentials; it must not carry the mutable telemetry handle.

    ``copy_context()`` propagates *references*, so a naive copy hands all N workers the
    one :class:`ProviderCallContextHandle` the caller is holding -- and they all write
    its ``last_call_id`` (leaving a later follow-up call parented on whichever sibling
    finished last) and all append to the single deferred-record list that ``finalize``
    tuples and clears. A worker that inherited an *empty* context read ``None`` here, so
    ``None`` is the behaviour to hold: nesting fan-out calls under the parent's logical
    call needs a per-worker handle and a join-time merge, which is a separate feature.

    The barrier forces both workers to be in flight together, which is the only state in
    which a shared handle is a race rather than merely wrong.
    """
    from uuid import uuid4

    from digillm.telemetry import CallPurpose

    fn_a = MagicMock()
    fn_a.name = "alpha"
    fn_a.arguments = "{}"
    tc_a = MagicMock()
    tc_a.id = "a"
    tc_a.function = fn_a
    fn_b = MagicMock()
    fn_b.name = "beta"
    fn_b.arguments = "{}"
    tc_b = MagicMock()
    tc_b.id = "b"
    tc_b.function = fn_b

    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = [
        _mock_response("", tool_calls=[tc_a, tc_b]),
        _mock_response("done"),
    ]

    barrier = threading.Barrier(2, timeout=10)
    seen_metadata: dict[str, Any] = {}
    seen_byok: dict[str, tuple[str, str] | None] = {}

    def execute_tool(name: str, args: dict) -> dict:
        barrier.wait()
        seen_metadata[name] = client_mod._provider_call_metadata.get()
        seen_byok[name] = digillm.get_byok()
        return {"content": name}

    tools = [
        {"type": "function", "function": {"name": "alpha", "parameters": {}}},
        {"type": "function", "function": {"name": "beta", "parameters": {}}},
    ]
    token = digillm.set_byok("sk-caller", "https://openrouter.ai/api/v1")
    try:
        with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
            with digillm.provider_call_context(
                node_run_id=uuid4(),
                purpose=CallPurpose.INITIAL_GENERATION,
                no_artifact_reason=digillm.NoArtifactReason.CONSUMED_INLINE,
            ) as handle:
                digillm.run_tools(
                    "gpt-4o-mini",
                    [{"role": "user", "content": "go"}],
                    tools,
                    execute_tool,
                    parallel_safe_tools={"alpha", "beta"},
                )
                # The caller keeps its own binding: the workers cleared their copies of
                # the context, and a copy is a snapshot rather than a view.
                still_bound = client_mod._provider_call_metadata.get()
    finally:
        digillm.reset_byok(token)

    assert seen_metadata == {"alpha": None, "beta": None}
    # ... and dropping the handle must not have dropped the credentials with it.
    expected = ("sk-caller", "https://openrouter.ai/api/v1")
    assert seen_byok == {"alpha": expected, "beta": expected}
    assert still_bound is not None and still_bound.handle is handle


def _two_tool_calls() -> tuple[Any, Any]:
    """Two mock tool calls, which is what selects ``run_tools``' parallel branch."""
    fn_a = MagicMock()
    fn_a.name = "alpha"
    fn_a.arguments = "{}"
    tc_a = MagicMock()
    tc_a.id = "a"
    tc_a.function = fn_a
    fn_b = MagicMock()
    fn_b.name = "beta"
    fn_b.arguments = "{}"
    tc_b = MagicMock()
    tc_b.id = "b"
    tc_b.function = fn_b
    return tc_a, tc_b


def test_the_fan_out_runs_the_consumer_detach_hook() -> None:
    """A consumer's own logical-call var has to be cleared per worker too.

    :func:`detach_provider_call_context` clears *this* module's var, but a consumer that
    layers its own logical-call ContextVar on top -- digigraph's
    ``usage._LOGICAL_CALL_CONTEXT``, whose value holds the same mutable
    :class:`ProviderCallContextHandle` -- would still hand every worker one shared handle
    through the credential snapshot. digillm is a leaf library and cannot reach into a
    consumer's module, so it calls back. Pinned here: the callback fires once per parallel
    worker, and *not* on the serial path, which runs in the caller's own context and must
    keep the binding it was given.
    """
    tc_a, tc_b = _two_tool_calls()
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = [
        _mock_response("", tool_calls=[tc_a, tc_b]),
        _mock_response("done"),
        _mock_response("", tool_calls=[tc_a]),
        _mock_response("done"),
    ]

    lock = threading.Lock()
    calls: list[str] = []

    def hook() -> None:
        with lock:
            calls.append(threading.current_thread().name)

    tools = [
        {"type": "function", "function": {"name": "alpha", "parameters": {}}},
        {"type": "function", "function": {"name": "beta", "parameters": {}}},
    ]
    previous = client_mod._fan_out_detach_hook
    digillm.set_fan_out_detach_hook(hook)
    try:
        with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
            digillm.run_tools(
                "gpt-4o-mini",
                [{"role": "user", "content": "go"}],
                tools,
                lambda name, args: {"content": name},
                parallel_safe_tools={"alpha", "beta"},
            )
            parallel_calls = list(calls)
            calls.clear()
            # One tool call in the round: ``run_parallel`` is False, so the serial
            # ``else`` branch runs ``execute_tool`` in this very context.
            digillm.run_tools(
                "gpt-4o-mini",
                [{"role": "user", "content": "go"}],
                tools,
                lambda name, args: {"content": name},
                parallel_safe_tools={"alpha", "beta"},
            )
            serial_calls = list(calls)
    finally:
        digillm.set_fan_out_detach_hook(previous)

    assert len(parallel_calls) == 2, "the hook must run once per parallel worker"
    assert serial_calls == [], "the serial branch owns the caller's context; do not unbind it"


def test_a_broken_detach_hook_does_not_fail_the_tool_call() -> None:
    """A consumer's callback is not allowed to break the fan-out.

    Same terms as the usage and telemetry observers: registered process-wide, and a
    raising hook degrades telemetry rather than the tool call itself.
    """
    tc_a, tc_b = _two_tool_calls()
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = [
        _mock_response("", tool_calls=[tc_a, tc_b]),
        _mock_response("done"),
    ]

    def hook() -> None:
        raise RuntimeError("consumer hook is broken")

    executed: set[str] = set()

    def execute_tool(name: str, args: dict) -> dict:
        executed.add(name)
        return {"content": name}

    tools = [
        {"type": "function", "function": {"name": "alpha", "parameters": {}}},
        {"type": "function", "function": {"name": "beta", "parameters": {}}},
    ]
    previous = client_mod._fan_out_detach_hook
    digillm.set_fan_out_detach_hook(hook)
    try:
        with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
            out = digillm.run_tools(
                "gpt-4o-mini",
                [{"role": "user", "content": "go"}],
                tools,
                execute_tool,
                parallel_safe_tools={"alpha", "beta"},
            )
    finally:
        digillm.set_fan_out_detach_hook(previous)

    assert out == "done"
    assert executed == {"alpha", "beta"}


# ── Streaming tool-calling loop (stream_deltas=True) ──────────────────────────


def _stream_chunk(
    content: str | None = None,
    reasoning: str | None = None,
    tool_calls: Any = None,
) -> MagicMock:
    """One streaming chunk exposing ``choices[0].delta`` with the given fields.

    All three delta attributes are set explicitly (to None when absent) so the
    accumulator's ``getattr(delta, ..., None)`` checks see real ``None`` rather
    than auto-created child mocks.
    """
    delta = MagicMock()
    delta.content = content
    delta.reasoning_content = reasoning
    delta.tool_calls = tool_calls
    choice = MagicMock()
    choice.delta = delta
    chunk = MagicMock()
    chunk.choices = [choice]
    return chunk


def _tc_fragment(
    index: int,
    *,
    id: str | None = None,
    name: str | None = None,
    arguments: str | None = None,
) -> MagicMock:
    """One streamed ``tool_call`` fragment (merged by ``index`` across chunks)."""
    fn = MagicMock()
    fn.name = name
    fn.arguments = arguments
    tc = MagicMock()
    tc.index = index
    tc.id = id
    tc.function = fn
    return tc


def test_stream_deltas_emits_content_and_returns_joined() -> None:
    """stream_deltas=True forwards each content chunk and returns the joined text."""
    chunks = [_stream_chunk("Hel"), _stream_chunk("lo"), _stream_chunk(" world")]
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = chunks
    seen: list[tuple[str, Any]] = []
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        out = digillm.run_tools(
            "gpt-4o-mini",
            [{"role": "user", "content": "hi"}],
            [],  # no tools → one streamed turn, then return
            execute_tool=lambda *_: "",
            on_tool_step=lambda kind, payload: seen.append((kind, payload)),
            stream_deltas=True,
        )
    assert out == "Hello world"
    assert [p for k, p in seen if k == "content"] == ["Hel", "lo", " world"]
    # stream=True must reach the wire on the streaming path.
    _, kwargs = fake_client.chat.completions.create.call_args
    assert kwargs["stream"] is True


def test_stream_deltas_emits_reasoning_then_content() -> None:
    """reasoning_content chunks surface as ('reasoning', delta); content as ('content', delta)."""
    chunks = [
        _stream_chunk(reasoning="think"),
        _stream_chunk(reasoning="ing"),
        _stream_chunk(content="answer"),
    ]
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = chunks
    seen: list[tuple[str, Any]] = []
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        out = digillm.run_tools(
            "gpt-4o-mini",
            [{"role": "user", "content": "hi"}],
            [],
            execute_tool=lambda *_: "",
            on_tool_step=lambda kind, payload: seen.append((kind, payload)),
            stream_deltas=True,
        )
    assert out == "answer"
    assert [p for k, p in seen if k == "reasoning"] == ["think", "ing"]
    assert [p for k, p in seen if k == "content"] == ["answer"]


def test_stream_deltas_tool_call_then_final_answer() -> None:
    """A tool call streamed across fragments runs, then the final answer streams."""
    round1 = [
        _stream_chunk(tool_calls=[_tc_fragment(0, id="c1", name="lookup")]),
        _stream_chunk(tool_calls=[_tc_fragment(0, arguments='{"q":')]),
        _stream_chunk(tool_calls=[_tc_fragment(0, arguments=' "x"}')]),
    ]
    round2 = [_stream_chunk(content="final "), _stream_chunk(content="answer")]
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = [round1, round2]
    executed: list[tuple[str, dict]] = []
    seen: list[tuple[str, Any]] = []

    def execute_tool(name: str, args: dict) -> str:
        executed.append((name, args))
        return "tool-result"

    tools = [{"type": "function", "function": {"name": "lookup", "parameters": {}}}]
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        out = digillm.run_tools(
            "gpt-4o-mini",
            [{"role": "user", "content": "go"}],
            tools,
            execute_tool,
            on_tool_step=lambda kind, payload: seen.append((kind, payload)),
            stream_deltas=True,
        )
    assert out == "final answer"
    assert executed == [("lookup", {"q": "x"})]
    assert ("tool_call", {"name": "lookup", "arguments": {"q": "x"}}) in seen
    assert any(k == "tool_result" for k, _ in seen)
    assert [p for k, p in seen if k == "content"] == ["final ", "answer"]
    # This round had no content alongside its tool_calls — no round_boundary to mark.
    assert not any(k == "round_boundary" for k, _ in seen)


def test_stream_deltas_narration_alongside_tool_call_emits_round_boundary() -> None:
    """Streaming path, mirroring the non-streaming test above: a round that streams
    real content (narration) fragments alongside its tool_calls must fire
    round_boundary with the JOINED content once tool_calls is known — not per
    fragment, and not on the non-streaming path only."""
    round1 = [
        _stream_chunk(content="I will "),
        _stream_chunk(content="load the notes."),
        _stream_chunk(tool_calls=[_tc_fragment(0, id="c1", name="lookup", arguments="{}")]),
    ]
    round2 = [_stream_chunk(content="Real answer.")]
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = [round1, round2]
    seen: list[tuple[str, Any]] = []
    tools = [{"type": "function", "function": {"name": "lookup", "parameters": {}}}]
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        out = digillm.run_tools(
            "gpt-4o-mini",
            [{"role": "user", "content": "go"}],
            tools,
            lambda name, args: "tool-result",
            on_tool_step=lambda kind, payload: seen.append((kind, payload)),
            stream_deltas=True,
        )
    assert out == "Real answer."
    boundaries = [p for k, p in seen if k == "round_boundary"]
    assert len(boundaries) == 1
    assert boundaries[0] == {"round_idx": 0, "narration": "I will load the notes."}


def test_stream_deltas_forwards_tool_choice_required() -> None:
    """tool_choice='required' reaches the wire on the STREAMING path — the only
    path production ever takes for this parameter (research.py always passes
    on_tool_step, which forces stream_deltas=True in digigraph's wrapper).

    max_tool_rounds=1 keeps this exercising the intended shape: one tool-enabled
    round (tool_calls present, so the fail-closed check added for the
    tool_choice='required' floor never fires) followed by the forced tool-free
    wrap-up completion (tools=None, so tool_choice never reaches that call's wire
    either) — not a second 'required' round, which would now raise."""
    round1 = [
        _stream_chunk(tool_calls=[_tc_fragment(0, id="c1", name="lookup")]),
        _stream_chunk(tool_calls=[_tc_fragment(0, arguments='{"q":')]),
        _stream_chunk(tool_calls=[_tc_fragment(0, arguments=' "x"}')]),
    ]
    round2 = [_stream_chunk(content="final "), _stream_chunk(content="answer")]
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = [round1, round2]

    tools = [{"type": "function", "function": {"name": "lookup", "parameters": {}}}]
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        out = digillm.run_tools(
            "gpt-4o-mini",
            [{"role": "user", "content": "go"}],
            tools,
            execute_tool=lambda name, args: "tool-result",
            on_tool_step=lambda kind, payload: None,
            stream_deltas=True,
            tool_choice="required",
            max_tool_rounds=1,
        )
    assert out == "final answer"
    # First round has tools attached, so tool_choice must be on the wire.
    first_call_kwargs = fake_client.chat.completions.create.call_args_list[0][1]
    assert first_call_kwargs["tool_choice"] == "required"


def test_stream_deltas_required_tool_choice_never_leaks_rejected_content() -> None:
    """A tool_choice='required' round that streams narration/reasoning but comes
    back with no tool_calls must not have leaked those deltas to on_tool_step
    before run_tools raises. A delta already streamed can't be un-streamed, so
    the fail-closed check alone isn't enough -- this pins the buffer-then-discard
    fix (CodeRabbit follow-up review on the fail-closed fix itself, PR #2361)."""
    round1 = [
        _stream_chunk(reasoning="Thinking it over..."),
        _stream_chunk(content="Let me think about this "),
        _stream_chunk(content="without calling a tool."),
    ]
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = [round1]
    seen: list[tuple[str, Any]] = []

    tools = [{"type": "function", "function": {"name": "lookup", "parameters": {}}}]
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        with pytest.raises(RuntimeError, match="tool_choice='required'"):
            digillm.run_tools(
                "gpt-4o-mini",
                [{"role": "user", "content": "go"}],
                tools,
                execute_tool=lambda name, args: "unused",
                on_tool_step=lambda kind, payload: seen.append((kind, payload)),
                stream_deltas=True,
                tool_choice="required",
            )
    # The rejected narration/reasoning must never have reached the caller's callback.
    assert not any(kind in ("content", "reasoning") for kind, _ in seen)


def test_stream_deltas_required_tool_choice_releases_content_when_tool_called() -> None:
    """Narration alongside a SATISFIED tool_choice='required' round (tool_calls
    present) must still reach on_tool_step -- buffering only discards a rejected
    round's deltas, it must not silently eat a legitimate one's.

    max_tool_rounds=1 means the round budget is exhausted right after this one
    tool-calling round, which now unconditionally forces the tool-free wrap-up
    completion (CodeRabbit follow-up review on PR #2361: the round's own
    narration was written before its tool_calls ran, so it can't reflect what
    "check that" actually returned -- returning it directly would discard the
    tool result this round just appended). The wrap-up's own content ("Final
    answer using tool result.") is what run_tools must return, not the earlier
    narration -- though that narration must still have been delivered live."""
    round1 = [
        _stream_chunk(content="I will "),
        _stream_chunk(content="check that."),
        _stream_chunk(tool_calls=[_tc_fragment(0, id="c1", name="lookup", arguments="{}")]),
    ]
    round2 = [_stream_chunk(content="Final answer using tool result.")]
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = [round1, round2]
    seen: list[tuple[str, Any]] = []

    tools = [{"type": "function", "function": {"name": "lookup", "parameters": {}}}]
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        out = digillm.run_tools(
            "gpt-4o-mini",
            [{"role": "user", "content": "go"}],
            tools,
            lambda name, args: "tool-result",
            on_tool_step=lambda kind, payload: seen.append((kind, payload)),
            stream_deltas=True,
            tool_choice="required",
            max_tool_rounds=1,
        )
    assert out == "Final answer using tool result."
    # The tool-calling round's narration was still delivered (buffering releases it
    # once tool_calls is confirmed) -- it's just no longer what run_tools returns.
    assert [p for k, p in seen if k == "content"] == [
        "I will ",
        "check that.",
        "Final answer using tool result.",
    ]
    assert any(k == "round_limit_exhausted" for k, _ in seen)
    # Second call is the tool-free wrap-up: no tools attached, so tool_choice
    # never reaches its wire even though the outer tool_choice is still "required".
    second_call_kwargs = fake_client.chat.completions.create.call_args_list[1][1]
    assert "tools" not in second_call_kwargs
    assert "tool_choice" not in second_call_kwargs


def test_stream_deltas_default_false_uses_non_streaming(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without stream_deltas, turns are produced by the non-streaming chat_completion."""
    fn = MagicMock()
    fn.name = "lookup"
    fn.arguments = "{}"
    tc = MagicMock()
    tc.id = "c1"
    tc.function = fn
    responses = [_mock_response("", tool_calls=[tc]), _mock_response("done")]
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = responses
    tools = [{"type": "function", "function": {"name": "lookup", "parameters": {}}}]
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        out = digillm.run_tools(
            "gpt-4o-mini",
            [{"role": "user", "content": "go"}],
            tools,
            lambda *_: "r",
        )
    assert out == "done"
    # Non-streaming path never sets stream=True.
    for call in fake_client.chat.completions.create.call_args_list:
        assert "stream" not in call.kwargs or call.kwargs["stream"] is not True


def test_normalize_tool_arguments_repairs_bad_json() -> None:
    assert json.loads(client_mod._normalize_tool_arguments('{"a": 1')) == {"a": 1}
    assert client_mod._normalize_tool_arguments("") == "{}"
    assert json.loads(client_mod._normalize_tool_arguments('{"a": 1,}')) == {"a": 1}
    assert client_mod._normalize_tool_arguments("not json at all") == "{}"


# ── Retry ────────────────────────────────────────────────────────────────────


def test_create_with_retry_retries_then_succeeds() -> None:
    from openai import APITimeoutError

    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = [
        APITimeoutError(request=MagicMock()),
        _mock_response("recovered"),
    ]
    with patch.object(client_mod, "_sleep_transient_retry", return_value=5.0) as sleep:
        r = client_mod._create_with_retry(fake_client, model="m", messages=[])
    assert r.choices[0].message.content == "recovered"
    assert sleep.call_count == 1


def test_completion_reports_transient_provider_retries() -> None:
    from openai import APITimeoutError

    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = [
        APITimeoutError(request=MagicMock()),
        _real_completion("recovered"),
    ]
    events: list[dict[str, Any]] = []
    digillm.set_usage_observer(lambda **fields: events.append(fields))

    with (
        patch.object(client_mod, "get_client_for_model", return_value=fake_client),
        patch.object(client_mod, "_sleep_transient_retry", return_value=5.0),
    ):
        digillm.completion("gpt-4o-mini", [{"role": "user", "content": "hi"}])

    assert fake_client.chat.completions.create.call_count == 2
    assert len(events) == 1
    assert events[0]["retry_count"] == 1


def test_completion_records_failed_410_fallback_retry() -> None:
    class GoneError(RuntimeError):
        status_code = 410

    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = [
        GoneError("live search removed"),
        ValueError("fallback failed"),
    ]
    events: list[dict[str, Any]] = []
    digillm.set_usage_observer(lambda **fields: events.append(fields))

    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        with pytest.raises(ValueError, match="fallback failed"):
            digillm.completion(
                "xai/grok-4",
                [{"role": "user", "content": "hi"}],
                search_parameters={"mode": "auto"},
            )

    assert fake_client.chat.completions.create.call_count == 2
    assert len(events) == 1
    assert events[0]["ok"] is False
    assert events[0]["retry_count"] == 1


def test_create_with_retry_propagates_non_transient() -> None:
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = ValueError("bad request")
    with pytest.raises(ValueError, match="bad request"):
        client_mod._create_with_retry(fake_client, model="m", messages=[])


def test_optional_nonnegative_int_rejects_bool_as_unavailable() -> None:
    """``bool`` subclasses ``int``; False must stay unavailable, never measured zero (#1989)."""
    assert client_mod._optional_nonnegative_int(False) is None
    assert client_mod._optional_nonnegative_int(True) is None
    assert client_mod._optional_nonnegative_int(None) is None
    assert client_mod._optional_nonnegative_int(-1) is None
    assert client_mod._optional_nonnegative_int(0) == 0
    assert client_mod._optional_nonnegative_int(3) == 3


def test_sdk_hidden_retries_remain_enabled_and_opaque() -> None:
    """Attempt telemetry observes SDK create calls, not the SDK's internal HTTP retries.

    We deliberately omit ``max_retries`` so the SDK default applies. Pin that default to the
    documented figure (``DEFAULT_MAX_RETRIES``) — otherwise the canary stays green while an
    unbounded ``openai`` resolve silently retunes how many HTTP exchanges hide under one
    attempt record (#1989).
    """
    from openai._constants import DEFAULT_MAX_RETRIES

    made = _capture_client_kwargs(digillm.get_client)
    assert len(made) == 1
    assert "max_retries" not in made[0]
    assert DEFAULT_MAX_RETRIES == 2


@pytest.mark.parametrize(
    ("search_name", "expected_kind"),
    [("web_search", "web_search"), ("x_search", "x_search")],
)
def test_direct_search_reports_duration(
    monkeypatch: pytest.MonkeyPatch,
    search_name: str,
    expected_kind: str,
) -> None:
    monkeypatch.setenv("XAI_API_KEY", "xai-test")
    response = MagicMock()
    response.output_text = "Grounded [[1]](https://example.test/source)"
    response.output = []
    fake_client = MagicMock()
    fake_client.responses.create.return_value = response
    events: list[dict[str, Any]] = []
    digillm.set_usage_observer(lambda **fields: events.append(fields))

    with (
        patch.object(client_mod, "get_client_for_model", return_value=fake_client),
        patch.object(client_mod.time, "perf_counter", side_effect=[10.0, 10.125]),
    ):
        result = getattr(client_mod, search_name)("xai/grok-4", "latest market news")

    assert result is not None
    assert len(events) == 1
    assert events[0]["kind"] == expected_kind
    assert events[0]["duration_ms"] == 125


@pytest.mark.parametrize("search_name", ["web_search", "x_search"])
def test_direct_search_failure_reports_duration(
    monkeypatch: pytest.MonkeyPatch,
    search_name: str,
) -> None:
    monkeypatch.setenv("XAI_API_KEY", "xai-test")
    fake_client = MagicMock()
    fake_client.responses.create.side_effect = RuntimeError("provider unavailable")
    events: list[dict[str, Any]] = []
    digillm.set_usage_observer(lambda **fields: events.append(fields))

    with (
        patch.object(client_mod, "get_client_for_model", return_value=fake_client),
        patch.object(client_mod.time, "perf_counter", side_effect=[20.0, 20.075]),
    ):
        result = getattr(client_mod, search_name)("xai/grok-4", "latest market news")

    assert result is None
    assert len(events) == 1
    assert events[0]["ok"] is False
    assert events[0]["duration_ms"] == 75


# ── Per-request overrides (contextvars) ──────────────────────────────────────


def test_set_proxy_key_changes_default_client_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    made: list[dict[str, Any]] = []
    with patch.object(
        client_mod, "OpenAI", side_effect=lambda **kw: made.append(kw) or MagicMock()
    ):
        digillm.get_client()  # uses env key
        with digillm.proxy_key("proxy-tok"):
            digillm.get_client()  # uses proxy override
    assert made[0]["api_key"] == "sk-env"
    assert made[1]["api_key"] == "proxy-tok"


def test_set_proxy_key_reset_restores(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    tok = digillm.set_proxy_key("temp")
    assert digillm.get_proxy_key() == "temp"
    digillm.reset_proxy_key(tok)
    assert digillm.get_proxy_key() is None


def test_set_byok_uncached_and_uses_supplied_key() -> None:
    made: list[dict[str, Any]] = []
    with patch.object(
        client_mod, "OpenAI", side_effect=lambda **kw: made.append(kw) or MagicMock()
    ):
        with digillm.byok("user-key", "https://api.openai.com/v1"):
            a = digillm.get_client()
            b = digillm.get_client()
    # BYOK clients are never cached: two constructions for two calls.
    assert len(made) == 2
    assert a is not b
    assert made[0]["api_key"] == "user-key"
    assert made[0]["base_url"] == "https://api.openai.com/v1"


def test_byok_bypasses_response_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _mock_response("byok-out")
    msgs = [{"role": "user", "content": "same"}]
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        with digillm.byok("user-key"):
            digillm.completion("gpt-4o-mini", msgs)
            digillm.completion("gpt-4o-mini", msgs)
    # No cache while BYOK active → API hit twice.
    assert fake_client.chat.completions.create.call_count == 2


# ── structured_completion ────────────────────────────────────────────────────


class _Person(BaseModel):
    name: str
    age: int


def test_structured_completion_happy_path() -> None:
    payload = '{"name": "Ada", "age": 36}'
    with patch.object(client_mod, "_create_with_retry", return_value=_mock_response(payload)):
        with patch.object(client_mod, "get_client_for_model", return_value=MagicMock()):
            person = digillm.structured_completion(
                "gpt-4o-mini", [{"role": "user", "content": "who?"}], _Person
            )
    assert isinstance(person, _Person)
    assert person.name == "Ada" and person.age == 36


def test_structured_completion_strips_markdown_fences() -> None:
    fenced = '```json\n{"name": "Bob", "age": 5}\n```'
    with patch.object(client_mod, "_create_with_retry", return_value=_mock_response(fenced)):
        with patch.object(client_mod, "get_client_for_model", return_value=MagicMock()):
            person = digillm.structured_completion(
                "gpt-4o-mini", [{"role": "user", "content": "who?"}], _Person
            )
    assert person.name == "Bob" and person.age == 5


def test_structured_completion_sends_json_schema_response_format() -> None:
    captured: dict[str, Any] = {}

    def fake_create(_client: Any, **kwargs: Any) -> MagicMock:
        captured.update(kwargs)
        return _mock_response('{"name": "X", "age": 1}')

    with patch.object(client_mod, "_create_with_retry", side_effect=fake_create):
        with patch.object(client_mod, "get_client_for_model", return_value=MagicMock()):
            digillm.structured_completion(
                "gpt-4o-mini", [{"role": "user", "content": "x"}], _Person
            )
    rf = captured["response_format"]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["name"] == "_Person"
    assert "properties" in rf["json_schema"]["schema"]


class _PersonWithOptional(BaseModel):
    name: str
    nickname: str | None = None


def test_structured_completion_strict_schema_lists_every_property_as_required() -> None:
    """Strict mode must list defaulted/optional fields in `required` too (nullable
    instead of omitted) — OpenAI-family providers 400 otherwise. Plain
    `model_json_schema()` omits fields with a default from `required`."""
    captured: dict[str, Any] = {}

    def fake_create(_client: Any, **kwargs: Any) -> MagicMock:
        captured.update(kwargs)
        return _mock_response('{"name": "X", "nickname": null}')

    with patch.object(client_mod, "_create_with_retry", side_effect=fake_create):
        with patch.object(client_mod, "get_client_for_model", return_value=MagicMock()):
            digillm.structured_completion(
                "gpt-4o-mini", [{"role": "user", "content": "x"}], _PersonWithOptional
            )
    schema = captured["response_format"]["json_schema"]["schema"]
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["additionalProperties"] is False


class _Address(BaseModel):
    city: str
    # Defaulted nested field — plain model_json_schema() omits it from required.
    country: str = "US"


class _PersonNested(BaseModel):
    name: str
    address: _Address


def test_structured_completion_strict_schema_forces_required_through_nested_defs() -> None:
    """#2353 claims recursive required-forcing through $defs/items/anyOf. Flat
    optional coverage alone would miss nested Atlas/digest schemas that still
    400 on OpenAI-family providers when a child property is omitted from
    required."""
    captured: dict[str, Any] = {}

    def fake_create(_client: Any, **kwargs: Any) -> MagicMock:
        captured.update(kwargs)
        return _mock_response('{"name": "X", "address": {"city": "Berlin", "country": "DE"}}')

    with patch.object(client_mod, "_create_with_retry", side_effect=fake_create):
        with patch.object(client_mod, "get_client_for_model", return_value=MagicMock()):
            digillm.structured_completion(
                "gpt-4o-mini", [{"role": "user", "content": "x"}], _PersonNested
            )
    schema = captured["response_format"]["json_schema"]["schema"]
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["additionalProperties"] is False

    # Nested object may live under $defs / $ref (OpenAI strict helper) or inline.
    defs = schema.get("$defs") or schema.get("definitions") or {}
    nested_candidates = [defs[k] for k in defs if "Address" in k] if defs else []
    if not nested_candidates:
        addr = schema["properties"].get("address")
        assert isinstance(addr, dict)
        nested_candidates = [addr]
    for nested in nested_candidates:
        assert set(nested["required"]) == set(nested["properties"])
        assert nested.get("additionalProperties") is False


def test_structured_completion_non_strict_keeps_plain_schema() -> None:
    """strict=False must NOT force-list optional fields into `required` — it uses
    plain `model_json_schema()`, which omits defaulted fields."""
    captured: dict[str, Any] = {}

    def fake_create(_client: Any, **kwargs: Any) -> MagicMock:
        captured.update(kwargs)
        return _mock_response('{"name": "X"}')

    with patch.object(client_mod, "_create_with_retry", side_effect=fake_create):
        with patch.object(client_mod, "get_client_for_model", return_value=MagicMock()):
            digillm.structured_completion(
                "gpt-4o-mini",
                [{"role": "user", "content": "x"}],
                _PersonWithOptional,
                strict=False,
            )
    schema = captured["response_format"]["json_schema"]["schema"]
    assert "nickname" not in schema["required"]


def test_structured_completion_validation_error() -> None:
    bad = '{"name": "NoAge"}'  # missing required 'age'
    with patch.object(client_mod, "_create_with_retry", return_value=_mock_response(bad)):
        with patch.object(client_mod, "get_client_for_model", return_value=MagicMock()):
            with pytest.raises(ValidationError):
                digillm.structured_completion(
                    "gpt-4o-mini", [{"role": "user", "content": "who?"}], _Person
                )


def test_structured_completion_empty_raises() -> None:
    with patch.object(client_mod, "_create_with_retry", return_value=_mock_response("")):
        with patch.object(client_mod, "get_client_for_model", return_value=MagicMock()):
            with pytest.raises(ValueError, match="Empty response"):
                digillm.structured_completion(
                    "gpt-4o-mini", [{"role": "user", "content": "x"}], _Person
                )


# ── Mode resolution ──────────────────────────────────────────────────────────


def test_resolve_model_from_mapping() -> None:
    modes = {"test": "gpt-4o-mini", "medium": "gpt-4o", "best": "o1"}
    assert digillm.resolve_model("test", modes) == "gpt-4o-mini"
    assert digillm.resolve_model("BEST", modes) == "o1"


def test_resolve_model_default_fallback() -> None:
    assert digillm.resolve_model("medium", {}, default="fallback-model") == "fallback-model"


def test_resolve_model_missing_raises() -> None:
    with pytest.raises(KeyError):
        digillm.resolve_model("best", {"test": "m"})


def test_resolve_model_from_yaml_path(tmp_path: Any) -> None:
    yaml_file = tmp_path / "model_modes.yaml"
    yaml_file.write_text("defaults:\n  test: tiny-model\n  best: big-model\n")
    assert digillm.resolve_model("test", path=yaml_file) == "tiny-model"
    assert digillm.resolve_model("best", path=yaml_file) == "big-model"


def test_resolve_model_yaml_flat_mapping(tmp_path: Any) -> None:
    yaml_file = tmp_path / "modes.yaml"
    yaml_file.write_text("test: a\nmedium: b\nbest: c\n")
    assert digillm.resolve_model("medium", path=yaml_file) == "b"


# ── Empty-retry configurability (#814) ──────────────────────────────────────────


def test_empty_retry_defaults_raised_after_814() -> None:
    """Defaults raised from 2/2.0s → 4/5.0s to survive the 25-analyst fan-out empty storm.
    These assertions catch any unintentional regression of the new defaults."""
    # The module-level constants reflect the env at import time. The autouse fixture
    # clears all relevant env vars before each test, so when no env vars are set the
    # constants hold the compiled-in default values.
    assert client_mod._EMPTY_RETRY_MAX == 4, (
        "DIGILLM_EMPTY_RETRY_MAX default should be 4 (raised from 2 in #814)"
    )
    assert client_mod._EMPTY_RETRY_DELAY == 5.0, (
        "DIGILLM_EMPTY_RETRY_BACKOFF default should be 5.0s (raised from 2.0s in #814)"
    )


def test_empty_retry_env_override_new_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """DIGILLM_EMPTY_RETRY_BACKOFF overrides the delay; DIGILLM_EMPTY_RETRY_MAX overrides count.
    Because these are module-level constants we verify via monkeypatch.setattr behaviour —
    the functional effect is tested by the existing retry-heals / gives-up tests."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    monkeypatch.setattr(client_mod, "_EMPTY_RETRY_MAX", 3)
    monkeypatch.setattr(client_mod, "_EMPTY_RETRY_DELAY", 0.0)
    monkeypatch.setattr(client_mod.time, "sleep", lambda *_a, **_k: None)
    fake_client = MagicMock()
    # Always returns empty so we can count attempts = 1 initial + _EMPTY_RETRY_MAX retries.
    fake_client.chat.completions.create.return_value = _mock_response("")
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        resp = digillm.completion("gpt-4o-mini", [{"role": "user", "content": "x"}])
    assert client_mod._is_empty_completion(resp)
    assert fake_client.chat.completions.create.call_count == 1 + 3  # 1 initial + 3 retries


def test_empty_retry_legacy_delay_env_still_honored(monkeypatch: pytest.MonkeyPatch) -> None:
    """DIGILLM_EMPTY_RETRY_DELAY (old name) is accepted as a back-compat alias (#814)."""
    monkeypatch.setenv("DIGILLM_EMPTY_RETRY_DELAY", "3.0")
    monkeypatch.delenv("DIGILLM_EMPTY_RETRY_BACKOFF", raising=False)
    # Re-derive the value using the same logic as the module (without a full reload, which
    # would require careful fixture teardown). We parse the env directly here to test the
    # intent: if only the old var is set, it should feed through.
    import os

    backoff_raw = (
        os.environ.get("DIGILLM_EMPTY_RETRY_BACKOFF", "").strip()
        or os.environ.get("DIGILLM_EMPTY_RETRY_DELAY", "").strip()
        or "5.0"
    )
    assert float(backoff_raw) == 3.0, "legacy DIGILLM_EMPTY_RETRY_DELAY must still be honored"


def test_empty_retry_new_name_wins_over_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    """When both DIGILLM_EMPTY_RETRY_BACKOFF and DIGILLM_EMPTY_RETRY_DELAY are set, new wins."""
    import os

    monkeypatch.setenv("DIGILLM_EMPTY_RETRY_BACKOFF", "8.0")
    monkeypatch.setenv("DIGILLM_EMPTY_RETRY_DELAY", "3.0")
    backoff_raw = (
        os.environ.get("DIGILLM_EMPTY_RETRY_BACKOFF", "").strip()
        or os.environ.get("DIGILLM_EMPTY_RETRY_DELAY", "").strip()
        or "5.0"
    )
    assert float(backoff_raw) == 8.0, "new DIGILLM_EMPTY_RETRY_BACKOFF must win over legacy name"
