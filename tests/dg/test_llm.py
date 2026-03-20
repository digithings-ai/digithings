"""Phase 1: Unit tests for digigraph LLM module (get_model_for_mode, get_client, chat_completion)."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from digigraph.llm import (
    _load_model_modes,
    chat_completion,
    chat_completion_with_tools,
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
class TestGetClient:
    """get_client() builds OpenAI client with optional base_url."""

    def test_includes_base_url_when_env_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Client uses OPENAI_API_BASE when set. get_client() reads env fresh each call."""
        monkeypatch.setenv("OPENAI_API_BASE", "http://litellm:4000/v1")
        client = get_client()
        base_url_str = str(client.base_url)
        assert "litellm" in base_url_str and "4000" in base_url_str

    def test_client_created_without_base_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_BASE", raising=False)
        client = get_client()
        assert client is not None
        if getattr(client, "base_url", None) is not None:
            assert "openai.com" in str(client.base_url)

    def test_strips_trailing_slash_from_base_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """base_url trailing slash is stripped by get_client() via rstrip('/')."""
        monkeypatch.setenv("OPENAI_API_BASE", "http://litellm:4000/v1/")
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


@pytest.mark.unit
class TestChatCompletionWithToolsParallel:
    """chat_completion_with_tools runs independent delegate tool calls in parallel."""

    def test_parallel_delegate_calls_faster_than_sequential(self) -> None:
        """Two delegate tool calls in one turn run in parallel (wall time < 2 * single call)."""
        tool_calls_payload = [
            {
                "id": "call_1",
                "function": {"name": "visualization_agent", "arguments": "{}"},
            },
            {
                "id": "call_2",
                "function": {"name": "analysis_agent", "arguments": "{}"},
            },
        ]
        turn = [0]

        def slow_execute(_name: str, _args: dict) -> str:
            time.sleep(0.08)
            return "ok"

        def do_one_turn_side_effect(*args: object, **kwargs: object) -> tuple[str, list] | str:
            turn[0] += 1
            if turn[0] == 1:
                return ("", tool_calls_payload)
            return ("done", None)

        with patch("digigraph.llm.chat_completion", side_effect=do_one_turn_side_effect):
            with patch(
                "digigraph.orchestration.registry.list_tool_names",
                return_value=["visualization_agent", "analysis_agent"],
            ):
                start = time.perf_counter()
                out = chat_completion_with_tools(
                    "test-model",
                    [{"role": "user", "content": "go"}],
                    [],
                    execute_tool=slow_execute,
                    max_tool_rounds=2,
                )
                elapsed = time.perf_counter() - start
        assert out == "done"
        # If sequential: ~0.16s; if parallel: ~0.08s. Require < 0.14s to prove parallel.
        assert elapsed < 0.14, f"Expected parallel execution (elapsed={elapsed:.3f}s)"
