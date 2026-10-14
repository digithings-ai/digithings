"""PII masking for ticket-derived index content (DIG-3578).

Masking runs BEFORE embedding and BEFORE any write to D1/Vectorize: raw
direct identifiers must never persist. Two complementary passes:

1. **Known-value pass** — exact strings supplied by structured ticket fields
   (customer display name, organization, owner, author). Exact matching means
   zero false positives on this pass; longest value first so overlapping
   values (e.g. "Mustermann" inside "Max Mustermann") mask greedily.
2. **Pattern pass** — email addresses, phone numbers and postal addresses in
   free text, whatever field they appear in.

The pattern pass is deliberately conservative: it prefers a missed
redaction over corrupting ticket content (a missed pattern is still caught
by the commit-time ``check_pii_seed_payloads`` gate and by review). Counts
per category are returned so callers can log/audit without values.

Placeholder vocabulary is fixed and asserted by tests: ``[EMAIL]``,
``[PHONE]``, ``[ADDRESS]``, ``[NAME]``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Fixed placeholder vocabulary. Do not extend without updating the tests
#: and every consumer that filters on these tokens.
EMAIL_TOKEN = "[EMAIL]"
PHONE_TOKEN = "[PHONE]"
ADDRESS_TOKEN = "[ADDRESS]"
NAME_TOKEN = "[NAME]"

#: Metadata keys whose values are direct identifiers and must never persist.
#: Structural keys (ticket_id, article_id, dates, state, ...) are untouched.
PII_METADATA_KEYS = frozenset(
    {
        "customer",
        "customer_name",
        "organization",
        "owner",
        "author",
    }
)

_EMAIL_RE = re.compile(
    r"[A-Za-z0-9._%+\-\u00e4\u00f6\u00fc\u00c4\u00d6\u00dc\u00df]+@[A-Za-z0-9.\-\u00e4\u00f6\u00fc\u00c4\u00d6\u00dc\u00df]+\.[A-Za-z]{2,}"
)

# Conservative phone pass: optional leading +, then at least 7 digits
# allowing spaces, dashes, dots, slashes and parentheses. Requires a
# separator or a long digit run so ticket numbers and years do not match.
_PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d .\-/()]{5,}\d)(?!\w)")

# Street-line indicators (German/Italian/English) followed by house number,
# or a postal-code-plus-city line. Conservative by construction.
# Compound heads allowed (Hauptstrasse, Bahnhofstrasse): the noun may be
# glued to a preceding word, so no leading word boundary.
_STREET_HEAD = r"[\w\u00e4\u00f6\u00fc\u00c4\u00d6\u00dc\u00df]*"
_STREET_NOUNS = (
    r"(?:Strasse|Stra\u00dfe|Str\.|Street|St\.|Via|Viale|Vicolo|Piazza|Allee|Weg|Gasse|Platz)"
)
_STREET_RE = re.compile(
    _STREET_HEAD + _STREET_NOUNS + r"\s+\d+[a-zA-Z]?"  # German order: Hauptstrasse 12
    r"|" + _STREET_NOUNS + r"\s+[A-ZÄÖÜ][\wäöüÄÖÜß'\-]*(?:\s+\d+[a-zA-Z]?)?",  # Via Roma 12
    re.IGNORECASE,
)
_POSTAL_RE = re.compile(
    r"\b(?:D-|I-|IT-|DE-)?\d{4,5}\s+[A-ZÄÖÜ][\wäöüÄÖÜß.'\-]+(?:\s+[A-ZÄÖÜ][\wäöüÄÖÜß.'\-]+)?"
)


@dataclass
class MaskedText:
    """Masked content plus per-category counts (counts only, never values)."""

    content: str
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        """Total number of redactions applied."""
        return sum(self.counts.values())


def mask_emails(text: str) -> MaskedText:
    """Replace email addresses with ``[EMAIL]``."""
    masked, n = _EMAIL_RE.subn(EMAIL_TOKEN, text)
    return MaskedText(content=masked, counts={"email": n})


def mask_phones(text: str) -> MaskedText:
    """Replace phone-number-like runs with ``[PHONE]``.

    Guarded: a candidate must contain at least 7 digits, otherwise it is
    left alone (ticket numbers, years, short ids).
    """

    count = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal count
        candidate = match.group(0).strip()
        # ISO/calendar dates are not phone numbers.
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", candidate):
            return match.group(0)
        digits = re.sub(r"\D", "", candidate)
        if len(digits) < 7:
            return match.group(0)
        count += 1
        return PHONE_TOKEN

    return MaskedText(content=_PHONE_RE.sub(_replace, text), counts={"phone": count})


def mask_postal_addresses(text: str) -> MaskedText:
    """Replace street lines and postal-code lines with ``[ADDRESS]``."""
    masked, n_street = _STREET_RE.subn(ADDRESS_TOKEN, text)
    masked, n_postal = _POSTAL_RE.subn(ADDRESS_TOKEN, masked)
    return MaskedText(content=masked, counts={"address": n_street + n_postal})


def mask_known_values(text: str, known: list[str]) -> MaskedText:
    """Replace exact known PII strings (names, orgs) with ``[NAME]``.

    Longest value first; case-insensitive; empty/blank values ignored.
    """
    values = sorted({v.strip() for v in known if v and v.strip()}, key=len, reverse=True)
    count = 0
    masked = text
    for value in values:
        pattern = re.compile(re.escape(value), re.IGNORECASE)
        masked, n = pattern.subn(NAME_TOKEN, masked)
        count += n
    return MaskedText(content=masked, counts={"known_name": count})


def mask_ticket_text(
    text: str,
    *,
    known_names: list[str] | None = None,
    known_orgs: list[str] | None = None,
) -> MaskedText:
    """Run all masking passes over free text; merged counts."""
    # Order matters: known values first so a name inside an email
    # local part does not fragment the email match.
    masked = text
    counts: dict[str, int] = {}
    for step in (
        lambda t: mask_known_values(t, list(known_names or []) + list(known_orgs or [])),
        mask_emails,
        mask_phones,
        mask_postal_addresses,
    ):
        result = step(masked)
        masked = result.content
        for key, value in result.counts.items():
            counts[key] = counts.get(key, 0) + value
    return MaskedText(content=masked, counts=counts)


def mask_metadata(metadata: dict[str, object]) -> dict[str, object]:
    """Replace direct-identifier metadata values with placeholders.

    Keys in :data:`PII_METADATA_KEYS` become ``[NAME]``; every other key
    passes through untouched (structural keys are needed for idempotent
    upsert). Values that are already masked text are left as-is.
    """
    masked: dict[str, object] = {}
    for key, value in metadata.items():
        if key in PII_METADATA_KEYS and isinstance(value, str) and value.strip():
            if NAME_TOKEN in value or EMAIL_TOKEN in value:
                masked[key] = value
            else:
                masked[key] = NAME_TOKEN
        else:
            masked[key] = value
    return masked
