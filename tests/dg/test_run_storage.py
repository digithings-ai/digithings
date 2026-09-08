"""Unit tests for run storage: write_search_results, resolve_dataset_ref."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from digigraph.digistore import digistore_get, digistore_put
from digigraph.run_storage import (
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
        with pytest.raises(ValueError, match="under run_data_dir|escape|session directory"):
            resolve_dataset_ref("sess1", "../../etc/passwd")
    finally:
        os.environ.pop("DIGI_RUN_DATA_DIR", None)


@pytest.mark.unit
def test_resolve_rejects_relative_cross_session(tmp_path) -> None:
    """``../other_sess/...`` must not read another session's datasets."""
    os.environ["DIGI_RUN_DATA_DIR"] = str(tmp_path)
    try:
        victim_ref = digistore_put("victim_sess", "search_1", [{"secret": "victim-row"}])
        assert Path(victim_ref).exists()
        with pytest.raises(ValueError, match="session directory"):
            resolve_dataset_ref("attacker_sess", "../victim_sess/datasets/search_1.json")
        with pytest.raises(ValueError, match="session directory"):
            digistore_get("attacker_sess", "../victim_sess/datasets/search_1.json")
    finally:
        os.environ.pop("DIGI_RUN_DATA_DIR", None)


@pytest.mark.unit
def test_resolve_rejects_absolute_cross_session(tmp_path) -> None:
    """Absolute dataset_ref from another session must be rejected."""
    os.environ["DIGI_RUN_DATA_DIR"] = str(tmp_path)
    try:
        victim_ref = digistore_put("victim_sess", "search_1", [{"secret": "victim-row"}])
        with pytest.raises(ValueError, match="session directory"):
            resolve_dataset_ref("attacker_sess", victim_ref)
        with pytest.raises(ValueError, match="session directory"):
            digistore_get("attacker_sess", victim_ref)
        # Same-session absolute ref still works (digistore_put return value).
        same = digistore_get("victim_sess", victim_ref)
        assert json.loads(same.read_text()) == [{"secret": "victim-row"}]
    finally:
        os.environ.pop("DIGI_RUN_DATA_DIR", None)
