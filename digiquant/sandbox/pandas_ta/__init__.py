"""Compatibility shim: expose pandas-ta-classic as ``pandas_ta``.

``pandas-ta-classic`` installs the top-level package ``pandas_ta_classic``.
research agent snippets and digiquant sandbox acceptance (#396) use the historical
``import pandas_ta`` name from the deleted ``pandas-ta`` project. Re-export so
both imports work inside the sandbox image.
"""

from __future__ import annotations

from pandas_ta_classic import *  # noqa: F403

try:
    from pandas_ta_classic import __version__ as __version__
except ImportError:  # pragma: no cover — older classic wheels
    __version__ = "unknown"

# Prefer the classic package's public surface; keep an explicit alias for agents
# that check the module path.
__all__ = [name for name in globals() if not name.startswith("_")]
