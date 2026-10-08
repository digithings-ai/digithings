"""Deterministic-render guard for the client-facing invoice template (DIG-2519).

DIG-2519 found the template render was not deterministic: the HTML fetches
Geist Mono from fonts.googleapis.com, and headless Chromium without
``--virtual-time-budget`` wrote a Menlo/Times fallback PDF on 1 of 5 runs
while still exiting 0. This suite pins the two cures:

1. The documented render path (README + template comment) passes
   ``--virtual-time-budget`` so the webfont fetch settles before the PDF is
   written.
2. ``assert_pdf_fonts`` fails loud on a Menlo/Times fallback PDF instead of
   letting a fallback render pass as a successful send candidate.

Source of record: ``packages/design/invoice/index.html`` (placeholders only;
real client names/amounts stay out of the repo per the invoice README).
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = REPO_ROOT / "packages/design/invoice/index.html"
README = REPO_ROOT / "packages/design/invoice/README.md"

BUDGET_FLAG = "--virtual-time-budget"

# A fallback render embeds one of these instead of the intended webfont.
FALLBACK_FONTS = ("Menlo", "Times", "/Times-", "Courier")


def assert_pdf_fonts(pdf_bytes: bytes) -> None:
    """Fail loud when a rendered invoice PDF fell back to system fonts.

    A good render embeds GeistMono; a racy render (no virtual-time budget)
    embeds Menlo/Times instead while Chromium still exits 0. Raises
    ``AssertionError`` naming the fallback font found.
    """
    text = pdf_bytes.decode("latin-1", errors="replace")
    fallbacks = {name for name in FALLBACK_FONTS if name in text}
    has_webfont = "GeistMono" in text or "Geist-Mono" in text
    assert not (fallbacks and not has_webfont), (
        "invoice PDF used fallback font(s) "
        f"{sorted(fallbacks)} without the Geist Mono webfont; "
        f"re-render with {BUDGET_FLAG}=10000"
    )


@pytest.mark.unit
def test_readme_render_path_passes_virtual_time_budget() -> None:
    assert BUDGET_FLAG in README.read_text(), (
        "README render command must pass --virtual-time-budget (DIG-2519)"
    )


@pytest.mark.unit
def test_template_comment_matches_readme_budget() -> None:
    assert BUDGET_FLAG in TEMPLATE.read_text(), (
        "template usage comment must document the same --virtual-time-budget"
    )


@pytest.mark.unit
def test_template_has_no_hardcoded_helvetica() -> None:
    text = TEMPLATE.read_text()
    assert "Helvetica" not in text, "template must not hardcode Helvetica (DIG-2519 failure mode)"


@pytest.mark.unit
def test_template_loads_geist_mono_webfont() -> None:
    text = TEMPLATE.read_text()
    assert "fonts.googleapis.com" in text and "Geist" in text


@pytest.mark.unit
def test_assert_pdf_fonts_rejects_menlo_times_fallback() -> None:
    with pytest.raises(AssertionError, match="Menlo"):
        assert_pdf_fonts(b"/BaseFont/Menlo-Regular /BaseFont/Times-Roman")


@pytest.mark.unit
def test_assert_pdf_fonts_accepts_geist_mono_render() -> None:
    assert_pdf_fonts(b"/BaseFont/GeistMono-Regular /BaseFont/GeistMono-Medium")
