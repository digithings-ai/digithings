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
    byok_model_routes_elsewhere,
    byok_operator_model_routes_elsewhere,
    byok_provider_supported,
    byok_routable_model,
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
    def test_a_routable_key_passes_through(
        self, monkeypatch: pytest.MonkeyPatch, provider: str, model: str
    ) -> None:
        # The ("openai", "") row is a bound key with *no* model, so its verdict depends
        # on this deployment's default model (#2490). Left to the ambient config it
        # passes only because the repo-root YAML resolves to ``ollama/qwen3:8b``, whose
        # prefix is unregistered — an accident that would flip to a 400 the day someone
        # points local dev at OpenRouter. Pin a default the user's key would serve, so
        # the row asserts "routable keys pass" rather than "the dev config is cheap".
        monkeypatch.delenv("DIGI_PROJECT_CONFIG", raising=False)
        monkeypatch.delenv("DIGI_LLM_PROVIDER", raising=False)
        monkeypatch.setenv("DIGI_LLM_MODE", "test")
        monkeypatch.setenv("DIGI_LLM_MODEL", "gpt-4o-mini")
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
class TestByokCatalogValidation:
    """Strict per-entry validation (CWE-319 + coercion-bug hardening).

    Each defect here was independently confirmed by a live reproduction script
    in CodeRabbit's review of this catalog-loading rewrite: a plain
    ``dict.get()`` walk let a JSON string ``"false"`` for ``requiresModel``
    coerce to ``True`` (``bool("false") is True``), let a JSON ``null`` for
    ``id`` collide with a real provider literally named "none"
    (``str(None).lower() == "none"``), and accepted a non-``https://``
    ``baseUrl`` — which is where the user's own BYOK key gets sent
    (:func:`digigraph.llm_auth.push_byok_header`), so a plaintext ``http://``
    entry would transmit that key in cleartext.
    """

    def _write_catalog(self, tmp_path, entries: list) -> Path:
        path = tmp_path / "byok-providers.json"
        path.write_text(json.dumps(entries), encoding="utf-8")
        return path

    def test_duplicate_id_rejected(self, tmp_path) -> None:
        from digigraph.llm_auth import _load_byok_catalog

        catalog = self._write_catalog(
            tmp_path,
            [
                {"id": "openai", "baseUrl": "https://a.example/v1"},
                {"id": "openai", "baseUrl": "https://b.example/v1"},
            ],
        )
        with pytest.raises(ValueError, match="duplicate id"):
            _load_byok_catalog(catalog)

    def test_http_base_url_rejected(self, tmp_path) -> None:
        """CWE-319: an http:// baseUrl would send the user's BYOK key in cleartext."""
        from digigraph.llm_auth import _load_byok_catalog

        catalog = self._write_catalog(
            tmp_path, [{"id": "openai", "baseUrl": "http://insecure.example/v1"}]
        )
        with pytest.raises(ValueError):
            _load_byok_catalog(catalog)

    def test_non_https_scheme_rejected(self, tmp_path) -> None:
        from digigraph.llm_auth import _load_byok_catalog

        catalog = self._write_catalog(tmp_path, [{"id": "openai", "baseUrl": "file:///etc/passwd"}])
        with pytest.raises(ValueError):
            _load_byok_catalog(catalog)

    def test_non_boolean_requires_model_rejected(self, tmp_path) -> None:
        """Strict mode: a JSON string must not silently coerce (bool("false") is True)."""
        from digigraph.llm_auth import _load_byok_catalog

        catalog = self._write_catalog(
            tmp_path,
            [{"id": "openai", "baseUrl": "https://a.example/v1", "requiresModel": "false"}],
        )
        with pytest.raises(ValueError):
            _load_byok_catalog(catalog)

    def test_null_id_rejected(self, tmp_path) -> None:
        """str(None).lower() == "none" must not silently become a routable provider id."""
        from digigraph.llm_auth import _load_byok_catalog

        catalog = self._write_catalog(tmp_path, [{"id": None, "baseUrl": "https://a.example/v1"}])
        with pytest.raises(ValueError):
            _load_byok_catalog(catalog)

    def test_empty_id_rejected(self, tmp_path) -> None:
        from digigraph.llm_auth import _load_byok_catalog

        catalog = self._write_catalog(tmp_path, [{"id": "   ", "baseUrl": "https://a.example/v1"}])
        with pytest.raises(ValueError):
            _load_byok_catalog(catalog)

    def test_requires_model_omitted_defaults_false(self, tmp_path) -> None:
        """Backward compatible: an entry may omit requiresModel entirely (defaults False)."""
        from digigraph.llm_auth import _load_byok_catalog

        catalog = self._write_catalog(
            tmp_path, [{"id": "openai", "baseUrl": "https://a.example/v1"}]
        )
        base_urls, model_required = _load_byok_catalog(catalog)
        assert base_urls == {"openai": "https://a.example/v1"}
        assert model_required == frozenset()

    def test_http_catalog_via_digi_config_path_override_still_rejected(
        self, tmp_path, monkeypatch
    ) -> None:
        """The https-only guard applies on the DIGI_CONFIG_PATH override path too, not
        only the repo-default path — a self-hoster pointing at their own config dir
        gets the same protection."""
        from digigraph.llm_auth import _load_byok_catalog, _resolve_byok_catalog_path

        override_dir = tmp_path / "custom-config"
        override_dir.mkdir()
        catalog = [{"id": "openai", "baseUrl": "http://insecure-override.example/v1"}]
        (override_dir / "byok-providers.json").write_text(json.dumps(catalog), encoding="utf-8")

        monkeypatch.setenv("DIGI_CONFIG_PATH", str(override_dir))
        resolved = _resolve_byok_catalog_path()
        with pytest.raises(ValueError):
            _load_byok_catalog(resolved)


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


