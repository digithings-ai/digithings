from digisearch.web_search.extractor import extract_markdown

HTML = "<html><body><nav>menu</nav><article><h1>T</h1><p>Hello <b>world</b></p><ul><li>a</li></ul></article></body></html>"


def test_extract_markdown_keeps_content_drops_nav():
    md = extract_markdown(HTML, url="https://a.com/1")
    assert "Hello" in md
    assert "menu" not in md
