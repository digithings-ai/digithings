"""Load optional third-party orchestrator tools via setuptools entry points (group: digigraph.tools)."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def load_entrypoint_tools() -> None:
    """Import each entry point ``digigraph.tools``; if the target is callable, call it with no args.

    Packages register tools by defining ``[project.entry-points."digigraph.tools"]`` pointing at a
    callable that invokes :func:`register_tool` / :func:`register_skill` as side effects.
    """
    try:
        from importlib.metadata import entry_points
    except ImportError:
        return

    eps: Any
    grouped = entry_points()
    if hasattr(grouped, "select"):
        eps = grouped.select(group="digigraph.tools")
    else:
        eps = grouped.get("digigraph.tools", ())

    for ep in eps:
        try:
            fn = ep.load()
            if callable(fn):
                fn()
        except Exception as exc:
            logger.warning("digigraph.tools entry point %s failed: %s", ep.name, exc)


__all__ = ["load_entrypoint_tools"]