@pytest.mark.unit
class TestByokModelCannotRedirectTheBill:
    """``X-BYOK-Model`` is caller-supplied, so it must not choose whose key pays.

    The provider guard above asks "is this provider routable"; the model-required
    guard asks "did they send a model". Neither asks whether the model belongs to the
    provider that was declared, and for openai nothing else closes the gap: openai is
    absent from digillm's registry because its canonical model string is bare, so it
    is the one provider that adds no prefix of its own and therefore the one that can
    carry a foreign prefix all the way to :func:`digillm.get_client_for_model`. There
    the BYOK override is skipped (its base_url is api.openai.com, not the target's)
    and the client is built on the operator's env key instead.
    """

    @pytest.mark.parametrize(
        "provider,model",
        [
            ("openai", "gemini/gemini-2.5-flash"),
            ("openai", "xai/grok-4-3"),
            ("openai", "anthropic/claude-sonnet-4-20250514"),
            ("openai", "openrouter/openai/gpt-4o-mini"),
        ],
    )
    def test_a_foreign_prefix_is_detected(self, provider: str, model: str) -> None:
        """Each of these would otherwise be answered on an operator env key."""
        assert byok_model_routes_elsewhere(provider, model)

    @pytest.mark.parametrize(
        "provider,model",
        [
            ("openai", "gpt-4o-mini"),
            ("openai", "openai/gpt-4o-mini"),
            ("openai", "o4-mini"),
            # OpenRouter's whole product is vendor sub-slugs; rejecting these would
            # break the shipped digichat path, so the rule must not be prefix equality.
            ("openrouter", "openai/gpt-4o-mini"),
            ("openrouter", "anthropic/claude-sonnet-4"),
            ("openrouter", "google/gemini-2.0-flash"),
            ("openrouter", "openrouter/anthropic/claude-sonnet-4"),
            ("gemini", "gemini-2.5-flash"),
            ("gemini", "gemini/gemini-2.0-flash"),
            ("anthropic", "claude-sonnet-4-20250514"),
            ("xai", "grok-4-3"),
            # Not a hole: membership is case-sensitive on *both* sides of this
            # (see test_the_guard_and_the_router_read_one_registry), so an
            # uppercased prefix names no provider anywhere and lands on the
            # user's own key, not an operator one.
            ("openai", "GEMINI/gemini-2.5-flash"),
            ("openai", "OpenRouter/openai/gpt-4o-mini"),
        ],
    )
    def test_a_legitimate_model_is_not_flagged(self, provider: str, model: str) -> None:
        assert not byok_model_routes_elsewhere(provider, model)

    @pytest.mark.parametrize("model", ["GEMINI/gemini-2.5-flash", "OpenRouter/openai/gpt-4o"])
    def test_the_guard_and_the_router_read_one_registry(self, model: str) -> None:
        """What the guard lets through, the router must not route to an operator key.

        The guard tests membership with :func:`digillm.is_registered_provider`, which is
        plain case-sensitive dict membership; both prefix splitters (digillm's
        ``_parse_provider_prefix`` and model_config's) call that same predicate on the
        head they partition off, and neither lowercases first. So a miscased prefix is
        unknown to the router too: it parses to ``None``, falls to :func:`digillm.get_client`,
        and under BYOK that returns the *user's* key — a wrong-model error billed to them,
        never an operator key. Reading membership from the registry rather than
        re-implementing it is what makes the guard exact instead of approximate; this test
        fails the moment either side starts normalizing case on its own.
        """
        from digillm.client import _parse_provider_prefix as router_parse

        assert not byok_model_routes_elsewhere("openai", model)
        assert router_parse(byok_routable_model("openai", model)) == (None, model)

    def test_the_check_normalizes_like_the_middleware(self) -> None:
        assert byok_model_routes_elsewhere("OpenAI", "  gemini/gemini-2.5-flash  ")
        assert not byok_model_routes_elsewhere(" OpenRouter ", "anthropic/claude-sonnet-4")

    @pytest.mark.parametrize(
        "provider,model,expected",
        [
            ("gemini", "gemini-2.5-flash", "gemini/gemini-2.5-flash"),
            ("gemini", "gemini/gemini-2.0-flash", "gemini/gemini-2.0-flash"),
            ("openrouter", "anthropic/claude-sonnet-4", "openrouter/anthropic/claude-sonnet-4"),
            ("anthropic", "claude-sonnet-4-20250514", "anthropic/claude-sonnet-4-20250514"),
            ("xai", "grok-4-3", "xai/grok-4-3"),
            ("openai", "gpt-4o-mini", "gpt-4o-mini"),
            ("openai", "openai/gpt-4o-mini", "gpt-4o-mini"),
        ],
    )
    def test_routable_form_is_idempotent(self, provider: str, model: str, expected: str) -> None:
        """Applying it twice must not double a prefix — the catalog ships prefixed
        fallbacks (``gemini/gemini-2.0-flash``) and bare ones in the same file."""
        once = byok_routable_model(provider, model)
        assert once == expected
        assert byok_routable_model(provider, once) == expected

    @pytest.mark.parametrize("provider", list(BYOK_ROUTABLE_PROVIDERS))
    @pytest.mark.parametrize("depth", [0, 1, 2, 3, 4])
    def test_routable_form_strips_the_own_prefix_to_a_fixpoint(
        self, provider: str, depth: int
    ) -> None:
        """A stacked self-prefix must collapse, not merely shrink by one.

        This is the property the two doors rely on: ``byok_routable_model`` has to
        give the same answer whether or not ``_normalize_byok_model_slug`` already
        removed a ``provider/``. Turning the strip loop back into a single ``if``
        fails here at ``depth >= 2``, before it can fail as a silent 400-bypass.
        """
        stacked = f"{provider}/" * depth + "gemini/gemini-2.5-flash"
        assert byok_routable_model(provider, stacked) == byok_routable_model(
            provider, f"{provider}/" * (depth + 1) + "gemini/gemini-2.5-flash"
        )

    def test_every_catalog_fallback_model_is_self_consistent(self) -> None:
        """No model this product actually offers may be refused by the new 400.

        Every entry, not just the first: ``byokModelPresets(provider)`` in digichat's
        ``use-byok-key.ts`` is asserted equal to this file's ``fallbackModels`` by
        ``use-byok-key.catalog-parity.test.ts``, so covering the catalog covers exactly
        the set the terminal's model picker can send. A cross-component regression is
        otherwise invisible from Python, and ``normalizeOpenRouterModel`` — the only
        transform digichat applies on the way out — merely strips a leading
        ``openrouter/``; it never adds a prefix, so it cannot manufacture a foreign one.
        """
        catalog = json.loads((_REPO_ROOT / "config" / "byok-providers.json").read_text())
        for entry in catalog:
            for model in entry.get("fallbackModels") or []:
                assert not byok_model_routes_elsewhere(entry["id"], model), (
                    f"catalog fallback {model!r} for {entry['id']!r} would be refused"
                )


