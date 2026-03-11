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


# --- Date filters (ISO 8601 strings; Azure Edm.DateTimeOffset) ---

FILTERABLE_WITH_DATES = [
    "sourceType",
    "sentDateTime",
    "createdDateTime",
    "receivedDateTime",
    "importance",
]


@pytest.mark.unit
def test_build_odata_date_eq() -> None:
    """Date equality: ISO string is quoted in OData."""
    f = _build_odata_filter(
        [{"field": "sentDateTime", "op": "eq", "value": "2024-01-15T00:00:00Z"}],
        FILTERABLE_WITH_DATES,
    )
    assert f == "(sentDateTime eq '2024-01-15T00:00:00Z')"


@pytest.mark.unit
def test_build_odata_date_ge_gt() -> None:
    """Date range: ge and gt produce correct OData."""
    f_ge = _build_odata_filter(
        [{"field": "createdDateTime", "op": "ge", "value": "2024-01-01T00:00:00Z"}],
        FILTERABLE_WITH_DATES,
    )
    assert f_ge == "(createdDateTime ge '2024-01-01T00:00:00Z')"
    f_gt = _build_odata_filter(
        [{"field": "receivedDateTime", "op": "gt", "value": "2023-06-01T12:00:00Z"}],
        FILTERABLE_WITH_DATES,
    )
    assert f_gt == "(receivedDateTime gt '2023-06-01T12:00:00Z')"


@pytest.mark.unit
def test_build_odata_date_le_lt() -> None:
    """Date range: le and lt produce correct OData."""
    f_le = _build_odata_filter(
        [{"field": "sentDateTime", "op": "le", "value": "2024-12-31T23:59:59Z"}],
        FILTERABLE_WITH_DATES,
    )
    assert f_le == "(sentDateTime le '2024-12-31T23:59:59Z')"
    f_lt = _build_odata_filter(
        [{"field": "createdDateTime", "op": "lt", "value": "2025-01-01T00:00:00Z"}],
        FILTERABLE_WITH_DATES,
    )
    assert f_lt == "(createdDateTime lt '2025-01-01T00:00:00Z')"


@pytest.mark.unit
def test_build_odata_date_ne() -> None:
    """Date not-equal."""
    f = _build_odata_filter(
        [{"field": "sentDateTime", "op": "ne", "value": "2024-01-15T00:00:00Z"}],
        FILTERABLE_WITH_DATES,
    )
    assert f == "(sentDateTime ne '2024-01-15T00:00:00Z')"


# --- Numeric filters (int and float) ---

@pytest.mark.unit
def test_build_odata_numeric_gt_ge_lt_le() -> None:
    """Numeric comparison ops: gt, ge, lt, le (no quotes)."""
    filterable = ["importance", "size"]
    f_gt = _build_odata_filter(
        [{"field": "importance", "op": "gt", "value": 0}],
        filterable,
    )
    assert f_gt == "(importance gt 0)"
    f_ge = _build_odata_filter(
        [{"field": "importance", "op": "ge", "value": 1}],
        filterable,
    )
    assert f_ge == "(importance ge 1)"
    f_lt = _build_odata_filter(
        [{"field": "size", "op": "lt", "value": 10000}],
        filterable,
    )
    assert f_lt == "(size lt 10000)"
    f_le = _build_odata_filter(
        [{"field": "size", "op": "le", "value": 65536}],
        filterable,
    )
    assert f_le == "(size le 65536)"


@pytest.mark.unit
def test_build_odata_numeric_float() -> None:
    """Float values are emitted unquoted."""
    f = _build_odata_filter(
        [{"field": "score", "op": "ge", "value": 0.5}],
        ["score"],
    )
    assert f == "(score ge 0.5)"


@pytest.mark.unit
def test_build_odata_numeric_ne() -> None:
    """Numeric not-equal."""
    f = _build_odata_filter(
        [{"field": "importance", "op": "ne", "value": 2}],
        ["importance"],
    )
    assert f == "(importance ne 2)"


# --- Categorical (string eq/ne) ---

