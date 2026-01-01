"""Optional imports for modules that ship outside the public package.

The repo split (#6751) moves the market-data vendor clients, the optimiser
and the proprietary strategies into private packages. Public code reaches
them through :func:`optional_attrs`, which yields ``None`` for every name when
the module is not installed. A module that is installed but fails to import
for any other reason still raises.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any  # score:allow untyped any — attributes of an optional module


def optional_attrs(module: str, *names: str) -> tuple[Any, ...]:
    """Return ``getattr(module, name)`` for each name, or all ``None`` when absent."""
    try:
        mod = import_module(module)
    except ModuleNotFoundError as exc:
        missing = exc.name or ""
        if missing and (module == missing or module.startswith(missing + ".")):
            return (None,) * len(names)
        raise
    return tuple(getattr(mod, name) for name in names)


def has_module(module: str) -> bool:
    """True when ``module`` can be found, without importing it."""
    from importlib.util import find_spec

    try:
        return find_spec(module) is not None
    except ModuleNotFoundError:  # a parent package is absent
        return False
