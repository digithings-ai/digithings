"""Headless-browser session lifecycle (the Playwright seam).

Both twelve-x scrapers open a browser the same way and differ only in what they
*do* with the page:

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(user_agent=...)   # TE sets a UA
        page = context.new_page()
        page.set_default_timeout(45_000)                 # TE sets this
        ...                                              # ← site-specific
        browser.close()

This module extracts *only* that lifecycle as a context manager that yields the
live ``page`` (and its ``context``, needed for ``context.cookies()``). Login,
``page.fill``/``click`` selector flows, "show more" pagination, row extraction
and HTML parsing stay in the consumer — they are selector-driven and have no
generic shape from a single consumer (see ARCHITECTURE.md "Deliberately not
extracted").

Optional dependency
-------------------
Playwright is the ``digifetch[browser]`` extra and is **not** imported at module
import time — the ``from playwright.sync_api import sync_playwright`` is deferred
into :func:`browser_session` so ``import digifetch`` works (and tests run)
without playwright or a downloaded browser. A missing dependency raises an
actionable :class:`BrowserNotAvailableError`, mirroring
``digibase.connectors.supabase.from_env`` and twelve-x's own TE ``RuntimeError``.

Typing without the dependency
-----------------------------
``Page`` / ``BrowserContext`` are minimal ``Protocol``s (structural types) so
consumers and this module get real type hints even when playwright is absent —
the same technique as ``digibase``'s ``SupabaseClient`` Protocol. The real
Playwright objects satisfy them structurally.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable  # noqa: ANN401 — see Page protocol below

logger = logging.getLogger(__name__)


class BrowserNotAvailableError(RuntimeError):
    """Raised when the optional ``digifetch[browser]`` (playwright) is missing."""


@runtime_checkable
class Page(Protocol):
    """Minimal structural view of a Playwright ``Page``.

    Only the members used across the engine seam are declared; the real
    ``playwright.sync_api.Page`` satisfies this structurally. Methods return
    ``Any`` because their concrete Playwright return types are unavailable when
    the optional dependency is absent (the whole point of the Protocol).
    """

    def goto(self, url: str, **kwargs: Any) -> Any:  # noqa: ANN401, D102
        raise NotImplementedError
    def content(self) -> str: ...  # noqa: D102, E704
    def wait_for_selector(self, selector: str, **kwargs: Any) -> Any: ...  # noqa: ANN401,D102,E704
    def set_default_timeout(self, timeout: float) -> None: ...  # noqa: D102, E704


@runtime_checkable
class BrowserContext(Protocol):
    """Minimal structural view of a Playwright ``BrowserContext``.

    Exposes ``cookies()`` — the hand-off twelve-x uses to replay an
    authenticated session over plain HTTP (see :mod:`digifetch.http`).
    """

    def cookies(self, urls: str | list[str] | None = None) -> list[dict[str, Any]]: ...  # noqa: ANN401,D102,E704
    def new_page(self) -> Any: ...  # noqa: ANN401, D102, E704


@dataclass(frozen=True)
class BrowserConfig:
    """Configuration for a headless-browser session.

    Attributes:
        headless:         Launch headless (always True in CI/scrape contexts).
        user_agent:       Optional UA string set on the browser context. TE's
                          scraper sets a desktop-Chrome UA to avoid bot blocks;
                          primemarket leaves it default. ``None`` = Playwright
                          default.
        default_timeout_ms: Per-page default timeout (ms) applied via
                          ``page.set_default_timeout``. TE uses 45_000.
        browser:          Which Playwright browser to launch (``chromium`` /
                          ``firefox`` / ``webkit``). Both consumers use chromium.
        viewport:         Optional ``{"width", "height"}`` for the context.
        launch_args:      Extra args forwarded to ``<browser>.launch(...)``.
    """

    headless: bool = True
    user_agent: str | None = None
    default_timeout_ms: float = 30_000.0
    browser: str = "chromium"
    viewport: Mapping[str, int] | None = None
    launch_args: Mapping[str, Any] | None = None


def _import_sync_playwright() -> Any:  # noqa: ANN401 — playwright is an optional dep, untyped here
    """Import ``sync_playwright`` lazily; raise an actionable error if absent."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - exercised via monkeypatched import in tests
        raise BrowserNotAvailableError(
            "playwright is not installed — install the browser extra:\n"
            "    pip install 'digifetch[browser]' && playwright install chromium"
        ) from exc
    return sync_playwright


@contextmanager
def browser_session(
    config: BrowserConfig | None = None,
    *,
    sync_playwright_factory: Any = None,  # noqa: ANN401 — injected callable for tests
) -> Iterator[tuple[Page, BrowserContext]]:
    """Open a headless browser and yield the live ``(page, context)`` pair.

    Handles the full lifecycle both twelve-x scrapers share — launch, context
    (with optional user-agent / viewport), page (with default timeout) — and
    **guarantees teardown**: the browser is closed and the Playwright driver
    stopped even if the body raises. The caller drives the page (navigate, fill
    selectors, click, read ``content()``) — that logic is site-specific and
    stays in the consumer.

    Args:
        config: Session configuration; a default :class:`BrowserConfig` if None.
        sync_playwright_factory: Inject a fake ``sync_playwright`` callable for
            unit tests (mirrors twelve-x's ``patch(... sync_playwright ...)``).
            When None, the real one is imported lazily.

    Yields:
        ``(page, context)`` — the live page and its browser context. ``context``
        is yielded so callers can pull ``context.cookies()`` for an HTTP hand-off.

    Raises:
        BrowserNotAvailableError: if playwright is not installed.
        ValueError: if ``config.browser`` is not a known Playwright browser.
    """
    cfg = config or BrowserConfig()
    factory = sync_playwright_factory or _import_sync_playwright()

    with factory() as pw:
        browser_type = getattr(pw, cfg.browser, None)
        if browser_type is None:
            raise ValueError(f"unknown browser {cfg.browser!r} — expected chromium/firefox/webkit")
        launch_kwargs: dict[str, Any] = {"headless": cfg.headless}
        if cfg.launch_args:
            launch_kwargs.update(cfg.launch_args)
        browser = browser_type.launch(**launch_kwargs)
        try:
            context_kwargs: dict[str, Any] = {}
            if cfg.user_agent:
                context_kwargs["user_agent"] = cfg.user_agent
            if cfg.viewport:
                context_kwargs["viewport"] = dict(cfg.viewport)
            context = browser.new_context(**context_kwargs)
            page = context.new_page()
            page.set_default_timeout(cfg.default_timeout_ms)
            logger.debug(
                "browser_session: launched %s (headless=%s, ua=%s)",
                cfg.browser,
                cfg.headless,
                bool(cfg.user_agent),
            )
            yield page, context
        finally:
            browser.close()
