import pytest
from digisearch.core.tables import (
    FilterClause,
    OrderClause,
    apply_filters,
    enrich_rows,
    group_count,
    order_rows,
)

pytestmark = pytest.mark.unit

ROWS = [
    {"id": 1, "state": "closed", "customer_id": 7, "updated_at": "2026-09-20T10:00:00Z"},
    {"id": 2, "state": "open", "customer_id": 7, "updated_at": "2026-09-25T10:00:00Z"},
    {"id": 3, "state": "closed", "customer_id": 9, "updated_at": "2026-09-26T10:00:00Z"},
]


def test_apply_filters_eq_and_ge():
    out = apply_filters(
        ROWS,
        [FilterClause(field="state", op="eq", value="closed")],
    )
    assert [r["id"] for r in out] == [1, 3]


def test_group_count_sorts_desc():
    assert group_count(ROWS, by="customer_id", top_n=5) == [
        {"value": "7", "count": 2},
        {"value": "9", "count": 1},
    ]


def test_order_rows_newest_first():
    out = order_rows(ROWS, [OrderClause(field="updated_at", direction="desc")])
    assert [r["id"] for r in out] == [3, 2, 1]


def test_enrich_rows_adds_display():
    out = enrich_rows(ROWS, "customer_id", {7: "Acme"}, missing="unknown")
    assert out[0]["customer_id_display"] == "Acme"
    assert out[2]["customer_id_display"] == "unknown"


def test_compare_int_float_equality_ignores_bool():
    from digisearch.core.tables import _compare

    assert _compare("eq", 1, 1.0) is True
    assert _compare("ne", 1, 1.0) is False
    assert _compare("eq", True, 1) is False
    assert _compare("ne", True, 1) is True
