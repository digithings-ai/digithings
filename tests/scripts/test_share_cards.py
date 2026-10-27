"""Link-preview metadata points at the studio cards."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.unit


def _text(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_digithings_root_points_at_the_wide_card() -> None:
    layout = _text("apps/digithings-web/app/layout.tsx")
    share = _text("apps/digithings-web/lib/share.ts")
    assert 'url: "/og.png"' in share
    assert "width: 1200" in share
    assert "height: 630" in share
    assert 'url: "/og-square.png"' in share
    assert "width: 1080" in share
    assert "SHARE_IMAGE" in layout
    assert "faviconThemeScript" in layout
    # A child openGraph block replaces the parent images unless it sets its own.
    home = _text("apps/digithings-web/app/page.tsx")
    assert "SHARE_IMAGE" in home


def test_book_summary_cards_point_at_the_square() -> None:
    for path in (
        "apps/digithings-web/app/book/[chapter]/page.tsx",
        "apps/digithings-web/app/book/[chapter]/[section]/page.tsx",
    ):
        source = _text(path)
        assert 'card: "summary"' in source
        assert "SHARE_SQUARE" in source
        assert "SHARE_IMAGE" in source


def test_digiquant_and_chat_point_at_og_png() -> None:
    quant = _text("apps/digiquant-web/app/layout.tsx")
    chat = _text("apps/digichat/src/app/(digichat)/layout.tsx")
    assert 'url: "/og.png"' in quant
    assert 'images: ["/og.png"]' in quant
    assert "faviconThemeScript" in quant
    assert 'url: "/og.png"' in chat
    assert 'images: ["/og.png"]' in chat
    assert "faviconThemeScript" in chat
