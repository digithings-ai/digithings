"""Leaf 7 (DIG-1080): a URL ingest is refused before the staged ``page.md`` write.

Spec §5.3, acceptance test 2: "URL ingest refused before the temp `page.md`
write". Leaf 6 screens inside `index_chunks` and so protects everything
downstream, but by then this module has already written the fetched bytes to
disk. This leaf stops that write.

The load-bearing assertion is therefore **that the write never happened**, not
that an exception was raised: a screen placed after the write still raises, and
a test that cannot tell the two placements apart pins nothing.

Asserting it by looking at the temp directory after the fact does not work
either. `ingest_url` removes its temp directory in a `finally`, so by the time
the caller sees the refusal the directory is already gone and
`os.listdir(tmpdir) == []` is satisfied by a screen that ran *after* the write.
So the assertion here is made against a spy that records every path opened for
writing inside that directory, and `test_clean_page_writes_page_md` is its
positive control: the same spy must show the write on the clean path.
"""

from __future__ import annotations

import builtins
import os
import tempfile
from pathlib import Path

import httpx
import pytest

from digibase import art9
from digisearch.pipeline import url_ingest as url_ingest_module
from digisearch.pipeline.url_ingest import UrlFetchError, ingest_url
from digisearch.search._stub import get_stub_index

pytestmark = pytest.mark.unit

_PUBLIC = "93.184.216.34"
_INDEX = "art9-url-ingest"

#: The Art. 9 identifier that trips `health/nhs_number`. Held in one place so
#: the leak assertions below can quote it without retyping it.
_ART9_NUMBER = "943 476 5919"

#: Realistic page shape: trafilatura only extracts a main body when there is
#: enough signal in it, so the identifier sits inside a three-paragraph article
#: rather than in boilerplate. `test_clean_control_does_not_trip_the_detector`
#: asserts the paragraph survives extraction with the identifier removed.
_ART9_HTML = f"""<html><head><title>Regional transport bulletin</title></head><body>
<article>
<h1>Regional transport bulletin</h1>
<p>The regional authority published its quarterly transport bulletin this week, covering
ridership trends across the metropolitan network, and reported that weekend services on the
northern corridor returned to their pre-closure timetable after the engineering works finished.
Officials said the revised schedule should reduce the average weekly delay by several minutes
for commuters travelling through the city centre during the morning peak.</p>
<p>Patient record: NHS number {_ART9_NUMBER} was quoted in the appendix to the report, and the
authority has asked that the identifier be removed from future editions before the bulletin is
republished online. A spokesperson confirmed the correction would be applied to the archive copy
as well, so that earlier downloads no longer carry the number.</p>
<p>Fares will be frozen for the coming year, and the authority expects to consult the public on a
proposed extension of the late-night service before the end of the season. Funding for the
programme comes from the regional transport budget allocated in the current spending review.</p>
</article>
</body></html>"""

#: The same page with the identifier paragraph replaced, so the only difference
#: between the two fixtures is the Art. 9 value.
_CLEAN_HTML = _ART9_HTML.replace(_ART9_NUMBER, "withheld on request")


def _handler_for(html: str):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=html, headers={"content-type": "text/html"})

    return handler


@pytest.fixture(autouse=True)
def _stub_backend(monkeypatch):
    monkeypatch.setenv("DIGISEARCH_ALLOW_STUB", "1")
    monkeypatch.setenv("DIGISEARCH_CHUNKER", "recursive")
    monkeypatch.setenv("DIGISEARCH_EMBED", "0")
    monkeypatch.delenv("DIGISEARCH_EMBEDDING_PROVIDER", raising=False)
    get_stub_index().clear()


@pytest.fixture
def staged_writes(monkeypatch):
    """Record every path opened for writing inside the ingest temp directory.

    Returns a list that is filled as the ingest runs. Filtering by the temp
    directory is what keeps unrelated ``open`` calls (httpx, trafilatura, the
    stub index) out of the record.
    """
    recorded: list[str] = []
    real_mkdtemp = tempfile.mkdtemp
    temp_dirs: list[str] = []

    def recording_mkdtemp(*args, **kwargs):
        path = real_mkdtemp(*args, **kwargs)
        temp_dirs.append(path)
        return path

    real_open = builtins.open

    def recording_open(file, mode="r", *args, **kwargs):
        if any(character in mode for character in "wxa+"):
            target = os.fspath(file)
            if any(
                target == directory or target.startswith(directory + os.sep)
                for directory in temp_dirs
            ):
                recorded.append(target)
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(tempfile, "mkdtemp", recording_mkdtemp)
    monkeypatch.setattr(builtins, "open", recording_open)
    return recorded


