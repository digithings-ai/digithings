"""Unit tests for digigraph.llm_auth (per-request proxy-key + BYOK funnel).

Split from the former tests/dg/test_llm.py (#632 P2). These are the safety net
for the auth/credential funnel: they assert that the header parsers feed digillm's
override contextvars correctly and that digigraph's own ``(key, provider)`` BYOK
record is preserved. Client-side key resolution now lives in digillm and is
covered by digillm/tests/test_digillm.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from digigraph.llm_auth import (
    BYOK_ROUTABLE_PROVIDERS,
    byok_provider_supported,
    get_byok_model_override,
    get_byok_override,
    pop_byok,
    pop_lite_llm_proxy,
    push_byok_header,
    push_lite_llm_proxy_header,
)

from digillm import get_byok as digillm_get_byok
from digillm import get_proxy_key as digillm_get_proxy_key

_REPO_ROOT = Path(__file__).resolve().parents[2]


class _Headers:
    """Case-insensitive header mapping mirroring Starlette's request.headers."""

    def __init__(self, d: dict[str, str]) -> None:
        self._d = {k.lower(): v for k, v in d.items()}

    def get(self, name: str) -> str | None:
        return self._d.get(name.lower())


class _Req:
    def __init__(self, headers: _Headers) -> None:
        self.headers = headers


def _byok_request(key: str = "", provider: str = "openai", model: str = "") -> _Req:
    h: dict[str, str] = {}
    if key:
        h["x-byok-key"] = key
    if provider:
        h["x-byok-provider"] = provider
    if model:
        h["x-byok-model"] = model
    return _Req(_Headers(h))


def _proxy_request(value: str | None) -> _Req:
    h: dict[str, str] = {}
    if value is not None:
        h["x-litellm-proxy-key"] = value
    return _Req(_Headers(h))


@pytest.mark.unit
class TestLiteLlmProxyHeader:
    """X-LiteLLM-Proxy-Key parsing → digillm proxy-key override."""

    def test_header_feeds_digillm_proxy_key(self) -> None:
        tok = push_lite_llm_proxy_header(_proxy_request("sk-header"))
        try:
            assert digillm_get_proxy_key() == "sk-header"
        finally:
            pop_lite_llm_proxy(tok)
        assert digillm_get_proxy_key() is None

    def test_no_header_leaves_override_unset(self) -> None:
        tok = push_lite_llm_proxy_header(_proxy_request(None))
        try:
            assert digillm_get_proxy_key() is None
        finally:
            pop_lite_llm_proxy(tok)

    def test_whitespace_header_ignored(self) -> None:
        tok = push_lite_llm_proxy_header(_proxy_request("   "))
        try:
            assert digillm_get_proxy_key() is None
        finally:
            pop_lite_llm_proxy(tok)


