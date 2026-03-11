"""Unit tests for digistore_list and digistore_profile orchestrator tool handlers."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from digigraph.orchestration.registry import ToolContext


@pytest.mark.unit
def test_digistore_list_handler_returns_datasets() -> None:
    from digigraph.orchestration.builtin import _handle_digistore_list

    ctx = ToolContext(
        session_id="sess-1",
        run_data_dir="/data/run",
        index_name="default",
        index_config={},
        state={},
    )
    with patch("digigraph.digistore.digistore_list") as m:
        m.return_value = [
            {"name": "search_1", "row_count": 42},
            {"name": "search_2", "row_count": 10},
        ]
        out = _handle_digistore_list({}, ctx)
    assert "content" in out
    data = json.loads(out["content"])
    assert "datasets" in data
    assert len(data["datasets"]) == 2
    assert data["datasets"][0]["name"] == "search_1"
    assert data["datasets"][0]["row_count"] == 42


@pytest.mark.unit
def test_digistore_list_handler_include_row_count_false() -> None:
    from digigraph.orchestration.builtin import _handle_digistore_list

    ctx = ToolContext(
        session_id="sess-1",
        run_data_dir="/data/run",
        index_name="default",
        index_config={},
        state={},
    )
    with patch("digigraph.digistore.digistore_list") as m:
        m.return_value = [{"name": "search_1"}]
        _handle_digistore_list({"include_row_count": False}, ctx)
        m.assert_called_once_with("sess-1", include_row_count=False)


@pytest.mark.unit
def test_digistore_profile_handler_returns_profile() -> None:
    from digigraph.orchestration.builtin import _handle_digistore_profile

    ctx = ToolContext(
        session_id="sess-1",
        run_data_dir="/data/run",
        index_name="default",
        index_config={},
        state={},
    )
    with patch("digigraph.digistore.digistore_profile") as m:
        m.return_value = {
            "row_count": 5,
            "columns": ["subject", "fromAddress"],
            "dtypes": {"subject": "str", "fromAddress": "str"},
            "sample_rows": [{"subject": "Hi", "fromAddress": "a@b.com"}],
        }
        out = _handle_digistore_profile({"dataset_ref": "search_1"}, ctx)
    assert "content" in out
    data = json.loads(out["content"])
    assert data["row_count"] == 5
    assert data["columns"] == ["subject", "fromAddress"]
    assert len(data["sample_rows"]) == 1


@pytest.mark.unit
def test_digistore_profile_handler_not_found_returns_error() -> None:
    from digigraph.orchestration.builtin import _handle_digistore_profile

    ctx = ToolContext(
        session_id="sess-1",
        run_data_dir="/data/run",
        index_name="default",
        index_config={},
        state={},
    )
    with patch("digigraph.digistore.digistore_profile") as m:
        m.side_effect = ValueError("dataset_ref file not found")
        out = _handle_digistore_profile({"dataset_ref": "missing"}, ctx)
    assert "content" in out
    data = json.loads(out["content"])
    assert "error" in data
