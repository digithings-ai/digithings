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
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

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

import digillm
from digillm import client as client_mod
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

    def test_example_is_stripped_before_it_reaches_user_facing_copy(self, tmp_path: Path) -> None:
        """``_id_non_empty`` stripped; this validator rejected blanks without stripping.

        The asymmetry was user-visible because this field is quoted verbatim into a
        refusal: a padded ``"  grok-4-3  "`` rendered as ``(e.g.   grok-4-3  )``. Not
        the *only* such field — entry ``id``s reach user copy the same way via
        ``byok_provider_unsupported`` — but the only one whose validator did not strip.
        """
        from digigraph.llm_auth import _load_byok_catalog

        catalog = self._write_catalog(
            tmp_path,
            [
                {
                    "id": "xai",
                    "baseUrl": "https://api.x.ai/v1",
                    "fallbackModels": ["  grok-4-3  "],
                }
            ],
        )
        _, _, examples = _load_byok_catalog(catalog)
        assert examples["xai"] == "grok-4-3"

    @pytest.mark.parametrize("bad", [None, "grok-4-3", [""], ["   "], [123], 7])
    def test_a_malformed_example_list_does_not_crash_startup(
        self, tmp_path: Path, bad: object
    ) -> None:
        """Routing survives a bad parenthetical — it did not have to before.

        Every other field in this entry is fail-loud because a bad value breaks
        routing. ``fallbackModels`` cannot: the refusal just drops its ``(e.g. …)``.
        And this key was an *ignored extra* before it was typed, so an operator
        catalog under ``DIGI_CONFIG_PATH`` carrying ``fallbackModels: null`` imported
        fine and would otherwise have begun crashing digigraph at import.
        """
        from digigraph.llm_auth import _load_byok_catalog

        catalog = self._write_catalog(
            tmp_path, [{"id": "xai", "baseUrl": "https://api.x.ai/v1", "fallbackModels": bad}]
        )
        base_urls, model_required, examples = _load_byok_catalog(catalog)
        assert base_urls == {"xai": "https://api.x.ai/v1"}, "routing must be unaffected"
        assert "xai" not in examples, "an unusable example must be dropped, not rendered"

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
        base_urls, model_required, examples = _load_byok_catalog(catalog)
        assert base_urls == {"openai": "https://a.example/v1"}
        assert model_required == frozenset()
        # fallbackModels is optional on the same terms: an entry without one routes,
        # and byok_default_model_refusal simply drops its example parenthetical.
        assert examples == {}

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

        base_urls, _, _ = _load_byok_catalog(resolved)
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

    def test_the_refusal_names_the_provider_and_no_operator_slug(self) -> None:
        """The *operator's* slug is their configuration and the key is the caller's secret.

        Naming the operator's model buys an anonymous caller no remediation — the fix is
        the same either way — and echoing the key is the failure every other BYOK refusal
        is already tested against. The catalog example the message does name is public
        and is asserted separately below.
        """
        from digigraph.llm_auth import byok_default_model_refusal

        msg = byok_default_model_refusal("openai")
        assert "openai" in msg
        assert "openrouter" not in msg
        assert "deepseek" not in msg
        assert "X-BYOK-Model" in msg, "a refusal the caller cannot act on is just a wall"

    # Derived, not hardcoded: a hardcoded list is the dominant idiom in this file, but
    # this test is the *only* JSON-to-refusal drift guard, so a provider added to
    # ``config/byok-providers.json`` later must not silently escape it. Verified: adding
    # a sixth provider whose ``fallbackModels[0]`` is blank leaves a hardcoded list green
    # while the refusal advertises ``[1]`` and the UI still shows ``[0]``. What it does
    # *not* assert is that an example exists at all: a provider may declare no
    # ``fallbackModels``, and the branch below checks that case for consistency instead.
    @pytest.mark.parametrize("provider", list(BYOK_ROUTABLE_PROVIDERS))
    def test_the_example_is_a_model_the_named_provider_declares(self, provider: str) -> None:
        """Send back exactly what the refusal suggested and the gate must let it through.

        This is the assertion the message failed before: it offered ``gpt-4o-mini`` to
        every provider, so a caller on any of the other four who followed it verbatim
        was told to send a model their own key does not serve. Only ``openai`` — one of
        five — was ever given actionable advice; openrouter counts among the four
        because its own entry is the prefixed ``openai/gpt-4o-mini``, not the bare slug.

        Checked against the catalog rather than through ``byok_model_routes_elsewhere``,
        which cannot see this class of error: that predicate only rejects a *prefixed*
        foreign slug, so it answers "fine" for a bare ``gpt-4o-mini`` asked about
        anthropic. Catalog membership is the property that actually distinguishes them
        (verified: a hardcoded example fails this for four of the five providers).
        """
        import re

        from digigraph.llm_auth import (
            _resolve_byok_catalog_path,
            byok_default_model_refusal,
            byok_model_routes_elsewhere,
            byok_routable_model,
        )

        catalog = json.loads(_resolve_byok_catalog_path().read_text(encoding="utf-8"))
        # Keyed normalized, valued *raw* — deliberately asymmetric. The key mirrors
        # ``_id_non_empty``, so a padded or upper-case catalog id gives a diagnosable
        # assertion here instead of a bare ``KeyError`` on the normalized ``provider``
        # (the TS side already rejects such an id: catalog-parity compares raw ids).
        # The values stay raw because the UI is pinned to raw JSON —
        # use-byok-key.catalog-parity.test.ts:82 asserts
        # ``toEqual(entry.fallbackModels)`` with no trimming, and digichat offers
        # ``byokModelPresets(provider)[0]``. Normalizing them would compare the
        # loader's cleaned[0] against its own cleaned[0] — the loader agreeing with
        # itself — and would pass on a catalog padded in *both* copies, the one case
        # where the UI really does render padding the refusal has stripped off.
        served = {e["id"].strip().lower(): e.get("fallbackModels", []) for e in catalog}

        msg = byok_default_model_refusal(provider)
        # ``fallbackModels`` is optional by design — the loader tolerates a missing or
        # empty list (test_a_malformed_example_list_does_not_crash_startup pins that),
        # and the refusal then just omits its parenthetical. Deriving the parametrize
        # from the catalog made that case reachable here, so assert the *consistent*
        # shape rather than failing on ``assert match``.
        if not served[provider]:
            assert "(e.g. " not in msg, (
                f"{provider} declares no fallbackModels, yet the refusal invents an example: {msg}"
            )
            assert "X-BYOK-Model" in msg, "a refusal the caller cannot act on is just a wall"
            return
        match = re.search(r"\(e\.g\. (.+?)\)", msg)
        assert match, (
            f"no example offered to {provider}: {msg} — raw fallbackModels is "
            f"{served[provider]!r}; the loader drops blank entries, so an all-blank list "
            f"leaves the refusal no example while looking non-empty here"
        )
        example = match.group(1)
        assert example in served[provider], (
            f"{provider} was told to send {example!r}, which is not in its own catalog entry"
        )
        # Index, not just membership: mutating the loader to ``fallbackModels[-1]``
        # left every test here green, while llm_auth.py's own comment claims the
        # refusal names the model the UI offers first — digichat renders
        # ``byokModelPresets(provider)[0]`` (byok-cli-flow.tsx:594), and
        # use-byok-key.catalog-parity.test.ts pins that array to this file with
        # toEqual (order included). Pinning index 0 here is the last link of that
        # chain; the membership assertion alone could not tell index 0 from any other.
        assert example == served[provider][0], (
            f"{provider} was offered {example!r}, but the UI offers "
            f"{served[provider][0]!r} first — the refusal and the UI have drifted"
        )
        # And it clears the BYOK gate, so following the refusal verbatim works.
        assert not byok_model_routes_elsewhere(provider, example)
        assert byok_routable_model(provider, example)

    @pytest.mark.parametrize("provider", ["openai", "anthropic", "gemini", "xai", "openrouter"])
    def test_no_indefinite_article_has_to_agree_with_a_provider_id(self, provider: str) -> None:
        """The old ``a {provider} model`` ran for all five and read wrong for four.

        ``a openai``, ``a anthropic``, ``a xai``, ``a openrouter`` — only ``a gemini``
        scans. (``a anthropic model`` was the literal output for anthropic alone.)

        Pinning the "a model served by <provider>" phrasing rather than a vowel
        heuristic: the ids are not English words (``xai`` reads "ex-AI", so no
        first-letter rule gets it right) and no phrasing that needs an article can.
        """
        from digigraph.llm_auth import byok_default_model_refusal

        assert f"a {provider}" not in byok_default_model_refusal(provider)

    def test_a_provider_with_no_catalog_example_still_gets_an_actionable_refusal(
        self, monkeypatch
    ) -> None:
        """fallbackModels is optional, and no example beats a wrong one."""
        from digigraph import llm_auth

        monkeypatch.setattr(llm_auth, "_BYOK_MODEL_EXAMPLES", {})
        msg = llm_auth.byok_default_model_refusal("openai")
        assert "e.g." not in msg
        assert "X-BYOK-Model" in msg


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
        middleware fails open, which is all this test pins: the probe answers 200 while
        ``operator_default_model`` itself still raises. The billing invariant is held
        elsewhere on this path — by that same raise surfacing out of
        ``get_model_for_mode``, not by a second verdict reached inside the resolver.
        """
        monkeypatch.delenv("DIGI_PROJECT_CONFIG", raising=False)
        monkeypatch.delenv("DIGI_LLM_PROVIDER", raising=False)
        monkeypatch.delenv("DIGI_LLM_MODEL", raising=False)
        monkeypatch.setenv("DIGI_LLM_MODE", "free")
        from digigraph.model_config import operator_default_model

        with pytest.raises(ValueError):
            operator_default_model()
        assert self._get().status_code == 200


@pytest.mark.unit
class TestOperatorDefaultLadderHasOneCopy:
    """The middleware's verdict and ``digi llm-settings`` must name the same model.

    ``operator_default_model`` and ``effective_llm_settings`` used to run the same
    fallback ladder in two copies (default_model → defaults[mode] → defaults['test']
    → ``gpt-4o-mini``). ``effective_llm_settings`` cannot simply call the former —
    it also reports ``provider`` / ``api_key_env`` / ``source`` — so the shared part
    is extracted into ``_fallback_model_for_mode``. That extraction is invisible at
    runtime, so re-duplicating it would go unnoticed; this pins the consequence
    instead. Drift here means the BYOK middleware refuses (or allows) a request on a
    model the operator's own diagnostic says is not in use, on a credential path.
    """

    @staticmethod
    def _fallback_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, yaml_text: str) -> None:
        """Reach the ladder: no explicit pin, so ``_resolve_explicit_model`` returns None."""
        monkeypatch.delenv("DIGI_PROJECT_CONFIG", raising=False)
        monkeypatch.delenv("DIGI_LLM_PROVIDER", raising=False)
        monkeypatch.delenv("DIGI_LLM_MODEL", raising=False)
        monkeypatch.delenv("DIGI_MODEL_MODES_FILE", raising=False)
        (tmp_path / "model_modes.yaml").write_text(yaml_text)
        monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))

    @pytest.mark.parametrize(
        ("yaml_text", "expected", "expected_source"),
        [
            # default_model wins outright.
            (
                "default_model: openrouter/deepseek/deepseek-chat\n",
                "openrouter/deepseek/deepseek-chat",
                "model_modes.default_model",
            ),
            # default_model outranks defaults[mode] when both are present. Pinned
            # separately because a copy that consulted ``defaults`` first would still
            # agree with the other entry point on every single-rung fixture.
            (
                "default_model: gemini/gemini-2.5-pro\n"
                "defaults:\n  medium: openrouter/qwen/qwen3-next-80b\n",
                "gemini/gemini-2.5-pro",
                "model_modes.default_model",
            ),
            # defaults[mode] — the shape the shipped release config actually has.
            (
                "defaults:\n  medium: openrouter/qwen/qwen3-next-80b\n",
                "openrouter/qwen/qwen3-next-80b",
                "model_modes",
            ),
            # defaults[mode] outranks defaults['test'] when both are present. Without
            # this rung an inverted copy passes: every other fixture sets one key, so
            # ``get(mode) or get("test")`` and ``get("test") or get(mode)`` agree.
            (
                "defaults:\n  medium: openrouter/qwen/qwen3-next-80b\n"
                "  test: gemini/gemini-2.5-flash\n",
                "openrouter/qwen/qwen3-next-80b",
                "model_modes",
            ),
            # defaults['test'] as the cross-mode fallback.
            (
                "defaults:\n  test: gemini/gemini-2.5-flash\n",
                "gemini/gemini-2.5-flash",
                "model_modes",
            ),
            # No usable entry at all — the hard floor.
            ("defaults: {}\n", "gpt-4o-mini", "default"),
        ],
    )
    def test_both_entry_points_resolve_the_same_model(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        yaml_text: str,
        expected: str,
        expected_source: str,
    ) -> None:
        from digigraph.model_config import effective_llm_settings, operator_default_model

        self._fallback_env(monkeypatch, tmp_path, yaml_text)
        monkeypatch.setenv("DIGI_LLM_MODE", "medium")
        assert operator_default_model() == expected
        settings = effective_llm_settings()
        assert settings["model"] == expected
        # The helper returns ``(model, source_label)`` and only ``effective_llm_settings``
        # reports the label, so a re-duplication that got the rung right but mislabelled
        # it would be invisible above: ``digi llm-settings`` would name the right model
        # and lie about where it came from.
        assert settings["source"] == expected_source

    def test_both_entry_points_refuse_free_mode_without_a_pin(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """``defaults.free`` is access policy, never a slug — so neither may invent one.

        Pinned on both because a copy that answered here would hand the middleware a
        model in a mode where the deployment has deliberately declined to name one.
        """
        from digigraph.model_config import effective_llm_settings, operator_default_model

        self._fallback_env(monkeypatch, tmp_path, "defaults:\n  free: openrouter/some/model:free\n")
        monkeypatch.setenv("DIGI_LLM_MODE", "free")
        with pytest.raises(ValueError):
            operator_default_model()
        with pytest.raises(ValueError):
            effective_llm_settings()


@pytest.mark.unit
class TestByokSurvivesIntoTheStreamingWorker:
    """The binding has to reach the code that spends the key, not just the request.

    ``/v1/chat/completions`` with ``stream=true`` runs the workflow on a worker
    thread. A bare ``threading.Thread`` starts with an empty context, so all three
    BYOK bindings read as their defaults inside it and the operator's key pays --
    accepted, shown as active, never spent, which is exactly what the middleware's
    ``byok_model_provider_mismatch`` refusal exists to prevent. The classes above
    pin the predicate and the middleware; this pins the one hop between them.

    Measured, not assumed: on the unfixed code the worker sees ``None`` for all
    three while the spawning frame still holds them, so the fix has something live
    to copy.
    """

    def _run(self, monkeypatch, provider: str, model: str) -> dict:
        from fastapi.testclient import TestClient

        from digigraph import server as srv
        from tests.digi_test_jwt import auth_headers

        seen: dict = {}

        def recording_worker(workflow_req, event_queue, cancel_event):
            seen["dg"] = get_byok_override()
            seen["model"] = get_byok_model_override()
            seen["llm"] = digillm_get_byok()
            event_queue.put(("content", "ok"))
            event_queue.put(("done",))

        monkeypatch.setattr(srv, "run_digigraph_workflow_streaming", recording_worker)

        headers = {"x-byok-key": "sk-probe", "x-byok-provider": provider}
        if model:
            headers["x-byok-model"] = model
        res = TestClient(srv.app, headers=auth_headers()).post(
            "/v1/chat/completions",
            headers=headers,
            json={
                "model": "digigraph-rag",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
            },
        )
        assert res.status_code == 200, res.text
        assert seen, "the streaming worker never ran"
        return seen

    def test_the_worker_sees_the_users_key_not_the_operators(self, monkeypatch) -> None:
        seen = self._run(monkeypatch, "openrouter", "openai/gpt-4o-mini")
        assert seen["dg"] == ("sk-probe", "openrouter")
        assert seen["llm"] == ("sk-probe", "https://openrouter.ai/api/v1")

    def test_the_worker_sees_the_users_model(self, monkeypatch) -> None:
        """Without this the user's key pays for the *operator's* default model."""
        assert self._run(monkeypatch, "openrouter", "openai/gpt-4o-mini")["model"] == (
            "openai/gpt-4o-mini"
        )

    def test_openai_byok_carries_over_with_no_model_header(self, monkeypatch) -> None:
        """openai is the one provider that may omit X-BYOK-Model; the key must
        still cross the thread boundary."""
        seen = self._run(monkeypatch, "openai", "")
        assert seen["dg"] == ("sk-probe", "openai")
        assert seen["llm"] == ("sk-probe", "https://api.openai.com/v1")
        assert seen["model"] is None

    def test_no_byok_header_leaves_the_worker_unbound(self, monkeypatch) -> None:
        """Copying the context must not invent a binding where the caller sent none."""
        from fastapi.testclient import TestClient

        from digigraph import server as srv
        from tests.digi_test_jwt import auth_headers

        seen: dict = {}

        def recording_worker(workflow_req, event_queue, cancel_event):
            seen["dg"] = get_byok_override()
            seen["llm"] = digillm_get_byok()
            event_queue.put(("done",))

        monkeypatch.setattr(srv, "run_digigraph_workflow_streaming", recording_worker)
        res = TestClient(srv.app, headers=auth_headers()).post(
            "/v1/chat/completions",
            json={
                "model": "digigraph-rag",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
            },
        )
        assert res.status_code == 200, res.text
        assert seen == {"dg": None, "llm": None}


@pytest.mark.unit
class TestTheStreamingWorkerDoesNotKeepTheKey:
    """Copying the context must not outlive the request that filled it.

    The worker's copy is taken while the request is open, but the thread is neither
    daemonic nor joined and ``byok_header_context``'s ``finally`` runs ``pop_byok``
    as soon as the response starts streaming. A copy is a snapshot, not a view, so
    that reset clears the parent and leaves the worker holding the user's plaintext
    key -- twice over, digigraph's record and digillm's -- for as long as the thread
    lives. That falsifies the middleware's own "for the duration of the request
    only" contract, so the worker clears its own copy in its ``finally``.

    Observed from inside the worker's context, which is the only place the copy is
    readable: the parent's values prove nothing about the copy.
    """

    def _observe(self, monkeypatch, *, worker_raises: bool) -> dict:
        import threading

        from fastapi.testclient import TestClient

        from digigraph import llm_auth
        from digigraph import server as srv
        from tests.digi_test_jwt import auth_headers

        seen: dict = {}
        cleared = threading.Event()
        real_clear = llm_auth.clear_byok_bindings

        def recording_clear() -> None:
            """Stand in the worker's ``finally``, inside the worker's context copy."""
            seen["before"] = (get_byok_override(), get_byok_model_override(), digillm_get_byok())
            real_clear()
            seen["after"] = (get_byok_override(), get_byok_model_override(), digillm_get_byok())
            cleared.set()

        monkeypatch.setattr(llm_auth, "clear_byok_bindings", recording_clear)

        def worker(workflow_req, event_queue, cancel_event):
            event_queue.put(("content", "ok"))
            event_queue.put(("done",))
            if worker_raises:
                raise RuntimeError("worker blew up after streaming its last event")

        monkeypatch.setattr(srv, "run_digigraph_workflow_streaming", worker)
        res = TestClient(srv.app, headers=auth_headers()).post(
            "/v1/chat/completions",
            headers={
                "x-byok-key": "sk-probe",
                "x-byok-provider": "openrouter",
                "x-byok-model": "openai/gpt-4o-mini",
            },
            json={
                "model": "digigraph-rag",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
            },
        )
        assert res.status_code == 200, res.text
        assert cleared.wait(5), "the worker never reached its cleanup"
        return seen

    def test_the_worker_clears_its_own_copy(self, monkeypatch) -> None:
        seen = self._observe(monkeypatch, worker_raises=False)
        assert seen["before"] == (
            ("sk-probe", "openrouter"),
            "openai/gpt-4o-mini",
            ("sk-probe", "https://openrouter.ai/api/v1"),
        ), "the copy has to still hold the key when cleanup runs, or this proves nothing"
        assert seen["after"] == (None, None, None)

    def test_the_copy_is_cleared_even_when_the_worker_raises(self, monkeypatch) -> None:
        """A crash mid-stream is exactly when a leaked key would go unnoticed."""
        assert self._observe(monkeypatch, worker_raises=True)["after"] == (None, None, None)

    def test_clearing_the_copy_is_token_free(self) -> None:
        """``pop_byok`` cannot do this job: a copy inherits values, never the tokens.

        Pinned because the obvious 'simplification' is to call ``pop_byok`` in the
        worker instead, which needs a token the worker does not have.
        """
        from digigraph.llm_auth import clear_byok_bindings

        token = push_byok_header(
            _byok_request(key="sk-user", provider="openrouter", model="openai/gpt-4o-mini")
        )
        try:
            clear_byok_bindings()
            assert (get_byok_override(), get_byok_model_override(), digillm_get_byok()) == (
                None,
                None,
                None,
            )
        finally:
            pop_byok(token)


@pytest.mark.unit
class TestByokSurvivesTheParallelFanOut:
    """The binding also has to reach tools that run *concurrently*.

    ``TestByokSurvivesIntoTheStreamingWorker`` pins the worker's entry frame, but
    two thread pools sit downstream of it and a pool worker starts with an empty
    context exactly as a bare ``Thread`` does. Both dispatch tools that call an
    LLM themselves -- the delegate agents (``visualization_agent`` et al.) are
    tagged ``parallel_safe`` in ``orchestration/builtin.py`` and each one runs its
    own completion -- so without a copied context they spend the *operator's* key.

    Unlike the streaming worker, this hop is on the non-streaming path too: the
    request thread holds the binding, the pool workers still would not.
    """

    def test_run_plan_layer_keeps_the_binding(self) -> None:
        """digigraph's planning executor fans a layer out over a pool."""
        from digigraph.planning.executor import run_plan

        def sample(_agent: str, _args: dict) -> dict:
            return {
                "dg": get_byok_override(),
                "model": get_byok_model_override(),
                "llm": digillm_get_byok(),
            }

        token = push_byok_header(_byok_request("sk-fan", "openrouter", "openai/gpt-4o-mini"))
        try:
            # Two steps in one layer: len(resolved) > 1 is what selects the pool
            # branch over the inline single-step path.
            results = run_plan(
                [{"id": "a", "agent": "t", "args": {}}, {"id": "b", "agent": "t", "args": {}}],
                sample,
            )
        finally:
            pop_byok(token)

        expected = {
            "dg": ("sk-fan", "openrouter"),
            "model": "openai/gpt-4o-mini",
            "llm": ("sk-fan", "https://openrouter.ai/api/v1"),
        }
        assert results["a"] == expected
        assert results["b"] == expected

    def test_a_single_step_layer_still_keeps_it(self) -> None:
        """The one-step path skips the pool entirely; it must not regress either."""
        from digigraph.planning.executor import run_plan

        def sample(_agent: str, _args: dict) -> dict:
            return {"dg": get_byok_override()}

        token = push_byok_header(_byok_request("sk-solo", "openai"))
        try:
            results = run_plan([{"id": "only", "agent": "t", "args": {}}], sample)
        finally:
            pop_byok(token)
        assert results["only"] == {"dg": ("sk-solo", "openai")}

    def test_unbound_stays_unbound_across_the_pool(self) -> None:
        """Copying a context must not invent a binding the caller never made."""
        from digigraph.planning.executor import run_plan

        def sample(_agent: str, _args: dict) -> dict:
            return {"dg": get_byok_override(), "llm": digillm_get_byok()}

        results = run_plan(
            [{"id": "a", "agent": "t", "args": {}}, {"id": "b", "agent": "t", "args": {}}],
            sample,
        )
        assert results["a"] == {"dg": None, "llm": None}
        assert results["b"] == {"dg": None, "llm": None}

    def test_the_pool_does_not_share_the_telemetry_handle(self) -> None:
        """The copy carries credentials; it must not carry the caller's telemetry handle.

        ``copy_context()`` propagates references, so every step in a layer would hold the
        one :class:`~digillm.client.ProviderCallContextHandle` the caller is holding, and
        they would all write its ``last_call_id`` and append to the single deferred-record
        list that ``finalize`` tuples and clears. A step that inherited an empty context
        read ``None`` here, so ``None`` is the behaviour to keep -- nesting fan-out calls
        under the parent's logical call needs a per-worker handle and a join-time merge.

        The single-step layer is the deliberate asymmetry: it runs in the caller's own
        context rather than a copy of it, so it keeps the handle it was given.
        """
        from uuid import uuid4

        from digigraph.planning.executor import run_plan
        from digillm.telemetry import CallPurpose

        def sample(_agent: str, _args: dict) -> dict:
            return {
                "metadata": client_mod._provider_call_metadata.get(),
                "dg": get_byok_override(),
            }

        token = push_byok_header(_byok_request("sk-fan", "openrouter", "openai/gpt-4o-mini"))
        try:
            with digillm.provider_call_context(
                node_run_id=uuid4(),
                purpose=CallPurpose.INITIAL_GENERATION,
                no_artifact_reason=digillm.NoArtifactReason.CONSUMED_INLINE,
            ) as handle:
                fanned = run_plan(
                    [{"id": "a", "agent": "t", "args": {}}, {"id": "b", "agent": "t", "args": {}}],
                    sample,
                )
                solo = run_plan([{"id": "only", "agent": "t", "args": {}}], sample)
                # The workers cleared their own copies, not the caller's binding.
                caller_metadata = client_mod._provider_call_metadata.get()
        finally:
            pop_byok(token)

        for sid in ("a", "b"):
            assert fanned[sid]["metadata"] is None
            # Dropping the handle must not have dropped the credentials with it.
            assert fanned[sid]["dg"] == ("sk-fan", "openrouter")
        assert caller_metadata is not None and caller_metadata.handle is handle
        assert solo["only"]["metadata"] is not None
        assert solo["only"]["metadata"].handle is handle


