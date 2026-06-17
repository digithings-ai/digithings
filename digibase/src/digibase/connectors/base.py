"""Abstract connector protocol for write actions to external services."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any  # noqa: PYI041


@dataclass
class ConnectorPayload:
    """Data sent to an external service."""

    operation: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConnectorResult:
    """Result from a connector write operation."""

    success: bool
    external_id: str = ""
    error: str = ""