@pytest.mark.unit
class TestByokModelMismatchOverHttp:
    """The same invariant at the door the attacker actually knocks on."""

    def _client(self):
        from digigraph.server import app
        from fastapi.testclient import TestClient

        return TestClient(app)

    def test_a_foreign_model_is_refused_not_billed_to_the_operator(self) -> None:
        res = self._client().get(
            "/healthz",
            headers={
                "x-byok-key": "sk-secret",
                "x-byok-provider": "openai",
                "x-byok-model": "gemini/gemini-2.5-flash",
            },
        )
        assert res.status_code == 400, res.text
        assert "byok_model_provider_mismatch" in str(res.json())
        assert "sk-secret" not in res.text

    def test_the_shipped_openrouter_sub_slug_still_passes(self) -> None:
        """digichat sends exactly this; a prefix-equality rule would 400 it."""
        res = self._client().get(
            "/healthz",
            headers={
                "x-byok-key": "sk-ok",
                "x-byok-provider": "openrouter",
                "x-byok-model": "anthropic/claude-sonnet-4",
            },
        )
        assert res.status_code == 200, res.text

    @pytest.mark.parametrize("depth", [1, 2, 3, 4])
    def test_a_stacked_own_prefix_cannot_smuggle_a_foreign_model(self, depth: int) -> None:
        """``openai/openai/gemini/…`` must be refused exactly like ``gemini/…``.

        The middleware tests the *raw* header while the resolver tests the slug
        ``_normalize_byok_model_slug`` bound — one strip apart. With a single-strip
        ``byok_routable_model`` the two disagreed from ``depth == 2`` on: the
        middleware answered 200 because the head of ``openai/gemini/…`` is
        ``openai``, which is not a registered provider, and the resolver then
        dropped the slug anyway. A 200 that silently ignores the caller's model is
        not the contract the 400 advertises.
        """
        res = self._client().get(
            "/healthz",
            headers={
                "x-byok-key": "sk-secret",
                "x-byok-provider": "openai",
                "x-byok-model": "openai/" * depth + "gemini/gemini-2.5-flash",
            },
        )
        assert res.status_code == 400, res.text
        assert "byok_model_provider_mismatch" in str(res.json())
        assert "sk-secret" not in res.text

    @pytest.mark.parametrize("provider", list(BYOK_ROUTABLE_PROVIDERS))
    @pytest.mark.parametrize(
        "tail",
        [
            "gemini/gemini-2.5-flash",
            "anthropic/claude-sonnet-4",
            "xai/grok-4",
            "openrouter/auto",
            "gpt-4o-mini",
        ],
    )
    @pytest.mark.parametrize("depth", [0, 1, 2, 3])
    def test_both_doors_reach_the_same_verdict(self, provider: str, tail: str, depth: int) -> None:
        """The middleware and the resolver must never disagree about one header.

        Walked through the real ingest path rather than a re-implementation of the
        normalizer: ``push_byok_header`` is the only production writer of
        ``_byok_model_override``, so ``get_byok_model_override()`` is exactly the
        string the resolver will test.
        """
        raw = f"{provider}/" * depth + tail
        at_middleware = byok_model_routes_elsewhere(provider, raw)
        tok = push_byok_header(_byok_request(key="sk-ok", provider=provider, model=raw))
        try:
            bound = get_byok_model_override()
        finally:
            pop_byok(tok)
        assert bound is not None
        at_resolver = byok_model_routes_elsewhere(provider, bound)
        assert at_middleware == at_resolver, (
            f"{provider!r} + {raw!r}: middleware says {at_middleware}, "
            f"resolver sees {bound!r} and says {at_resolver}"
        )


