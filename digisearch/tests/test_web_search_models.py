from digisearch.web_search.models import WebSearchRequest, WebSearchResponse  # noqa: F401


def test_request_defaults_fail_closed():
    req = WebSearchRequest(query="bitcoin etf flows")
    assert req.max_results == 4
    assert req.include_domains == []
    assert req.exclude_domains == []


def test_domain_filter_helper():
    from digisearch.web_search.models import apply_domain_filter

    results = [
        {"url": "https://a.com/x", "title": "a", "snippet": "s"},
        {"url": "https://evil.com/x", "title": "e", "snippet": "s"},
    ]
    kept = apply_domain_filter(results, include_domains=["a.com"], exclude_domains=["evil.com"])
    assert [r["url"] for r in kept] == ["https://a.com/x"]
