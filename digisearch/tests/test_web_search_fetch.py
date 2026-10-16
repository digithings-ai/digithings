def test_fetch_markdown_decodes_and_extracts(monkeypatch):
    from digifetch import DownloadResult

    from digisearch.web_search import fetch as mod

    seen: dict[str, str] = {}

    def fake_extract(html: str, url: str = "") -> str:
        seen["html"], seen["url"] = html, url
        return "# body"

    monkeypatch.setattr(mod, "extract_markdown", fake_extract)

    class _FakeFetcher:
        def download(self, url: str) -> DownloadResult:
            return DownloadResult(
                status_code=200,
                url=url,
                content="<html><body><p>café</p></body></html>".encode(),
                content_type="text/html; charset=utf-8",
            )

    assert mod.fetch_markdown("https://a.com/1", fetcher=_FakeFetcher()) == "# body"
    assert "café" in seen["html"] and seen["url"] == "https://a.com/1"


def test_fetch_module_is_non_indexing():
    import inspect

    from digisearch.web_search import fetch as mod

    src = inspect.getsource(mod)
    assert "ingest_url" not in src
    assert "ingest_source" not in src