@pytest.mark.unit
class TestByokHeader:
    """X-BYOK-Key / X-BYOK-Provider lifecycle + digillm BYOK funnel."""

    def test_no_header_gives_none(self) -> None:
        tok = push_byok_header(_byok_request())
        try:
            assert get_byok_override() is None
            assert digillm_get_byok() is None
        finally:
            pop_byok(tok)

    def test_openai_key_stored(self) -> None:
        tok = push_byok_header(_byok_request(key="sk-test123", provider="openai"))
        try:
            result = get_byok_override()
            assert result is not None
            key, provider = result
            assert key == "sk-test123"
            assert provider == "openai"
        finally:
            pop_byok(tok)

    def test_anthropic_key_stored(self) -> None:
        tok = push_byok_header(_byok_request(key="sk-ant-testkey", provider="anthropic"))
        try:
            result = get_byok_override()
            assert result is not None
            key, provider = result
            assert key == "sk-ant-testkey"
            assert provider == "anthropic"
        finally:
            pop_byok(tok)

    def test_pop_clears_override(self) -> None:
        tok = push_byok_header(_byok_request(key="sk-abc", provider="openai"))
        pop_byok(tok)
        assert get_byok_override() is None
        assert digillm_get_byok() is None

    def test_openai_byok_feeds_digillm(self) -> None:
        """OpenAI BYOK → digillm BYOK override (direct api.openai.com client)."""
        tok = push_byok_header(_byok_request(key="sk-byok-key", provider="openai"))
        try:
            byok = digillm_get_byok()
            assert byok is not None
            key, base_url = byok
            assert key == "sk-byok-key"
            assert base_url == "https://api.openai.com/v1"
        finally:
            pop_byok(tok)
        assert digillm_get_byok() is None

    def test_openrouter_byok_feeds_digillm_and_model(self) -> None:
        """OpenRouter BYOK → digillm BYOK override + model slug contextvar."""
        tok = push_byok_header(
            _byok_request(
                key="sk-or-v1-test",
                provider="openrouter",
                model="openai/gpt-4o-mini",
            )
        )
        try:
            assert get_byok_override() == ("sk-or-v1-test", "openrouter")
            assert get_byok_model_override() == "openai/gpt-4o-mini"
            byok = digillm_get_byok()
            assert byok is not None
            key, base_url = byok
            assert key == "sk-or-v1-test"
            assert base_url == "https://openrouter.ai/api/v1"
        finally:
            pop_byok(tok)
        assert get_byok_model_override() is None
        assert digillm_get_byok() is None

    def test_anthropic_byok_feeds_digillm(self) -> None:
        """Anthropic BYOK → digillm BYOK override (Anthropic OpenAI-compat endpoint)."""
        tok = push_byok_header(
            _byok_request(
                key="sk-ant-xyz",
                provider="anthropic",
                model="claude-sonnet-4-6",
            )
        )
        try:
            assert get_byok_override() == ("sk-ant-xyz", "anthropic")
            assert get_byok_model_override() == "claude-sonnet-4-6"
            byok = digillm_get_byok()
            assert byok is not None
            key, base_url = byok
            assert key == "sk-ant-xyz"
            assert base_url.rstrip("/") == "https://api.anthropic.com/v1"
        finally:
            pop_byok(tok)

    def test_gemini_byok_feeds_digillm(self) -> None:
        tok = push_byok_header(
            _byok_request(key="gem-key", provider="gemini", model="gemini/gemini-2.5-flash")
        )
        try:
            assert get_byok_override() == ("gem-key", "gemini")
            assert get_byok_model_override() == "gemini-2.5-flash"
            byok = digillm_get_byok()
            assert byok is not None
            assert byok[0] == "gem-key"
            assert "generativelanguage.googleapis.com" in byok[1]
        finally:
            pop_byok(tok)


@pytest.mark.unit
class TestByokProviderGuard:
    """The routability guard behind digigraph's 400 (#1873).

    Before it, a pasted Anthropic or Gemini key was accepted, displayed as active, and
    then the request was answered with the operator's credentials — which the operator
    pays for, silently. The table in llm_auth is now the single source of truth for
    which providers a key is actually spent on, and server.py refuses the rest.
    """

    @pytest.mark.parametrize("provider", ["openai", "openrouter", "gemini", "anthropic", "xai"])
    def test_routed_providers_are_supported(self, provider: str) -> None:
        assert byok_provider_supported(provider)
        assert provider in BYOK_ROUTABLE_PROVIDERS

    @pytest.mark.parametrize("provider", ["", "nonsense"])
    def test_unrouted_providers_are_refused(self, provider: str) -> None:
        """Each of these would otherwise have been billed to the operator."""
        assert not byok_provider_supported(provider)

    def test_the_guard_normalizes_like_the_middleware(self) -> None:
        """server.py lowercases and strips before asking, so the guard must agree."""
        assert byok_provider_supported("OpenAI")
        assert byok_provider_supported("  openrouter  ")
        assert byok_provider_supported(" Anthropic ")
        assert byok_provider_supported("Gemini")

    def test_every_routable_provider_has_a_base_url(self) -> None:
        """A provider in the tuple with no URL would pass the guard and route nowhere."""
        from digigraph.llm_auth import _BYOK_BASE_URLS

        assert set(BYOK_ROUTABLE_PROVIDERS) == set(_BYOK_BASE_URLS)
        assert all(u.startswith("https://") for u in _BYOK_BASE_URLS.values())


