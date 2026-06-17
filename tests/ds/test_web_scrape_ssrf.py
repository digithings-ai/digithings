"""REM-064: SSRF allowlist for web-scrape hrefs."""

from __future__ import annotations

import pytest

from digisearch.ingestion.web_scrape import filter_scrape_hrefs, is_allowed_scrape_url


@pytest.mark.unit
@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://127.0.0.1/admin",
        "http://localhost/secret",
        "http://169.254.169.254/latest/meta-data/",
        "javascript:alert(1)",
    ],
)
def test_is_allowed_scrape_url_blocks_unsafe(url: str) -> None:
    assert is_allowed_scrape_url(url) is False


@pytest.mark.unit
def test_is_allowed_scrape_url_allows_public_https() -> None:
    assert is_allowed_scrape_url("https://example.com/doc") is True


@pytest.mark.unit
def test_filter_scrape_hrefs() -> None:
    hrefs = [
        "https://example.com/a",
        "file:///etc/passwd",
        "http://127.0.0.1/x",
    ]
    assert filter_scrape_hrefs(hrefs) == ["https://example.com/a"]