def _ingest(html: str, index_name: str = _INDEX):
    from digifetch import HttpFetcher

    with HttpFetcher(transport=httpx.MockTransport(_handler_for(html))) as fetcher:
        return ingest_url(
            f"http://{_PUBLIC}/bulletin",
            index_name=index_name,
            fetcher=fetcher,
        )


def test_clean_page_writes_page_md(staged_writes):
    """Positive control: the spy records the staged write when nothing is refused.

    Without this, every assertion below would also hold for a spy that never
    records anything, and the refusal tests would prove nothing.
    """
    _ingest(_CLEAN_HTML)

    assert [os.path.basename(path) for path in staged_writes] == ["page.md"]


def test_clean_control_does_not_trip_the_detector():
    """The clean fixture is clean in the string the screen actually sees."""
    from digisearch.web_search.extractor import extract_markdown

    markdown = extract_markdown(_CLEAN_HTML, url="https://example.org/bulletin")

    assert _ART9_NUMBER not in markdown
    assert art9.screen_text(markdown).decision == "allow"


def test_refused_before_page_md_is_written(staged_writes):
    """Acceptance test 2: the refusal happens before the staged write."""
    with pytest.raises(UrlFetchError) as excinfo:
        _ingest(_ART9_HTML)

    assert excinfo.value.code == "url_art9_refused"
    assert staged_writes == []
    assert (get_stub_index().get(_INDEX) or []) == []


def test_refusal_names_the_category_and_never_the_value(staged_writes):
    """The refusal reports the category; it never copies the value into the message."""
    with pytest.raises(UrlFetchError) as excinfo:
        _ingest(_ART9_HTML)

    message = excinfo.value.message
    assert "health" in message
    assert "art9:health:nhs_number" in message
    assert _ART9_NUMBER not in message


def test_screen_reads_the_extracted_markdown_once(monkeypatch, staged_writes):
    """The screen is handed the extracted markdown, exactly once, with no letter.

    Screening the raw HTML would be a different string and a different
    decision; more than one call would be a retry, which a refusal must not
    attract.
    """
    calls: list[tuple[str, dict]] = []
    real_screen_text = art9.screen_text

    def recording_screen_text(value, **kwargs):
        calls.append((value, kwargs))
        return real_screen_text(value, **kwargs)

    monkeypatch.setattr(url_ingest_module, "screen_text", recording_screen_text)

    with pytest.raises(UrlFetchError):
        _ingest(_ART9_HTML)

    assert len(calls) == 1
    screened, kwargs = calls[0]
    assert "<article>" not in screened
    assert _ART9_NUMBER in screened
    assert kwargs.get("exception_ref") is None


def test_clean_page_still_ingests(staged_writes):
    """The guard discriminates; it does not refuse every URL."""
    result = _ingest(_CLEAN_HTML)

    assert result.source_url == f"http://{_PUBLIC}/bulletin"
    assert result.chunks_created >= 1
    chunks = get_stub_index().get(_INDEX) or []
    assert [chunk.metadata.get("source_url") for chunk in chunks] == [
        result.source_url
    ] * result.chunks_created


def test_empty_extract_still_reports_its_own_code(staged_writes):
    """An empty extract keeps its own error code; the screen does not shadow it."""
    empty = "<html><head><title>Empty</title></head><body></body></html>"

    with pytest.raises(UrlFetchError) as excinfo:
        _ingest(empty)

    assert excinfo.value.code == "url_empty_extract"
    assert staged_writes == []


def test_the_staged_path_is_page_md_in_the_temp_directory():
    """Pin what the refusal is protecting: the staged file is `<tmpdir>/page.md`."""
    source = Path(url_ingest_module.__file__).read_text(encoding="utf-8")

    assert 'os.path.join(tmpdir, "page.md")' in source