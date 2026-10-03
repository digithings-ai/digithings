from datetime import datetime, timezone

import pytest
from digisearch.core.tables import (
    FilterClause,
    OrderClause,
    _compare,
    apply_filters,
    enrich_rows,
    group_count,
    order_rows,
    window,
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
    assert _compare("eq", 2**53 + 1, 2**53) is False
    assert _compare("ne", 2**53 + 1, 2**53) is True


def test_compare_datetime_strings_use_instant_not_lexicographic():
    """Ordering ops on ISO instants resolve the instant, never the ASCII string."""
    earlier = "2026-09-25T10:00:00+02:00"  # 08:00Z
    later = "2026-09-25T09:00:00Z"  # 09:00Z
    # ASCII order must disagree with instant order here, else the case is vacuous.
    assert later < earlier
    assert _compare("lt", earlier, later) is True
    assert _compare("le", earlier, later) is True
    assert _compare("gt", later, earlier) is True
    assert _compare("ge", later, earlier) is True
    assert _compare("gt", earlier, later) is False
    assert _compare("lt", later, earlier) is False
    assert _compare("eq", earlier, later) is False
    # Same disagreement for a naive stamp read as UTC behind a space separator.
    naive_later = "2026-09-25 23:30:00"
    assert naive_later < later  # ASCII: space sorts before "T"
    assert _compare("gt", naive_later, later) is True
    assert _compare("lt", naive_later, later) is False
    # Aware datetime vs ISO string (ticket rows mix shapes).
    aware = datetime(2026, 9, 25, 8, 0, tzinfo=timezone.utc)
    assert _compare("le", aware, later) is True
    assert _compare("gt", aware, later) is False


def test_apply_filters_orders_offset_stamps_by_instant():
    rows = [
        {"id": 1, "updated_at": "2026-09-25T09:00:00Z"},
        {"id": 2, "updated_at": "2026-09-25T10:00:00+02:00"},
    ]
    before_cutoff = apply_filters(
        rows,
        [FilterClause(field="updated_at", op="lt", value="2026-09-25T09:00:00Z")],
    )
    assert [r["id"] for r in before_cutoff] == [2]
    at_or_after = apply_filters(
        rows,
        [FilterClause(field="updated_at", op="ge", value="2026-09-25T09:00:00Z")],
    )
    assert [r["id"] for r in at_or_after] == [1]


def test_window_since_days_bounds_by_instant_against_explicit_now():
    rows = [
        {"id": 1, "updated_at": "2026-09-24T09:00:00Z"},
        {"id": 2, "updated_at": "2026-09-20T09:00:00+02:00"},
        {"id": 3, "updated_at": "not-a-timestamp"},
    ]
    kept = window(
        rows,
        "updated_at",
        since_days=5,
        now=datetime(2026, 9, 25, 9, 0, tzinfo=timezone.utc),
    )
    assert [r["id"] for r in kept] == [1]


def test_apply_filters_updated_at_window_keeps_rows_inside_range():
    out = apply_filters(
        ROWS,
        [
            FilterClause(field="updated_at", op="ge", value="2026-09-25T00:00:00Z"),
            FilterClause(field="updated_at", op="lt", value="2026-09-26T00:00:00Z"),
        ],
    )
    assert [r["id"] for r in out] == [2]
