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

**Why this exists for congressional trades** (DIG-1057; Counsel's ruling on the
inert feed is DIG-1029, and on the live surface DIG-1251). The reports at issue
are the periodic transaction reports filed under 5 U.S.C. 13105(l), which are
therefore "reports" for the purposes of 5 U.S.C. 13107(c). The clauses relied on
are 5 U.S.C. 13107(a), 13107(b)(2)(C), 13107(c)(1)(B) and 13107(c)(2):

* **13107(c)(1)(B)** makes it unlawful to use such a report *for a commercial
  purpose* unless the user is a news and communications media entity
  disseminating the report to the general public. The carve-out is scoped to the
  commercial-purpose limb; it is not a general permission for any non-commercial
  purpose.
* **13107(c)(2)** is the separate limb that makes it unlawful knowingly and
  wilfully to sell or otherwise transfer such a report for any purpose.

We are not news and communications media and we operate commercially, so
``digifetch_congress_trades`` sits in :data:`REFUSED_TOOLS` and is refused
regardless of who asks, until Counsel clears it in writing. An earlier version of
this note described (c)(1)(B) as a bar on all non-media purposes, which
overstated the statute: the carve-out attaches to the commercial-purpose limb
only, not to every purpose. Our outcome is unchanged; the statement of law is not
(DIG-1479).

**Scope of this refusal, and the LuxAlgo trackers exception (DIG-1472).** This
refusal is keyed on *tool names*, so it refuses the ``digifetch_congress_trades``
tool surface specifically — not the congressional-trades data class as a whole.
The LuxAlgo ``market-trackers-data`` ``congress-trades`` dataset carries the same
data class as the rows Counsel classified under 13105(l)/13107(c). Counsel
confirmed the classification and advised refusal (DIG-1472, CONFIRMED). The
business owner (Chris) decided on **2026-10-06** to keep that dataset in service
anyway, accepting the 13107(c)(2) exposure. That is a business decision against
Counsel's advice, not a legal clearance, and it is recorded here and in
``digisearch.trackers_ingest`` so no later reader mistakes the allowlist for a
Counsel opinion. The business owner is not Counsel, and the phrase "no legal
risk" is not Counsel's position and does not appear in this repository.

**The environment denylist is additive only.**
:data:`ENV_DENYLIST_VAR` can *add* refused names. It can never remove one, and
it has no allow / negate / un-refuse syntax, so the effective rule is:

.. code-block:: text

    refused = REFUSED_TOOLS | env_denied_tools(DIGIQUANT_REFUSED_TOOLS)

Counsel approved this shape on four conditions (DIG-1251, Q5), and conditions 1
and 2 are structural facts about this module rather than promises in a
comment:

1. **Deny-only.** ``REFUSED_TOOLS`` is an unconditional floor. No value of the
   environment variable — missing, empty, whitespace, or a list containing an
   apparent negation such as ``-digifetch_congress_trades`` or
   ``allow=digifetch_congress_trades`` — can make a ``REFUSED_TOOLS`` member
   permitted, because :func:`env_denied_tools` has no code path that subtracts.
2. **Fail closed.** A missing, empty or whitespace-only variable contributes no
   names, leaving the code constant in force. A malformed value contributes
   tokens, never exceptions, so a typo cannot raise past the refusal check.
3. **Proven by test, not by log line.**
   ``tests/dq/test_tool_refusals_env_denylist.py`` asserts every
   :data:`REFUSED_TOOLS` member is still refused under every legal value of the
   variable, including the adversarial ones.
4. Approval is on the shape only.

**Do not remove a name from :data:`REFUSED_TOOLS` without Counsel's written
clearance and the CTO's merge.** That is the real gate. The environment variable
is an operational convenience for refusing *more* things, never a way to permit
this one: a production env var is not a legal gate (anyone with a deploy could
flip it back), whereas a code change is reviewed and gated by the same people who
hold the ruling. Reversal is a one-line deletion.

What a refusal deliberately does **not** do: it does not delete the client,
normalizer, models, or entitlement entry. Counsel may clear the feed, and if
they do we want it back without re-deriving the endpoint shape
(``GET /cloud/congress/house`` on ``api.gloom.sh``, anonymous). Nothing is
fetched, cached, stored, or substituted while refused — the data simply has no
route into digiquant.
"""

from __future__ import annotations

import os
from typing import Final

#: Tool names refused on every digiquant surface, unconditionally. Members of
#: this set are refused whatever :data:`ENV_DENYLIST_VAR` is set to. See the
#: module docstring for the legal basis and the removal rule.
REFUSED_TOOLS: Final[frozenset[str]] = frozenset(
    {
        # 5 U.S.C. 13107(c)(1)(B) — House/Senate STOCK Act disclosure reports are
        # not ours to obtain or use for a commercial purpose (DIG-1057).
        "digifetch_congress_trades",
    }
)

#: Name of the environment variable holding an extra, deny-only denylist. It
#: follows the existing ``DIGIQUANT_*`` convention. The value is a
#: separator-delimited list of tool names, e.g. ``"digifetch_a,digifetch_b"``.
ENV_DENYLIST_VAR: Final[str] = "DIGIQUANT_REFUSED_TOOLS"

#: Characters that separate entries in :data:`ENV_DENYLIST_VAR`.
_ENV_SEPARATORS: Final[frozenset[str]] = frozenset({",", ";", " ", "\t", "\n", "\r"})

#: Stable machine-readable code callers can branch on, distinct from an
#: upstream failure (``upstream_error``) or a missing entitlement
#: (``auth_required`` / ``pro_required``): a refusal is our own policy, not a
#: transient vendor condition, and must not be retried.
REFUSAL_CODE: Final[str] = "tool_refused"


def env_denied_tools() -> frozenset[str]:
    """Return the extra names denied by :data:`ENV_DENYLIST_VAR`.

    Read per call so a deployment change takes effect on the next request and so
    tests can vary the variable without reloading this module.

    Split on any whitespace or comma/semicolon, then keep every non-empty token
    verbatim after stripping and lowercasing. Tokens are never interpreted: there
    is deliberately no ``-``/``!``/``allow=``/``unrefuse=`` handling, because any
    such syntax would be a path by which a value could *remove* a refusal, and
    Counsel's first condition forbids that. A missing, empty or whitespace-only
    value yields an empty set, leaving :data:`REFUSED_TOOLS` in force.
    """
    raw = os.environ.get(ENV_DENYLIST_VAR)
    if raw is None or not raw.strip():
        return frozenset()
    tokens: list[str] = []
    current: list[str] = []
    for char in raw:
        if char in _ENV_SEPARATORS:
            tokens.append("".join(current))
            current = []
        else:
            current.append(char)
    tokens.append("".join(current))
    return frozenset(token.strip().lower() for token in tokens if token.strip())


def is_refused(tool_name: str) -> bool:
    """Return True when ``tool_name`` must not be registered or dispatched.

    Deny-only: membership of :data:`REFUSED_TOOLS` short-circuits, so no
    environment value can permit a refused feed. The comparison of the
    environment denylist is case-insensitive, which can only match more names.
    """
    return tool_name in REFUSED_TOOLS or tool_name.lower() in env_denied_tools()


def refusal_message(tool_name: str) -> str:
    """Return the caller-facing refusal string for a refused tool."""
    return (
        f"{tool_name} is refused ({REFUSAL_CODE}): not available on any "
        "digiquant surface. Do not retry."
    )


__all__ = [
    "ENV_DENYLIST_VAR",
    "REFUSAL_CODE",
    "REFUSED_TOOLS",
    "env_denied_tools",
    "is_refused",
    "refusal_message",
]
