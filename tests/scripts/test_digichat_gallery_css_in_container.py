"""Product `chrome.skin: digichat` grammar lives in the package (WS1).

The digichat grammar sheet moved from the reference gallery into
`packages/ui/src/styles/chat-digichat.css`, and the shared app theme bridge
into `packages/ui/src/styles/digichat-app-theme.css`. The Cloudflare
Container / GHCR image COPY `packages/ui` and `packages/design` only, so the
build no longer needs the gallery sheet in its context (closes #3717).
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_CSS = "packages/ui/src/styles/chat-digichat.css"
BRIDGE_CSS = "packages/ui/src/styles/digichat-app-theme.css"
GALLERY_CSS = "apps/reference/app/(chatbot)/chatbot/chatbot.css"
SHIM_CSS = "packages/ui/src/styles/chatbot.css"
DOCKERFILES = (
    "Dockerfile.digichat-cloudflare",
    "apps/digichat/Dockerfile",
)


def test_package_chat_grammar_sheet_exists() -> None:
    text = (REPO_ROOT / PACKAGE_CSS).read_text(encoding="utf-8")
    assert '[data-thread-skin="digichat"]' in text
    assert ".aui-theme-stage" in text


def test_shared_app_theme_bridge_exists() -> None:
    text = (REPO_ROOT / BRIDGE_CSS).read_text(encoding="utf-8")
    assert "--color-background: var(--background)" in text
    assert "--background: oklch(1 0 0)" in text


def test_gallery_sheet_and_shim_are_gone() -> None:
    assert not (REPO_ROOT / GALLERY_CSS).exists()
    assert not (REPO_ROOT / SHIM_CSS).exists()


def test_package_sheet_reaches_nowhere_into_reference() -> None:
    for rel in (PACKAGE_CSS, BRIDGE_CSS):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "apps/reference" not in text, f"{rel} must not reach into reference/"


def test_dockerfiles_no_longer_copy_gallery_chatbot_css() -> None:
    for rel in DOCKERFILES:
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert GALLERY_CSS not in text, f"{rel} must not COPY {GALLERY_CSS}"
