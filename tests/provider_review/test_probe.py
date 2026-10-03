# tests/provider_review/test_probe.py
"""Unit tests for scripts/provider_review/probe.py."""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from scripts.provider_review.probe import PROVIDERS, exit_code, probe_provider, run_probes


@pytest.mark.unit
def test_probe_provider_skipped_when_key_missing():
    """Returns skipped when the API key env var is absent."""
    config = {
        "base_url": "https://example.com/v1",
        "api_key_env": "MISSING_KEY_XYZ_99",
        "model": "test-model",
    }
    result = probe_provider("test", config)
    assert result["status"] == "skipped"
    assert result["latency_ms"] is None
    assert result["error"] is None
    assert "MISSING_KEY_XYZ_99" in result["reason"]


@pytest.mark.unit
def test_probe_provider_ok_on_success():
    """Returns ok status and non-null latency on a successful call."""
    config = {
        "base_url": "https://example.com/v1",
        "api_key_env": "FAKE_KEY_ABC",
        "model": "test-model",
    }
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock()
    with patch.dict(os.environ, {"FAKE_KEY_ABC": "sk-test"}):
        with patch("scripts.provider_review.probe.OpenAI", return_value=mock_client):
            result = probe_provider("test", config)
    assert result["status"] == "ok"
    assert isinstance(result["latency_ms"], int)
    assert result["error"] is None


@pytest.mark.unit
def test_probe_provider_failed_on_exception():
    """Returns failed status with error message when the call raises."""
    config = {
        "base_url": "https://example.com/v1",
        "api_key_env": "FAKE_KEY_ABC",
        "model": "test-model",
    }
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = Exception("401 Unauthorized")
    with patch.dict(os.environ, {"FAKE_KEY_ABC": "sk-test"}):
        with patch("scripts.provider_review.probe.OpenAI", return_value=mock_client):
            result = probe_provider("test", config)
    assert result["status"] == "failed"
    assert "401 Unauthorized" in result["error"]
    assert isinstance(result["latency_ms"], int)


@pytest.mark.unit
def test_run_probes_writes_json(tmp_path):
    """run_probes writes a JSON array to the output path."""
    output = tmp_path / "probe-results.json"
    config = {
        "base_url": "https://example.com/v1",
        "api_key_env": "MISSING_KEY_XYZ_99",
        "model": "test-model",
    }
    with patch("scripts.provider_review.probe.PROVIDERS", {"test": config}):
        run_probes(str(output))
    assert output.exists()
    data = json.loads(output.read_text())
    assert isinstance(data, list)
    assert data[0]["provider"] == "test"
    assert data[0]["status"] == "skipped"


@pytest.mark.unit
def test_providers_dict_has_eight_entries():
    """PROVIDERS covers exactly the 8 still-probeable providers (github_models retired #1589)."""
    assert len(PROVIDERS) == 8
    expected = {
        "gemini",
        "groq",
        "cerebras",
        "mistral",
        "nvidia_nim",
        "ollama_cloud",
        "openrouter",
        "deepseek",
    }
    assert set(PROVIDERS.keys()) == expected
    assert "github_models" not in PROVIDERS


_RETIRED_MODELS = {
    "llama-3.3-70b-versatile",
    "llama-3.3-70b",
    "meta/llama-3.3-70b-instruct",
    "rnj-1:cloud",
    "meta-llama/llama-3.3-70b-instruct:free",
    "deepseek-chat",
}

_LIVE_MODELS = {
    "gemini": "gemini-2.5-flash",
    "groq": "openai/gpt-oss-120b",
    "cerebras": "openai/gpt-oss-120b",
    "mistral": "mistral-small-latest",
    "nvidia_nim": "nvidia/llama-3.3-nemotron-super-49b-v1",
    "ollama_cloud": "gpt-oss:20b",
    "openrouter": "openai/gpt-oss-20b:free",
    "deepseek": "deepseek-v4-flash",
}


@pytest.mark.unit
def test_probe_models_are_not_retired_ids():
    """The weekly probe used to call models the providers already 404/410."""
    for name, config in PROVIDERS.items():
        assert config["model"] not in _RETIRED_MODELS
        assert config["model"] == _LIVE_MODELS[name]


@pytest.mark.unit
def test_exit_code_is_nonzero_only_when_a_probe_failed():
    """A failed probe used to print and still exit 0."""
    assert exit_code([{"status": "ok"}, {"status": "skipped"}]) == 0
    assert exit_code([{"status": "ok"}, {"status": "failed"}]) == 1
    assert exit_code([]) == 0
