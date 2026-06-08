"""Tests for digifetch.browser — session lifecycle with a fully mocked Playwright.

Playwright is NOT installed in CI; these tests inject a fake ``sync_playwright``
factory (mirroring twelve-x's ``_make_mock_playwright``) so the lifecycle is
exercised without a real browser. We assert the engine launches headless, wires
the user-agent / default timeout, yields the live page+context, and *always*
closes the browser — even when the caller's body raises.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from digifetch.browser import (
    BrowserConfig,
    BrowserContext,
    BrowserNotAvailableError,
    Page,
    browser_session,
)

pytestmark = pytest.mark.unit


def _make_mock_playwright() -> tuple[MagicMock, MagicMock, MagicMock, MagicMock]:
    """Build a fake sync_playwright() context manager.

    Returns ``(factory, browser, context, page)`` so tests can assert calls.
    """
    page = MagicMock(name="page")
    page.content.return_value = "<html>fixture</html>"

    context = MagicMock(name="context")
    context.new_page.return_value = page
    context.cookies.return_value = [{"name": "session", "value": "abc123"}]

    browser = MagicMock(name="browser")
    browser.new_context.return_value = context

    chromium = MagicMock(name="chromium")
    chromium.launch.return_value = browser

    pw = MagicMock(name="pw")
    pw.chromium = chromium

    factory = MagicMock(name="sync_playwright")
    cm = factory.return_value
    cm.__enter__.return_value = pw
    cm.__exit__.return_value = False
    return factory, browser, context, page


def test_session_yields_live_page_and_context() -> None:
    factory, browser, context, page = _make_mock_playwright()
    with browser_session(sync_playwright_factory=factory) as (p, ctx):
        assert p is page
        assert ctx is context
        assert p.content() == "<html>fixture</html>"
    browser.close.assert_called_once()


def test_default_launch_is_headless() -> None:
    factory, browser, _ctx, _page = _make_mock_playwright()
    with browser_session(sync_playwright_factory=factory):
        pass
    factory.return_value.__enter__.return_value.chromium.launch.assert_called_once_with(
        headless=True
    )


def test_user_agent_and_timeout_and_viewport_wired() -> None:
    factory, browser, context, page = _make_mock_playwright()
    cfg = BrowserConfig(
        user_agent="UA/1.0",
        default_timeout_ms=45_000.0,
        viewport={"width": 1280, "height": 800},
    )
    with browser_session(cfg, sync_playwright_factory=factory):
        pass
    browser.new_context.assert_called_once_with(
        user_agent="UA/1.0", viewport={"width": 1280, "height": 800}
    )
    page.set_default_timeout.assert_called_once_with(45_000.0)


def test_no_user_agent_means_default_context() -> None:
    factory, browser, _ctx, _page = _make_mock_playwright()
    with browser_session(sync_playwright_factory=factory):
        pass
    # No user_agent / viewport set → context created with no extra kwargs.
    browser.new_context.assert_called_once_with()


def test_browser_closed_even_when_body_raises() -> None:
    factory, browser, _ctx, _page = _make_mock_playwright()

    class _CallerError(RuntimeError):
        pass

    raised = False
    try:
        with browser_session(sync_playwright_factory=factory):
            raise _CallerError("boom in caller body")
    except _CallerError:
        raised = True
    assert raised, "caller error should propagate out of browser_session"
    browser.close.assert_called_once()  # teardown still ran


def test_launch_args_forwarded() -> None:
    factory, browser, _ctx, _page = _make_mock_playwright()
    cfg = BrowserConfig(launch_args={"args": ["--no-sandbox"]})
    with browser_session(cfg, sync_playwright_factory=factory):
        pass
    factory.return_value.__enter__.return_value.chromium.launch.assert_called_once_with(
        headless=True, args=["--no-sandbox"]
    )


def test_unknown_browser_raises() -> None:
    factory, _browser, _ctx, _page = _make_mock_playwright()
    # The fake pw only defines `chromium`; firefox attr is a MagicMock, so to
    # simulate "unknown" we point at a name the SUT looks up and we set to None.
    factory.return_value.__enter__.return_value.firefox = None
    with pytest.raises(ValueError, match="unknown browser"):
        with browser_session(BrowserConfig(browser="firefox"), sync_playwright_factory=factory):
            pass


def test_missing_playwright_raises_actionable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the real import path is used and playwright is absent, raise clearly."""
    import builtins

    real_import = builtins.__import__

    def _no_playwright(name: str, *args: object, **kwargs: object):
        if name.startswith("playwright"):
            raise ImportError("No module named 'playwright'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_playwright)
    # No injected factory → falls back to the real lazy import, which now fails.
    with pytest.raises(BrowserNotAvailableError, match="digifetch\\[browser\\]"):
        with browser_session():
            pass


def test_protocols_are_runtime_checkable() -> None:
    """A duck-typed object with the seam methods satisfies the Protocols.

    This is the typing-seam contract: the real ``playwright.sync_api.Page`` /
    ``BrowserContext`` satisfy these Protocols structurally (so callers get
    type-checking without importing playwright). We assert with a minimal real
    object — ``MagicMock`` is intentionally not used here because its attribute
    synthesis does not register against ``runtime_checkable`` ``isinstance``.
    """

    class _DuckPage:
        def goto(self, url: str, **kwargs: object) -> None:
            return None

        def content(self) -> str:
            return ""

        def wait_for_selector(self, selector: str, **kwargs: object) -> None:
            return None

        def set_default_timeout(self, timeout: float) -> None:
            return None

    class _DuckContext:
        def cookies(self, urls: object = None) -> list:
            return []

        def new_page(self) -> object:
            return object()

    assert isinstance(_DuckPage(), Page)
    assert isinstance(_DuckContext(), BrowserContext)
