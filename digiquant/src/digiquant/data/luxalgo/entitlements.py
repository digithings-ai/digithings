"""Per-tool entitlement declarations for the LuxAlgo hosted family (#4779 P0, #4844).

One vocabulary, declared once per tool and rendered on two surfaces:

* the MCP registration (``mcp_server`` attaches ``fn.entitlement`` and appends
  the note to the registered description), and
* the orchestrator manifest (``orchestrator_tools`` sets a top-level
  ``entitlement`` key and appends the same note).

Because both surfaces append the same note, every tool description an agent
reads also states its entitlement before the call.

Vocabulary (shared with the digifetch x Gloomberb family; today every LuxAlgo
tool is keyless):

``free``
    Anonymous read; no key, cookie, or OAuth token is needed.

Deliberately NOT wrapped (see scope §P0, #4844):

* ``library_get_source_code`` — CC BY-NC-SA: no paid-product embed without a
  commercial license;
* ``trackers_query`` — ad-hoc dump search; the CC0 dumps stay the source of
  record and live queries are freshness/ad-hoc lookups only;
* ``broker_*`` — local-only keys; broker credentials are never sent to the
  hosted MCP;
* ``journal_*`` (OAuth), ``propfirms_*`` — separate packages, not this wrap.
"""

from __future__ import annotations

from typing import Literal

__all__ = [
    "Entitlement",
    "TOOL_ENTITLEMENTS",
    "ENTITLEMENT_DESCRIPTIONS",
    "TOOL_NOTES",
    "entitlement_for",
    "entitlement_note",
    "with_entitlement_note",
]

Entitlement = Literal["free"]

#: One declaration per luxalgo tool (mirrors the MCP + manifest surfaces).
TOOL_ENTITLEMENTS: dict[str, Entitlement] = {
    "luxalgo_library_search": "free",
    "luxalgo_library_get_concept": "free",
    "luxalgo_library_get_indicator": "free",
    "luxalgo_library_list_concepts": "free",
    "luxalgo_library_list_indicators": "free",
    "luxalgo_library_list_tags": "free",
    "luxalgo_library_list_families": "free",
    "luxalgo_library_get_family": "free",
    "luxalgo_edge_symbols": "free",
    "luxalgo_edge_presets": "free",
    "luxalgo_edge_report": "free",
    "luxalgo_trackers_datasets": "free",
    "luxalgo_trackers_latest": "free",
    "luxalgo_trackers_ticker": "free",
}

#: The sentence appended to the MCP/manifest description for each entitlement.
ENTITLEMENT_DESCRIPTIONS: dict[Entitlement, str] = {
    "free": (
        "Entitlement: free (anonymous; no key needed). Library content is "
        "LuxAlgo's — attribute and link back; indicator source code is not "
        "available through these tools (CC BY-NC-SA)."
    ),
}

#: Per-tool note overrides (#4844): the Edge Stats and Trackers families share
#: the ``free`` entitlement but need their own description sentence — the
#: Library source-code note would mislead on a preset stat or a CC0 row.
TOOL_NOTES: dict[str, str] = {
    "luxalgo_edge_symbols": (
        "Entitlement: free (anonymous; no key needed). Edge Stats content is "
        "LuxAlgo's — attribute and link back; precomputed historical "
        "frequencies, not predictions."
    ),
    "luxalgo_edge_presets": (
        "Entitlement: free (anonymous; no key needed). Edge Stats content is "
        "LuxAlgo's — attribute and link back; precomputed historical "
        "frequencies, not predictions."
    ),
    "luxalgo_edge_report": (
        "Entitlement: free (anonymous; no key needed). Edge Stats content is "
        "LuxAlgo's — attribute and link back; precomputed historical "
        "frequencies, not predictions."
    ),
    "luxalgo_trackers_datasets": (
        "Entitlement: free (anonymous; no key needed). Trackers rows are CC0 "
        "public records — cite the primary source (provenance.sourceUrl); "
        "the dumps are the source of record."
    ),
    "luxalgo_trackers_latest": (
        "Entitlement: free (anonymous; no key needed). Trackers rows are CC0 "
        "public records — cite the primary source (provenance.sourceUrl); "
        "the dumps are the source of record."
    ),
    "luxalgo_trackers_ticker": (
        "Entitlement: free (anonymous; no key needed). Trackers rows are CC0 "
        "public records — cite the primary source (provenance.sourceUrl); "
        "the dumps are the source of record."
    ),
}


def entitlement_for(name: str) -> Entitlement | None:
    """The declared entitlement for a tool name, or None when undeclared."""
    return TOOL_ENTITLEMENTS.get(name)


def entitlement_note(name: str) -> str | None:
    """The description sentence for a declared tool, or None."""
    if name in TOOL_NOTES:
        return TOOL_NOTES[name]
    entitlement = entitlement_for(name)
    if entitlement is None:
        return None
    return ENTITLEMENT_DESCRIPTIONS[entitlement]


def with_entitlement_note(name: str, description: str) -> str:
    """Append the declared entitlement note to *description* (idempotent)."""
    note = entitlement_note(name)
    if note is None or note in description:
        return description
    return f"{description.rstrip()}\n\n{note}"