@pytest.mark.unit
def test_build_odata_categorical_eq() -> None:
    """Categorical field eq: already covered by test_build_odata_single_eq; explicit categorical."""
    f = _build_odata_filter(
        [{"field": "itemType", "op": "eq", "value": "EmailMessage"}],
        ["itemType"],
    )
    assert f == "(itemType eq 'EmailMessage')"


@pytest.mark.unit
def test_build_odata_categorical_ne() -> None:
    """Categorical not-equal."""
    f = _build_odata_filter(
        [{"field": "sourceType", "op": "ne", "value": "SHAREPOINT"}],
        ["sourceType"],
    )
    assert f == "(sourceType ne 'SHAREPOINT')"


@pytest.mark.unit
def test_build_odata_categorical_in_multiple() -> None:
    """Categorical 'in' with several values."""
    f = _build_odata_filter(
        [{"field": "sourceType", "op": "in", "value": ["EXCHANGE", "TEAMS", "SHAREPOINT"]}],
        ["sourceType"],
    )
    assert f == "search.in(sourceType, 'EXCHANGE,TEAMS,SHAREPOINT', ',')"


# --- Boolean ---

@pytest.mark.unit
def test_build_odata_boolean_false() -> None:
    """Boolean false."""
    f = _build_odata_filter(
        [{"field": "hasAttachments", "op": "eq", "value": False}],
        ["hasAttachments"],
    )
    assert f == "(hasAttachments eq false)"


# --- Null ---

@pytest.mark.unit
def test_build_odata_null() -> None:
    """Null value produces (field eq null)."""
    f = _build_odata_filter(
        [{"field": "fromAddress", "op": "eq", "value": None}],
        ["fromAddress"],
    )
    assert f == "(fromAddress eq null)"


# --- Combined (date + categorical + numeric) ---

@pytest.mark.unit
def test_build_odata_combined_date_categorical_numeric() -> None:
    """Multiple clauses: date range + category + number, all ANDed."""
    filterable = ["sourceType", "sentDateTime", "importance", "hasAttachments"]
    f = _build_odata_filter(
        [
            {"field": "sourceType", "op": "eq", "value": "EXCHANGE"},
            {"field": "sentDateTime", "op": "ge", "value": "2024-01-01T00:00:00Z"},
            {"field": "sentDateTime", "op": "le", "value": "2024-12-31T23:59:59Z"},
            {"field": "importance", "op": "ge", "value": 1},
            {"field": "hasAttachments", "op": "eq", "value": True},
        ],
        filterable,
    )
    assert "(sourceType eq 'EXCHANGE')" in f
    assert "(sentDateTime ge '2024-01-01T00:00:00Z')" in f
    assert "(sentDateTime le '2024-12-31T23:59:59Z')" in f
    assert "(importance ge 1)" in f
    assert "(hasAttachments eq true)" in f
    assert f.count(" and ") == 4


# --- Edge cases ---

@pytest.mark.unit
def test_build_odata_default_op_eq() -> None:
    """Missing op defaults to eq."""
    f = _build_odata_filter(
        [{"field": "sourceType", "value": "TEAMS"}],
        ["sourceType"],
    )
    assert f == "(sourceType eq 'TEAMS')"


@pytest.mark.unit
def test_build_odata_invalid_op_skipped() -> None:
    """Invalid op is skipped (no clause added)."""
    f = _build_odata_filter(
        [
            {"field": "sourceType", "op": "eq", "value": "EXCHANGE"},
            {"field": "itemType", "op": "invalid", "value": "X"},
        ],
        ["sourceType", "itemType"],
    )
    assert f == "(sourceType eq 'EXCHANGE')"


@pytest.mark.unit
def test_build_odata_in_empty_list_value_skipped() -> None:
    """op 'in' with empty list produces no clause (search.in with empty would be invalid)."""
    f = _build_odata_filter(
        [{"field": "sourceType", "op": "in", "value": []}],
        ["sourceType"],
    )
    assert f is None


@pytest.mark.unit
def test_build_odata_in_single_value() -> None:
    """op 'in' with single-element list is valid."""
    f = _build_odata_filter(
        [{"field": "sourceType", "op": "in", "value": ["EXCHANGE"]}],
        ["sourceType"],
    )
    assert f == "search.in(sourceType, 'EXCHANGE', ',')"
