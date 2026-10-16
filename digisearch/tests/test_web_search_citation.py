import pytest

from digisearch.web_search.citation import Citation, normalize_url


def test_citation_shape_forbids_extras():
    from pydantic import ValidationError

    c = Citation(url="https://A.com/x#frag", title="A", excerpt="e")
    assert c.excerpt == "e"
    with pytest.raises(ValidationError):
        Citation(url="https://a.com", bogus="x")


def test_normalize_url_semantics():
    assert normalize_url("https://Example.COM:443/Path/?x=1#frag") == (
        "https://example.com/Path?x=1"
    )
    assert normalize_url("http://Example.com:80/a/") == "http://example.com/a"
    assert normalize_url("https://example.com/") == "https://example.com/"
