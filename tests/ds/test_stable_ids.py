"""Unit tests for deterministic document ids."""

from __future__ import annotations

from pathlib import Path

import pytest
from digisearch.core.stable_ids import stable_doc_id


@pytest.mark.unit
def test_stable_doc_id_same_path_same_id(tmp_path: Path) -> None:
    doc = tmp_path / "note.md"
    doc.write_text("# hello", encoding="utf-8")
    first = stable_doc_id(source=str(doc), content="# hello")
    second = stable_doc_id(source=str(doc), content="# hello")
    assert first == second
    assert first.startswith("doc-")


@pytest.mark.unit
def test_stable_doc_id_inline_content_hash() -> None:
    first = stable_doc_id(source="<string>", content="same text")
    second = stable_doc_id(source="<string>", content="same text")
    other = stable_doc_id(source="<string>", content="other text")
    assert first == second
    assert first != other