@pytest.mark.unit
class TestByokGuardOverHttp:
    """The guard as a caller actually meets it: a 400 from the middleware.

    The class above pins the predicate; this pins the wiring. They are different
    failures — a correct predicate that server.py forgets to call still bills the
    operator. `/healthz` is used deliberately: it runs the middleware without
    reaching an LLM, so the test needs no network and no credentials.
    """

    def _client(self):
        from digigraph.server import app
        from fastapi.testclient import TestClient

        return TestClient(app)

    @pytest.mark.parametrize("provider", ["nonsense"])
    def test_an_unroutable_key_is_refused_not_silently_swallowed(self, provider: str) -> None:
        res = self._client().get(
            "/healthz", headers={"x-byok-key": "sk-secret", "x-byok-provider": provider}
        )
        assert res.status_code == 400, res.text
        body = res.json()
        assert "byok_provider_unsupported" in str(body)
        # The refusal must say what WOULD work, or the caller cannot act on it.
        assert "openai" in str(body) and "openrouter" in str(body)
        # And it must never echo the key back.
        assert "sk-secret" not in res.text

    @pytest.mark.parametrize("provider", ["gemini", "anthropic", "openrouter", "xai"])
    def test_model_required_for_non_openai(self, provider: str) -> None:
        res = self._client().get(
            "/healthz", headers={"x-byok-key": "sk-ok", "x-byok-provider": provider}
        )
        assert res.status_code == 400, res.text
        assert "byok_model_required" in str(res.json())

    @pytest.mark.parametrize(
        "provider,model",
        [
            ("openai", ""),
            ("openrouter", "openai/gpt-4o-mini"),
            ("gemini", "gemini-2.5-flash"),
            ("anthropic", "claude-sonnet-4-6"),
            ("xai", "grok-4-3"),
        ],
    )
    def test_a_routable_key_passes_through(self, provider: str, model: str) -> None:
        headers = {"x-byok-key": "sk-ok", "x-byok-provider": provider}
        if model:
            headers["x-byok-model"] = model
        res = self._client().get("/healthz", headers=headers)
        assert res.status_code == 200, res.text

    def test_no_byok_header_is_untouched(self) -> None:
        """The guard must only fire when a key is actually present."""
        assert self._client().get("/healthz").status_code == 200


@pytest.mark.unit
class TestByokCatalogLoad:
    """The catalog is loaded once at import time and fails loudly, not silently.

    DEVIATION FROM THE ORIGINAL TASK SPEC — see task-a2-report.md for detail:
    the originally-specified test drove this through
    ``importlib.reload(llm_auth)`` with ``monkeypatch.setattr(llm_auth,
    "_BYOK_CATALOG_PATH", ...)``. That pattern is self-contradictory against
    the loader's own (correct, and required) production behavior — a
    module-level constant unconditionally recomputed from ``Path(__file__)``
    on every exec — and was confirmed empirically, not just by inspection:
    the first ``importlib.reload`` inside ``pytest.raises`` recomputes the
    *real* catalog path before ``_load_byok_catalog`` ever sees the
    monkeypatched one, so the expected exception never fires. Making the
    module remember the monkeypatched path across reload (e.g. a
    ``globals().get(...)`` guard) fixes that, but then the very next line in
    the same test — the "restore the real module state" reload — reloads
    again while the monkeypatch is *still active* (monkeypatch only undoes
    at fixture teardown, after the test body returns) and raises the same
    exception a second time, uncaught, failing the test outright. Nothing in
    the module's own state can tell that second reload apart from the
    first. Both variants were run against this exact test file to confirm
    before choosing this replacement.

    So this class instead drives ``_load_byok_catalog`` directly — the exact
    function ``_BYOK_BASE_URLS``/``BYOK_MODEL_REQUIRED_PROVIDERS`` are built
    from at import time (see the unconditional module-level call right below
    its definition) — which exercises the identical fail-loud behavior
    without the reload/monkeypatch contradiction.
    """

    def test_missing_catalog_file_raises(self, tmp_path) -> None:
        from digigraph.llm_auth import _load_byok_catalog

        with pytest.raises(FileNotFoundError):
            _load_byok_catalog(tmp_path / "does-not-exist.json")

    def test_malformed_catalog_raises(self, tmp_path) -> None:
        from digigraph.llm_auth import _load_byok_catalog

        bad = tmp_path / "byok-providers.json"
        bad.write_text("not json", encoding="utf-8")
        with pytest.raises(ValueError):
            _load_byok_catalog(bad)