@pytest.mark.unit
class TestByokModelOverrideResolution:
    """``_apply_byok_model_override`` is the second door: in-process callers."""

    def _resolve(self, provider: str, model: str, resolved: str) -> str:
        from digigraph.model_config import _apply_byok_model_override

        tok = push_byok_header(_byok_request(key="sk-test", provider=provider, model=model))
        try:
            return _apply_byok_model_override(resolved)
        finally:
            pop_byok(tok)

    def test_a_foreign_model_is_discarded(self) -> None:
        """The poisoned model must not come back out; the request lands where it
        would have landed had the header been absent."""
        assert self._resolve("openai", "gemini/gemini-2.5-flash", "gpt-4o-mini") == "gpt-4o-mini"

    @pytest.mark.parametrize(
        "provider,model,resolved,expected",
        [
            ("openai", "gpt-4o", "gpt-4o-mini", "gpt-4o"),
            ("gemini", "gemini-2.5-flash", "gpt-4o-mini", "gemini/gemini-2.5-flash"),
            ("xai", "grok-4-3", "gpt-4o-mini", "xai/grok-4-3"),
            (
                "anthropic",
                "claude-sonnet-4-20250514",
                "gpt-4o-mini",
                "anthropic/claude-sonnet-4-20250514",
            ),
            (
                "openrouter",
                "anthropic/claude-sonnet-4",
                "gpt-4o-mini",
                "openrouter/anthropic/claude-sonnet-4",
            ),
        ],
    )
    def test_a_legitimate_model_still_wins(
        self, provider: str, model: str, resolved: str, expected: str
    ) -> None:
        """Replacing the per-provider ladder must not change any routable answer."""
        assert self._resolve(provider, model, resolved) == expected

    def test_no_byok_leaves_the_resolved_model_alone(self) -> None:
        from digigraph.model_config import _apply_byok_model_override

        assert _apply_byok_model_override("gpt-4o-mini") == "gpt-4o-mini"


