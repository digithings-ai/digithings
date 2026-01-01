"""Root conftest: optional path setup, plus the paid-LLM guard.

Packages are found via the venv editable install. The guard lives in
``tests/paid_llm_guard.py``. A package with its own ``[tool.pytest.ini_options]``
does not load this file; that package's ``conftest.py`` installs the same guard.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_GUARD = Path(__file__).resolve().parent / "tests" / "paid_llm_guard.py"
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
