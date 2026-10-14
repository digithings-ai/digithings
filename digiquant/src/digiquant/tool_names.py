"""Public and legacy names for the Gloomberb MCP family.

The tools are programmatic extensions of the Gloomberb platform. Their public
MCP name uses the ``gloomberb_`` prefix (the same shape as ``luxalgo_``).
``digifetch_`` is the internal dispatch key. Invoke and the in-process
dispatcher still accept it and call the same handler. It is not registered
as a second MCP tool.
"""

from __future__ import annotations

LEGACY_PREFIX = "digifetch_"
CANONICAL_PREFIX = "gloomberb_"

#: Leading sentence on every public Gloomberb tool description.
GLOOMBERB_PLATFORM_NOTE = "Programmatic extension of the Gloomberb platform."


def canonical_tool_name(name: str) -> str:
    """Return the public name. ``digifetch_quote`` becomes ``gloomberb_quote``."""
    if name.startswith(LEGACY_PREFIX):
        return CANONICAL_PREFIX + name[len(LEGACY_PREFIX) :]
    return name


def legacy_tool_name(name: str) -> str:
    """Return the compatibility name. ``gloomberb_quote`` becomes ``digifetch_quote``."""
    if name.startswith(CANONICAL_PREFIX):
        return LEGACY_PREFIX + name[len(CANONICAL_PREFIX) :]
    return name


def gloomberb_family(name: str) -> bool:
    """True when *name* is a Gloomberb tool under either prefix."""
    return name.startswith(LEGACY_PREFIX) or name.startswith(CANONICAL_PREFIX)
