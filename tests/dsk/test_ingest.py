"""LocalPathCorpusBuilder tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from digiskills.ingest import LocalPathCorpusBuilder
from digiskills.models import SkillSource, SourceKind

pytestmark = pytest.mark.unit


def _source(path: Path) -> SkillSource:
    return SkillSource(kind=SourceKind.LOCAL_PATH, name="acme-sdk", local_path=path)


def test_ingests_text_files_and_skips_binaries(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# hi\n")
    (tmp_path / "app.py").write_text("print('hi')\n")
    (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    corpus = LocalPathCorpusBuilder().build(_source(tmp_path))

    origins = {d.origin for d in corpus.documents}
    assert origins == {"README.md", "app.py"}
    assert corpus.truncated is False


def test_skips_ignored_directories(tmp_path: Path) -> None:
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "junk.md").write_text("junk\n")
    (tmp_path / "keep.md").write_text("keep\n")

    corpus = LocalPathCorpusBuilder().build(_source(tmp_path))

    assert [d.origin for d in corpus.documents] == ["keep.md"]


def test_skips_empty_or_whitespace_only_files(tmp_path: Path) -> None:
    (tmp_path / "empty.md").write_text("   \n\n")
    (tmp_path / "real.md").write_text("content\n")

    corpus = LocalPathCorpusBuilder().build(_source(tmp_path))

    assert [d.origin for d in corpus.documents] == ["real.md"]


def test_max_files_cap_truncates(tmp_path: Path) -> None:
    for i in range(5):
        (tmp_path / f"doc{i}.md").write_text(f"content {i}\n")

    corpus = LocalPathCorpusBuilder(max_files=2).build(_source(tmp_path))

    assert len(corpus.documents) == 2
    assert corpus.truncated is True


def test_max_total_chars_cap_truncates(tmp_path: Path) -> None:
    (tmp_path / "big.md").write_text("x" * 1000)

    corpus = LocalPathCorpusBuilder(max_total_chars=10).build(_source(tmp_path))

    assert corpus.truncated is True
    assert corpus.total_chars <= 10


def test_max_file_chars_truncates_single_file(tmp_path: Path) -> None:
    (tmp_path / "big.md").write_text("y" * 1000)

    corpus = LocalPathCorpusBuilder(max_file_chars=50).build(_source(tmp_path))

    assert corpus.truncated is True
    assert len(corpus.documents[0].content) == 50


def test_missing_path_raises(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    with pytest.raises(FileNotFoundError):
        LocalPathCorpusBuilder().build(_source(missing))


def test_wrong_kind_raises() -> None:
    source = SkillSource(kind=SourceKind.URLS, name="acme-sdk", urls=["https://example.com"])
    with pytest.raises(ValueError, match="LOCAL_PATH"):
        LocalPathCorpusBuilder().build(source)


def test_single_file_source(tmp_path: Path) -> None:
    file_path = tmp_path / "solo.md"
    file_path.write_text("solo content\n")

    corpus = LocalPathCorpusBuilder().build(_source(file_path))

    assert len(corpus.documents) == 1
    assert corpus.documents[0].origin == str(file_path)


def test_content_type_by_extension(tmp_path: Path) -> None:
    (tmp_path / "spec.json").write_text('{"openapi": "3.0.0"}')

    corpus = LocalPathCorpusBuilder().build(_source(tmp_path))

    assert corpus.documents[0].content_type == "application/json"
