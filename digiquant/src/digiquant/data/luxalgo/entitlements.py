"""Per-tool entitlement declarations for the LuxAlgo Library family (#4779 P0).

One vocabulary, declared once per tool and rendered on two surfaces:

* the MCP registration (``mcp_server`` attaches ``fn.entitlement`` and appends
  the note to the registered description), and
* the orchestrator manifest (``orchestrator_tools`` sets a top-level
  ``entitlement`` key and appends the same note).

Because both surfaces append the same note, every tool description an agent
reads also states its entitlement before the call.

Vocabulary (shared with the digifetch x Gloomberb family; today every LuxAlgo
Library tool is keyless):

``free``
    Anonymous read; no key, cookie, or OAuth token is needed.

Deliberately NOT wrapped (see scope §P0):

* ``library_get_source_code`` — CC BY-NC-SA: no paid-product embed without a
  commercial license;
* ``broker_*`` — local-only keys; broker credentials are never sent to the
  hosted MCP;
* ``journal_*`` (OAuth), ``edge_*`` / ``trackers_*`` / ``propfirms_*`` —
  separate P0 packages, not this Library-research wrap.
"""

from __future__ import annotations

from typing import Literal

__all__ = [
    "Entitlement",
    "TOOL_ENTITLEMENTS",
    "ENTITLEMENT_DESCRIPTIONS",
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
}

#: The sentence appended to the MCP/manifest description for each entitlement.
ENTITLEMENT_DESCRIPTIONS: dict[Entitlement, str] = {
    "free": (
        "Entitlement: free (anonymous; no key needed). Library content is "
        "LuxAlgo's — attribute and link back; indicator source code is not "
        "available through these tools (CC BY-NC-SA)."
    ),
}


def entitlement_for(name: str) -> Entitlement | None:
    """The declared entitlement for a tool name, or None when undeclared."""
    return TOOL_ENTITLEMENTS.get(name)


def entitlement_note(name: str) -> str | None:
    """The description sentence for a declared tool, or None."""
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
