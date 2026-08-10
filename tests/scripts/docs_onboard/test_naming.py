from __future__ import annotations

import pytest

from scripts.docs_onboard.naming import normalize_digi_product_names

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("DigiGraph", "digigraph"),
        ("DigiGraph API reference", "digigraph API reference"),
        ("DigiThings — Ecosystem Overview", "digithings — Ecosystem Overview"),
        ("ARCHITECTURE", "ARCHITECTURE"),
        ("DigiChatSession", "DigiChatSession"),
    ],
)
def test_normalize_digi_product_names(raw: str, expected: str) -> None:
    assert normalize_digi_product_names(raw) == expected
