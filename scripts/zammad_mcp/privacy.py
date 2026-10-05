"""Customer-data disclosure policy for the Zammad MCP output (DIG-1063).

This module is the only place that decides whether a customer's name, email
address and organization may leave the helpdesk. It exists because #4944
("OCC demo") turned masking off in the renderers themselves, so every output
path inherited the decision with no way to review it.

Policy, in one line: **masked by default; unmasking requires a named human who
accepts the risk.**

- ``ZAMMAD_MCP_CUSTOMER_DISCLOSURE=masked`` (default) — customers render as a
  stable pseudonym (``customer #<id>``), no name, no email, no email domain,
  and internal notes are not returned at all.
- ``ZAMMAD_MCP_CUSTOMER_DISCLOSURE=unmasked`` — the #4944 behaviour. Refused
  unless ``ZAMMAD_MCP_UNMASK_APPROVER`` names the human who accepted the risk,
  so the override cannot be set by accident or left unowned.

Everything fails **closed**: an unknown value, a blank approver, or a missing
variable all resolve to ``masked``. A typo in a deploy cannot leak the corpus.

Why a pseudonym and not the old ``j***@example.test`` mask: for a B2B helpdesk
the email domain *is* the customer's company, so a partial mask still
identifies. The pseudonym keeps rankings, grouping and the customer-history
drill-down working while carrying no personal data.

The accepted-risk record for the override lives in
``docs/ops/ZAMMAD_MCP_CUSTOMER_DISCLOSURE.md``.
"""

from __future__ import annotations

import hashlib
import os
import re
from typing import Any, Mapping

MASKED = "masked"
UNMASKED = "unmasked"
MODES = (MASKED, UNMASKED)

DISCLOSURE_ENV = "ZAMMAD_MCP_CUSTOMER_DISCLOSURE"
APPROVER_ENV = "ZAMMAD_MCP_UNMASK_APPROVER"

PSEUDONYM_PREFIX = "customer #"
#: Stand-in for an email address found in free text (DIG-1210). Same vocabulary
#: as the customer pseudonym so the prompt has one rule to describe.
ADDRESS_PREFIX = "email#"
_DIGEST_CHARS = 8

#: Deliberately conservative: an address is an address, and the corpus is a mix
#: of customer, staff and third-party contacts. Splitting on ``@`` with an
#: optional trailing dot keeps a trailing sentence period out of the match
#: without depending on a full RFC 5322 grammar.
_ADDRESS_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\.?")

#: Tells the model *why* it is reading `customer #7` and no internal notes, so
#: it does not treat the redaction as missing data or invent the real value.
MASKED_NOTICE = (
    "Customer names, email addresses and organizations are hidden and internal "
    "notes are not shown. Customers appear as a stable id such as "
    f"'{PSEUDONYM_PREFIX}7'. Never guess or reconstruct a name."
)


def _env(name: str, env: Mapping[str, str] | None = None) -> str:
    source = os.environ if env is None else env
    return (source.get(name) or "").strip()


def unmask_blocker(env: Mapping[str, str] | None = None) -> str | None:
    """Why unmasking is refused, or ``None`` when it is allowed.

    A blank reason means the environment asks for ``unmasked`` *and* names the
    human who accepted the risk. Callers log the reason so a refused override
    leaves a trace instead of silently degrading.
    """
    requested = _env(DISCLOSURE_ENV, env).lower()
    if requested == MASKED:
        return f"{DISCLOSURE_ENV} is '{MASKED}'"
    if requested != UNMASKED:
        return (
            f"{DISCLOSURE_ENV}={requested or '(unset)'!r} is not one of {list(MODES)}; "
            f"using '{MASKED}'"
        )
    if not _env(APPROVER_ENV, env):
        return (
            f"unmasking needs {APPROVER_ENV} to name the human who accepted the risk "
            f"(accepted risk in docs/ops/ZAMMAD_MCP_CUSTOMER_DISCLOSURE.md); using '{MASKED}'"
        )
    return None


def disclosure_mode(env: Mapping[str, str] | None = None) -> str:
    """Return :data:`MASKED` or :data:`UNMASKED`. Fails closed."""
    return UNMASKED if unmask_blocker(env) is None else MASKED


def is_masked(env: Mapping[str, str] | None = None) -> bool:
    return disclosure_mode(env) == MASKED


def _raw_text(value: Any) -> str:
    """The identifying value as stored, or '' when there is none.

    A dict is an expanded Zammad customer/organization; ``email`` is preferred
    because it is the most identifying field, but any of them is personal data
    and none of them may reach the model in masked mode.
    """
    if value is None:
        return ""
    if isinstance(value, dict):
        for key in ("email", "login", "fullname", "name", "firstname", "lastname"):
            candidate = value.get(key)
            if candidate:
                return str(candidate).strip()
        return ""
    text = str(value).strip()
    # Zammad writes "-" for an unset relation; it is not a customer.
    return "" if text == "-" else text


def _raw_id(value: Any, cid: Any = None) -> str:
    """The numeric Zammad id, from ``cid`` or from an expanded payload."""
    for candidate in (cid, value.get("id") if isinstance(value, dict) else None):
        if candidate is None or candidate == "":
            continue
        text = str(candidate).strip()
        if text and text != "-":
            return text
    return ""


