"""Unit tests for free-tier DigiProject LLM resolution + quota error codes."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from digigraph.llm_errors import (
    FREE_QUOTA_EXCEEDED,
    RATE_LIMIT,
    classify_llm_error,
    is_rate_limit_error,
)
from digigraph.model_config import (
    effective_llm_settings,
    get_model_for_mode,
    is_free_tier_model,
)
from digigraph.project_config import DigiProjectConfig


@pytest.mark.unit
def test_is_free_tier_model() -> None:
    assert is_free_tier_model("openrouter/openai/gpt-oss-20b:free")
    assert is_free_tier_model("openai/gpt-oss-20b:free")
    assert is_free_tier_model("ollama/qwen3:8b")
    assert not is_free_tier_model("openrouter/deepseek/deepseek-chat")
    assert not is_free_tier_model("gpt-4o-mini")


@pytest.mark.unit
def test_free_mode_refuses_paid_model(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = tmp_path / "digiproject.yaml"
    cfg.write_text(
        "agents:\n"
        "  llm_mode: free\n"
        "  llm:\n"
        "    provider: openrouter\n"
        "    model: deepseek/deepseek-chat\n"
        "    api_key_env: OPENROUTER_API_KEY\n"
    )
    monkeypatch.setenv("DIGI_PROJECT_CONFIG", str(cfg))
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    with pytest.raises(ValueError, match="refused paid/non-free model"):
        get_model_for_mode()


@pytest.mark.unit
def test_free_mode_without_explicit_model_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """free is policy-only — no hardcoded slug / model_modes.defaults.free fallback."""
    (tmp_path / "model_modes.yaml").write_text(
        "defaults:\n  test: ollama/mini\n  free: openrouter/openai/gpt-oss-20b:free\n"
    )
    monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
    monkeypatch.setenv("DIGI_LLM_MODE", "free")
    monkeypatch.delenv("DIGI_PROJECT_CONFIG", raising=False)
    monkeypatch.delenv("DIGI_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("DIGI_LLM_MODEL", raising=False)
    with pytest.raises(ValueError, match="agents.llm|DIGI_LLM_MODEL"):
        get_model_for_mode()


@pytest.mark.unit
def test_free_mode_uses_env_model(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "model_modes.yaml").write_text("defaults:\n  test: ollama/mini\n")
    monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
    monkeypatch.setenv("DIGI_LLM_MODE", "free")
    monkeypatch.delenv("DIGI_PROJECT_CONFIG", raising=False)
    monkeypatch.setenv("DIGI_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("DIGI_LLM_MODEL", "openai/gpt-oss-20b:free")
    assert get_model_for_mode() == "openrouter/openai/gpt-oss-20b:free"


@pytest.mark.unit
def test_free_mode_keeps_explicit_free_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cfg = tmp_path / "digiproject.yaml"
    cfg.write_text(
        "agents:\n"
        "  llm_mode: free\n"
        "  llm:\n"
        "    provider: openrouter\n"
        "    model: openai/gpt-oss-20b:free\n"
        "    api_key_env: OPENROUTER_API_KEY\n"
    )
    monkeypatch.setenv("DIGI_PROJECT_CONFIG", str(cfg))
    resolved = get_model_for_mode()
    assert resolved == "openrouter/openai/gpt-oss-20b:free"


@pytest.mark.unit
def test_openrouter_key_alone_does_not_force_paid(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "model_modes.yaml").write_text("defaults:\n  test: ollama/mini\n")
    monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
    monkeypatch.setenv("DIGI_LLM_MODE", "test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-present")
    monkeypatch.delenv("DIGI_PROJECT_CONFIG", raising=False)
    monkeypatch.delenv("DIGI_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("DIGI_LLM_MODEL", raising=False)
    assert get_model_for_mode() == "ollama/mini"


@pytest.mark.unit
def test_env_llm_provider_model_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "model_modes.yaml").write_text("defaults:\n  test: ollama/mini\n")
    monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
    monkeypatch.delenv("DIGI_PROJECT_CONFIG", raising=False)
    monkeypatch.setenv("DIGI_LLM_MODE", "test")
    monkeypatch.setenv("DIGI_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("DIGI_LLM_MODEL", "gemini-2.5-flash")
    assert get_model_for_mode() == "gemini/gemini-2.5-flash"


@pytest.mark.unit
def test_project_config_get_llm(tmp_path: Path) -> None:
    cfg_file = tmp_path / "digiproject.yaml"
    cfg_file.write_text(
        "agents:\n"
        "  llm_mode: free\n"
        "  llm:\n"
        "    provider: openrouter\n"
        "    model: openai/gpt-oss-20b:free\n"
    )
    cfg = DigiProjectConfig.load(str(cfg_file))
    assert cfg.get_llm_mode() == "free"
    llm = cfg.get_llm()
    assert llm is not None
    assert llm.provider == "openrouter"
    assert llm.model == "openai/gpt-oss-20b:free"
    assert llm.resolved_api_key_env() == "OPENROUTER_API_KEY"


@pytest.mark.unit
def test_effective_llm_settings_never_includes_secret(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cfg = tmp_path / "digiproject.yaml"
    cfg.write_text(
        "agents:\n"
        "  llm_mode: free\n"
        "  llm:\n"
        "    provider: openrouter\n"
        "    model: openai/gpt-oss-20b:free\n"
        "    api_key_env: OPENROUTER_API_KEY\n"
    )
    monkeypatch.setenv("DIGI_PROJECT_CONFIG", str(cfg))
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-SECRET-value")
    settings = effective_llm_settings()
    blob = str(settings)
    assert "sk-or-SECRET-value" not in blob
    assert settings["api_key_present"] is True
    assert settings["api_key_env"] == "OPENROUTER_API_KEY"
    assert settings["llm_mode"] == "free"


@pytest.mark.unit
def test_classify_free_quota_exceeded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGI_LLM_MODE", "free")
    monkeypatch.delenv("DIGI_PROJECT_CONFIG", raising=False)

    class Fake429(Exception):
        status_code = 429

    assert classify_llm_error(Fake429("rate limit exceeded")) == FREE_QUOTA_EXCEEDED
    assert is_rate_limit_error(Fake429("rpd"))


@pytest.mark.unit
def test_classify_rate_limit_outside_free(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGI_LLM_MODE", "test")
    monkeypatch.delenv("DIGI_PROJECT_CONFIG", raising=False)

    class Fake429(Exception):
        status_code = 429

    assert classify_llm_error(Fake429("too many requests")) == RATE_LIMIT


@pytest.mark.unit
def test_cli_llm_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    cfg = tmp_path / "digiproject.yaml"
    cfg.write_text(
        "agents:\n"
        "  llm_mode: free\n"
        "  llm:\n"
        "    provider: openrouter\n"
        "    model: openai/gpt-oss-20b:free\n"
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-x")
    monkeypatch.delenv("DIGI_PROJECT_CONFIG", raising=False)
    from digigraph.cli import main

    assert main(["llm-settings", "--config", str(cfg)]) == 0
    out = capsys.readouterr().out
    assert "llm_mode: free" in out
    assert "openrouter/openai/gpt-oss-20b:free" in out
    assert "sk-or-x" not in out
    assert "api_key_present: True" in out
    # CLI must not leave DIGI_PROJECT_CONFIG sticky for later tests in-process.
    assert "DIGI_PROJECT_CONFIG" not in os.environ
