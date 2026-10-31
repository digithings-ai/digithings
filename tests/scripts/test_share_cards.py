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


def test_chat_metadata_has_a_production_base() -> None:
    chat = _text("apps/digichat/src/app/(digichat)/layout.tsx")
    assert "metadataBase: PUBLIC_ORIGIN" in chat
    docker = _text("infra/docker/Dockerfile.digichat-cloudflare")
    assert 'ARG DIGICHAT_PUBLIC_ORIGIN="https://digithings.ai"' in docker
    assert "ENV NEXT_PUBLIC_DIGICHAT_PUBLIC_ORIGIN=$DIGICHAT_PUBLIC_ORIGIN" in docker
    assert "localhost" not in chat


def _studio():
    import importlib.util
    import sys

    path = REPO_ROOT / "packages" / "brand" / "studio_compose.py"
    spec = importlib.util.spec_from_file_location("studio_compose", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["studio_compose"] = module
    spec.loader.exec_module(module)
    return module


def test_pixel_wordmark_draws_the_studio_mask_shape() -> None:
    import re

    studio = _studio()
    cells = set(studio.pixel_cells("DIGITHINGS", studio.pixel_font()))
    mask = _text("packages/brand/studio/wordmark-mask.svg")
    drawn = {
        (int(float(x)), int(float(y)))
        for x, y in re.findall(r'<rect x="([\d.]+)" y="([\d.]+)"', mask)
    }
    assert cells == drawn


def test_digiquant_card_is_the_pixel_wordmark_over_a_chart() -> None:
    studio = _studio()
    glyphs = studio.pixel_font("digiquant")
    # The module's own Q and A, not the family font's.
    assert glyphs["Q"][-1] == ".######"
    inner, width, height = studio.pixel_wordmark_inner(
        "DIGIQUANT", "#fff", module="digiquant", seed=1
    )
    assert (width, height) == (79.0, 10.0)
    assert inner.count("<rect") == 16 * len(studio.pixel_cells("DIGIQUANT", glyphs))
    svg = _text("packages/brand/og/digiquant-og.svg")
    assert "Pixel wordmark over the digiquant hero chart" in svg
    assert "<polyline" in svg
