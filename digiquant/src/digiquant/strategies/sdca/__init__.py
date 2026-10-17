"""Compatibility alias: ``digiquant.strategies.sdca`` -> ``digiquant.strategies.lab``.

The SDCA research code now lives in :mod:`digiquant.strategies.lab`, the
asset-neutral strategy lab. This package is a **lazy** alias, so every existing
importer keeps working unchanged -- the 55 test modules under
``tests/dq/strategies/sdca``, ``digiquant.strategies.__init__``, and the
``digiquant/scripts/`` one-offs -- and ``mock.patch`` keeps patching the same
object the live code uses.

**Identity is the contract.** ``sdca.X is lab.X`` holds for every module, and
each alias is registered in :data:`sys.modules` under the legacy dotted path so
both spellings resolve to exactly one object.

Laziness is deliberate: importing the 38 modules eagerly would fire every
import-time side effect (``nautilus_strategy`` registers a strategy,
``presets`` builds a ``TypeAdapter``, and three modules configure loggers) as a
cost of merely naming the package.
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import pkgutil
import sys

_ALIAS_ROOT = __name__  # digiquant.strategies.sdca
_TARGET_ROOT = "digiquant.strategies.lab"

#: Attributes the import machinery rebinds while initialising an aliased
#: module. They are restored by :meth:`_AliasLoader.exec_module`.
_CANONICAL_ATTRS = ("__name__", "__qualname__", "__spec__", "__loader__", "__package__")


def _target_name(legacy_name: str) -> str:
    """Map ``digiquant.strategies.sdca.x`` onto ``digiquant.strategies.lab.x``."""
    return _TARGET_ROOT + legacy_name[len(_ALIAS_ROOT) :]


def __getattr__(name: str):
    """Resolve ``sdca.<module>`` on demand, one module at a time."""
    if name.startswith("__"):
        raise AttributeError(name)
    legacy = f"{_ALIAS_ROOT}.{name}"
    try:
        module = importlib.import_module(_target_name(legacy))
    except ModuleNotFoundError:
        raise AttributeError(f"module {_ALIAS_ROOT!r} has no attribute {name!r}") from None
    # Register the legacy dotted path so a later
    # ``import digiquant.strategies.sdca.<name>`` returns this same object
    # instead of re-running the finder, and so both spellings agree.
    sys.modules[legacy] = module
    return module


def __dir__() -> list[str]:
    return sorted(set(globals()) | {m.name for m in pkgutil.iter_modules(__path__)})


class _AliasLoader(importlib.abc.Loader):
    """Loads an aliased module by returning the already-importable lab module.

    The canonical dotted name is carried on the loader instance rather than
    re-derived from ``module.__name__``: on importlib 3.12 ``_init_module_attrs``
    leaves the dunders of a module returned by ``create_module`` untouched, so
    ``module.__name__`` is already canonical and slicing ``_ALIAS_ROOT`` off it
    yields the wrong offset (``digiquant.strategies.labvaluation``). ``spec.name``
    is the only authoritative answer to "what was asked for".
    """

    def __init__(self, canonical_name: str) -> None:
        self.canonical_name = canonical_name

    def create_module(self, spec):
        return importlib.import_module(self.canonical_name)

    def exec_module(self, module) -> None:
        # Point this object's ``__spec__``, ``__loader__`` and ``__package__``
        # back at the canonical module so the alias is a faithful stand-in.
        canonical = importlib.import_module(self.canonical_name)
        for attr in _CANONICAL_ATTRS:
            try:
                setattr(module, attr, getattr(canonical, attr))
            except AttributeError:
                pass


class _AliasFinder(importlib.abc.MetaPathFinder):
    """Maps any ``digiquant.strategies.sdca.<mod>`` onto its ``lab`` twin."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname == _ALIAS_ROOT or not fullname.startswith(_ALIAS_ROOT + "."):
            return None
        return importlib.machinery.ModuleSpec(
            fullname, _AliasLoader(_target_name(fullname)), is_package=False
        )


if not any(isinstance(f, _AliasFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, _AliasFinder())
