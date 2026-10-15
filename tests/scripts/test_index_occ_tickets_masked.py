"""Guard: ticket index chunks are PII-masked before embedding (DIG-3578).

Chris (14 Oct) decided: rebuild the OCC ticket index WITH masking, daily.
Masking runs in ``build_ticket_chunks`` -- the single chunk-building choke
point -- so raw direct identifiers never reach embedding or the index.

This is deliberately scoped to the INDEX surface only. The live MCP demo
surface stays unmasked per the pinned decision in
``test_zammad_mcp_no_mask`` (Chris, 6 Oct); nothing here touches
``scripts/zammad_mcp/``.
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


def test_chunk_content_carries_no_raw_pii() -> None:
    (chunk,) = build_ticket_chunks(_ticket(), _articles(), customer_name="Max Mustermann")
    assert "Max Mustermann" not in chunk.content
    assert "max.mustermann@example.com" not in chunk.content
    assert "+49 170 1234567" not in chunk.content
    assert "[NAME]" in chunk.content
    assert "[PHONE]" in chunk.content
    assert "[EMAIL]" in chunk.content


def test_chunk_metadata_identifiers_redacted_structure_kept() -> None:
    (chunk,) = build_ticket_chunks(_ticket(), _articles(), customer_name="Max Mustermann")
    assert chunk.metadata["customer"] == "[NAME]"
    assert chunk.metadata["customer_name"] == "[NAME]"
    assert chunk.metadata["organization"] == "[NAME]"
    assert chunk.metadata["owner"] == "[NAME]"
    assert chunk.metadata["ticket_id"] == 4711
    assert chunk.metadata["customer_id"] == 42
