"""Attribution + external-link conventions for LuxAlgo-sourced values (#4779 P0, #4844).

Canonical attribution is **"Sourced from LuxAlgo Library"** plus the upstream
canonical URL (``url`` / ``md_url``) wherever a value is rendered outside the
agent loop. Deep links are the Library page URLs the upstream returns per row —
there is no URL scheme of our own to construct.

The Edge Stats (#4844) and Market Trackers (#4844) families carry their own
attribution sets via :data:`TOOL_ATTRIBUTION` (edge-stats engine repo / CC0
trackers-dumps repo as the fallback link); :func:`attribution_fields_for`
selects them per tool.

License boundary (scope §P0, guard #4845): the Library search/concept/
indicator-metadata reads are research references. Indicator *source code*
(``library_get_source_code``) is CC BY-NC-SA and is deliberately NOT wrapped —
no Pine source is embedded in a paid product surface. A commercial Library
license is an explicit opt-in (``LUXALGO_COMMERCIAL_LICENSE``, default OFF;
see :mod:`digiquant.data.luxalgo.license_guard`), and every payload states
the flag state it was produced under (``commercial_license`` /
``license_state``) so a rendered payload shows whether source-code use was
licensed.
"""

from __future__ import annotations

from digiquant.stats.honesty import DISCLAIMER as HONESTY_DISCLAIMER

from .license_guard import (
    LUXALGO_LICENSE_STATE_NOTE_DISABLED,
    LUXALGO_LICENSE_STATE_NOTE_ENABLED,
    commercial_license_note,
    luxalgo_commercial_license_enabled,
)

__all__ = [
    "LUXALGO_ATTRIBUTION",
    "LUXALGO_LIBRARY_URL",
    "LUXALGO_LICENSE_NOTE",
    "LUXALGO_LICENSE_STATE_NOTE_ENABLED",
    "LUXALGO_LICENSE_STATE_NOTE_DISABLED",
    "commercial_license_note",
    "LUXALGO_EDGE_ATTRIBUTION",
    "LUXALGO_EDGE_URL",
    "LUXALGO_EDGE_LICENSE_NOTE",
    "LUXALGO_TRACKERS_ATTRIBUTION",
    "LUXALGO_TRACKERS_URL",
    "LUXALGO_TRACKERS_LICENSE_NOTE",
    "TOOL_ATTRIBUTION",
    "attribution_fields",
    "attribution_fields_for",
]

LUXALGO_ATTRIBUTION = "Sourced from LuxAlgo Library"
LUXALGO_LIBRARY_URL = "https://luxalgo.com/library/"
LUXALGO_LICENSE_NOTE = (
    "Research reference only: concept/indicator metadata, never indicator "
    "source code (CC BY-NC-SA; not embedded in paid product surfaces)."
)

LUXALGO_EDGE_ATTRIBUTION = "Sourced from LuxAlgo Edge Stats (hosted store)"
LUXALGO_EDGE_URL = "https://github.com/LuxAlgo/edge-stats"
LUXALGO_EDGE_LICENSE_NOTE = (
    "Precomputed session statistics from the open-source edge-stats engine "
    "over free market data. Historical conditional frequencies with sample "
    "sizes — never a pipeline primary, never predictions, never advice."
)

LUXALGO_TRACKERS_ATTRIBUTION = "Sourced from LuxAlgo Market Trackers (CC0 public-record dumps)"
LUXALGO_TRACKERS_URL = "https://github.com/LuxAlgo/market-trackers-data"
LUXALGO_TRACKERS_LICENSE_NOTE = (
    "CC0 public-record data with primary-source receipts "
    "(provenance.sourceUrl on every row). Data only: no signals, scores, or "
    "predictions. The dumps are the source of record — live queries are "
    "freshness checks and ad-hoc lookups only, never a pipeline primary."
)

#: Per-tool attribution for the non-Library families (#4844): each entry is
#: ``(attribution, license_note, fallback_url)``. Tools absent here keep the
#: Library attribution via :func:`attribution_fields`.
TOOL_ATTRIBUTION: dict[str, tuple[str, str, str]] = {
    "luxalgo_edge_symbols": (
        LUXALGO_EDGE_ATTRIBUTION,
        LUXALGO_EDGE_LICENSE_NOTE,
        LUXALGO_EDGE_URL,
    ),
    "luxalgo_edge_presets": (
        LUXALGO_EDGE_ATTRIBUTION,
        LUXALGO_EDGE_LICENSE_NOTE,
        LUXALGO_EDGE_URL,
    ),
    "luxalgo_edge_report": (
        LUXALGO_EDGE_ATTRIBUTION,
        f"{LUXALGO_EDGE_LICENSE_NOTE} {HONESTY_DISCLAIMER}",
        LUXALGO_EDGE_URL,
    ),
    "luxalgo_trackers_datasets": (
        LUXALGO_TRACKERS_ATTRIBUTION,
        LUXALGO_TRACKERS_LICENSE_NOTE,
        LUXALGO_TRACKERS_URL,
    ),
    "luxalgo_trackers_latest": (
        LUXALGO_TRACKERS_ATTRIBUTION,
        LUXALGO_TRACKERS_LICENSE_NOTE,
        LUXALGO_TRACKERS_URL,
    ),
    "luxalgo_trackers_ticker": (
        LUXALGO_TRACKERS_ATTRIBUTION,
        LUXALGO_TRACKERS_LICENSE_NOTE,
        LUXALGO_TRACKERS_URL,
    ),
}


def attribution_fields(
    canonical_url: str | None = None,
    *,
    commercial_license: bool | None = None,
) -> dict[str, str | bool]:
    """The attribution block appended to every LuxAlgo tool payload.

    Always states the license-flag state the payload was produced under:
    ``commercial_license`` plus the matching ``license_state`` sentence, so a
    rendered payload shows whether source-code use was licensed. ``None``
    (default) resolves the live flag; an explicit bool pins the block (tests,
    licensed renderers).
    """
    enabled = (
        luxalgo_commercial_license_enabled() if commercial_license is None else commercial_license
    )
    fields: dict[str, str | bool] = {
        "attribution": LUXALGO_ATTRIBUTION,
        "license_note": LUXALGO_LICENSE_NOTE,
        "commercial_license": enabled,
        "license_state": commercial_license_note(enabled),
    }
    fields["source_url"] = (
        canonical_url.strip() if canonical_url and canonical_url.strip() else LUXALGO_LIBRARY_URL
    )
    return fields


def attribution_fields_for(tool: str, canonical_url: str | None = None) -> dict[str, str]:
    """Attribution block for *tool*, falling back to the Library set when undeclared."""
    declared = TOOL_ATTRIBUTION.get(tool)
    if declared is None:
        return attribution_fields(canonical_url)
    attribution, license_note, fallback_url = declared
    return {
        "attribution": attribution,
        "license_note": license_note,
        "source_url": (
            canonical_url.strip() if canonical_url and canonical_url.strip() else fallback_url
        ),
    }
