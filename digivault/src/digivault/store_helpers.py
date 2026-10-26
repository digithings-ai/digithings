"""Helpers shared by more than one store backend.

These live outside ``store.py`` so the backends agree on one behaviour without
widening the :class:`~digivault.store.VaultStore` protocol.
"""

from __future__ import annotations

import os

__all__ = ["escape_like", "first_env"]


def first_env(*names: str) -> str:
    """Return the first non-blank value among *names*, or ``""`` when none is set."""
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def escape_like(value: str) -> str:
    """Escape ``\\``, ``%`` and ``_`` so *value* is a literal LIKE prefix, not a pattern.

    ``%`` and ``_`` are LIKE wildcards; binding a caller-supplied path prefix into a
    ``LIKE`` pattern without escaping them lets ``_`` in a prefix match any single
    character and leak a sibling corpus's rows across the tenant-isolation boundary —
    verified: an unescaped prefix ``clients/my_corp`` also matches
    ``clients/myXcorp/...``. Must be paired with ``LIKE ? ESCAPE '\\'`` in the SQL and
    applied only to the prefix component, never the trailing ``/%`` wildcard suffix.
    """
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
