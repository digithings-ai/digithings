"""Deny-list for grounding searches that must not reach a refused domain (DIG-1133).

Same shape as the DIG-1057 tool kill — *deny by default, one line to reverse* —
applied to the other surface Counsel named: the ``alt-politician-signals``
segment's web-grounding pre-pass. That segment used to name
``capitoltrades.com`` / ``quiverquant.com`` in
``research/config/search_domains.yaml``, so a scheduled harvest pulled
congressional-trades write-ups into a persisted research memo on its own.

**UNSURE-to-LIKELY under 5 U.S.C. 13107(c)(1)(B) is not a clearance.** Counsel
(DIG-1056 § 8.1) rated this surface UNSURE-to-LIKELY — the ruling settled the MCP
tool surface (DIG-1056, CONFIRMED), explicitly *not* this one — and flagged that
it is live and publishing today. This list is containment, not a legal opinion.

Why a code constant and not yaml: ``search_domains.yaml`` is a tuning file an
operator edits, and an env var is not a legal gate. Counsel's own phrasing —
"controlling that list is the control; the hook is not" — is why this is a
frozen module constant honoured at the call site, beside the ``disclosures-clerk``
local hook that is *not* a safeguard. **Reversal is deleting a line here.**

Independent of DIG-1057 by necessity: the ``digifetch_congress_trades`` kill
(commit ``2ec75a55``) is not an ancestor of ``develop``, so this module does not
import its refusal table. Cross-referenced so the two can be unified when that
commit lands.
"""

from __future__ import annotations

from urllib.parse import urlsplit

# Congressional-trades material: two politician-trades aggregators plus the
# Clerk's own disclosure portal (the first-level origin of the same reports).
# A tuple, not a set: it is the order the deny-list rides into `exclude_domains`,
# and that order must be deterministic for the cap and for the tests.
REFUSED_SEARCH_DOMAINS: tuple[str, ...] = (
    "capitoltrades.com",
    "quiverquant.com",
    "disclosures-clerk.house.gov",
)


def _registrable(value: str) -> str:
    """Lowercase host for a bare domain or a full URL, scheme/port/path stripped."""
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if "//" not in text:
        text = f"//{text}"
    host = urlsplit(text).hostname or ""
    return host[4:] if host.startswith("www.") else host


def is_refused_search_domain(value: str) -> bool:
    """True when ``value`` is a refused domain or a subdomain of one.

    Subdomain matching on purpose: a result row citing ``data.capitoltrades.com``
    is the same refused surface as ``capitoltrades.com``, and the yaml allowlist
    is not the only way a host can reach the search call.
    """
    host = _registrable(value)
    if not host:
        return False
    return any(
        host == refused or host.endswith(f".{refused}") for refused in REFUSED_SEARCH_DOMAINS
    )
