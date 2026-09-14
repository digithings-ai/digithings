"""#3787 — validators exit non-zero under --strict when nothing is checked."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_refresh_model_routes_strict_exits_when_no_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load("refresh_model_routes_3787", REPO_ROOT / "scripts" / "refresh_model_routes.py")
    monkeypatch.setattr(mod, "configured_providers", lambda: [])
    assert mod.main(["--strict"]) == 1
    assert mod.main([]) == 0


def test_validate_digiquant_pools_strict_exits_without_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load(
        "validate_digiquant_pools_3787",
        REPO_ROOT / "scripts" / "validate_digiquant_pools.py",
    )
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    monkeypatch.setattr(sys, "argv", ["validate_digiquant_pools.py", "--strict"])
    assert mod.main() == 1

    monkeypatch.setattr(sys, "argv", ["validate_digiquant_pools.py"])
    assert mod.main() == 0
