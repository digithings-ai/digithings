"""Unit tests for ingest path containment."""

from __future__ import annotations

from pathlib import Path

import pytest
from digisearch.ingest_paths import ingest_root, resolve_ingest_source


@pytest.mark.unit
def test_resolve_relative_under_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGISEARCH_INGEST_ROOT", str(tmp_path))
    doc = tmp_path / "docs" / "a.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("# hi", encoding="utf-8")
    resolved = resolve_ingest_source("docs/a.md")
    assert resolved == doc.resolve()


@pytest.mark.unit
def test_reject_escape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGISEARCH_INGEST_ROOT", str(tmp_path / "jail"))
    (tmp_path / "jail").mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="DIGISEARCH_INGEST_ROOT"):
        resolve_ingest_source(str(outside))


@pytest.mark.unit
def test_ingest_root_default_cwd(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGISEARCH_INGEST_ROOT", raising=False)
    assert ingest_root() == Path.cwd().resolve()


@pytest.mark.unit
def test_reject_symlink_that_resolves_outside_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A symlink inside the jail is still an escape once resolve() follows it."""
    jail = tmp_path / "jail"
    jail.mkdir()
    outside = tmp_path / "secret.md"
    outside.write_text("secret", encoding="utf-8")
    (jail / "note.md").symlink_to(outside)
    monkeypatch.setenv("DIGISEARCH_INGEST_ROOT", str(jail))
    with pytest.raises(ValueError, match="DIGISEARCH_INGEST_ROOT"):
        resolve_ingest_source("note.md")


@pytest.mark.unit
def test_reject_dotdot_through_symlinked_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``sub/../secret`` leaves the jail when ``sub`` is a symlink to an outside dir."""
    jail = tmp_path / "jail"
    jail.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("nope", encoding="utf-8")
    (jail / "sub").symlink_to(outside)
    monkeypatch.setenv("DIGISEARCH_INGEST_ROOT", str(jail))
    with pytest.raises(ValueError, match="DIGISEARCH_INGEST_ROOT"):
        resolve_ingest_source("sub/../secret.txt")
