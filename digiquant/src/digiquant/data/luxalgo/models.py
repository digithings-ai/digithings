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
    "EdgeSymbolsInput",
    "EdgePresetsInput",
    "EdgeReportInput",
    "LUXALGO_TRACKERS_ALLOWED_DATASETS",
    "TrackersDatasetName",
    "TrackersDatasetsInput",
    "TrackersLatestInput",
    "TrackersTickerInput",
    # concrete envelopes
    "LibrarySearchEnvelope",
    "LibraryGetConceptEnvelope",
    "LibraryGetIndicatorEnvelope",
    "LibraryListConceptsEnvelope",
    "LibraryListIndicatorsEnvelope",
    "LibraryListTagsEnvelope",
    "LibraryListFamiliesEnvelope",
    "LibraryGetFamilyEnvelope",
    "EdgeSymbolsEnvelope",
    "EdgePresetsEnvelope",
    "EdgeReportEnvelope",
    "TrackersDatasetsEnvelope",
    "TrackersLatestEnvelope",
    "TrackersTickerEnvelope",
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
# Input models — Edge Stats preset reads (#4844)
# ---------------------------------------------------------------------------
#
# Probe-verified 2026-09-30 against the hosted tools/list: edge_symbols takes
# no parameters, edge_presets takes an optional category, edge_report takes a
# preset id + symbol (both required).


class EdgeSymbolsInput(_InputModel):
    """Coverage of the hosted Edge Stats store (takes no parameters upstream)."""


class EdgePresetsInput(_InputModel):
    """Preset catalog; ``category`` narrows to one category when given."""

    category: str | None = None


class EdgeReportInput(_InputModel):
    """One precomputed preset result (probe-verified: ``preset`` + ``symbol``)."""

    preset: NonEmptyStr
    symbol: NonEmptyStr


# ---------------------------------------------------------------------------
# Input models — Market Trackers live-query companions (#4844)
# ---------------------------------------------------------------------------
#
# Probe-verified 2026-09-30: trackers_datasets takes an optional dataset id,
# trackers_latest takes a required dataset plus ticker/text/where/sort/limit/
# offset, trackers_ticker takes a required ticker plus year/limit. Bounds below
# mirror the upstream input schemas (limit caps, ticker/text lengths, year
# range). Dataset membership is NOT upstream's to decide: it is pinned
# client-side in :data:`LUXALGO_TRACKERS_ALLOWED_DATASETS` (DIG-1479), so a
# newly published dataset is refused until a reviewed code change adds it.
# Upstream validating membership is not a legal classification. Adding a
# dataset is a code review with a statute attached, not an upstream event.
# trackers_query (ad-hoc dump search) is deliberately NOT wrapped — dumps stay
# the source of record.

#: The trackers datasets this service will ask for. The only sanctioned way to
#: widen it is to edit this frozenset in a reviewed change; there is no
#: environment override, in either direction.
LUXALGO_TRACKERS_ALLOWED_DATASETS: frozenset[str] = frozenset(
    {
        "insider-transactions",  # EDGAR Form 4, 17 C.F.R. 240.16a-3
        "thirteenf-holdings",  # 13F-HR, 15 U.S.C. 78m(a)(6)
        "short-volume",  # FINRA daily
        "lobbying-filings",  # LDA, 2 U.S.C. 1601 et seq.
        "gov-contracts",  # USAspending, 31 U.S.C. 3512
        # RISK-ACCEPTED 2026-10-06 (business owner: Chris). Counsel classified these
        # rows as periodic transaction reports under 5 U.S.C. 13105(l), therefore
        # "reports" for 13107(c), and advised refusal (DIG-1472, CONFIRMED). The
        # business owner decided to keep this dataset in service. That is a decision
        # to accept the 13107(c)(2) exposure, not a legal clearance.
        # digifetch_congress_trades stays in REFUSED_TOOLS for the same data class.
        # Do not read the entry below as counsel clearance.
        "congress-trades",
    }
)

#: The pydantic-facing spelling of the six datasets above. Hand-written rather
#: than derived — a ``Literal`` cannot be built from a frozenset — so it is a
#: second place to forget. Drift is caught, not prevented, by
#: ``test_the_literal_alias_and_the_frozenset_agree`` (corrected in DIG-1519).
TrackersDatasetName = Literal[
    "insider-transactions",
    "thirteenf-holdings",
    "short-volume",
    "lobbying-filings",
    "gov-contracts",
    "congress-trades",
]

TickerStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=12)]
TrackerTextStr = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
SortOrder = Literal["newest", "oldest"]


class TrackersDatasetsInput(_InputModel):
    """Trackers catalog; ``dataset`` selects one dataset's detailed view when given."""

    dataset: TrackersDatasetName | None = None


class TrackersLatestInput(_InputModel):
    """Newest ingestion day's rows for one dataset (freshness/ad-hoc lookups only)."""

    dataset: TrackersDatasetName
    ticker: TickerStr | None = None
    text: TrackerTextStr | None = None
    where: dict[str, str | int | bool] | None = None
    sort: SortOrder | None = None
    limit: int = Field(default=25, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class TrackersTickerInput(_InputModel):
    """One ticker's newest rows across every ticker-bearing dataset for one year."""

    ticker: TickerStr
    year: int | None = Field(default=None, ge=1900, le=2100)
    limit: int = Field(default=5, ge=1, le=25)


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
EdgeSymbolsEnvelope = LuxalgoEnvelope[Any]
EdgePresetsEnvelope = LuxalgoEnvelope[Any]
EdgeReportEnvelope = LuxalgoEnvelope[Any]
TrackersDatasetsEnvelope = LuxalgoEnvelope[Any]
TrackersLatestEnvelope = LuxalgoEnvelope[Any]
TrackersTickerEnvelope = LuxalgoEnvelope[Any]
