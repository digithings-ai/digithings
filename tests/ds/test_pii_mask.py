"""Tests for ticket PII masking (DIG-3578).

All fixtures are synthetic and clearly fake (Mustermann/Muster families,
example.com). No real customer data appears in this file.
"""

from __future__ import annotations

from digisearch.pipeline import pii_mask
from digisearch.pipeline.pii_mask import (
    ADDRESS_TOKEN,
    EMAIL_TOKEN,
    NAME_TOKEN,
    PHONE_TOKEN,
    PII_METADATA_KEYS,
    mask_emails,
    mask_known_values,
    mask_metadata,
    mask_phones,
    mask_postal_addresses,
    mask_ticket_text,
)

# Synthetic fixture: a ticket article body carrying every PII class.
ARTICLE_WITH_PII = """Ticket 4711: Login problem
Article 1 (customer/email)
From: Max Mustermann <max.mustermann@example.com>
Subject: cannot log in

Hello, this is Max Mustermann from Muster GmbH, Hauptstrasse 12, 80331 Muenchen.
Please call me back on +49 170 1234567 or write to max.mustermann@example.com.
My colleague Erika Muster (erika.muster@example.org, 089/9876543) can also help.
"""

TICKET_NUMBERS_MUST_SURVIVE = "Ticket 4711 article 3 from 2024, ref 12345"


def test_placeholder_vocabulary_is_fixed() -> None:
    assert (EMAIL_TOKEN, PHONE_TOKEN, ADDRESS_TOKEN, NAME_TOKEN) == (
        "[EMAIL]",
        "[PHONE]",
        "[ADDRESS]",
        "[NAME]",
    )


def test_emails_masked_everywhere() -> None:
    result = mask_emails(ARTICLE_WITH_PII)
    assert result.counts["email"] == 3
    assert "@" not in result.content
    assert result.content.count(EMAIL_TOKEN) == 3


def test_phones_masked_ticket_numbers_survive() -> None:
    result = mask_phones(ARTICLE_WITH_PII)
    assert result.counts["phone"] == 2
    assert result.content.count(PHONE_TOKEN) == 2
    untouched = mask_phones(TICKET_NUMBERS_MUST_SURVIVE)
    assert untouched.counts["phone"] == 0
    assert untouched.content == TICKET_NUMBERS_MUST_SURVIVE


def test_postal_addresses_masked() -> None:
    result = mask_postal_addresses(ARTICLE_WITH_PII)
    assert result.total >= 2
    assert "Hauptstrasse 12" not in result.content
    assert "80331" not in result.content


def test_known_names_masked_longest_first() -> None:
    result = mask_known_values(
        "Max Mustermann and Mustermann agree", ["Mustermann", "Max Mustermann"]
    )
    assert result.content == f"{NAME_TOKEN} and {NAME_TOKEN} agree"
    assert result.counts["known_name"] == 2


def test_known_values_case_insensitive_blank_ignored() -> None:
    result = mask_known_values("MAX MUSTERMANN wrote", ["max mustermann", "  ", ""])
    assert result.content == f"{NAME_TOKEN} wrote"


def test_full_text_no_raw_pii_remains() -> None:
    result = mask_ticket_text(
        ARTICLE_WITH_PII,
        known_names=["Max Mustermann", "Erika Muster"],
        known_orgs=["Muster GmbH"],
    )
    assert "max.mustermann@example.com" not in result.content
    assert "erika.muster@example.org" not in result.content
    assert "Max Mustermann" not in result.content
    assert "Muster GmbH" not in result.content
    assert "+49 170 1234567" not in result.content
    assert "80331" not in result.content
    assert result.total >= 8
    assert set(result.counts) >= {"known_name", "email", "phone", "address"}


def test_full_text_clean_input_is_noop() -> None:
    body = "Ticket 4711: scheduled maintenance window on 2024-05-01."
    result = mask_ticket_text(body)
    assert result.content == body
    assert result.total == 0


def test_metadata_pii_keys_redacted_structural_keys_kept() -> None:
    metadata = {
        "source": "zammad",
        "ticket_id": 4711,
        "number": "4711",
        "title": "Login problem",
        "state": "open",
        "customer": "Max Mustermann",
        "customer_id": 42,
        "customer_name": "Max Mustermann",
        "organization": "Muster GmbH",
        "owner": "Erika Muster",
        "created_at": "2024-05-01",
    }
    masked = mask_metadata(metadata)
    for key in ("customer", "customer_name", "organization", "owner"):
        assert masked[key] == NAME_TOKEN
    for key in ("source", "ticket_id", "number", "title", "state", "customer_id", "created_at"):
        assert masked[key] == metadata[key]


def test_metadata_keys_are_exact_not_prefix() -> None:
    # Structural keys must never be redacted: the set is exact.
    assert "customer_id" not in PII_METADATA_KEYS
    assert "ticket_id" not in PII_METADATA_KEYS
    assert mask_metadata({"customer_id": 42}) == {"customer_id": 42}


def test_pii_package_exports() -> None:
    assert pii_mask.EMAIL_TOKEN == EMAIL_TOKEN
