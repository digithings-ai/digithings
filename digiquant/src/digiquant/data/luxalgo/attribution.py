"""Attribution + external-link conventions for LuxAlgo-sourced values (#4779 P0, #4844).

Canonical attribution is **"Sourced from LuxAlgo Library"** plus the upstream
canonical URL (``url`` / ``md_url``) wherever a value is rendered outside the
agent loop. Deep links are the Library page URLs the upstream returns per row —
there is no URL scheme of our own to construct.

The Edge Stats (#4844) and Market Trackers (#4844) families carry their own
attribution sets via :data:`TOOL_ATTRIBUTION` (edge-stats engine repo / the
CC0-1.0 trackers-dumps repo as the fallback link); :func:`attribution_fields_for`
selects them per tool.

Two licences are in play here and only one of them used to be guarded. The
*code* licence is LuxAlgo indicator Pine source, CC BY-NC-SA, kept off every
surface by :mod:`digiquant.data.luxalgo.license_guard`. The *data* licence
governs what a trackers row is: the vendor publishes those dumps under a
CC0 1.0 Universal LICENSE (classified 2026-10-06, DIG-1464 — see
:data:`LUXALGO_TRACKERS_DATA_LICENSE`), but two of the six families need a limit
the copyright waiver cannot supply — congress-trades is restricted by 5 U.S.C.
13107 and short-volume carries unresolved FINRA redistribution terms — so every
trackers licence note carries :func:`trackers_data_caveat`. A payload that says
only "CC0" is not telling the truth about those two.

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
    "LUXALGO_TRACKERS_DATA_LICENSE",
    "LUXALGO_TRACKERS_LICENSE_ARTEFACT",
    "LUXALGO_TRACKERS_DATA_CAVEATS",
    "TOOL_ATTRIBUTION",
    "trackers_data_caveat",
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

#: The trackers **data** licence, classified by Security 2026-10-06 (DIG-1464).
#: This is a different licence from the code boundary above, and it is the one
#: that governs every row a trackers tool returns. The vendor publishes these
#: dumps at :data:`LUXALGO_TRACKERS_URL` under a CC0 1.0 Universal LICENSE file,
#: read and hashed on that date; GitHub's own licence detection on that
#: repository reports SPDX ``CC0-1.0``. The LuxAlgo ToS "Market Data & Delays"
#: clause is scoped to quote and price data (Vela, luxalgo.com market pages), so
#: its redistribution prohibition does not reach these public-record extracts.
#: The verdict is per-family: congress-trades is restricted by 5 U.S.C. 13107
#: and short-volume carries unresolved FINRA redistribution terms — see
#: :data:`LUXALGO_TRACKERS_DATA_CAVEATS`.
LUXALGO_TRACKERS_DATA_LICENSE = "CC0-1.0"

#: The artefacts the classification rests on, named so the claim stays
#: checkable rather than inherited (DIG-1318 intake trap 1). Both the grant and
#: the negative reading are pinned: a licence hash alone would leave "the ToS
#: does not reach these" as the same unverified assertion in the other
#: direction.
LUXALGO_TRACKERS_LICENSE_ARTEFACT = (
    "https://github.com/LuxAlgo/market-trackers-data LICENSE @ main, sha256 "
    "a2010f343487d3f7618affe54f789f5487602331c0a8d03f49e9a7c547cf0499"
)

#: Read and hashed 2026-10-06. The "Market Data & Delays" clause quoted in the
#: module comment is scoped to quote and price feeds; it names Cboe EDGX, CME
#: via Databento, Financial Modeling Prep, Massive and Twelve Data, and says
#: such data "may not be redistributed".
LUXALGO_TRACKERS_TOS_ARTEFACT = (
    "https://www.luxalgo.com/legal/terms-of-service/ @ 2026-10-06, sha256 "
    "cad4afb7b7d7545f2c299c2c07b6ed761bcf7ac8be8a0fcadf3d36af65c5fad0"
)

#: Per-family position on top of the CC0 grant, for the families where "CC0" on
#: its own overstates the position. A CC0 dedication is a waiver by the affirmer:
#: it cannot waive a statutory use prohibition, and under CC0 §4(b)-(c) the
#: affirmer gives no warranty of title and disclaims any duty to clear other
#: people's rights. Both limits bite on exactly one family each:
#: congress-trades for the statute, short-volume for the upstream terms.
LUXALGO_TRACKERS_DATA_CAVEATS: dict[str, str] = {
    "congress-trades": (
        "Congress-trades rows are 13107(c) disclosure reports: the CC0 grant "
        "covers the copyright, but 5 U.S.C. 13107(c)(1)(B) restricts their "
        "commercial use and 13107(c)(2) runs to whoever obtains or uses them, "
        "so no licence can cure it. Counsel ruled this the refused data class "
        "(DIG-1472); the dataset is in service by business decision dated "
        "2026-10-06 against that advice, which is not a clearance."
    ),
    "short-volume": (
        "Short-volume rows originate with FINRA, a private self-regulatory "
        "organisation rather than a federal records custodian, so its own "
        "upstream terms are unresolved — CC0 §4(b)-(c) means the vendor cannot "
        "clear rights it does not hold. Do not present as cleared. Open with "
        "Counsel (raised DIG-1464; the durable question is the upstream FINRA "
        "redistribution terms, which no vendor licence answers)."
    ),
}

LUXALGO_TRACKERS_ATTRIBUTION = (
    f"Sourced from LuxAlgo Market Trackers ({LUXALGO_TRACKERS_DATA_LICENSE} "
    "public-record dumps — see license_note for the per-family limits)"
)
LUXALGO_TRACKERS_URL = "https://github.com/LuxAlgo/market-trackers-data"
LUXALGO_TRACKERS_LICENSE_NOTE = (
    f"{LUXALGO_TRACKERS_DATA_LICENSE} public-record data with primary-source "
    "receipts (provenance.sourceUrl on every row), classified 2026-10-06 "
    f"(DIG-1464) from {LUXALGO_TRACKERS_LICENSE_ARTEFACT}. Data only: no "
    "signals, scores, or predictions. The dumps are the source of record — live "
    "queries are freshness checks and ad-hoc lookups only, never a pipeline "
    "primary."
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


#: The tools whose licence note carries the trackers data-licence position, as
#: opposed to the Library and Edge Stats licences. Kept as a set so the caveat
#: rule cannot be applied to the wrong family by a future tool.
_TRACKERS_TOOLS = frozenset(
    {
        "luxalgo_trackers_datasets",
        "luxalgo_trackers_latest",
        "luxalgo_trackers_ticker",
    }
)


def trackers_data_caveat(dataset: str | None = None) -> str:
    """The per-family limits that ride on the trackers CC0 grant.

    A bare "CC0 public-record dumps" string reads as permission for every family,
    and two of the six need a limit that a copyright waiver cannot supply —
    congress-trades under 5 U.S.C. 13107 and short-volume under the unresolved
    FINRA terms. With
    *dataset* given, only that family's caveats render; with ``None`` (the
    default, and the only thing a tool-level attribution block can know) every
    caveat renders, so a payload mixing families is never quietly clean.

    Fails **closed**. A *dataset* that is not in
    :data:`LUXALGO_TRACKERS_DATA_CAVEATS` — a typo, a case variant, an empty
    string — renders every caveat rather than none. Returning ``""`` for an
    unknown family would let a misspell clear the very limit the caveat exists
    to state, which is the opposite of what a licence note is for.
    """
    if dataset is not None and dataset in LUXALGO_TRACKERS_DATA_CAVEATS:
        return f" {LUXALGO_TRACKERS_DATA_CAVEATS[dataset]}"
    caveats = " ".join(
        LUXALGO_TRACKERS_DATA_CAVEATS[dataset] for dataset in sorted(LUXALGO_TRACKERS_DATA_CAVEATS)
    )
    return (
        " Two families need a limit the CC0 grant cannot supply: congress-trades "
        "is restricted by 5 U.S.C. 13107, and short-volume carries unresolved "
        f"FINRA redistribution terms. {caveats}"
    )


def attribution_fields_for(
    tool: str,
    canonical_url: str | None = None,
    *,
    dataset: str | None = None,
) -> dict[str, str]:
    """Attribution block for *tool*, falling back to the Library set when undeclared.

    *dataset* narrows the trackers data-licence caveat to one family. It is
    optional because attribution is a per-tool property and a ``_latest``
    response can mix families; when it is not supplied the caveat covers all of
    them rather than none.
    """
    declared = TOOL_ATTRIBUTION.get(tool)
    if declared is None:
        return attribution_fields(canonical_url)
    attribution, license_note, fallback_url = declared
    if tool in _TRACKERS_TOOLS:
        license_note += trackers_data_caveat(dataset)
    return {
        "attribution": attribution,
        "license_note": license_note,
        "source_url": (
            canonical_url.strip() if canonical_url and canonical_url.strip() else fallback_url
        ),
    }
