"""Package-level tests: public surface and the lazy (playwright-free) import.

The headline guarantee: ``import digifetch`` must NOT import playwright, so the
package is usable on a machine without a browser installed (CI, the dev venv).
"""

from __future__ import annotations

import sys

import pytest

pytestmark = pytest.mark.unit


def test_import_digifetch_does_not_import_playwright() -> None:
    """Importing the package pulls only the light deps — never playwright."""
    # Drop any cached import so this is a faithful fresh-import check.
    for mod in list(sys.modules):
        if mod == "digifetch" or mod.startswith("digifetch.") or mod.startswith("playwright"):
            del sys.modules[mod]

    import digifetch  # noqa: F401 — importing for its side effect (module load)

    assert not any(m == "playwright" or m.startswith("playwright.") for m in sys.modules), (
        "import digifetch must not import playwright"
    )
    # The browser submodule must also stay unimported until explicitly used.
    assert "digifetch.browser" not in sys.modules


def test_public_api_exports_present() -> None:
    import digifetch

    for name in (
        "RetryPolicy",
        "with_retry",
        "RateLimiter",
        "HttpFetcher",
        "FetchResult",
        "DownloadResult",
        "DownloadTooLargeError",
        "cookies_from_playwright",
        "DEFAULT_TIMEOUT",
        "BrowserConfig",
        "browser_session",
        "Page",
        "BrowserContext",
        "BrowserNotAvailableError",
    ):
        assert hasattr(digifetch, name), f"missing public export: {name}"
        assert name in digifetch.__all__, f"{name} not advertised in __all__"


def test_lazy_browser_symbol_resolves_on_access() -> None:
    import digifetch

    # Accessing a browser export triggers the PEP 562 __getattr__ shim, which
    # imports digifetch.browser on demand (still no playwright at this point).
    assert digifetch.browser_session is not None
    assert "digifetch.browser" in sys.modules
    assert "playwright" not in sys.modules


def test_unknown_attribute_raises_attribute_error() -> None:
    import digifetch

    with pytest.raises(AttributeError, match="no attribute 'nope'"):
        _ = digifetch.nope


def test_version_is_set() -> None:
    import digifetch

    assert digifetch.__version__ == "0.1.0"
