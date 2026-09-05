"""Adversarial BYOK / LiteLLM isolation tests (#3605).

These pin the trust boundary: BYOK secrets may ride ``extra_body`` only to an
explicitly declared LiteLLM proxy, never to a vendor endpoint that merely is
not OpenRouter. LiteLLM's shared response cache must not be written or read
for BYOK, and a caller-supplied ``api_base`` outside the catalog is refused
before it reaches the proxy.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import digillm
from digillm import client as client_mod

_BYOK_CATALOG = json.loads(
    (Path(__file__).resolve().parents[2] / "config" / "byok-providers.json").read_text(
        encoding="utf-8"
    )
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch: pytest.MonkeyPatch) -> None:
    digillm.clear_caches()
    for var in (
        "OPENAI_API_KEY",
        "OPENAI_API_BASE",
        "LITELLM_PROXY_API_KEY",
        "DIGILLM_TRUSTED_LITELLM_BASES",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "XAI_API_KEY",
        "OPENROUTER_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    yield
    digillm.clear_caches()


def _mock_response(content: str = "ok") -> MagicMock:
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = None
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _completion_kwargs(model: str, *, byok_key: str, byok_base: str) -> dict[str, Any]:
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _mock_response()
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        with digillm.byok(byok_key, byok_base):
            digillm.completion(model, [{"role": "user", "content": "same prompt"}])
    _, kwargs = fake_client.chat.completions.create.call_args
    return kwargs


@pytest.mark.parametrize(
    "base",
    [
        "http://127.0.0.1:4000/v1",
        "http://127.0.0.1:4000",
        "http://localhost:4000/",
        "http://litellm:4000/v1",
        "http://host.docker.internal:4000/v1",
    ],
)
def test_documented_litellm_urls_are_trusted_proxies(
    monkeypatch: pytest.MonkeyPatch, base: str
) -> None:
    monkeypatch.setenv("OPENAI_API_BASE", base)
    assert client_mod._litellm_proxy_configured() is True


@pytest.mark.parametrize(
    "base",
    [
        "https://api.openai.com/v1",
        "https://openrouter.ai/api/v1",
        "http://127.0.0.1:11434/v1",
        "https://api.anthropic.com/v1",
        "https://evil.example/v1",
        "",
    ],
)
def test_direct_and_vendor_bases_are_not_trusted_proxies(
    monkeypatch: pytest.MonkeyPatch, base: str
) -> None:
    if base:
        monkeypatch.setenv("OPENAI_API_BASE", base)
    assert client_mod._litellm_proxy_configured() is False


def test_trusted_proxy_allowlist_is_explicit_env_not_not_openrouter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_BASE", "http://llm-proxy.internal:4000/v1")
    assert client_mod._litellm_proxy_configured() is False
    monkeypatch.setenv("DIGILLM_TRUSTED_LITELLM_BASES", "http://llm-proxy.internal:4000/v1")
    assert client_mod._litellm_proxy_configured() is True


def test_direct_openai_base_does_not_receive_cross_provider_byok_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repo-documented direct OpenAI endpoint must not see an Anthropic BYOK key."""
    monkeypatch.setenv("OPENAI_API_BASE", "https://api.openai.com/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-house-openai")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-operator")
    made: list[dict[str, Any]] = []
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _mock_response()

    def fake_openai(**kwargs: Any) -> MagicMock:
        made.append(kwargs)
        return fake_client

    with patch.object(client_mod, "OpenAI", side_effect=fake_openai):
        with digillm.byok("sk-ant-user-secret", "https://api.anthropic.com/v1"):
            digillm.get_client_for_model("anthropic/claude-sonnet-4-20250514")
            digillm.completion(
                "anthropic/claude-sonnet-4-20250514",
                [{"role": "user", "content": "hi"}],
            )

    assert made, "expected a direct vendor client"
    assert all(kw["api_key"] == "sk-ant-user-secret" for kw in made)
    assert all("api.anthropic.com" in (kw.get("base_url") or "") for kw in made)
    assert all(kw["api_key"] != "sk-house-openai" for kw in made)
    extra = fake_client.chat.completions.create.call_args[1].get("extra_body") or {}
    assert extra.get("api_key") != "sk-ant-user-secret"
    assert "api_key" not in extra
    assert "api_base" not in extra


def test_ollama_base_does_not_receive_byok_extra_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:11434/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-house")
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _mock_response()
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        with digillm.byok("sk-or-user", "https://openrouter.ai/api/v1"):
            digillm.completion(
                "openrouter/openai/gpt-4o-mini",
                [{"role": "user", "content": "hi"}],
            )
    extra = fake_client.chat.completions.create.call_args[1].get("extra_body") or {}
    assert extra.get("api_key") != "sk-or-user"
    assert "api_key" not in extra


