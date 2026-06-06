"""DigiBase connectors — write clients for external services (Notion, etc.).

The Notion connector requires the optional ``digibase[notion]`` extra. It is
imported lazily so that ``import digibase.connectors`` and the base connector
types remain usable even when ``notion-client`` is not installed.
"""

from __future__ import annotations

from typing import Any

from digibase.connectors.base import ConnectorPayload, ConnectorResult

__all__ = [
    "ConnectorPayload",
    "ConnectorResult",
    "NotionConnector",
    "UpsertResult",
]

# Placeholders satisfy static export checks; resolved on first access via __getattr__.
NotionConnector: Any = None
UpsertResult: Any = None


def __getattr__(name: str) -> Any:
    if name in ("NotionConnector", "UpsertResult"):
        from digibase.connectors import notion

        value = getattr(notion, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
