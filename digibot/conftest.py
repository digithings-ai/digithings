"""Install the paid-LLM guard when this package is the pytest rootdir.

This package carries ``[tool.pytest.ini_options]``, so a run rooted here does
not load the repo-root conftest. The guard module is ``tests/paid_llm_guard.py``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_GUARD = Path(__file__).resolve().parents[1] / "tests" / "paid_llm_guard.py"
_GUARD_MODULE = "digithings_paid_llm_guard"


def _load_guard():
    loaded = sys.modules.get(_GUARD_MODULE)
    if loaded is not None:
        return loaded
    spec = importlib.util.spec_from_file_location(_GUARD_MODULE, _GUARD)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"paid LLM guard missing at {_GUARD}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_GUARD_MODULE] = module
    spec.loader.exec_module(module)
    return module


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    del config
    message = _load_guard().install()
    if message:
        pytest.exit(message, returncode=4)
