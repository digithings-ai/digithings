"""Guard: ticket index chunks keep the article text (DIG-3964).

No PII masking: the invite link is the only gate (Chris, 9 Oct, reaffirmed
16 Oct). ``build_ticket_chunks`` stores the body and the metadata as written.
"""

from __future__ import annotations

import pytest

from scripts.index_occ_tickets import build_ticket_chunks

pytestmark = pytest.mark.unit


def _ticket() -> dict:
    return {
        "id": 4711,
        "number": "4711",
        "title": "Login problem",
        "state": "open",
        "group": "Support",
        "priority": "high",
        "customer": "Max Mustermann",
        "customer_id": 42,
        "organization": "Muster GmbH",
        "owner": "Erika Muster",
        "created_at": "2024-05-01",
        "updated_at": "2024-05-02",
    }


def _articles() -> list:
    return [
        {
            "id": 7,
            "body": ("<p>Call Max Mustermann at +49 170 1234567, max.mustermann@example.com</p>"),
            "sender": "customer",
            "type": "email",
            "from": "Max Mustermann",
            "subject": "help",
            "internal": False,
            "created_at": "2024-05-01",
        }
    ]


def test_chunk_content_keeps_the_article_text() -> None:
    (chunk,) = build_ticket_chunks(_ticket(), _articles(), customer_name="Max Mustermann")
    assert "Max Mustermann" in chunk.content
    assert "max.mustermann@example.com" in chunk.content
    assert "+49 170 1234567" in chunk.content
    assert "[NAME]" not in chunk.content
    assert "[PHONE]" not in chunk.content
    assert "[EMAIL]" not in chunk.content


def test_chunk_metadata_keeps_identifiers_and_structure() -> None:
    (chunk,) = build_ticket_chunks(_ticket(), _articles(), customer_name="Max Mustermann")
    assert chunk.metadata["customer"] == "Max Mustermann"
    assert chunk.metadata["customer_name"] == "Max Mustermann"
    assert chunk.metadata["organization"] == "Muster GmbH"
    assert chunk.metadata["owner"] == "Erika Muster"
    assert chunk.metadata["ticket_id"] == 4711
    assert chunk.metadata["customer_id"] == 42
