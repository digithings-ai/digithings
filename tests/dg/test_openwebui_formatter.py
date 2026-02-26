"""Unit tests for Open WebUI formatter: delegate result rendering and tool_result branching."""

from __future__ import annotations

import pytest

from digigraph.formatters.openwebui import (
    OpenWebUIStreamFormatter,
    _format_delegate_result,
    _matrix_to_markdown,
    _stats_to_markdown,
    _table_from_rows,
)


@pytest.mark.unit
def test_format_delegate_result_error() -> None:
    summary, body = _format_delegate_result({"error": "Column x not found"})
    assert summary == "Error"
    assert "Column x not found" in body
    assert "Error" in body


@pytest.mark.unit
def test_format_delegate_result_mermaid_only() -> None:
    summary, body = _format_delegate_result({"mermaid_source": "graph LR\n  A-->B"})
    assert "Mermaid" in summary
    assert "```mermaid" in body
    assert "A-->B" in body


@pytest.mark.unit
def test_format_delegate_result_table() -> None:
    summary, body = _format_delegate_result({
        "table": [{"a": 1, "b": 2}, {"a": 3, "b": 4}],
        "columns": ["a", "b"],
    })
    assert "table" in summary
    assert "|" in body and "a" in body and "b" in body


@pytest.mark.unit
def test_format_delegate_result_matrix() -> None:
    summary, body = _format_delegate_result({
        "matrix": {"x": {"x": 1.0, "y": 0.5}, "y": {"x": 0.5, "y": 1.0}},
    })
    assert "correlation" in summary
    assert "|" in body and "x" in body and "y" in body


@pytest.mark.unit
def test_format_delegate_result_path_rows() -> None:
    summary, body = _format_delegate_result({"path": "/data/out.csv", "rows": 42})
    assert "Exported" in summary
    assert "42" in body and "out.csv" in body


@pytest.mark.unit
def test_format_tool_result_search_with_name() -> None:
    formatter = OpenWebUIStreamFormatter()
    out = formatter.format_tool_result({
        "name": "digisearch",
        "results": [{"content": "hi", "score": 0.9, "doc_id": "d1", "metadata": {}}],
    })
    assert "Result:" in out
    assert "1 results" in out
    assert "|" in out


@pytest.mark.unit
def test_format_tool_result_delegate_json() -> None:
    formatter = OpenWebUIStreamFormatter()
    out = formatter.format_tool_result({
        "name": "visualization_agent",
        "content": '{"mermaid_source": "flowchart LR\\n  A-->B"}',
    })
    assert "Result:" in out
    assert "```mermaid" in out
    assert "A-->B" in out


@pytest.mark.unit
def test_format_tool_result_backward_compat_no_name() -> None:
    formatter = OpenWebUIStreamFormatter()
    out = formatter.format_tool_result({"results": [{"content": "x", "score": 0.5, "doc_id": "d1", "metadata": {}}]})
    assert "Result" in out
    assert "|" in out


def test_matrix_to_markdown() -> None:
    m = _matrix_to_markdown({"a": {"a": 1.0, "b": 0.1}, "b": {"a": 0.1, "b": 1.0}})
    assert "a" in m and "b" in m
    assert "1" in m and "0.1" in m


def test_table_from_rows() -> None:
    t = _table_from_rows([{"x": 1, "y": 2}, {"x": 3, "y": 4}], ["x", "y"])
    assert "x" in t and "y" in t
    assert "1" in t and "3" in t


def test_stats_to_markdown() -> None:
    s = _stats_to_markdown({"col1": {"mean": 0.5, "min": 0, "max": 1}, "col2": {"mean": 1.0}})
    assert "mean" in s
    assert "col1" in s or "col2" in s
