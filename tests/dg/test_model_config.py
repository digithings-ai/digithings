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


@pytest.mark.unit
class TestGetModelForMode:
    """get_model_for_mode() respects DIGI_LLM_MODE and config."""

    def test_fallback_when_no_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIGI_CONFIG_PATH", "/nonexistent_xyz")
        monkeypatch.setenv("DIGI_LLM_MODE", "test")
        assert get_model_for_mode() == "gpt-4o-mini"

    def test_uses_defaults_test_from_config(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        (tmp_path / "model_modes.yaml").write_text("defaults:\n  test: ollama/mini\n")
        monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
        monkeypatch.setenv("DIGI_LLM_MODE", "test")
        assert get_model_for_mode() == "ollama/mini"

    def test_uses_defaults_medium_when_mode_medium(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
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
        (tmp_path / "model_modes.yaml").write_text("defaults:\n  test: ollama/fallback\n")
        monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
        monkeypatch.setenv("DIGI_LLM_MODE", "best")
        assert get_model_for_mode() == "ollama/fallback"

    def test_normalizes_mode_lowercase(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
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
        (tmp_path / "model_modes.yaml").write_text("defaults:\n  test: ollama/qwen3:8b\n")
        monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
        monkeypatch.setenv("DIGI_LLM_MODE", "test")
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:11434/v1")
        monkeypatch.delenv("OLLAMA_MODEL", raising=False)
        assert resolve_effective_model("ignored") == "qwen3:8b"

    def test_no_strip_for_litellm_base(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
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
        monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
        assert resolve_request_model("groq/llama-3.1-8b-instant") == "groq/llama-3.1-8b-instant"

    def test_provider_falls_back_to_ollama_when_key_missing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Missing provider key → Ollama mode model (legacy silent fallback, not a raise)."""
        (tmp_path / "model_modes.yaml").write_text("defaults:\n  test: ollama/qwen3:8b\n")
        monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
        monkeypatch.setenv("DIGI_LLM_MODE", "test")
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_MODEL", raising=False)
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:4000/v1")  # not :11434 → no strip
        assert resolve_request_model("groq/llama-3.1-8b-instant") == "ollama/qwen3:8b"

    def test_plain_model_uses_effective_model(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A non-prefixed model resolves via resolve_effective_model (mode + ollama/ strip)."""
        (tmp_path / "model_modes.yaml").write_text("defaults:\n  test: ollama/qwen3:8b\n")
        monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
        monkeypatch.setenv("DIGI_LLM_MODE", "test")
        monkeypatch.delenv("OLLAMA_MODEL", raising=False)
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:11434/v1")  # :11434 → strip ollama/
        assert resolve_request_model("gpt-4o-mini") == "qwen3:8b"
