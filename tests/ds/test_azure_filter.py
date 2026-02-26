"""Unit tests for Azure backend OData filter builder."""

from __future__ import annotations

import pytest

from digisearch.indexes.backends.azure_search import _build_odata_filter


@pytest.mark.unit
def test_build_odata_empty() -> None:
    assert _build_odata_filter([], ["sourceType"]) is None
    assert _build_odata_filter([{"field": "sourceType", "op": "eq", "value": "X"}], []) is None


@pytest.mark.unit
def test_build_odata_single_eq() -> None:
    f = _build_odata_filter(
        [{"field": "sourceType", "op": "eq", "value": "EXCHANGE"}],
        ["sourceType"],
    )
    assert f == "(sourceType eq 'EXCHANGE')"


@pytest.mark.unit
def test_build_odata_allowlist_ignores_unknown_field() -> None:
    f = _build_odata_filter(
        [{"field": "unknownField", "op": "eq", "value": "x"}],
        ["sourceType"],
    )
    assert f is None


@pytest.mark.unit
def test_build_odata_multiple_and() -> None:
    f = _build_odata_filter(
        [
            {"field": "sourceType", "op": "eq", "value": "EXCHANGE"},
            {"field": "hasAttachments", "op": "eq", "value": True},
        ],
        ["sourceType", "hasAttachments"],
    )
    assert "(sourceType eq 'EXCHANGE')" in f
    assert "(hasAttachments eq true)" in f
    assert " and " in f


@pytest.mark.unit
def test_build_odata_numeric_and_string() -> None:
    f = _build_odata_filter(
        [
            {"field": "importance", "op": "eq", "value": 1},
            {"field": "fromAddress", "op": "eq", "value": "user@example.com"},
        ],
        ["importance", "fromAddress"],
    )
    assert "(importance eq 1)" in f
    assert "user@example.com" in f
    assert "'user@example.com'" in f or "user@example.com" in f


@pytest.mark.unit
def test_build_odata_escape_quotes() -> None:
    f = _build_odata_filter(
        [{"field": "sourceType", "op": "eq", "value": "O'Brien"}],
        ["sourceType"],
    )
    assert "''" in f  # escaped single quote
    assert "O'Brien" in f or "O''Brien" in f


@pytest.mark.unit
def test_build_odata_op_in_list() -> None:
    """op 'in' with list of values produces search.in(field, 'v1,v2', ',')."""
    f = _build_odata_filter(
        [{"field": "sourceType", "op": "in", "value": ["EXCHANGE", "TEAMS"]}],
        ["sourceType"],
    )
    assert f == "search.in(sourceType, 'EXCHANGE,TEAMS', ',')"


@pytest.mark.unit
def test_build_odata_op_in_string() -> None:
    """op 'in' with comma-separated string produces search.in(field, '...', ',')."""
    f = _build_odata_filter(
        [{"field": "itemType", "op": "in", "value": "MessageItem,EmailMessage"}],
        ["itemType"],
    )
    assert "search.in(itemType," in f
    assert "MessageItem,EmailMessage" in f
    assert "',')" in f or "', ')" in f
