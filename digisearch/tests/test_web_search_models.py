from digisearch.web_search.models import (  # noqa: F401
    WebSearchRequest,
    WebSearchResponse,
    recency_days_to_ddgs_timelimit,
    recency_days_to_searxng_time_range,
)


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


def test_domain_filter_normalizes_entries():
    from digisearch.web_search.models import apply_domain_filter

    results = [
        {"url": "https://a.com/x", "title": "a", "snippet": "s"},
        {"url": "https://sub.a.com/y", "title": "sub", "snippet": "s"},
        {"url": "https://evil.com/x", "title": "e", "snippet": "s"},
    ]
    kept = apply_domain_filter(
        results, include_domains=[" a.com "], exclude_domains=["", "  ", "EVIL.com"]
    )
    assert [r["url"] for r in kept] == ["https://a.com/x", "https://sub.a.com/y"]


def test_recency_mapping():
    assert recency_days_to_ddgs_timelimit(None) is None
    assert recency_days_to_searxng_time_range(None) is None
    assert recency_days_to_ddgs_timelimit(1) == "d"
    assert recency_days_to_ddgs_timelimit(7) == "w"
    assert recency_days_to_ddgs_timelimit(31) == "m"
    assert recency_days_to_ddgs_timelimit(365) == "y"
    assert recency_days_to_searxng_time_range(1) == "day"
    # searxng has no week bucket: sub-month windows map to month.
    assert recency_days_to_searxng_time_range(7) == "month"
    assert recency_days_to_searxng_time_range(31) == "month"
    assert recency_days_to_searxng_time_range(365) == "year"
