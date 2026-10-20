"""``digisearch ingest`` must exit non-zero when it ingests nothing (#5045).

Production regression: the stack's Chroma seed runs ``digisearch ingest`` and
treated exit 0 as "seeded". Every parse/embed failure is skipped by
``ingest_paths(skip_errors=True)``, so an unreachable embedding provider made
the seed report success over an *empty* index. digisearch then served a
confident "no results" for every query on every index, with ``/health`` green.
Offline only.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from digisearch.cli import app as cli_app
from digisearch.pipeline.ingest import IngestError
from typer.testing import CliRunner

pytestmark = pytest.mark.unit

runner = CliRunner()

_MD = "# Title\n\nSome body text long enough to be chunked into at least one chunk.\n"


@pytest.fixture(autouse=True)
def _offline_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGISEARCH_ALLOW_STUB", "1")
    monkeypatch.setenv("DIGISEARCH_CHUNKER", "recursive")
    monkeypatch.setenv("DIGISEARCH_EMBED", "0")
    monkeypatch.delenv("DIGISEARCH_EMBEDDING_PROVIDER", raising=False)


@pytest.fixture
def seed_dir(tmp_path: Path) -> Path:
    d = tmp_path / "occ_help"
    d.mkdir()
    (d / "faq.md").write_text(_MD, encoding="utf-8")
    return d


def _ingest(*args: str):
    return runner.invoke(cli_app, ["ingest", *args])


# --- the production failure: candidates offered, nothing ingested ----------


def test_total_failure_exits_nonzero(monkeypatch: pytest.MonkeyPatch, seed_dir: Path) -> None:
    """Every file skipped/errored => exit 1, not 0. This is the #5045 bug."""
    import digisearch.cli as cli_mod

    def _boom(
        paths,
        *,
        index_name,
        chunker_name,
        metadata=None,
        embedding_provider=None,
        skip_errors=True,
    ):
        return 0, []  # exactly what ingest_paths returns on total failure

    monkeypatch.setattr("digisearch.pipeline.ingest.ingest_paths", _boom)

    result = _ingest("--index", "occ_help", str(seed_dir))

    assert result.exit_code == 1, result.output
    assert "Nothing ingested" in result.output
    assert cli_mod.app is not None  # import guard


def test_unsupported_files_only_exits_nonzero(tmp_path: Path) -> None:
    """A directory of files with no registered parser is also a failure."""
    d = tmp_path / "junk"
    d.mkdir()
    (d / "a.bin").write_bytes(b"\x00\x01")

    result = _ingest("--index", "idx", str(d))

    assert result.exit_code == 1, result.output
    assert "Nothing ingested" in result.output


def test_missing_source_exits_nonzero(tmp_path: Path) -> None:
    result = _ingest("--index", "idx", str(tmp_path / "does-not-exist"))

    assert result.exit_code == 1, result.output
    assert "does not exist" in result.output


def test_empty_dir_exits_nonzero(tmp_path: Path) -> None:
    """A missing/empty seed dir must not look like a successful seed."""
    d = tmp_path / "empty"
    d.mkdir()

    result = _ingest("--index", "idx", str(d))

    assert result.exit_code == 1, result.output
    assert "no files" in result.output


# --- the happy paths must NOT regress --------------------------------------


def test_success_exits_zero(seed_dir: Path) -> None:
    result = _ingest("--index", "occ_help", str(seed_dir))

    assert result.exit_code == 0, result.output
    assert "Total chunks:" in result.output


def test_ingest_error_exits_nonzero(monkeypatch: pytest.MonkeyPatch, seed_dir: Path) -> None:
    """The hard-failure branch exits 1 rather than returning 0."""

    def _raise(
        paths,
        *,
        index_name,
        chunker_name,
        metadata=None,
        embedding_provider=None,
        skip_errors=True,
    ):
        raise IngestError("backend unreachable")

    monkeypatch.setattr("digisearch.pipeline.ingest.ingest_paths", _raise)

    result = _ingest("--index", "occ_help", str(seed_dir))

    assert result.exit_code == 1, result.output
    assert "Ingest failed" in result.output


def test_ingest_batch_shares_the_contract(seed_dir: Path) -> None:
    """``ingest-batch`` uses the same helper, so it inherits both behaviours."""
    ok = runner.invoke(cli_app, ["ingest-batch", "--index", "idx", str(seed_dir)])
    assert ok.exit_code == 0, ok.output

    missing = runner.invoke(cli_app, ["ingest-batch", "--index", "idx", str(seed_dir / "nope")])
    assert missing.exit_code == 1, missing.output
