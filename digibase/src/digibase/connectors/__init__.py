"""DigiBase connectors — write clients for external services (Notion, etc.).

The Notion connector requires the optional ``digibase[notion]`` extra. It is
imported lazily so that ``import digibase.connectors`` and the base connector
types remain usable even when ``notion-client`` is not installed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from digibase.connectors.base import ConnectorPayload, ConnectorResult

if TYPE_CHECKING:
    from digibase.connectors.notion import NotionConnector, UpsertResult

__all__ = [
    "ConnectorPayload",
    "ConnectorResult",
    "NotionConnector",
    "UpsertResult",
]


def __getattr__(name: str) -> Any:
    if name in ("NotionConnector", "UpsertResult"):
        from digibase.connectors import notion

        value = getattr(notion, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
