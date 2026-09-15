"""Phase C monitor dedup (#4065, Task 3).

Pins the changedetection.io + Huginn-style dedup semantics: the landed Phase B
``normalize_url`` identity for URL keys (R2), a deterministic offline sha256
content fingerprint with the R7 multi-key text fallback
(``text`` → EXA ``highlights`` → OSS ``snippet``), ``url`` vs ``url_content``
matching, and the near-duplicate title collapse. Pure stdlib — no network, no
store, no page fetches.
"""

from __future__ import annotations

import hashlib

import pytest
from digisearch.monitors.dedup import dedup_results, fingerprint
from digisearch.monitors.models import DedupRule
from digisearch.web_search.citation import normalize_url

pytestmark = pytest.mark.unit


def test_normalize_uses_landed_phase_b_identity():
    # landed semantics: lowercase host, fragment dropped, default port dropped,
    # trailing slash trimmed except root, query preserved verbatim — NO utm_*
    # stripping (R2: dedup identity must equal Phase B citation identity)
    assert normalize_url("https://A.com/x/?utm_source=n#frag") == "https://a.com/x?utm_source=n"
    assert normalize_url("https://a.com:443/x/") == "https://a.com/x"


def test_unseen_url_is_new_changed_content_is_new():
    rule = DedupRule(match="url_content")
    seen = {"https://a.com/1": fingerprint("T1", "body one")}
    current = [
        {"url": "https://a.com/1", "title": "T1 EDITED substantially", "text": "body one v2"},
        {"url": "https://b.com/2", "title": "Brand new", "text": "hello"},
    ]
    new, stats = dedup_results(current, seen, rule)
    assert stats == {"seen": 1, "new": 1, "changed": 1, "unchanged": 0}
    assert {r["url"] for r in new} == {"https://a.com/1", "https://b.com/2"}


def test_near_duplicate_title_collapses():
    rule = DedupRule(match="url_content", similarity_threshold=0.5)
    seen = {"https://a.com/1": fingerprint("Bitcoin ETF flows rise", "x")}
    current = [{"url": "https://a.com/2", "title": "Bitcoin ETF flows rise!", "text": "y"}]
    new, stats = dedup_results(current, seen, rule)
    assert new == [] and stats["unchanged"] == 1


def test_fingerprint_is_deterministic_sha256_over_normalized_fields():
    expected = hashlib.sha256(b"t1\nbody one").hexdigest()
    assert expected in fingerprint("T1", "body one")
    assert fingerprint("T1", "body one") == fingerprint("  t1  ", "body\n  one")
    assert fingerprint("T1", "body one") != fingerprint("T1", "body one v2")
    assert fingerprint("T1", "body one") != fingerprint("T1 EDITED", "body one")


def test_match_url_ignores_content_changes():
    rule = DedupRule(match="url")
    seen = {"https://a.com/1": fingerprint("T1", "body one")}
    current = [
        {"url": "https://a.com/1", "title": "T1 EDITED", "text": "body one v2"},
        {"url": "https://b.com/2", "title": "Brand new", "text": "hello"},
    ]
    new, stats = dedup_results(current, seen, rule)
    assert stats == {"seen": 1, "new": 1, "changed": 0, "unchanged": 1}
    assert [r["url"] for r in new] == ["https://b.com/2"]


def test_match_url_does_not_collapse_near_duplicate_titles():
    rule = DedupRule(match="url", similarity_threshold=0.5)
    seen = {"https://a.com/1": fingerprint("Bitcoin ETF flows rise", "x")}
    current = [{"url": "https://a.com/2", "title": "Bitcoin ETF flows rise!", "text": "y"}]
    new, stats = dedup_results(current, seen, rule)
    assert [r["url"] for r in new] == ["https://a.com/2"]
    assert stats["new"] == 1


def test_unchanged_seen_result_matches_with_trailing_slash_identity():
    rule = DedupRule(match="url_content")
    seen = {"https://a.com/1": fingerprint("T1", "body one")}
    current = [{"url": "https://a.com/1/", "title": "T1", "text": "body one"}]
    new, stats = dedup_results(current, seen, rule)
    assert new == []
    assert stats == {"seen": 1, "new": 0, "changed": 0, "unchanged": 1}


def test_seen_counts_only_current_results_matching_memory():
    rule = DedupRule(match="url_content")
    seen = {"https://stale.example/9": fingerprint("Old story", "old")}
    current = [{"url": "https://b.com/2", "title": "Brand new", "text": "hello"}]
    new, stats = dedup_results(current, seen, rule)
    assert stats == {"seen": 0, "new": 1, "changed": 0, "unchanged": 0}
    assert [r["url"] for r in new] == ["https://b.com/2"]


def test_stats_keys_are_exact_and_empty_input_is_quiet():
    new, stats = dedup_results([], {}, DedupRule())
    assert new == []
    assert stats == {"seen": 0, "new": 0, "changed": 0, "unchanged": 0}


def test_exa_highlights_fall_back_when_text_absent():
    rule = DedupRule(match="url_content")
    seen = {"https://a.com/1": fingerprint("T1", "alpha beta")}
    current = [{"url": "https://a.com/1", "title": "T1", "highlights": ["alpha", "beta"]}]
    new, stats = dedup_results(current, seen, rule)
    assert new == [] and stats["unchanged"] == 1

    changed = [{"url": "https://a.com/1", "title": "T1", "highlights": ["gamma"]}]
    new2, stats2 = dedup_results(changed, seen, rule)
    assert [r["url"] for r in new2] == ["https://a.com/1"] and stats2["changed"] == 1


def test_oss_snippet_falls_back_when_text_and_highlights_absent():
    rule = DedupRule(match="url_content")
    seen = {"https://a.com/1": fingerprint("T1", "alpha beta")}
    current = [{"url": "https://a.com/1", "title": "T1", "snippet": "alpha beta"}]
    new, stats = dedup_results(current, seen, rule)
    assert new == [] and stats["unchanged"] == 1

    changed = [{"url": "https://a.com/1", "title": "T1", "snippet": "gamma"}]
    new2, stats2 = dedup_results(changed, seen, rule)
    assert [r["url"] for r in new2] == ["https://a.com/1"] and stats2["changed"] == 1


def test_empty_text_falls_through_to_highlights():
    rule = DedupRule(match="url_content")
    seen = {"https://a.com/1": fingerprint("T1", "alpha")}
    current = [{"url": "https://a.com/1", "title": "T1", "text": "  ", "highlights": ["alpha"]}]
    new, stats = dedup_results(current, seen, rule)
    assert new == [] and stats["unchanged"] == 1


def test_dissimilar_title_below_threshold_is_new():
    rule = DedupRule(match="url_content", similarity_threshold=0.9)
    seen = {"https://a.com/1": fingerprint("Bitcoin ETF flows rise", "x")}
    current = [{"url": "https://a.com/2", "title": "Ethereum staking yields", "text": "y"}]
    new, stats = dedup_results(current, seen, rule)
    assert [r["url"] for r in new] == ["https://a.com/2"]
    assert stats == {"seen": 0, "new": 1, "changed": 0, "unchanged": 0}