def _digest(value: str) -> str:
    """Stable, non-reversible stand-in for a value with no id.

    Deterministic so the same customer groups together across calls and pages.
    A keyed digest would be stronger, but the input is a Zammad *email*, which
    is guessable from a known customer list — so the digest buys readability of
    grouping, not confidentiality of the digest itself. The id path is the one
    that matters; this only keeps a ranking row from becoming ``?``.
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:_DIGEST_CHARS]


def customer_label(value: Any, cid: Any = None, *, env: Mapping[str, str] | None = None) -> str:
    """Render one customer for any output path.

    Masked: ``customer #7``, or ``customer #a1b2c3d4`` when the id is unknown.
    Unmasked: the #4944 format, ``jane.doe@example.test (id 7)``.
    """
    text = _raw_text(value)
    identifier = _raw_id(value, cid)
    if disclosure_mode(env) == UNMASKED:
        if not text:
            return f"(id {identifier})" if identifier else "unknown customer"
        return f"{text} (id {identifier})" if identifier else text
    if not identifier and text.isdigit():
        # An aggregate ranking's `value` for a customer is the stringified
        # customer_id; a bare number in this corpus is an id, never a name.
        identifier = text
    if identifier:
        return f"{PSEUDONYM_PREFIX}{identifier}"
    if not text:
        # No customer at all (Zammad's "-", or a row with no customer field):
        # render nothing so the caller omits the line entirely.
        return ""
    return f"{PSEUDONYM_PREFIX}{_digest(text)}"


def is_pseudonym(text: str) -> bool:
    """True when ``text`` is already a masked label (idempotency guard)."""
    return bool(text) and text.startswith(PSEUDONYM_PREFIX)


def organization_label(value: Any, *, env: Mapping[str, str] | None = None) -> str:
    """Render a ticket's organization. Empty in masked mode.

    An organization here is the customer's company, so it identifies the same
    person the name does. Masked mode drops the field rather than pseudonyming
    it, because no other output line needs it.
    """
    if disclosure_mode(env) == UNMASKED:
        return _raw_text(value)
    return ""


def visible_articles(
    articles: list[dict[str, Any]], *, env: Mapping[str, str] | None = None
) -> tuple[list[dict[str, Any]], int]:
    """Split articles into (shown, internal-hidden) for the current policy."""
    if disclosure_mode(env) == UNMASKED:
        return list(articles), 0
    visible = [article for article in articles if not article.get("internal")]
    return visible, len(articles) - len(visible)


def author_label(author: str, *, env: Mapping[str, str] | None = None) -> str:
    """Render an article's ``from`` field, or '' when it must not be shown.

    A customer-authored article carries the customer's own email address here,
    so masking the ``Customer:`` header alone would be cosmetic. Masked mode
    therefore drops ``from`` for every article, staff ones included: agent names
    are Art. 4(1) personal data on the same corpus, and one rule to review beats
    two. The article header still prints Zammad's ``sender`` role
    (``customer``/``agent``/``system``), which is what a reader needs to follow
    a thread.

    Scope, stated so the boundary is reviewable: this covers the *subject* of the
    corpus — the customer and the people who wrote in their tickets. The ticket
    ``Owner`` line is deliberately **not** masked: an owner is digithings staff,
    not customer data, and the model needs it to answer "who handles this". If
    that call is ever revisited it is a separate decision, not a privacy fix.
    """
    if disclosure_mode(env) == UNMASKED:
        return author
    return ""


def _address_placeholder(match: re.Match[str]) -> str:
    """One address becomes one stable pseudonym; trailing punctuation survives.

    A match can end on a sentence full stop — ``write to jane@acme.test.`` — and
    dropping it would silently run sentences together in the indexed text. The
    address is digested without it; the punctuation is put back.
    """
    raw = match.group(0)
    address = raw.rstrip(".")
    return ADDRESS_PREFIX + _digest(address.lower()) + raw[len(address) :]


def redact_addresses(text: str, *, env: Mapping[str, str] | None = None) -> str:
    """Replace every email address in free text with a stable pseudonym.

    Added for DIG-1210, where the corpus is *indexed* rather than rendered. The
    structured-field mask could not carry that surface: measured against the
    committed ``occ_tickets`` snapshot, dropping internal articles and masking
    the metadata still left 1 146 address occurrences in article bodies across
    250 distinct addresses, 183 of them the ticket customer's own address echoed
    from a mail signature. 503 of the 547 surviving chunks still quoted one.

    Why this is mechanical rather than a product trade-off: an address has an
    unambiguous shape, and for a B2B helpdesk the domain *is* the customer
    company, so there is no partial mask worth keeping. Removing just the
    address string leaves the surrounding sentence readable, which is why the
    cost is small enough to take without a product decision.

    What this does **not** do, and needs a separate decision: it cannot find a
    *name* in free text ("Hallo, hier ist Hans Müller"). 375 of those 547 chunks
    still carry a full customer display name. Closing that needs name
    detection over German and Spanish prose, which is a product trade-off, and
    it is recorded in ``docs/adr/0031`` rather than guessed at here.

    Idempotent: the pseudonym contains no ``@``, so a second pass is a no-op.
    """
    if not text:
        return text
    if disclosure_mode(env) == UNMASKED:
        return text
    return _ADDRESS_RE.sub(_address_placeholder, text)