def _pin_operator_default(monkeypatch: pytest.MonkeyPatch, model: str) -> None:
    """Pin this deployment's default model and prove the pin took.

    The repo-root ``config/model_modes.yaml`` resolves every tier to ``ollama/qwen3:8b``,
    whose prefix is *not* in digillm's registry — so a test that inherits it answers
    "fine" for every provider and would pass no matter what the predicate did. Pinning
    is what makes these tests mean something.

    The ``operator_default_model()`` assertion is not decoration: ``_resolve_explicit_model``
    composes ``DIGI_LLM_PROVIDER`` with ``DIGI_LLM_MODEL``, so a stray provider in the
    ambient environment would re-prefix the pin and quietly change which branch is under
    test. Assert the string first, then the verdict.
    """
    from digigraph.model_config import operator_default_model

    monkeypatch.delenv("DIGI_PROJECT_CONFIG", raising=False)
    monkeypatch.delenv("DIGI_LLM_PROVIDER", raising=False)
    monkeypatch.setenv("DIGI_LLM_MODE", "test")
    monkeypatch.setenv("DIGI_LLM_MODEL", model)
    assert operator_default_model() == model


@pytest.mark.unit
class TestOperatorDefaultCannotBillTheOperator:
    """A bound key with *no* ``X-BYOK-Model`` must be spent or refused — never idled.

    ``TestByokModelCannotRedirectTheBill`` covers the model the caller *sent*. This
    covers the model they didn't: when the header is absent, digigraph falls back to
    the deployment's own default, and on the shipped release config that default is an
    ``openrouter/…`` string served by the operator's ``OPENROUTER_API_KEY``. The user's
    key is accepted, displayed as active, and never spent — the same mis-billing as a
    foreign header, reached by omission instead of by input (#2490).
    """

    def test_the_shipped_release_config_is_exactly_this_bug(self) -> None:
        """Encode the deployment, not just the predicate.

        An env-pinned test proves the rule; this proves the rule fires on the config
        digichat actually ships, and it keeps proving it if someone edits the dev
        config out from under the tests above.
        """
        import yaml

        cfg = yaml.safe_load(
            (_REPO_ROOT / "infra" / "digichat-release" / "config" / "model_modes.yaml").read_text(
                encoding="utf-8"
            )
        )
        defaults = cfg["defaults"]
        assert defaults, "release config must pin the tier defaults this test reasons about"
        for tier, model in defaults.items():
            assert byok_operator_model_routes_elsewhere("openai", model), (
                f"release default {tier}={model!r} no longer reproduces #2490 — if the "
                "release config moved to a bare model this assertion should be inverted, "
                "not deleted"
            )

    def test_normalizing_the_operator_default_would_answer_the_wrong_question(self) -> None:
        """Why this is a second entry point rather than a reuse.

        ``byok_model_routes_elsewhere`` normalizes through ``byok_routable_model`` first,
        which is right for a caller-supplied header because the resolver really does route
        the normalized form. For a *registered* provider that normalization re-prefixes to
        the provider itself, so the head always equals the declared provider and the answer
        is unconditionally ``False`` — including for a default served by someone else.
        """
        provider, operator_default = "openrouter", "gemini/gemini-2.5-flash"
        assert not byok_model_routes_elsewhere(provider, operator_default)
        assert byok_operator_model_routes_elsewhere(provider, operator_default)

    @pytest.mark.parametrize(
        "provider,default_model",
        [
            ("openai", "openrouter/deepseek/deepseek-chat"),
            ("openai", "openrouter/google/gemini-2.5-flash"),
            ("openai", "gemini/gemini-2.5-flash"),
            ("openai", "xai/grok-4-3"),
            ("openai", "anthropic/claude-sonnet-4-20250514"),
            ("openrouter", "gemini/gemini-2.5-flash"),
            ("gemini", "openrouter/deepseek/deepseek-chat"),
        ],
    )
    def test_a_default_served_by_another_provider_is_detected(
        self, provider: str, default_model: str
    ) -> None:
        assert byok_operator_model_routes_elsewhere(provider, default_model)

    @pytest.mark.parametrize(
        "provider,default_model",
        [
            # Bare: no prefix to route on, so the BYOK client the override installed
            # serves it — the user's key pays, which is the whole point.
            ("openai", "gpt-4o-mini"),
            ("openai", "o4-mini"),
            # ollama/ and ollama-cloud/ are absent from digillm's registry: local dev
            # and the repo-root config must not start 400ing every BYOK request.
            ("openai", "ollama/qwen3:8b"),
            ("openai", "ollama-cloud/qwen3-coder:480b"),
            # The default already belongs to the declared provider.
            ("openrouter", "openrouter/deepseek/deepseek-chat"),
            ("gemini", "gemini/gemini-2.5-flash"),
            ("xai", "xai/grok-4-3"),
            ("anthropic", "anthropic/claude-sonnet-4-20250514"),
        ],
    )
    def test_a_default_the_users_key_would_serve_is_left_alone(
        self, provider: str, default_model: str
    ) -> None:
        assert not byok_operator_model_routes_elsewhere(provider, default_model)

    def test_the_refusal_names_the_provider_and_nothing_else(self) -> None:
        """The slug is the operator's configuration and the key is the caller's secret.

        Naming the model buys an anonymous caller no remediation — the fix is the same
        either way — and echoing the key is the failure every other BYOK refusal is
        already tested against.
        """
        from digigraph.llm_auth import byok_default_model_refusal

        msg = byok_default_model_refusal("openai")
        assert "openai" in msg
        assert "openrouter" not in msg
        assert "deepseek" not in msg
        assert "X-BYOK-Model" in msg, "a refusal the caller cannot act on is just a wall"


