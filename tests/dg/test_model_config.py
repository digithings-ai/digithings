"""Unit tests for digigraph.model_config (mode resolution + request-model routing).

Split from the former tests/dg/test_llm.py (#632 P2). Covers model_modes.yaml
loading, test/medium/best mode resolution, ``ollama/`` prefix normalization, and
the :func:`resolve_request_model` routing helper (provider-key→Ollama fallback,
``ollama-cloud/`` strip) that yields the model string handed to
``digillm.completion``. Client/retry/completion mechanics now live in digillm and
are covered by digillm/tests/test_digillm.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from digigraph.model_config import (
    ModelModesConfig,
    _load_model_modes,
    _parse_provider_prefix,
    get_model_for_mode,
    resolve_effective_model,
    resolve_request_model,
)


@pytest.mark.unit
class TestLoadModelModes:
    """_load_model_modes() with config path and missing/bad YAML."""

    def test_returns_empty_when_path_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIGI_CONFIG_PATH", "/nonexistent_config_xyz")
        assert _load_model_modes() == ModelModesConfig()

    def test_returns_empty_when_file_missing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
        assert not (tmp_path / "model_modes.yaml").exists()
        assert _load_model_modes() == ModelModesConfig()

    def test_loads_valid_yaml(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        (tmp_path / "model_modes.yaml").write_text(
            "defaults:\n  test: ollama/test\n  medium: ollama/med\n"
        )
        monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
        data = _load_model_modes()
        assert data.defaults.get("test") == "ollama/test"
        assert data.defaults.get("medium") == "ollama/med"

    def test_respects_digi_model_modes_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        (tmp_path / "alt.yaml").write_text("defaults:\n  test: ollama/alt\n")
        monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
        monkeypatch.setenv("DIGI_MODEL_MODES_FILE", "alt.yaml")
        data = _load_model_modes()
        assert data.defaults.get("test") == "ollama/alt"

    def test_returns_empty_on_invalid_yaml(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        (tmp_path / "model_modes.yaml").write_text("defaults:\n  test: [unclosed\n")
        monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
        assert _load_model_modes() == ModelModesConfig()


def _clear_explicit_llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate mode/YAML resolution from sticky process env / project pins."""
    monkeypatch.delenv("DIGI_PROJECT_CONFIG", raising=False)
    monkeypatch.delenv("DIGI_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("DIGI_LLM_MODEL", raising=False)


@pytest.mark.unit
class TestGetModelForMode:
    """get_model_for_mode() respects DIGI_LLM_MODE and config."""

    def test_fallback_when_no_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_explicit_llm_env(monkeypatch)
        monkeypatch.setenv("DIGI_CONFIG_PATH", "/nonexistent_xyz")
        monkeypatch.setenv("DIGI_LLM_MODE", "test")
        assert get_model_for_mode() == "gpt-4o-mini"

    def test_uses_defaults_test_from_config(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _clear_explicit_llm_env(monkeypatch)
        (tmp_path / "model_modes.yaml").write_text("defaults:\n  test: ollama/mini\n")
        monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
        monkeypatch.setenv("DIGI_LLM_MODE", "test")
        assert get_model_for_mode() == "ollama/mini"

    def test_uses_defaults_medium_when_mode_medium(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _clear_explicit_llm_env(monkeypatch)
        (tmp_path / "model_modes.yaml").write_text(
            "defaults:\n  test: t\n  medium: ollama/medium\n  best: b\n"
        )
        monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
        monkeypatch.setenv("DIGI_LLM_MODE", "medium")
        # Mode is resolved per-call via env var; no cached global to patch
        assert get_model_for_mode() == "ollama/medium"

    def test_falls_back_to_test_when_mode_missing_in_config(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _clear_explicit_llm_env(monkeypatch)
        (tmp_path / "model_modes.yaml").write_text("defaults:\n  test: ollama/fallback\n")
        monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
        monkeypatch.setenv("DIGI_LLM_MODE", "best")
        assert get_model_for_mode() == "ollama/fallback"

    def test_normalizes_mode_lowercase(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _clear_explicit_llm_env(monkeypatch)
        (tmp_path / "model_modes.yaml").write_text("defaults:\n  test: ollama/t\n")
        monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
        monkeypatch.setenv("DIGI_LLM_MODE", "TEST")
        assert get_model_for_mode() == "ollama/t"


@pytest.mark.unit
class TestResolveEffectiveModel:
    """Strip LiteLLM ``ollama/`` prefix when talking to Ollama's OpenAI shim (:11434)."""

    def test_strips_prefix_for_local_ollama_base(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _clear_explicit_llm_env(monkeypatch)
        (tmp_path / "model_modes.yaml").write_text("defaults:\n  test: ollama/qwen3:8b\n")
        monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
        monkeypatch.setenv("DIGI_LLM_MODE", "test")
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:11434/v1")
        monkeypatch.delenv("OLLAMA_MODEL", raising=False)
        assert resolve_effective_model("ignored") == "qwen3:8b"

    def test_no_strip_for_litellm_base(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _clear_explicit_llm_env(monkeypatch)
        (tmp_path / "model_modes.yaml").write_text("defaults:\n  test: ollama/qwen3:8b\n")
        monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
        monkeypatch.setenv("DIGI_LLM_MODE", "test")
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:4000/v1")
        monkeypatch.delenv("OLLAMA_MODEL", raising=False)
        assert resolve_effective_model("x") == "ollama/qwen3:8b"

    def test_env_ollama_model_wins(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        (tmp_path / "model_modes.yaml").write_text("defaults:\n  test: ollama/qwen3:8b\n")
        monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:11434/v1")
        monkeypatch.setenv("OLLAMA_MODEL", "ollama/deepseek-r1:14b")
        assert resolve_effective_model("x") == "deepseek-r1:14b"


@pytest.mark.unit
class TestResolveRequestModel:
    """resolve_request_model() routing: provider fallback, ollama-cloud strip, mode model.

    Reproduces the model-resolution behavior the old chat_completion did inline
    before handing the string to the (Ollama/LiteLLM/provider) client.
    """

    def test_env_ollama_model_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OLLAMA_MODEL", "ollama/qwen:8b")
        monkeypatch.delenv("OPENAI_API_BASE", raising=False)
        assert resolve_request_model("gpt-4o-mini") == "ollama/qwen:8b"

    def test_ollama_cloud_prefix_stripped_not_overridden_by_mode(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """ollama-cloud/ prefix is stripped; get_model_for_mode() must NOT override it.

        Regression: DIGI_LLM_MODE=medium previously caused resolution to return
        'gemini/gemini-2.5-flash' instead of the intended cloud model (a 404 from
        Ollama Cloud).
        """
        (tmp_path / "model_modes.yaml").write_text(
            "defaults:\n  test: ollama-cloud/rnj-1:cloud\n  medium: gemini/gemini-2.5-flash\n"
        )
        monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
        monkeypatch.setenv("DIGI_LLM_MODE", "medium")
        monkeypatch.delenv("OLLAMA_MODEL", raising=False)
        assert (
            resolve_request_model("ollama-cloud/deepseek-v4-flash:cloud")
            == "deepseek-v4-flash:cloud"
        )

    def test_provider_model_passthrough_when_key_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A provider/ model with its key set is handed to digillm unchanged (digillm routes)."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-test")
        assert (
            resolve_request_model("openrouter/mistral/mistral-7b")
            == "openrouter/mistral/mistral-7b"
        )

    def test_provider_falls_back_to_ollama_when_key_missing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Missing provider key → Ollama mode model (legacy silent fallback, not a raise)."""
        _clear_explicit_llm_env(monkeypatch)
        (tmp_path / "model_modes.yaml").write_text("defaults:\n  test: ollama/qwen3:8b\n")
        monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
        monkeypatch.setenv("DIGI_LLM_MODE", "test")
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_MODEL", raising=False)
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:4000/v1")  # not :11434 → no strip
        assert resolve_request_model("openrouter/mistral/mistral-7b") == "ollama/qwen3:8b"

    def test_house_digiquant_slug_not_clobbered_by_mode_defaults(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Unprefixed house pins (#3414) must survive resolve_request_model.

        Regression: after stripping ``openrouter/`` from digiquant pools, phase
        models like ``deepseek/deepseek-v4-flash`` fell through to
        ``resolve_effective_model``, which prefers ``model_modes`` local defaults
        (``ollama/qwen3:8b``). OpenRouter then rejects the call as an invalid
        model id — observed on decision_log reflector / preflight_reflect.
        """
        _clear_explicit_llm_env(monkeypatch)
        (tmp_path / "model_modes.yaml").write_text("defaults:\n  test: ollama/qwen3:8b\n")
        monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
        monkeypatch.setenv("DIGI_LLM_MODE", "test")
        monkeypatch.delenv("OLLAMA_MODEL", raising=False)
        monkeypatch.setenv("OPENAI_API_BASE", "https://openrouter.ai/api/v1")
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-test")
        assert resolve_request_model("deepseek/deepseek-v4-flash") == "deepseek/deepseek-v4-flash"
        assert resolve_request_model("perplexity/sonar") == "perplexity/sonar"
        # Explicit local ollama requests still go through effective-model resolution.
        assert resolve_request_model("ollama/qwen3:8b") == "ollama/qwen3:8b"

    def test_plain_model_uses_effective_model(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A non-prefixed model resolves via resolve_effective_model (mode + ollama/ strip)."""
        _clear_explicit_llm_env(monkeypatch)
        (tmp_path / "model_modes.yaml").write_text("defaults:\n  test: ollama/qwen3:8b\n")
        monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
        monkeypatch.setenv("DIGI_LLM_MODE", "test")
        monkeypatch.delenv("OLLAMA_MODEL", raising=False)
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:11434/v1")  # :11434 → strip ollama/
        assert resolve_request_model("gpt-4o-mini") == "qwen3:8b"

    def test_openrouter_byok_passthrough_without_platform_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OpenRouter BYOK keeps the provider model even when OPENROUTER_API_KEY is unset."""
        from digigraph.llm_auth import pop_byok, push_byok_header

        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

        class _Headers:
            def __init__(self, d: dict[str, str]) -> None:
                self._d = {k.lower(): v for k, v in d.items()}

            def get(self, name: str) -> str | None:
                return self._d.get(name.lower())

        class _Req:
            def __init__(self) -> None:
                self.headers = _Headers(
                    {
                        "x-byok-key": "sk-or-v1-test",
                        "x-byok-provider": "openrouter",
                        "x-byok-model": "openai/gpt-4o-mini",
                    }
                )

        tok = push_byok_header(_Req())
        try:
            assert (
                resolve_request_model("openrouter/openai/gpt-4o-mini")
                == "openrouter/openai/gpt-4o-mini"
            )
        finally:
            pop_byok(tok)

    def test_openai_byok_bare_model_not_clobbered_by_ollama_model(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OpenAI BYOK keeps a bare slug even when OLLAMA_MODEL is set.

        openai is not a digillm-registered prefix, so BYOK models are bare
        (``gpt-4o-mini``). ``resolve_effective_model`` prefers ``OLLAMA_MODEL``;
        applying it under BYOK sent ``ollama/…`` to api.openai.com with the
        user's key (model_not_found) while digichat still showed BYOK as active.
        """
        from digigraph.llm_auth import pop_byok, push_byok_header
        from digigraph.model_config import _apply_byok_model_override

        monkeypatch.setenv("OLLAMA_MODEL", "ollama/qwen3:8b")
        monkeypatch.delenv("OPENAI_API_BASE", raising=False)

        class _Headers:
            def __init__(self, d: dict[str, str]) -> None:
                self._d = {k.lower(): v for k, v in d.items()}

            def get(self, name: str) -> str | None:
                return self._d.get(name.lower())

        class _Req:
            def __init__(self) -> None:
                self.headers = _Headers(
                    {
                        "x-byok-key": "sk-openai-test",
                        "x-byok-provider": "openai",
                        "x-byok-model": "gpt-4o-mini",
                    }
                )

        tok = push_byok_header(_Req())
        try:
            # Mirror llm_client: override first, then resolve_request_model.
            chosen = _apply_byok_model_override("operator-default-ignored")
            assert chosen == "gpt-4o-mini"
            assert resolve_request_model(chosen) == "gpt-4o-mini"
            # Operator path without BYOK still lets OLLAMA_MODEL win (sibling test).
        finally:
            pop_byok(tok)
        assert resolve_request_model("gpt-4o-mini") == "ollama/qwen3:8b"

    def test_bare_slug_unroutable_byok_provider_does_not_bypass_ollama_model(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A BYOK override for an unroutable provider must not bypass OLLAMA_MODEL.

        push_byok_header binds digigraph's ``(key, provider)`` contextvar whenever a
        key is present, independent of whether the provider has a catalog base_url —
        only a *routable* provider also gets digillm's own BYOK override
        (``set_byok``). Gating the bare-slug passthrough on "BYOK bound at all"
        rather than "BYOK bound for a routable provider" would let an unroutable
        provider's override reach here and skip the operator's OLLAMA_MODEL
        fallback even though digillm was never told to route to that provider's
        key. ``server.py``'s 400 on unroutable providers (#1873) means this never
        happens over HTTP today, but ``resolve_request_model`` must not depend on
        that caller for its own correctness.
        """
        from digigraph.llm_auth import pop_byok, push_byok_header

        monkeypatch.setenv("OLLAMA_MODEL", "ollama/qwen3:8b")
        monkeypatch.delenv("OPENAI_API_BASE", raising=False)

        class _Headers:
            def __init__(self, d: dict[str, str]) -> None:
                self._d = {k.lower(): v for k, v in d.items()}

            def get(self, name: str) -> str | None:
                return self._d.get(name.lower())

        class _Req:
            def __init__(self) -> None:
                self.headers = _Headers(
                    {
                        "x-byok-key": "co-test-key",
                        "x-byok-provider": "cohere",
                        "x-byok-model": "command-r-plus",
                    }
                )

        tok = push_byok_header(_Req())
        try:
            assert resolve_request_model("gpt-4-turbo") == "ollama/qwen3:8b"
        finally:
            pop_byok(tok)

    def test_free_mode_byok_paid_model_not_clamped_by_ollama_model(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``llm_mode: free`` + BYOK + a paid ``X-BYOK-Model`` now reaches digillm unchanged.

        Documents an intentional behavior change, not a regression: before this fix,
        ``resolve_request_model`` ignored any BYOK override on the bare-slug path and
        always preferred ``OLLAMA_MODEL``, so a paid BYOK model was clamped to the
        local Ollama default as a *side effect* of the OLLAMA_MODEL-clobber bug, not
        by any deliberate free-mode policy check. That accidental clamp is gone now
        that the bare-slug path respects BYOK — the user's own key pays, matching
        the documented free_quota_exceeded → BYOK handoff design. Pinned so a future
        change to free-mode policy doesn't silently assume the old accidental clamp
        is still in effect.
        """
        from digigraph.llm_auth import pop_byok, push_byok_header
        from digigraph.model_config import _apply_byok_model_override

        monkeypatch.setenv("DIGI_LLM_MODE", "free")
        monkeypatch.setenv("OLLAMA_MODEL", "ollama/qwen3:8b")
        monkeypatch.delenv("OPENAI_API_BASE", raising=False)

        class _Headers:
            def __init__(self, d: dict[str, str]) -> None:
                self._d = {k.lower(): v for k, v in d.items()}

            def get(self, name: str) -> str | None:
                return self._d.get(name.lower())

        class _Req:
            def __init__(self) -> None:
                self.headers = _Headers(
                    {
                        "x-byok-key": "sk-openai-test",
                        "x-byok-provider": "openai",
                        "x-byok-model": "gpt-4o",
                    }
                )

        tok = push_byok_header(_Req())
        try:
            chosen = _apply_byok_model_override("ollama/qwen3:8b")
            assert chosen == "gpt-4o"
            assert resolve_request_model(chosen) == "gpt-4o"
        finally:
            pop_byok(tok)

    def test_provider_registry_is_digillm_not_a_local_copy(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression: model_config must defer to digillm's provider registry, not keep

        its own duplicate. Registering a brand-new provider via
        ``digillm.register_provider`` (with no digigraph code change) must make
        ``_parse_provider_prefix`` recognize it immediately — proving there is a
        single source of truth, not two dicts that can drift apart.
        """
        import digillm.client

        import digillm

        digillm.register_provider(
            "zzz-test-provider", "https://example.invalid/v1", "ZZZ_TEST_PROVIDER_API_KEY"
        )
        try:
            provider, model_id = _parse_provider_prefix("zzz-test-provider/some-model")
            assert provider == "zzz-test-provider"
            assert model_id == "some-model"

            monkeypatch.setenv("ZZZ_TEST_PROVIDER_API_KEY", "test-key")
            assert (
                resolve_request_model("zzz-test-provider/some-model")
                == "zzz-test-provider/some-model"
            )
        finally:
            del digillm.client._EXTERNAL_PROVIDERS["zzz-test-provider"]


@pytest.mark.unit
class TestByokModelOverride:
    """OpenRouter BYOK model slug overrides mode/phase resolution."""

    def test_get_model_for_mode_uses_byok_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from digigraph.llm_auth import pop_byok, push_byok_header

        monkeypatch.setenv("DIGI_CONFIG_PATH", "/nonexistent_xyz")
        monkeypatch.setenv("DIGI_LLM_MODE", "test")

        class _Headers:
            def __init__(self, d: dict[str, str]) -> None:
                self._d = {k.lower(): v for k, v in d.items()}

            def get(self, name: str) -> str | None:
                return self._d.get(name.lower())

        class _Req:
            def __init__(self) -> None:
                self.headers = _Headers(
                    {
                        "x-byok-key": "sk-or-v1-test",
                        "x-byok-provider": "openrouter",
                        "x-byok-model": "openai/gpt-4o-mini",
                    }
                )

        tok = push_byok_header(_Req())
        try:
            assert get_model_for_mode() == "openrouter/openai/gpt-4o-mini"
        finally:
            pop_byok(tok)

    def test_get_model_for_mode_uses_byok_model_xai(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """x.ai BYOK must route to the user's model (#2361 review finding).

        Before the ``xai`` branch existed, ``_apply_byok_model_override`` fell
        through to ``return resolved`` for any provider it didn't recognize,
        so an x.ai BYOK request silently ran on the operator's own
        model/key instead of the user's — reproducing #1873 for the new
        provider.
        """
        from digigraph.llm_auth import pop_byok, push_byok_header

        monkeypatch.setenv("DIGI_CONFIG_PATH", "/nonexistent_xyz")
        monkeypatch.setenv("DIGI_LLM_MODE", "test")

        class _Headers:
            def __init__(self, d: dict[str, str]) -> None:
                self._d = {k.lower(): v for k, v in d.items()}

            def get(self, name: str) -> str | None:
                return self._d.get(name.lower())

        class _Req:
            def __init__(self) -> None:
                self.headers = _Headers(
                    {
                        "x-byok-key": "xai-test",
                        "x-byok-provider": "xai",
                        "x-byok-model": "grok-4-3",
                    }
                )

        tok = push_byok_header(_Req())
        try:
            assert get_model_for_mode() == "xai/grok-4-3"
        finally:
            pop_byok(tok)

    def test_every_routable_byok_provider_routes_the_users_model(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression guard: a catalog provider whose model is not routed
        silently discards the user's ``X-BYOK-Model`` and falls through to the
        operator's own model/key (the #2361/#1873 failure mode). Every provider
        in ``BYOK_ROUTABLE_PROVIDERS`` other than ``openai`` must prefix the
        resolved model with ``<provider>/`` — so adding a new BYOK provider to
        ``config/byok-providers.json`` that ``byok_routable_model`` does not
        handle fails this test instead of merging silently broken.

        ``_apply_byok_model_override`` no longer carries a per-provider ladder:
        it defers to ``llm_auth.byok_routable_model``, which reads digillm's
        registry. This test is unchanged in what it asserts — a new provider
        still has to come out routed — only in where the answer comes from.
        """
        from digigraph.llm_auth import BYOK_ROUTABLE_PROVIDERS, pop_byok, push_byok_header

        monkeypatch.setenv("DIGI_CONFIG_PATH", "/nonexistent_xyz")
        monkeypatch.setenv("DIGI_LLM_MODE", "test")

        class _Headers:
            def __init__(self, d: dict[str, str]) -> None:
                self._d = {k.lower(): v for k, v in d.items()}

            def get(self, name: str) -> str | None:
                return self._d.get(name.lower())

        class _Req:
            def __init__(self, provider: str) -> None:
                self.headers = _Headers(
                    {
                        "x-byok-key": "test-key",
                        "x-byok-provider": provider,
                        "x-byok-model": "some-model",
                    }
                )

        assert BYOK_ROUTABLE_PROVIDERS, "catalog produced no routable providers"
        for provider in BYOK_ROUTABLE_PROVIDERS:
            tok = push_byok_header(_Req(provider))
            try:
                resolved = get_model_for_mode()
            finally:
                pop_byok(tok)
            expected = "some-model" if provider == "openai" else f"{provider}/some-model"
            assert resolved == expected, (
                f"provider {provider!r} did not route the user's BYOK model "
                f"(got {resolved!r}, expected {expected!r}) — check "
                "llm_auth.byok_routable_model and digillm's provider registry"
            )