@pytest.mark.unit
class TestByokCatalogPathResolution:
    """``DIGI_CONFIG_PATH`` override for the catalog path (deploy distribution fix).

    ``_resolve_byok_catalog_path`` is a plain function of ``os.environ`` — unlike
    ``_BYOK_CATALOG_PATH`` (computed once at import), calling it fresh per-test
    sidesteps the reload/monkeypatch contradiction documented on
    ``TestByokCatalogLoad`` above.
    """

    def test_unset_env_resolves_to_repo_config(self, monkeypatch) -> None:
        """With no override, resolution must still land on the repo's real catalog —
        this is the path digigraph actually imports with in local dev/tests."""
        monkeypatch.delenv("DIGI_CONFIG_PATH", raising=False)
        from digigraph.llm_auth import _BYOK_CATALOG_PATH, _resolve_byok_catalog_path

        resolved = _resolve_byok_catalog_path()
        assert resolved == _REPO_ROOT / "config" / "byok-providers.json"
        assert resolved.exists()
        # And this is exactly what the module computed at import time.
        assert _BYOK_CATALOG_PATH == resolved

    def test_digi_config_path_override_wins(self, tmp_path, monkeypatch) -> None:
        """Set DIGI_CONFIG_PATH → the loader reads from THAT directory, not the repo default."""
        from digigraph.llm_auth import _load_byok_catalog, _resolve_byok_catalog_path

        override_dir = tmp_path / "custom-config"
        override_dir.mkdir()
        catalog = [{"id": "openai", "baseUrl": "https://example-override.test/v1"}]
        (override_dir / "byok-providers.json").write_text(json.dumps(catalog), encoding="utf-8")

        monkeypatch.setenv("DIGI_CONFIG_PATH", str(override_dir))
        resolved = _resolve_byok_catalog_path()
        assert resolved == override_dir / "byok-providers.json"
        assert resolved != _REPO_ROOT / "config" / "byok-providers.json"

        base_urls, _ = _load_byok_catalog(resolved)
        assert base_urls == {"openai": "https://example-override.test/v1"}

    def test_missing_file_still_raises_with_override_set(self, tmp_path, monkeypatch) -> None:
        """The fail-loud guarantee (#existing behavior) must survive the override path too."""
        from digigraph.llm_auth import _load_byok_catalog, _resolve_byok_catalog_path

        empty_dir = tmp_path / "empty-config"
        empty_dir.mkdir()
        monkeypatch.setenv("DIGI_CONFIG_PATH", str(empty_dir))
        resolved = _resolve_byok_catalog_path()
        with pytest.raises(FileNotFoundError):
            _load_byok_catalog(resolved)


@pytest.mark.unit
class TestByokCatalogVendoredCopy:
    """The infra/digichat-release vendored copy must never silently drift from the
    canonical repo-root catalog — that drift is exactly how #FIX-1 broke two of
    three real deploy targets (baked/mounted images shipping a stale or missing
    catalog while the repo-root copy moved on)."""

    def test_vendored_copy_matches_canonical_catalog(self) -> None:
        canonical = _REPO_ROOT / "config" / "byok-providers.json"
        vendored = _REPO_ROOT / "infra" / "digichat-release" / "config" / "byok-providers.json"
        assert canonical.exists(), canonical
        assert vendored.exists(), vendored
        assert json.loads(canonical.read_text(encoding="utf-8")) == json.loads(
            vendored.read_text(encoding="utf-8")
        )
