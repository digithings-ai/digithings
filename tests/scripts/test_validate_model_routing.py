"""Unit tests for scripts/validate_model_routing.py routing helpers (CI --routing).

``ci.yml`` runs ``validate_model_routing.py --routing`` against real config. The
load-bearing logic is the offline resolver: exact ``phase_models`` pins, trailing-``-``
prefix matches (per-ticker H6 deliberation slugs), and ``DIGI_LLM_MODE`` / default
fallbacks when a slug is unpinned. Network ``--ping`` stays out of unit tests.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any  # score:allow untyped any — dynamically loaded module

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "validate_model_routing.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("validate_model_routing", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["validate_model_routing"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def routing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    mod = _load()
    cfg = {
        "defaults": {
            "test": "ollama/test-model",
            "medium": "ollama/medium-model",
            "best": "openrouter/best-model",
        },
        "phase_models": {
            "master-digest": "openrouter/deepseek/deepseek-v4-flash",
            "hermes/portfolio/deliberation-": "openrouter/deepseek/deepseek-v4-flash",
            # Non-prefix key (no trailing '-') must never match via startswith.
            "risk-aggressive": "openrouter/pinned-risk",
        },
    }
    (tmp_path / "model_modes.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
    monkeypatch.delenv("DIGI_LLM_MODE", raising=False)
    return mod


def test_exact_phase_slug_wins(routing: Any) -> None:
    assert (
        routing.get_model_for_phase("master-digest")
        == "openrouter/deepseek/deepseek-v4-flash"
    )


def test_trailing_dash_prefix_matches_per_ticker_slug(routing: Any) -> None:
    """#1006 — deliberation- prefix must cover hermes/portfolio/deliberation-{ticker}."""
    assert (
        routing.get_model_for_phase("hermes/portfolio/deliberation-AAPL")
        == "openrouter/deepseek/deepseek-v4-flash"
    )
    assert (
        routing.get_model_for_phase("hermes/portfolio/deliberation-DBO")
        == "openrouter/deepseek/deepseek-v4-flash"
    )


def test_prefix_key_without_trailing_dash_does_not_match_siblings(routing: Any) -> None:
    # ``risk-aggressive`` is an exact pin; ``risk-aggressive-extra`` must not inherit it.
    assert routing.get_model_for_phase("risk-aggressive") == "openrouter/pinned-risk"
    assert routing.get_model_for_phase("risk-aggressive-extra") is None


def test_unknown_slug_returns_none_from_phase_lookup(routing: Any) -> None:
    assert routing.get_model_for_phase("decision-reflector") is None


def test_resolve_falls_back_to_mode_default(routing: Any) -> None:
    assert routing._resolve("decision-reflector") == "ollama/test-model"


def test_get_model_for_mode_respects_digi_llm_mode(
    routing: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DIGI_LLM_MODE", "best")
    assert routing.get_model_for_mode() == "openrouter/best-model"
    monkeypatch.setenv("DIGI_LLM_MODE", "medium")
    assert routing.get_model_for_mode() == "ollama/medium-model"


def test_get_model_for_mode_unknown_mode_falls_to_test_then_hardcoded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mod = _load()
    (tmp_path / "model_modes.yaml").write_text(
        yaml.safe_dump({"defaults": {}, "phase_models": {}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
    monkeypatch.setenv("DIGI_LLM_MODE", "free")
    assert mod.get_model_for_mode() == "gpt-4o-mini"


def test_default_model_overrides_mode_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mod = _load()
    (tmp_path / "model_modes.yaml").write_text(
        yaml.safe_dump(
            {
                "default_model": "openrouter/explicit-default",
                "defaults": {"test": "ollama/ignored"},
                "phase_models": {},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
    assert mod.get_model_for_mode() == "openrouter/explicit-default"


@pytest.mark.parametrize(
    ("model", "provider"),
    [
        ("gemini/flash", "gemini"),
        ("ollama-cloud/qwen", "ollama-cloud"),
        ("openrouter/deepseek/deepseek-v4-flash", "openrouter"),
        ("xai/grok", "xai"),
        ("gpt-4o-mini", "default-openai"),
        ("ollama/qwen3:8b", "default-openai"),
    ],
)
def test_provider_prefix_classification(routing: Any, model: str, provider: str) -> None:
    assert routing._provider(model) == provider


def test_repo_config_pins_h6_deliberation_prefix_and_master_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Smoke against committed config — CI --routing depends on these pins."""
    mod = _load()
    monkeypatch.delenv("DIGI_CONFIG_PATH", raising=False)
    assert (
        mod.get_model_for_phase("hermes/portfolio/deliberation-AAPL")
        == "openrouter/deepseek/deepseek-v4-flash"
    )
    assert mod.get_model_for_phase("master-digest") == "openrouter/deepseek/deepseek-v4-flash"
    assert (REPO_ROOT / "config" / "model_modes.yaml").is_file()
