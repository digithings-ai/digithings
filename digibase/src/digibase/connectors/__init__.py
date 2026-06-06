"""DigiBase connectors — write clients for external services (Notion, etc.).

The Notion connector requires the optional ``digibase[notion]`` extra. It is
imported lazily so that ``import digibase.connectors`` and the base connector
types remain usable even when ``notion-client`` is not installed.
"""

from digibase.connectors.base import ConnectorPayload, ConnectorResult

__all__ = [
    "ConnectorPayload",
    "ConnectorResult",
    "NotionConnector",
    "UpsertResult",
]


def __getattr__(name: str):
    if name in ("NotionConnector", "UpsertResult"):
        from digibase.connectors import notion

        return getattr(notion, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