@pytest.mark.unit
class TestOperatorDefaultRefusalAtTheResolver:
    """Door 2: ``_apply_byok_model_override``, for callers that never met the middleware."""

    def _resolve(self, provider: str, model: str, resolved: str) -> str:
        from digigraph.model_config import _apply_byok_model_override

        tok = push_byok_header(_byok_request(key="sk-secret", provider=provider, model=model))
        try:
            return _apply_byok_model_override(resolved)
        finally:
            pop_byok(tok)

    def test_no_header_plus_a_foreign_default_is_refused_not_billed(self) -> None:
        with pytest.raises(ValueError) as exc:
            self._resolve("openai", "", "openrouter/deepseek/deepseek-chat")
        assert "openai" in str(exc.value)
        assert "sk-secret" not in str(exc.value)
        assert "deepseek" not in str(exc.value)

    def test_a_discarded_foreign_header_lands_where_absence_lands(self) -> None:
        """The discard path must not hand back the operator's default.

        ``return resolved`` there is the same mis-billing this class exists to refuse,
        reached by a foreign header on an in-process caller instead of by omission. So
        the discard falls through to the no-header branch and is refused with it.
        """
        with pytest.raises(ValueError):
            self._resolve("openai", "gemini/gemini-2.5-flash", "openrouter/deepseek/deepseek-chat")

    def test_a_discarded_foreign_header_still_passes_a_servable_default(self) -> None:
        """Falling through must not turn every discard into a refusal."""
        assert self._resolve("openai", "gemini/gemini-2.5-flash", "gpt-4o-mini") == "gpt-4o-mini"

    @pytest.mark.parametrize(
        "provider,resolved",
        [
            ("openai", "gpt-4o-mini"),
            ("openai", "ollama/qwen3:8b"),
            ("openrouter", "openrouter/deepseek/deepseek-chat"),
        ],
    )
    def test_a_default_the_key_would_serve_passes_through_untouched(
        self, provider: str, resolved: str
    ) -> None:
        assert self._resolve(provider, "", resolved) == resolved

    def test_an_explicit_model_still_beats_the_default(self) -> None:
        """The refusal is for the *absence* of a choice, not for a foreign default."""
        assert self._resolve("openai", "gpt-4o", "openrouter/deepseek/deepseek-chat") == "gpt-4o"

    def test_the_refusal_needs_a_bound_key(self) -> None:
        """No BYOK, no opinion: the operator's own default is the operator's business."""
        from digigraph.model_config import _apply_byok_model_override

        assert (
            _apply_byok_model_override("openrouter/deepseek/deepseek-chat")
            == "openrouter/deepseek/deepseek-chat"
        )

    def test_get_model_for_mode_refuses_through_the_same_door(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The wiring, not just the helper: the resolver every caller actually calls."""
        from digigraph.model_config import get_model_for_mode

        _pin_operator_default(monkeypatch, "openrouter/deepseek/deepseek-chat")
        tok = push_byok_header(_byok_request(key="sk-secret", provider="openai"))
        try:
            with pytest.raises(ValueError):
                get_model_for_mode()
        finally:
            pop_byok(tok)

    def test_operator_default_model_ignores_a_bound_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The split exists so the middleware's question is structurally independent.

        If ``operator_default_model`` applied the override it would raise here, and the
        middleware's check would depend on running before ``push_byok_header`` — a
        credential check resting on middleware ordering.
        """
        from digigraph.model_config import operator_default_model

        _pin_operator_default(monkeypatch, "openrouter/deepseek/deepseek-chat")
        tok = push_byok_header(_byok_request(key="sk-secret", provider="openai"))
        try:
            assert operator_default_model() == "openrouter/deepseek/deepseek-chat"
        finally:
            pop_byok(tok)


@pytest.mark.unit
class TestOperatorDefaultRefusalOverHttp:
    """Door 1: the 400 a digichat user actually meets, before the key is ever bound."""

    def _client(self):
        from digigraph.server import app
        from fastapi.testclient import TestClient

        return TestClient(app)

    def _get(self, provider: str = "openai", model: str = ""):
        headers = {"x-byok-key": "sk-secret", "x-byok-provider": provider}
        if model:
            headers["x-byok-model"] = model
        return self._client().get("/healthz", headers=headers)

    def test_a_key_with_no_model_is_refused_when_the_default_bills_elsewhere(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _pin_operator_default(monkeypatch, "openrouter/deepseek/deepseek-chat")
        res = self._get()
        assert res.status_code == 400, res.text
        assert "byok_default_model_provider_mismatch" in str(res.json())
        assert "sk-secret" not in res.text
        assert "deepseek" not in res.text

    def test_naming_a_model_is_the_remediation_the_refusal_advertises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A 400 whose instruction does not clear it is worse than no 400."""
        _pin_operator_default(monkeypatch, "openrouter/deepseek/deepseek-chat")
        assert self._get(model="gpt-4o-mini").status_code == 200

    @pytest.mark.parametrize("default_model", ["gpt-4o-mini", "ollama/qwen3:8b"])
    def test_a_default_the_key_would_serve_still_passes(
        self, monkeypatch: pytest.MonkeyPatch, default_model: str
    ) -> None:
        _pin_operator_default(monkeypatch, default_model)
        assert self._get().status_code == 200

    @pytest.mark.parametrize("provider", ["gemini", "anthropic", "openrouter", "xai"])
    def test_model_required_answers_first_for_every_registered_provider(
        self, monkeypatch: pytest.MonkeyPatch, provider: str
    ) -> None:
        """The new code is openai-only by construction, and must stay that way.

        Every provider in digillm's registry is ``requiresModel: true`` in the catalog,
        so a key with no model is already refused with ``byok_model_required`` — a
        property of the *provider*, which digichat's own catalog knows and enforces
        client-side. Answering the new code there would tell the operator their frontend
        is broken when it is not. Reordering the middleware breaks that silently, so it
        is pinned here rather than left to reading order.
        """
        _pin_operator_default(monkeypatch, "openrouter/deepseek/deepseek-chat")
        res = self._get(provider=provider)
        assert res.status_code == 400, res.text
        assert "byok_model_required" in str(res.json())
        assert "byok_default_model_provider_mismatch" not in str(res.json())

    def test_a_server_side_resolution_failure_does_not_blame_the_caller(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``llm_mode: free`` with no pin makes ``operator_default_model`` raise.

        That is a server misconfiguration, and converting it into a 400 about the
        caller's key would send every BYOK user chasing their own credentials. The
        middleware fails open; the invariant survives because the resolver re-derives
        the same verdict on the same string and refuses there.
        """
        monkeypatch.delenv("DIGI_PROJECT_CONFIG", raising=False)
        monkeypatch.delenv("DIGI_LLM_PROVIDER", raising=False)
        monkeypatch.delenv("DIGI_LLM_MODEL", raising=False)
        monkeypatch.setenv("DIGI_LLM_MODE", "free")
        from digigraph.model_config import operator_default_model

        with pytest.raises(ValueError):
            operator_default_model()
        assert self._get().status_code == 200
