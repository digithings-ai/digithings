"""Unit tests for run storage: write_search_results, resolve_dataset_ref."""

from __future__ import annotations

import tempfile
import os

import pytest

from digigraph.run_storage import (
    get_run_data_dir,
    resolve_dataset_ref,
    write_search_results,
)


@pytest.mark.unit
def test_write_and_resolve(tmp_path) -> None:
    """Write search results and resolve_dataset_ref returns the path."""
    os.environ["DIGI_RUN_DATA_DIR"] = str(tmp_path)
    try:
        results = [
            {"content": "a", "score": 0.9, "doc_id": "d1", "rank": 1, "metadata": {"x": "1"}},
        ]
        path = write_search_results("sess1", results)
        assert path
        assert "sess1" in path or "default" in path
        resolved = resolve_dataset_ref("sess1", path)
        assert resolved.exists()
        assert resolved.read_text()
    finally:
        os.environ.pop("DIGI_RUN_DATA_DIR", None)


@pytest.mark.unit
def test_resolve_rejects_escape(tmp_path) -> None:
    """resolve_dataset_ref rejects path that escapes run_data_dir."""
    os.environ["DIGI_RUN_DATA_DIR"] = str(tmp_path)
    try:
        with pytest.raises(ValueError, match="under run_data_dir|escape"):
            resolve_dataset_ref("sess1", "../../etc/passwd")
    finally:
        os.environ.pop("DIGI_RUN_DATA_DIR", None)
