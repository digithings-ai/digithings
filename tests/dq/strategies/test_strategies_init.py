"""Tests for digiquant.strategies package init: optional-nautilus import gating.

Registration must be gated on whether nautilus_trader is installed (find_spec),
not on catching every ImportError -- the latter would also hide a genuine bug
inside one of the strategy modules and leave the registry silently incomplete.
"""

from __future__ import annotations

import importlib
import importlib.util as importlib_util
import sys

import pytest

pytestmark = pytest.mark.unit


def _clear_strategies_modules() -> None:
    for name in list(sys.modules):
        if name == "digiquant.strategies" or name.startswith("digiquant.strategies."):
            del sys.modules[name]


class TestStrategiesInitOptionalNautilus:
    def test_skips_registration_when_nautilus_trader_absent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real_find_spec = importlib_util.find_spec

        def fake_find_spec(name: str, *args: object, **kwargs: object) -> object:
            if name == "nautilus_trader":
                return None
            return real_find_spec(name, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(importlib_util, "find_spec", fake_find_spec)
        _clear_strategies_modules()
        try:
            module = importlib.import_module("digiquant.strategies")
            assert module.list_strategies() == []
            # Nautilus-free submodules must stay importable regardless.
            importlib.import_module("digiquant.strategies.sdca.curve")
        finally:
            _clear_strategies_modules()

    def test_propagates_import_error_when_nautilus_trader_present_but_broken(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real_find_spec = importlib_util.find_spec

        def fake_find_spec(name: str, *args: object, **kwargs: object) -> object:
            if name == "nautilus_trader":
                # Claim the dependency is present so the gate takes the
                # import branch, regardless of whether it's actually
                # installed in the environment running this test.
                return real_find_spec("digiquant", *args, **kwargs)  # type: ignore[arg-type]
            return real_find_spec(name, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(importlib_util, "find_spec", fake_find_spec)
        _clear_strategies_modules()
        # A `None` entry in sys.modules is CPython's own signal for "this
        # module previously failed to import" -- it raises ImportError
        # immediately on the next import attempt, deterministically, whether
        # or not nautilus_trader is genuinely installed here.
        monkeypatch.setitem(sys.modules, "digiquant.strategies.bollinger_mr", None)
        try:
            with pytest.raises(ImportError):
                importlib.import_module("digiquant.strategies")
        finally:
            _clear_strategies_modules()
