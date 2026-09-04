"""Social headers are a compact OG lockup, not a cropped 1200×630 card."""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BRAND = REPO_ROOT / "frontend" / "digiweb" / "brand"
PUBLIC_BRAND = REPO_ROOT / "frontend" / "digiweb" / "reference" / "public" / "brand"
MARKETING_PUBLIC_BRAND = REPO_ROOT / "frontend" / "digithings-web" / "public" / "brand"
MARKETING_BRAND_PAGE = REPO_ROOT / "frontend" / "digithings-web" / "app" / "brand"
KIT_TS = REPO_ROOT / "frontend" / "digiweb" / "reference" / "lib" / "brandKit.ts"

pytestmark = pytest.mark.unit


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def header_mod():
    return _load("digiweb_brand_build_header", BRAND / "build-header.py")


@pytest.fixture(scope="module")
def og_headlines() -> dict[str, dict[str, str]]:
    src = ast.parse((BRAND / "build-og.py").read_text(encoding="utf-8"))
    for node in src.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "HEADLINES":
                    value = ast.literal_eval(node.value)
                    assert isinstance(value, dict)
                    return value
    raise AssertionError("HEADLINES missing from build-og.py")


def test_copy_is_the_og_headline(header_mod, og_headlines) -> None:
    og = header_mod._load_og()
    copy = og.HEADLINES["digithings"]
    assert copy == og_headlines["digithings"]
    assert copy["word"] == "digithings"
    assert copy["line"] == "AI infrastructure in a glass box you own."
    assert copy["domain"] == "digithings.ai"
    for lay in (header_mod.layout(og, spec) for spec in header_mod.FORMATS):
        assert lay.word == copy["word"]
        assert lay.line == copy["line"]
        assert lay.domain == copy["domain"]
        assert lay.bg == "#0A0E0C"
        assert lay.ink == "#ECEEF0"


def test_sizes_match_platform_uploads(header_mod) -> None:
    by_key = {spec.key: spec for spec in header_mod.FORMATS}
    assert by_key["x"].width == 1500 and by_key["x"].height == 500
    assert by_key["linkedin-personal"].width == 1584
    assert by_key["linkedin-personal"].height == 396
    assert by_key["linkedin-company"].width == 1128
    assert by_key["linkedin-company"].height == 191


def test_stack_fits_safe_zone_and_is_compact(header_mod) -> None:
    og = header_mod._load_og()
    for spec in header_mod.FORMATS:
        lay = header_mod.layout(og, spec)
        assert lay.inside_safe(), (spec.key, lay.ink_box(), spec.safe)
        stack_h = lay.stack_bottom - lay.stack_top
        # Company cover is 191px: the stack has to use most of that height or
        # the tagline becomes unreadably small. X and LinkedIn personal are
        # tall enough to keep a compact centred lockup.
        limit = spec.height * (0.90 if spec.key == "linkedin-company" else 0.55)
        assert stack_h < limit, spec.key
        # OG parks the domain at ~86% down a 630px card; that is the crop bug
        # on X / LinkedIn personal. Company is 191px tall, so the domain sits
        # near the bottom of the canvas by necessity — inside_safe covers it.
        if spec.key != "linkedin-company":
            assert lay.domain_baseline < spec.height * 0.72, spec.key
        assert spec.height / spec.width < 0.45, spec.key  # short, not 630/1200


def test_signoff_is_lowercase_and_names_no_clients(header_mod, og_headlines) -> None:
    copy = og_headlines["digithings"]
    txt = header_mod.signoff_text(copy)
    html = header_mod.signoff_html(copy)
    assert "digithings" in txt
    assert "https://digithings.ai" in txt
    assert copy["line"] in txt
    assert "digithings.ai" in html
    for blob in (txt, html):
        for needle in header_mod.FORBIDDEN:
            assert needle not in blob
        assert "live-trading" not in blob
        assert "live trading" not in blob


def test_committed_svgs_declare_platform_sizes() -> None:
    expected = {
        "digithings-x-1500x500.svg": (1500, 500),
        "digithings-linkedin-personal-1584x396.svg": (1584, 396),
        "digithings-linkedin-company-1128x191.svg": (1128, 191),
    }
    for name, (width, height) in expected.items():
        svg = (BRAND / "headers" / name).read_text(encoding="utf-8")
        assert f'width="{width}"' in svg
        assert f'height="{height}"' in svg
        assert "<text" not in svg
        assert "HEADLINES" in svg
        public = PUBLIC_BRAND / "headers" / name
        assert public.read_bytes() == (BRAND / "headers" / name).read_bytes()


def test_header_svg_is_outlined_not_text(header_mod) -> None:
    og = header_mod._load_og()
    if not og.FONT.exists():
        pytest.skip("geist font not installed — npm ci first")
    lay = header_mod.layout(og, header_mod.FORMATS[0])
    svg = header_mod.header_svg(og, lay)
    assert "<text" not in svg
    assert "build-header.py" in svg
    assert lay.word in svg or "path d=" in svg
    assert f'width="{lay.spec.width}"' in svg
    assert f'height="{lay.spec.height}"' in svg


def test_brand_kit_ts_matches_og_headlines(og_headlines) -> None:
    """The design-reference /brand constants must track HEADLINES — --check does not read TS."""
    kit = KIT_TS.read_text(encoding="utf-8")
    copy = og_headlines["digithings"]
    assert f'export const BRAND_WORD = "{copy["word"]}"' in kit
    assert f'export const BRAND_TAGLINE = "{copy["line"]}"' in kit
    assert f'export const BRAND_DOMAIN = "{copy["domain"]}"' in kit


def test_kit_is_not_on_the_marketing_site() -> None:
    """digithings.ai must not ship /brand — the kit is design-reference only."""
    assert not (MARKETING_BRAND_PAGE / "page.tsx").exists()
    assert not MARKETING_PUBLIC_BRAND.exists() or not any(MARKETING_PUBLIC_BRAND.rglob("*"))
    nav = (REPO_ROOT / "frontend" / "digithings-web" / "app" / "_nav.tsx").read_text(
        encoding="utf-8"
    )
    assert 'href: "/brand"' not in nav
    redirects = (REPO_ROOT / "frontend" / "digithings-web" / "public" / "_redirects").read_text(
        encoding="utf-8"
    )
    assert "/brand" not in redirects


def test_design_reference_ships_the_kit_page() -> None:
    page = (
        REPO_ROOT / "frontend" / "digiweb" / "reference" / "app" / "brand" / "page.tsx"
    ).read_text(encoding="utf-8")
    assert "{BRAND_TAGLINE}" in page
    assert "design-reference" in page
    nav_path = (
        REPO_ROOT / "frontend" / "digiweb" / "reference" / "components" / "site-nav.tsx"
    )
    assert 'href: "/brand"' in nav_path.read_text(encoding="utf-8")