def test_byok_proxy_request_disables_litellm_shared_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:4000/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proxy")
    kwargs = _completion_kwargs(
        "anthropic/claude-sonnet-5",
        byok_key="sk-ant-user-a",
        byok_base="https://api.anthropic.com/v1/",
    )
    extra = kwargs["extra_body"]
    assert extra["api_key"] == "sk-ant-user-a"
    assert extra["api_base"].rstrip("/") == "https://api.anthropic.com/v1"
    assert extra["cache"] == {"no-cache": True, "no-store": True}


@pytest.mark.parametrize(
    ("key_a", "key_b", "base_a", "base_b"),
    [
        (
            "sk-user-a",
            "sk-user-b",
            "https://api.openai.com/v1",
            "https://api.openai.com/v1",
        ),
        (
            "sk-ant-a",
            "sk-or-b",
            "https://api.anthropic.com/v1",
            "https://openrouter.ai/api/v1",
        ),
        (
            "sk-user-a",
            "sk-house-not-used",
            "https://api.openai.com/v1",
            "https://api.openai.com/v1",
        ),
    ],
)
def test_cross_principal_byok_proxy_requests_all_disable_shared_cache(
    monkeypatch: pytest.MonkeyPatch,
    key_a: str,
    key_b: str,
    base_a: str,
    base_b: str,
) -> None:
    monkeypatch.setenv("OPENAI_API_BASE", "http://litellm:4000/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proxy")
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _mock_response("fresh")
    msgs = [{"role": "user", "content": "identical prompt"}]
    extras: list[dict[str, Any]] = []
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        with digillm.byok(key_a, base_a):
            digillm.completion("gpt-4o-mini", msgs)
        extras.append(fake_client.chat.completions.create.call_args[1]["extra_body"])
        with digillm.byok(key_b, base_b):
            digillm.completion("gpt-4o-mini", msgs)
        extras.append(fake_client.chat.completions.create.call_args[1]["extra_body"])
        digillm.completion("gpt-4o-mini", msgs)  # house caller, no BYOK
    assert fake_client.chat.completions.create.call_count == 3
    assert extras[0]["api_key"] == key_a
    assert extras[1]["api_key"] == key_b
    for extra in extras:
        assert extra["cache"]["no-cache"] is True
        assert extra["cache"]["no-store"] is True
    house_kwargs = fake_client.chat.completions.create.call_args_list[2][1]
    house_extra = house_kwargs.get("extra_body") or {}
    assert house_extra.get("api_key") not in {key_a, key_b}
    cache = house_extra.get("cache") or {}
    assert cache.get("no-store") is not True


def test_byok_stream_also_disables_litellm_shared_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:4000/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proxy")
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = iter([])
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        with digillm.byok("sk-or-user", "https://openrouter.ai/api/v1"):
            client_mod._stream_completion_one_turn(
                "openrouter/openai/gpt-4o-mini",
                [{"role": "user", "content": "hi"}],
            )
    extra = fake_client.chat.completions.create.call_args[1]["extra_body"]
    assert extra["cache"] == {"no-cache": True, "no-store": True}


def test_caller_supplied_non_catalog_api_base_is_rejected_on_proxy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:4000/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proxy")
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _mock_response()
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        with digillm.byok("sk-stolen", "https://evil.example/v1"):
            with pytest.raises(RuntimeError, match="catalog"):
                digillm.completion("gpt-4o-mini", [{"role": "user", "content": "hi"}])
    fake_client.chat.completions.create.assert_not_called()


def _advertised_presets() -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for entry in _BYOK_CATALOG:
        for model in entry["fallbackModels"]:
            rows.append((str(entry["id"]), str(model), str(entry["baseUrl"])))
    return rows


@pytest.mark.parametrize("provider, model, base_url", _advertised_presets())
def test_every_advertised_byok_model_routes_through_declared_proxy(
    monkeypatch: pytest.MonkeyPatch, provider: str, model: str, base_url: str
) -> None:
    """Each catalog preset is a LiteLLM model id with catalog-host clientside credentials."""
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:4000/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proxy")
    kwargs = _completion_kwargs(
        model,
        byok_key=f"sk-{provider}-user",
        byok_base=base_url,
    )
    extra = kwargs["extra_body"]
    assert kwargs["model"] == model
    assert extra["api_key"] == f"sk-{provider}-user"
    assert extra["api_base"] == base_url.rstrip("/")
    assert extra["cache"] == {"no-cache": True, "no-store": True}
