"""Unit tests for the slimmed digiquant/scripts/research/validate-providers.py.

Fail-fast house (Cheaper Inference): the preflight runs no LLM checks — provider
errors surface from the real run. What remains is env-var gating, the bounded
digillm/production-tier environment setup, and graph dry-runs. These tests pin
that contract without touching any provider.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from collections.abc import Generator
from pathlib import Path
from typing import Any  # score:allow untyped any — dynamically loaded module
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = REPO_ROOT / "digiquant" / "scripts" / "research" / "validate-providers.py"

pytestmark = pytest.mark.unit


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("validate_providers", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def vp() -> Any:
    return _load_module()


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")
    monkeypatch.setenv("CHEAPERINFERENCE_API_KEY", "ci_live_test")


@pytest.fixture(autouse=True)
def _hermetic_environ() -> Generator[None, None, None]:
    """Restore real env after each test.

    ``_configure_preflight_environment`` (via ``apply_digiquant_house_env``)
    mutates ``os.environ`` for real — including ``OPENAI_API_BASE``. Without a
    restore that leak changes digillm routing for whichever suite runs next.
    """
    snapshot = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(snapshot)


def test_check_env_vars_passes_with_house_key(vp: Any) -> None:
    vp.results.clear()
    assert vp.check_env_vars() is True


def test_check_env_vars_fails_without_house_key(vp: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CHEAPERINFERENCE_API_KEY", raising=False)
    vp.results.clear()
    assert vp.check_env_vars() is False


def test_preflight_configures_bounded_digillm_env(vp: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """digillm reads timeout/retry env at import — preflight must set them first (#2528/#2531)."""
    monkeypatch.delenv("DIGILLM_REQUEST_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("DIGILLM_EMPTY_RETRY_MAX", raising=False)
    vp._configure_preflight_environment()
    assert os.environ["DIGILLM_REQUEST_TIMEOUT_SECONDS"] == str(
        vp._PREFLIGHT_REQUEST_TIMEOUT_SECONDS
    )
    assert os.environ["DIGILLM_EMPTY_RETRY_MAX"] == str(vp._PREFLIGHT_EMPTY_RETRY_MAX)


def test_preflight_applies_house_env(vp: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Preflight must call apply_digiquant_house_env so dry-runs match production (#2532).

    The house function only points the default client (no model-policy env) —
    assert the rewrite ran and that no dead provider-knob env was written.
    """
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("CHEAPERINFERENCE_API_KEY", raising=False)
    vp._configure_preflight_environment()
    assert os.environ.get("OPENAI_API_BASE", "") == "https://openrouter.ai/api/v1"
    assert "OPENROUTER_ALLOWED_MODELS" not in os.environ
    assert "OPENROUTER_COST_QUALITY_TRADEOFF" not in os.environ


def test_no_llm_checks_remain(vp: Any) -> None:
    """Fail-fast: the preflight must not define any provider ping checks."""
    for name in (
        "check_openrouter",
        "check_openrouter_structured",
        "check_openrouter_function_tools",
        "check_openrouter_web_search",
    ):
        assert not hasattr(vp, name), f"{name} must be removed"
    with (
        patch.object(sys, "argv", ["validate-providers.py"]),
        patch.object(vp, "check_supabase", return_value=True),
        patch.object(vp, "check_dry_run", return_value=True),
    ):
        vp.results.clear()
        assert vp.main() == 0
