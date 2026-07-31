"""DigiBase connectors — write clients for external services (Supabase, etc.).

The Supabase connector requires the optional ``digibase[supabase]`` extra. It is
imported lazily so that ``import digibase.connectors`` and the base connector
types remain usable even when ``supabase`` is not installed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from digibase.connectors.base import ConnectorPayload, ConnectorResult

if TYPE_CHECKING:
    from digibase.connectors.supabase import (
        SupabaseConnector,
        SupabaseReadResult,
        SupabaseWriteResult,
    )

# Only always-defined names are advertised as wildcard exports. The Supabase
# names are optional (they require digibase[supabase]) and are accessible via
# __getattr__ lazy lookup, not guaranteed to be present.
__all__ = [
    "ConnectorPayload",
    "ConnectorResult",
]


def __getattr__(name: str) -> Any:
    if name in ("SupabaseConnector", "SupabaseReadResult", "SupabaseWriteResult"):
        from digibase.connectors import supabase

        value = getattr(supabase, name)
        globals()[name] = value  # cache for subsequent attribute lookups
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
