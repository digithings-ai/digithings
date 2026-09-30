"""Pydantic v2 models for the LuxAlgo Library thin wrap (#4779 P0).

This package is a thin client over the hosted LuxAlgo MCP
(``https://mcp.luxalgo.com/mcp``, streamable HTTP JSON-RPC): upstream result
payloads are passed through as ``data`` unchanged (upstream shapes vary and are
only partly probe-verified), wrapped in the shared :class:`LuxalgoEnvelope` /
:class:`LuxalgoError` contract.

Layout:

* :mod:`digiquant.data.luxalgo.models` - input/output models and the shared
  ``LuxalgoEnvelope[T]``/``LuxalgoError`` contract.
* :mod:`digiquant.data.luxalgo.client` - the JSON-RPC client (fixed endpoint,
  error mapping, TTL cache, kill switch, server-side ``context`` injection).
* :mod:`digiquant.data.luxalgo.agent_tools` - the in-process agent surface
  (manifest-generated schemas, research subset, dispatcher).

Input models type the probe-verified core fields and allow the rest
(``extra="allow"``): the upstream parameter surface beyond ``query``/``slug``/
``limit``/``family`` is unverified, and a thin wrap must not reject a
parameter the upstream accepts. The JSON-RPC layer itself only ever forwards
JSON values.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Generic, Literal, TypeVar  # score:allow untyped any — wire JSON

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

__all__ = [
    "SOURCE",
    "PROVIDER_ID",
    "ErrorCode",
    "LuxalgoError",
    "LuxalgoEnvelope",
    # inputs
    "LibrarySearchInput",
    "LibraryGetConceptInput",
    "LibraryGetIndicatorInput",
    "LibraryListConceptsInput",
    "LibraryListIndicatorsInput",
    "LibraryListTagsInput",
    "LibraryListFamiliesInput",
    "LibraryGetFamilyInput",
    # concrete envelopes
    "LibrarySearchEnvelope",
    "LibraryGetConceptEnvelope",
    "LibraryGetIndicatorEnvelope",
    "LibraryListConceptsEnvelope",
    "LibraryListIndicatorsEnvelope",
    "LibraryListTagsEnvelope",
    "LibraryListFamiliesEnvelope",
    "LibraryGetFamilyEnvelope",
    "envelope_error",
]

SOURCE: Literal["luxalgo"] = "luxalgo"
PROVIDER_ID = "luxalgo-hosted-mcp"

ErrorCode = Literal[
    "not_found",
    "rate_limited",
    "upstream_error",
    "invalid_input",
]

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class _LuxalgoModel(BaseModel):
    """Base for LuxAlgo models: extras preserved (upstream shapes vary)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class _InputModel(BaseModel):
    """Base for tool inputs: core fields typed, upstream extras forwarded."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")


# ---------------------------------------------------------------------------
# Shared envelope / error contract
# ---------------------------------------------------------------------------


class LuxalgoError(_LuxalgoModel):
    """Typed failure carried in the envelope ``data`` slot.

    ``retryable`` is true only for wire 5xx/timeouts; the client never retries
    404/429 and never retries the kill-switch gate.
    """

    code: ErrorCode
    message: str
    retryable: bool = False


DataT = TypeVar("DataT")


class LuxalgoEnvelope(_LuxalgoModel, Generic[DataT]):
    """The one shared envelope, generic over the tool payload.

    ``data`` is either the upstream result payload (passed through unchanged)
    or a typed :class:`LuxalgoError`; tools never raise to the transport.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow", frozen=True)

    source: Literal["luxalgo"] = "luxalgo"
    provider_id: str = PROVIDER_ID
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    stale: bool = False
    warnings: list[str] = Field(default_factory=list)
    data: DataT | LuxalgoError


def envelope_error(
    code: ErrorCode, message: str, *, retryable: bool = False
) -> LuxalgoEnvelope[Any]:
    """Build an error envelope for the kill-switch / client-fault paths."""
    return LuxalgoEnvelope[Any](data=LuxalgoError(code=code, message=message, retryable=retryable))


# ---------------------------------------------------------------------------
# Input models (one per tool; core fields are probe-verified)
# ---------------------------------------------------------------------------


class LibrarySearchInput(_InputModel):
    """Full-text Library search (probe-verified: ``query`` + ``limit``)."""

    query: NonEmptyStr
    limit: int = Field(default=10, ge=1, le=50)


class LibraryGetConceptInput(_InputModel):
    """One concept page by slug (probe-verified: ``slug``, e.g. ``"rsi"``)."""

    slug: NonEmptyStr


class LibraryGetIndicatorInput(_InputModel):
    """One indicator's metadata by slug (no source code — license boundary)."""

    slug: NonEmptyStr


class LibraryListConceptsInput(_InputModel):
    """List concept pages; ``limit`` bounds the page."""

    limit: int = Field(default=50, ge=1, le=200)


class LibraryListIndicatorsInput(_InputModel):
    """List indicator entries; ``limit`` bounds the page."""

    limit: int = Field(default=50, ge=1, le=200)


class LibraryListTagsInput(_InputModel):
    """List Library tags (takes no parameters upstream)."""


class LibraryListFamiliesInput(_InputModel):
    """List indicator families (takes no parameters upstream)."""


class LibraryGetFamilyInput(_InputModel):
    """One indicator family by name/slug."""

    family: NonEmptyStr


# ---------------------------------------------------------------------------
# Concrete envelopes (data slot is the upstream payload, passed through)
# ---------------------------------------------------------------------------

LibrarySearchEnvelope = LuxalgoEnvelope[Any]
LibraryGetConceptEnvelope = LuxalgoEnvelope[Any]
LibraryGetIndicatorEnvelope = LuxalgoEnvelope[Any]
LibraryListConceptsEnvelope = LuxalgoEnvelope[Any]
LibraryListIndicatorsEnvelope = LuxalgoEnvelope[Any]
LibraryListTagsEnvelope = LuxalgoEnvelope[Any]
LibraryListFamiliesEnvelope = LuxalgoEnvelope[Any]
LibraryGetFamilyEnvelope = LuxalgoEnvelope[Any]
