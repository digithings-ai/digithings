"""Unit tests for the two provider tables #5029 moved out of scripts/.

``scripts/provider_review/probe.py`` and ``scripts/validate-provider-keys.py``
each carried a hardcoded ``PROVIDERS`` dict whose ``model`` / ``model_default``
values are provider facts, not probing facts. Both now load
``config/provider-probes.json`` and ``config/provider-key-checks.json``.

The loaders are the risky part: each one runs at *import* time and feeds a
script whose failure mode is a confident report. A silently empty table would
make ``validate-provider-keys.py`` print "all configured providers OK", and a
silently-dropped provider would make the weekly probe report "every provider
failed" and read as an outage. So both are fail-loud, and these tests pin that
they stay loud rather than degrading to an empty dict.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any  # score:allow untyped any — dynamically loaded modules

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, relative: str) -> Any:
    """Load a scripts/ module by path — ``scripts/`` is not a package."""
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def probe_mod() -> Any:
    return _load("refresh_probe_module", "scripts/provider_review/probe.py")


@pytest.fixture
def keys_mod(monkeypatch: pytest.MonkeyPatch) -> Any:
    # The key table's env overlay reads the process env at import time, so the
    # host's OLLAMA_API_KEY / OPENAI_API_BASE would otherwise leak into the
    # assertions below.
    for var in ("OLLAMA_API_KEY", "OPENAI_API_KEY", "OPENAI_API_BASE"):
        monkeypatch.delenv(var, raising=False)
    return _load("validate_provider_keys_module", "scripts/validate-provider-keys.py")


# ── probe.py ────────────────────────────────────────────────────────────────


def test_probe_table_is_config_not_code(probe_mod: Any) -> None:
    """The loaded table must match the committed config file byte for byte.

    This is the whole point of the move: if someone re-adds a literal table to
    probe.py this file is where it shows up.
    """
    committed = json.loads(
        (REPO_ROOT / "config" / "provider-probes.json").read_text(encoding="utf-8")
    )
    assert probe_mod.PROVIDERS == committed["providers"]


def test_probe_table_carries_a_model_for_every_provider(probe_mod: Any) -> None:
    for name, cfg in probe_mod.PROVIDERS.items():
        assert cfg.get("model"), f"{name} has no probe model"
        assert cfg.get("base_url"), f"{name} has no base_url"
        assert cfg.get("api_key_env"), f"{name} has no api_key_env"


def test_probe_loader_is_fail_loud_on_a_missing_table(probe_mod: Any, tmp_path: Path) -> None:
    probe_mod.PROBE_CONFIG_PATH = tmp_path / "nope.json"
    with pytest.raises(RuntimeError, match="probe table missing"):
        probe_mod._load_providers()


def test_probe_loader_is_fail_loud_on_malformed_json(probe_mod: Any, tmp_path: Path) -> None:
    bad = tmp_path / "provider-probes.json"
    bad.write_text("{not json", encoding="utf-8")
    probe_mod.PROBE_CONFIG_PATH = bad
    with pytest.raises(RuntimeError, match="not valid JSON"):
        probe_mod._load_providers()


def test_probe_loader_rejects_an_empty_provider_set(probe_mod: Any, tmp_path: Path) -> None:
    """An empty table would make the weekly review report a total outage."""
    empty = tmp_path / "provider-probes.json"
    empty.write_text(json.dumps({"providers": {}}), encoding="utf-8")
    probe_mod.PROBE_CONFIG_PATH = empty
    with pytest.raises(RuntimeError, match="no non-empty 'providers'"):
        probe_mod._load_providers()


def test_probe_loader_rejects_a_provider_missing_its_keys(probe_mod: Any, tmp_path: Path) -> None:
    partial = tmp_path / "provider-probes.json"
    partial.write_text(
        json.dumps({"providers": {"groq": {"base_url": "https://api.groq.com/openai/v1"}}}),
        encoding="utf-8",
    )
    probe_mod.PROBE_CONFIG_PATH = partial
    with pytest.raises(RuntimeError, match=r"missing base_url/api_key_env/model"):
        probe_mod._load_providers()


# ── validate-provider-keys.py ───────────────────────────────────────────────


def test_key_check_table_is_config_not_code(keys_mod: Any) -> None:
    committed = json.loads(
        (REPO_ROOT / "config" / "provider-key-checks.json").read_text(encoding="utf-8")
    )
    for name, cfg in committed["providers"].items():
        assert keys_mod.PROVIDERS[name]["model_default"] == cfg["model_default"]
        assert keys_mod.PROVIDERS[name]["label"] == cfg["label"]


def test_ollama_base_url_override_still_comes_from_the_env(
    keys_mod: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The proxy override is an environment fact, so it must stay in code."""
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:11434/v1")
    providers = keys_mod._apply_env_overrides(keys_mod._load_providers())
    assert providers["ollama"]["base_url"] == "http://127.0.0.1:11434/v1"


def test_ollama_api_key_falls_back_to_openai_api_key(
    keys_mod: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CI maps secrets.OLLAMA_API_KEY onto OPENAI_API_KEY, so a shell holding
    only the latter must still find a key to smoke-test with."""
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    providers = keys_mod._apply_env_overrides(keys_mod._load_providers())
    assert providers["ollama"]["api_key_env"] == "OPENAI_API_KEY"


def test_ollama_api_key_prefers_the_specific_var(
    keys_mod: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OLLAMA_API_KEY", "oll-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    providers = keys_mod._apply_env_overrides(keys_mod._load_providers())
    assert providers["ollama"]["api_key_env"] == "OLLAMA_API_KEY"


def test_env_overlay_leaves_other_providers_alone(
    keys_mod: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:11434/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    providers = keys_mod._apply_env_overrides(keys_mod._load_providers())
    committed = json.loads(
        (REPO_ROOT / "config" / "provider-key-checks.json").read_text(encoding="utf-8")
    )
    for name in ("gemini", "openrouter"):
        assert providers[name] == committed["providers"][name]


def test_key_check_loader_is_fail_loud_on_a_missing_table(keys_mod: Any, tmp_path: Path) -> None:
    keys_mod.CHECK_CONFIG_PATH = tmp_path / "nope.json"
    with pytest.raises(RuntimeError, match="provider check table missing"):
        keys_mod._load_providers()


def test_key_check_loader_rejects_an_empty_provider_set(keys_mod: Any, tmp_path: Path) -> None:
    """An empty set would print 'all configured providers OK' — the most
    dangerous output a validation script can produce."""
    empty = tmp_path / "provider-key-checks.json"
    empty.write_text(json.dumps({"providers": {}}), encoding="utf-8")
    keys_mod.CHECK_CONFIG_PATH = empty
    with pytest.raises(RuntimeError, match="no non-empty 'providers'"):
        keys_mod._load_providers()


def test_key_check_loader_rejects_a_provider_missing_its_keys(
    keys_mod: Any, tmp_path: Path
) -> None:
    partial = tmp_path / "provider-key-checks.json"
    partial.write_text(
        json.dumps(
            {"providers": {"gemini": {"label": "Gemini", "base_url": "https://x/v1"}}},
        ),
        encoding="utf-8",
    )
    keys_mod.CHECK_CONFIG_PATH = partial
    with pytest.raises(RuntimeError, match=r"missing \['api_key_env'"):
        keys_mod._load_providers()
