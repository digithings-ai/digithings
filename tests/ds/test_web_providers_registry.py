"""Registry contracts for the unified ``web_search`` tool (#4711).

Two load-bearing rules are pinned here:

- ``provider="auto"`` is **always** the in-house tool — no external API key can
  reroute the default path, at the registry level or over HTTP.
- A named external provider is fail-closed: missing key -> 503 (HTTP) /
  ``WebProviderNotConfiguredError`` (library), never a silent fallback.
"""

from __future__ import annotations

import pytest
from digisearch.server import app
from digisearch.web_providers import (
    EXTERNAL_PROVIDER_ENV,
    PROVIDER_NAMES,
    UnknownProviderError,
    WebProviderCapabilityError,
    WebProviderNotConfiguredError,
    available_providers,
    configured_providers,
    get_provider,
    provider_enum_choices,
    resolve_provider_name,
)
from digisearch.web_providers.exa import ExaWebProvider
from digisearch.web_providers.internal import InternalWebProvider
from digisearch.web_search.models import WebSearchRequest, WebSearchResponse
from fastapi.testclient import TestClient

from tests.digi_test_jwt import auth_headers

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _no_external_keys(monkeypatch):
    """Start every test key-less; individual tests opt a key in."""
    for env in EXTERNAL_PROVIDER_ENV.values():
        monkeypatch.delenv(env, raising=False)


# --- name resolution: auto is unconditionally internal ------------------------


@pytest.mark.parametrize("raw", ["auto", "AUTO", "  auto ", "", "   ", None])
def test_auto_and_blank_resolve_to_internal(raw):
    assert resolve_provider_name(raw) == "internal"
    assert isinstance(get_provider(raw), InternalWebProvider)


def test_auto_stays_internal_even_with_every_external_key_set(monkeypatch):
    for env in EXTERNAL_PROVIDER_ENV.values():
        monkeypatch.setenv(env, "test-key")
    assert resolve_provider_name("auto") == "internal"
    assert isinstance(get_provider("auto"), InternalWebProvider)
    # Every provider now reports configured — yet `auto` still picked in-house.
    assert set(configured_providers()) == set(PROVIDER_NAMES)


def test_named_providers_resolve_case_insensitively():
    assert resolve_provider_name(" TAVILY ") == "tavily"
    assert resolve_provider_name("Exa") == "exa"


def test_unknown_provider_lists_the_valid_names():
    with pytest.raises(UnknownProviderError) as excinfo:
        resolve_provider_name("google")
    message = str(excinfo.value)
    assert "google" in message
    for name in PROVIDER_NAMES:
        assert name in message


# --- fail-closed: a named provider never falls back without its key -----------


@pytest.mark.parametrize("name", [n for n in PROVIDER_NAMES if n != "internal"])
def test_named_external_provider_without_key_fails_closed(name):
    provider = get_provider(name)
    assert provider.is_configured() is False
    with pytest.raises(WebProviderNotConfiguredError) as excinfo:
        provider.search(WebSearchRequest(query="q", provider=name))
    assert provider.env_var in str(excinfo.value)


def test_env_is_read_at_call_time_not_import_time(monkeypatch):
    provider = get_provider("tavily")
    assert provider.is_configured() is False
    monkeypatch.setenv("TAVILY_API_KEY", "late-key")  # added after import
    assert get_provider("tavily").is_configured() is True
    assert "tavily" in configured_providers()
    monkeypatch.delenv("TAVILY_API_KEY")
    assert get_provider("tavily").is_configured() is False


# --- offset is a capability guard, checked before anything else ---------------


@pytest.mark.parametrize("name", ["internal", "tavily", "parallel", "firecrawl", "tinyfish"])
def test_offset_above_zero_rejected_for_non_paging_providers(name):
    # No key set anywhere: the capability guard must fire *before* the key
    # check, otherwise "page past cap" would surface as a misleading 503.
    with pytest.raises(WebProviderCapabilityError) as excinfo:
        get_provider(name).search(WebSearchRequest(query="q", provider=name, offset=5))
    assert "offset" in str(excinfo.value)
    assert name in str(excinfo.value)


def test_only_exa_pages():
    caps = available_providers()
    assert caps["exa"]["supports_offset"] is True
    assert ExaWebProvider.supports_offset is True
    assert [n for n, c in caps.items() if c["supports_offset"]] == ["exa"]


# --- manifest introspection ---------------------------------------------------


def test_enum_choices_always_offer_auto_and_internal():
    assert provider_enum_choices()[0] == "auto"
    assert provider_enum_choices() == ["auto", "internal"]  # key-less install


def test_enum_choices_add_keyed_externals(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-key")
    assert provider_enum_choices() == ["auto", "internal", "tavily"]


def test_available_providers_describes_every_provider():
    caps = available_providers()
    assert set(caps) == set(PROVIDER_NAMES)
    assert caps["internal"]["env_var"] == ""
    assert caps["tavily"]["env_var"] == "TAVILY_API_KEY"
    assert [n for n, c in caps.items() if c["supports_contents"]] == ["exa"]
    assert [n for n, c in caps.items() if c["supports_answer"]] == ["exa"]


# --- HTTP route: the same rules with status codes -----------------------------


def test_route_unknown_provider_is_400():
    client = TestClient(app, headers=auth_headers())
    resp = client.post("/v1/web_search", json={"query": "q", "provider": "google"})
    assert resp.status_code == 400, resp.text
    assert "unknown provider" in resp.text


def test_route_named_provider_without_key_is_503():
    client = TestClient(app, headers=auth_headers())
    resp = client.post("/v1/web_search", json={"query": "q", "provider": "tavily"})
    assert resp.status_code == 503, resp.text
    assert "TAVILY_API_KEY" in resp.text


def test_route_offset_on_non_paging_provider_is_400(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-key")
    client = TestClient(app, headers=auth_headers())
    resp = client.post("/v1/web_search", json={"query": "q", "provider": "tavily", "offset": 5})
    assert resp.status_code == 400, resp.text
    assert "offset" in resp.text


def test_route_auto_with_every_key_set_still_runs_the_in_house_tool(monkeypatch):
    """The default path must never be reachable by an external vendor."""
    from digisearch.web_providers import base as providers_base
    from digisearch.web_search import service as svc

    from digisearch import web_exa

    for env in EXTERNAL_PROVIDER_ENV.values():
        monkeypatch.setenv(env, "test-key")

    def _no_external_transport(*args, **kwargs):
        raise AssertionError("an external vendor HTTP call must never happen on auto")

    monkeypatch.setattr(providers_base.httpx, "request", _no_external_transport)
    monkeypatch.setattr(web_exa.httpx, "post", _no_external_transport)
    monkeypatch.setattr(
        svc,
        "run_web_search",
        lambda req, config=None: WebSearchResponse(query=req.query, provider="searxng", results=[]),
    )

    client = TestClient(app, headers=auth_headers())
    resp = client.post("/v1/web_search", json={"query": "q"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["provider"] == "internal"
    assert body["output"] == {"backend": "searxng"}


# --- retired surfaces stay gone (hard-break convergence, #4711) ---------------


def test_retired_digisearch_web_search_route_is_404():
    client = TestClient(app, headers=auth_headers())
    resp = client.post(
        "/v1/digisearch_web_search",
        json={"query": "q", "search_type": "auto", "num_results": 3},
    )
    assert resp.status_code == 404, resp.text


def test_mcp_no_longer_advertises_exa_web_search():
    import digisearch.mcp_server as mcp_mod

    assert hasattr(mcp_mod, "web_search")
    assert not hasattr(mcp_mod, "exa_web_search")