@pytest.mark.unit
class TestTheFanOutDropsDigigraphsLogicalCallHandle:
    """digillm clearing *its own* logical-call var is only half the boundary.

    digigraph layers ``usage._LOGICAL_CALL_CONTEXT`` on top of digillm's, and its value
    holds the very same mutable :class:`~digillm.client.ProviderCallContextHandle` --
    ``llm_client._logical_call_scope`` passes ``metadata.handle`` straight through. So a
    fan-out worker that inherited the credential snapshot would still be handed one
    shared handle one layer up: every worker writing its ``last_call_id`` and appending
    into the single deferred-record list ``finalize`` tuples and clears.

    digillm is a leaf library and cannot reach into a consumer's module to clear it, so
    digigraph registers ``usage.detach_logical_call_context`` as digillm's fan-out detach
    hook (``llm_client``, next to the usage and telemetry observers). These pin both pools
    that copy a context: digillm's own tool pool, and digigraph's planning executor.

    ``usage._CALL_CONTEXT`` is deliberately *not* cleared -- its ``CallContext`` is frozen
    and holds no mutable state, so inheriting the node identity is safe and gives the
    worker's telemetry better attribution than it had.
    """

    @staticmethod
    def _tool_round() -> tuple[Any, Any]:
        """Two mock tool calls: >1 parallel-safe call is what selects the pool branch."""
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

    @staticmethod
    def _response(content: str = "", tool_calls: Any = None) -> MagicMock:
        msg = MagicMock()
        msg.content = content
        msg.tool_calls = tool_calls
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        return resp

    def test_the_hook_is_registered_by_importing_llm_client(self) -> None:
        """The wiring is what makes the two tests below mean anything.

        ``llm_client`` is the module every digigraph LLM call imports, which is why the
        usage and telemetry observers are registered there; this rides along with them.
        """
        import digigraph.llm_client  # noqa: F401  (imported for its registration)
        from digigraph.usage import detach_logical_call_context

        assert client_mod._fan_out_detach_hook is detach_logical_call_context

    def test_digillms_tool_pool_clears_it(self) -> None:
        """digillm's parallel tool branch, through the registered hook."""
        import digigraph.llm_client  # noqa: F401  (registers the detach hook)
        from digillm.telemetry import CallPurpose

        from digigraph import usage as dg_usage

        tc_a, tc_b = self._tool_round()
        fake_client = MagicMock()
        fake_client.chat.completions.create.side_effect = [
            self._response("", tool_calls=[tc_a, tc_b]),
            self._response("done"),
        ]

        seen: dict[str, Any] = {}
        seen_byok: dict[str, Any] = {}

        def execute_tool(name: str, args: dict) -> dict:
            seen[name] = dg_usage._LOGICAL_CALL_CONTEXT.get()
            seen_byok[name] = get_byok_override()
            return {"content": name}

        tools = [
            {"type": "function", "function": {"name": "alpha", "parameters": {}}},
            {"type": "function", "function": {"name": "beta", "parameters": {}}},
        ]
        token = push_byok_header(_byok_request("sk-fan", "openrouter", "openai/gpt-4o-mini"))
        try:
            with dg_usage.logical_call_context(
                purpose=CallPurpose.TOOL_SELECTION,
                no_artifact_reason=dg_usage.NoArtifactReason.TOOL_DISPATCH,
            ) as handle:
                with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
                    with digillm.provider_call_context(
                        node_run_id=uuid4(),
                        purpose=CallPurpose.TOOL_SELECTION,
                        no_artifact_reason=digillm.NoArtifactReason.TOOL_DISPATCH,
                    ):
                        digillm.run_tools(
                            "gpt-4o-mini",
                            [{"role": "user", "content": "go"}],
                            tools,
                            execute_tool,
                            parallel_safe_tools={"alpha", "beta"},
                        )
                # A copy is a snapshot, not a view: the caller keeps its own binding.
                still_bound = dg_usage._LOGICAL_CALL_CONTEXT.get()
        finally:
            pop_byok(token)

        assert seen == {"alpha": None, "beta": None}
        # Dropping the handle must not have dropped the credentials with it -- carrying
        # those across the boundary is the whole reason the context is copied.
        expected = ("sk-fan", "openrouter")
        assert seen_byok == {"alpha": expected, "beta": expected}
        assert still_bound is not None and still_bound.handle is handle

    def test_the_planning_pool_clears_it(self) -> None:
        """digigraph's planning executor copies the context itself, so it clears directly.

        The single-step layer is the deliberate asymmetry: it runs in the caller's own
        context rather than a copy of it, so unbinding there would lose the caller's live
        handle and its deferred records.
        """
        from digigraph.planning.executor import run_plan
        from digillm.telemetry import CallPurpose

        from digigraph import usage as dg_usage

        def sample(_agent: str, _args: dict) -> dict:
            return {
                "logical": dg_usage._LOGICAL_CALL_CONTEXT.get(),
                "node": dg_usage._CALL_CONTEXT.get().node_run_id,
                "dg": get_byok_override(),
            }

        node_run_id = uuid4()
        token = push_byok_header(_byok_request("sk-fan", "openrouter", "openai/gpt-4o-mini"))
        try:
            with dg_usage.call_context(node_run_id=node_run_id):
                with dg_usage.logical_call_context(
                    purpose=CallPurpose.TOOL_SELECTION,
                    no_artifact_reason=dg_usage.NoArtifactReason.TOOL_DISPATCH,
                ) as handle:
                    fanned = run_plan(
                        [
                            {"id": "a", "agent": "t", "args": {}},
                            {"id": "b", "agent": "t", "args": {}},
                        ],
                        sample,
                    )
                    solo = run_plan([{"id": "only", "agent": "t", "args": {}}], sample)
                    still_bound = dg_usage._LOGICAL_CALL_CONTEXT.get()
        finally:
            pop_byok(token)

        for sid in ("a", "b"):
            assert fanned[sid]["logical"] is None
            assert fanned[sid]["dg"] == ("sk-fan", "openrouter")
            # ``_CALL_CONTEXT`` is frozen and stays inherited: node identity is safe to
            # carry and is what lets a worker's telemetry be attributed at all.
            assert fanned[sid]["node"] == node_run_id
        assert still_bound is not None and still_bound.handle is handle
        assert solo["only"]["logical"] is not None
        assert solo["only"]["logical"].handle is handle

    def test_a_broken_llm_stack_does_not_discard_the_layer(self) -> None:
        """An ImportError on the detach imports must cost one step's telemetry, not the layer.

        The two imports run in the pool worker *outside* ``_run_step``'s handler, and
        ``run_plan`` reads ``future.result()`` bare -- so an unguarded raise there escapes
        the worker and discards every other step in the layer, while the single-step path
        would have degraded to one error string (``ImportError`` is in
        ``_PLAN_STEP_ERRORS``). ``digillm`` is a hard dependency, so this needs a broken
        install; the point is that the fan-out fails no worse than the serial path.

        Swallowing is safe precisely here: the module that binds the handle is the one that
        failed to import, so there is no bound handle left to share.
        """
        import sys

        from digigraph.planning.executor import run_plan

        def sample(_agent: str, _args: dict) -> dict:
            return {"dg": get_byok_override()}

        token = push_byok_header(_byok_request("sk-broken", "openai"))
        try:
            # ``None`` in sys.modules is the documented way to make an import raise.
            with patch.dict(sys.modules, {"digillm": None}):
                fanned = run_plan(
                    [
                        {"id": "a", "agent": "t", "args": {}},
                        {"id": "b", "agent": "t", "args": {}},
                    ],
                    sample,
                )
        finally:
            pop_byok(token)

        # Both steps came back: the layer survived, credentials included.
        assert set(fanned) == {"a", "b"}
        for sid in ("a", "b"):
            assert fanned[sid] == {"dg": ("sk-broken", "openai")}


