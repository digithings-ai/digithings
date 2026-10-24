"""Unit tests for :mod:`digiquant.scalars`.

These pin the failure policy of each coercion. They exist because the same
helper had been copied into eight modules with two different policies:
``_opt_float`` returned ``None`` in the portfolio writers and raised in
``tearsheet_data``, so the same bad row could be dropped from a book and crash
a tearsheet. One helper per policy means a caller has to choose on purpose.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

import pytest
from digiquant.scalars import (
    decimal_or_raise,
    is_cash,
    opt_decimal,
    opt_float,
    opt_float_strict,
)


@pytest.mark.unit
class TestIsCash:
    @pytest.mark.parametrize("ticker", ["CASH", "cash", " Cash ", "CASH\n"])
    def test_recognises_the_cash_sleeve(self, ticker: str) -> None:
        assert is_cash(ticker) is True

    @pytest.mark.parametrize("ticker", ["AAPL", "CASHX", "", "  "])
    def test_rejects_other_tickers(self, ticker: str) -> None:
        assert is_cash(ticker) is False

    @pytest.mark.parametrize("ticker", [None, 123, Decimal("1"), {"ticker": "CASH"}, ["CASH"]])
    def test_non_string_ticker_is_never_cash_and_never_raises(self, ticker: object) -> None:
        # Two of the six copies did ``ticker.strip()`` and raised AttributeError
        # on a non-string ticker coming out of a broker or LLM payload.
        assert is_cash(ticker) is False


@pytest.mark.unit
class TestOptFloat:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (None, None),
            ("1.5", 1.5),
            ("-2", -2.0),
            (3, 3.0),
            (Decimal("0.25"), 0.25),
            ("not-a-number", None),
            ("", None),
            (object(), None),
        ],
    )
    def test_lenient_coercion(self, raw: object, expected: float | None) -> None:
        assert opt_float(raw) == expected


@pytest.mark.unit
class TestOptFloatStrict:
    def test_none_passes_through(self) -> None:
        assert opt_float_strict(None) is None

    def test_numeric_values_coerce(self) -> None:
        assert opt_float_strict("1.5") == 1.5
        assert opt_float_strict(2) == 2.0

    @pytest.mark.parametrize("raw", ["not-a-number", "", object()])
    def test_garbage_raises_instead_of_vanishing(self, raw: object) -> None:
        # The tearsheet path must not publish a statistic that was silently
        # turned into a blank because the source row was malformed.
        with pytest.raises((TypeError, ValueError)):
            opt_float_strict(raw)


@pytest.mark.unit
class TestOptDecimal:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (None, None),
            ("1.10", Decimal("1.10")),
            (2, Decimal("2")),
            ("not-a-number", None),
            (object(), None),
        ],
    )
    def test_lenient_coercion(self, raw: object, expected: Decimal | None) -> None:
        assert opt_decimal(raw) == expected

    def test_float_goes_through_its_string_form(self) -> None:
        # ``Decimal(0.1)`` would drag in the binary float's error; the shared
        # helper must keep taking the string route.
        assert opt_decimal(0.1) == Decimal("0.1")


@pytest.mark.unit
class TestDecimalOrRaise:
    def test_coerces_exactly(self) -> None:
        assert decimal_or_raise("1.10") == Decimal("1.10")

    def test_garbage_raises(self) -> None:
        with pytest.raises(InvalidOperation):
            decimal_or_raise("not-a-number")


@pytest.mark.unit
class TestNoPrivateCopiesRemain:
    """The eight private copies are gone; they must not come back."""

    MODULES = (
        "digiquant.dashboard.accounting.io",
        "digiquant.data.onchain.bgeometrics",
        "digiquant.data.onchain.bitview",
        "digiquant.data.onchain.coinmetrics",
        "digiquant.data.onchain.fear_greed",
        "digiquant.portfolio.allocation_inputs",
        "digiquant.portfolio.phases.phase7e_risk_sizing",
        "digiquant.portfolio.portfolio_materialize",
        "digiquant.portfolio.turnover",
        "digiquant.portfolio.writers.commit_io",
        "digiquant.portfolio.writers.execution_io",
        "digiquant.portfolio.writers.ledger_io",
        "digiquant.portfolio.writers.opening_snapshot",
        "digiquant.portfolio.writers.reconvergence",
        "digiquant.research.phases.preflight",
        "digiquant.tearsheet_data",
    )

    @pytest.mark.parametrize("module_name", MODULES)
    def test_module_has_no_private_copy(self, module_name: str) -> None:
        import importlib
        import pathlib

        source = pathlib.Path(importlib.import_module(module_name).__file__).read_text()
        for removed in (
            "def _is_cash(",
            "def _is_cash_ticker(",
            "def _opt_float(",
            "def _decimal(",
            "def _empty_frame(",
        ):
            assert removed not in source, f"{module_name} re-introduced {removed!r}"
