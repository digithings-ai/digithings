"""Phase 1: Unit tests for digigraph LLM module (get_model_for_mode, get_client, chat_completion)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from digigraph.llm import (
    _load_model_modes,
    chat_completion,
    get_client,
    get_model_for_mode,
)


@pytest.mark.unit
class TestLoadModelModes:
    """_load_model_modes() with config path and missing/bad YAML."""

    def test_returns_empty_when_path_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIGI_CONFIG_PATH", "/nonexistent_config_xyz")
        assert _load_model_modes() == {}

    def test_returns_empty_when_file_missing(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
        assert not (tmp_path / "model_modes.yaml").exists()
        assert _load_model_modes() == {}

    def test_loads_valid_yaml(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        (tmp_path / "model_modes.yaml").write_text("defaults:\n  test: ollama/test\n  medium: ollama/med\n")
        monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
        data = _load_model_modes()
        assert data.get("defaults", {}).get("test") == "ollama/test"
        assert data.get("defaults", {}).get("medium") == "ollama/med"

    def test_returns_empty_on_invalid_yaml(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        (tmp_path / "model_modes.yaml").write_text("defaults:\n  test: [unclosed\n")
        monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
        assert _load_model_modes() == {}


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
        # Module reads DIGI_LLM_MODE at import; patch the cached value
        with patch("digigraph.llm._DIGI_LLM_MODE", "medium"):
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
class TestGetClient:
    """get_client() builds OpenAI client with optional base_url."""

    def test_includes_base_url_when_env_set(self) -> None:
        """Client uses OPENAI_API_BASE when set (patch module-level _BASE_URL)."""
        with patch("digigraph.llm._BASE_URL", "http://litellm:4000/v1"):
            client = get_client()
        base_url_str = str(client.base_url)
        assert "litellm" in base_url_str and "4000" in base_url_str

    def test_client_created_without_base_url(self) -> None:
        with patch("digigraph.llm._BASE_URL", None):
            client = get_client()
        assert client is not None
        if getattr(client, "base_url", None) is not None:
            assert "openai.com" in str(client.base_url)

    def test_strips_trailing_slash_from_base_url(self) -> None:
        """base_url is stored without trailing slash (llm passes rstrip('/'))."""
        with patch("digigraph.llm._BASE_URL", "http://litellm:4000/v1/"):
            client = get_client()
        base_url_str = str(client.base_url).rstrip("/")
        assert base_url_str == "http://litellm:4000/v1"


@pytest.mark.unit
class TestChatCompletion:
    """chat_completion() uses client and returns first choice content."""

    def test_returns_content_from_first_choice(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_create = MagicMock()
        mock_create.return_value.choices = [
            MagicMock(message=MagicMock(content="  strategy_name: mean_reversion  "))
        ]
        mock_client = MagicMock()
        mock_client.chat.completions.create = mock_create
        with patch("digigraph.llm.get_client", return_value=mock_client):
            out = chat_completion("gpt-4o-mini", [{"role": "user", "content": "Hi"}])
        assert out == "strategy_name: mean_reversion"
        mock_create.assert_called_once()
        call_kw = mock_create.call_args[1]
        assert call_kw["temperature"] == 0.2
        assert call_kw["messages"] == [{"role": "user", "content": "Hi"}]

    def test_returns_empty_when_no_choices(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_create = MagicMock()
        mock_create.return_value.choices = []
        mock_client = MagicMock()
        mock_client.chat.completions.create = mock_create
        with patch("digigraph.llm.get_client", return_value=mock_client):
            out = chat_completion("x", [])
        assert out == ""

    def test_uses_ollama_model_when_env_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OLLAMA_MODEL", "ollama/qwen:8b")
        mock_create = MagicMock()
        mock_create.return_value.choices = [MagicMock(message=MagicMock(content="OK"))]
        mock_client = MagicMock()
        mock_client.chat.completions.create = mock_create
        with patch("digigraph.llm.get_client", return_value=mock_client):
            chat_completion("gpt-4o-mini", [{"role": "user", "content": "x"}])
        assert mock_create.call_args[1]["model"] == "ollama/qwen:8b"
