"""Deny-by-default refusal list for tools Counsel has ruled off our surfaces.

A *refused* tool is one we may not offer to any caller — not through the
dashboard-chat MCP read scope, not through the orchestrator manifest, and not
through ``POST /v1/orchestrator_invoke``. Refusal is **registration-level**: the
name is never registered and never advertised, so there is nothing for an agent
to call and nothing for a hub to route. The refusal is enforced in three places
that all read this one set, so a new surface cannot reopen a refused tool by
omission:

* :mod:`digiquant.mcp_server` — ``_maybe_tool`` skips registration on **both**
  ``scope="read"`` (dashboard chat) and ``scope="full"``;
* :mod:`digiquant.orchestrator_tools` — :func:`build_orchestrator_tool_manifest`
  filters refused names out of the advertised manifest;
* :mod:`digiquant.server` — ``v1_orchestrator_invoke`` answers a typed
  ``tool_refused`` refusal instead of dispatching.

Why this exists for congressional trades (DIG-1057; Counsel's ruling on the
inert feed is DIG-1029): 5 U.S.C. 13107(c)(1)(B) makes it unlawful to obtain
or use a House/Senate financial-disclosure report for any purpose other than
news-and-communications-media dissemination. We are not a news outlet, so the
feed is refused regardless of who asks. ``digifetch_congress_trades`` sits in
:data:`REFUSED_TOOLS` until Counsel clears it in writing.

**Do not remove a name from :data:`REFUSED_TOOLS` without Counsel's written
clearance and the CTO's merge.** The list is deliberately a code constant rather
than an environment variable: a production env var is not a legal gate (anyone
with a deploy could flip it back), whereas a code change is reviewed and gated by
the same people who hold the ruling. Reversal is a one-line deletion.

What a refusal deliberately does **not** do: it does not delete the client,
normalizer, models, or entitlement entry. Counsel may clear the feed, and if
they do we want it back without re-deriving the endpoint shape
(``GET /cloud/congress/house`` on ``api.gloom.sh``, anonymous). Nothing is
fetched, cached, stored, or substituted while refused — the data simply has no
route into digiquant.
"""

from __future__ import annotations

from typing import Final

#: Tool names refused on every digiquant surface. See the module docstring for
#: the legal basis and the removal rule.
REFUSED_TOOLS: Final[frozenset[str]] = frozenset(
    {
        # 5 U.S.C. 13107(c)(1)(B) — House/Senate STOCK Act disclosure reports are
        # not ours to obtain or use for a commercial purpose (DIG-1057).
        "digifetch_congress_trades",
    }
)

#: Stable machine-readable code callers can branch on, distinct from an
#: upstream failure (``upstream_error``) or a missing entitlement
#: (``auth_required`` / ``pro_required``): a refusal is our own policy, not a
#: transient vendor condition, and must not be retried.
REFUSAL_CODE: Final[str] = "tool_refused"


def is_refused(tool_name: str) -> bool:
    """Return True when ``tool_name`` must not be registered or dispatched."""
    return tool_name in REFUSED_TOOLS


def refusal_message(tool_name: str) -> str:
    """Return the caller-facing refusal string for a refused tool."""
    return (
        f"{tool_name} is refused ({REFUSAL_CODE}): not available on any "
        "digiquant surface. Do not retry."
    )


__all__ = ["REFUSAL_CODE", "REFUSED_TOOLS", "is_refused", "refusal_message"]