@pytest.mark.unit
class TestByokReachesTheOpenRouterAutoRouter:
    """The full header -> normalizer -> wire chain for OpenRouter's auto-router.

    ``openrouter/auto`` is the one model id that repeats its own provider's name, so it
    is the only id whose litellm form carries the prefix twice. Operators write that
    doubled form by hand; BYOK cannot, because :func:`byok_routable_model` strips the
    provider's own prefix to a **fixpoint** and re-applies exactly one — deliberately, to
    keep the middleware and the resolver from disagreeing about a hostile header.

    The two halves are pinned separately in ``digillm/tests``; what this class asserts is
    that they compose, i.e. that no header a user can send is silently downgraded to a
    model OpenRouter does not have. This test crosses the package boundary on purpose:
    each side is individually correct, and the defect lived only in the seam.
    """

    @staticmethod
    def _wire(provider: str, header: str) -> str:
        """Walk a raw header through the production path to the string sent to the API."""
        token = push_byok_header(_byok_request(key="sk-user", provider=provider, model=header))
        try:
            slug = get_byok_model_override() or ""
        finally:
            pop_byok(token)
        litellm_string = byok_routable_model(provider, slug)
        prov, model_id = client_mod._parse_provider_prefix(litellm_string)
        return client_mod._wire_model(prov, model_id, litellm_string)

    @pytest.mark.parametrize("header", ["auto", "openrouter/auto", "openrouter/openrouter/auto"])
    def test_every_spelling_a_user_can_send_reaches_the_auto_router(self, header: str) -> None:
        """Regression: all three used to arrive as a bare ``auto`` and fail at OpenRouter."""
        assert self._wire("openrouter", header) == "openrouter/auto"

    @pytest.mark.parametrize(
        ("header", "expected"),
        [
            ("openai/gpt-4o-mini", "openai/gpt-4o-mini"),
            ("anthropic/claude-sonnet-4", "anthropic/claude-sonnet-4"),
            ("openrouter/openai/gpt-4o-mini", "openai/gpt-4o-mini"),
        ],
    )
    def test_ordinary_models_are_unchanged(self, header: str, expected: str) -> None:
        """Control: the vendor sub-slug still reaches the wire with the routing prefix gone."""
        assert self._wire("openrouter", header) == expected

    def test_the_fixpoint_strip_is_still_intact(self) -> None:
        """The fix must not have been bought by weakening the credential-path invariant.

        ``byok_routable_model`` still collapses any depth of the provider's own prefix to
        exactly one, so the middleware and the resolver cannot diverge at depth two.
        """
        for depth in range(4):
            raw = "openrouter/" * depth + "openai/gpt-4o-mini"
            assert byok_routable_model("openrouter", raw) == "openrouter/openai/gpt-4o-mini"
