"""Product `chrome.skin: digichat` @imports gallery chatbot.css outside web/.

The Cloudflare Container / GHCR image COPY `cloudflare/digiweb/web` and
`cloudflare/digiweb/design` only. Without the gallery sheet in the build
context, `next build` fails (deploy after #3715, 2026-09-08):

    Can't resolve '../../../reference/app/(chatbot)/chatbot/chatbot.css'
    in '/app/cloudflare/digiweb/web/src/styles'
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
GALLERY_CSS = "cloudflare/digiweb/reference/app/(chatbot)/chatbot/chatbot.css"
PRODUCT_IMPORT = "../../../reference/app/(chatbot)/chatbot/chatbot.css"
DOCKERFILES = (
    "Dockerfile.digichat-cloudflare",
    "cloudflare/digichat/Dockerfile",
)


def test_gallery_chatbot_css_exists() -> None:
    assert (REPO_ROOT / GALLERY_CSS).is_file()


def test_product_skin_imports_gallery_sheet_not_a_fork() -> None:
    text = (REPO_ROOT / "cloudflare/digiweb/web/src/styles/chatbot.css").read_text(
        encoding="utf-8"
    )
    assert PRODUCT_IMPORT in text
    assert "@import" in text


def test_dockerfiles_copy_gallery_chatbot_css() -> None:
    for rel in DOCKERFILES:
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert GALLERY_CSS in text, f"{rel} must COPY {GALLERY_CSS} into the builder"
