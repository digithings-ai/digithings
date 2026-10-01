"""Calculator + composition tools: OVME/YAS/KELLY/DVD/FXC/VIX (130-coverage Task 2).

Pure calculators (options, bond, Kelly) must never reach the wire; the three
compositions build on the existing quote/corporate-actions/exchange-rate/
econ-series reads. None claims Gloomberb sourcing (attributed=False).
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.unit

from digiquant.data.gloomberb import GloomberbClient  # noqa: E402
from digiquant.data.gloomberb.agent_tools import (  # noqa: E402
    build_digifetch_tool_dispatcher,
)
from digiquant.data.gloomberb.calculators import black_scholes_price  # noqa: E402

from digifetch import HttpFetcher, RateLimiter, RetryPolicy  # noqa: E402


def make_client(handler: Any, **kwargs: Any) -> GloomberbClient:
    fetcher = HttpFetcher(
        transport=httpx.MockTransport(handler),
        allowed_hosts=["api.gloom.sh"],
    )
    kwargs.setdefault("rate_limiter", RateLimiter(0))
    kwargs.setdefault("retry_policy", RetryPolicy(attempts=1))
    return GloomberbClient(fetcher=fetcher, **kwargs)


def _envelope(data: Any, status: str = "success", **extra: Any) -> httpx.Response:
    return httpx.Response(200, json={"status": status, "data": data, **extra})


AAPL_QUOTE = {
    "symbol": "AAPL",
    "currency": "USD",
    "price": 100.0,
    "change": 1.0,
    "changePercent": 1.0,
    "lastUpdated": 1773000000000,
    "marketState": "CLOSED",
    "listingExchangeName": "NASDAQ",
    "dataSource": "delayed",
}


def test_options_calculator_puts_parity_without_a_request() -> None:
    calls: list[int] = []

    def _fail(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise AssertionError("pure calculators must not reach the wire")

    client = make_client(_fail)
    envelope = client.options_calculator(
        {
            "spot": 100.0,
            "strike": 100.0,
            "rate": 0.05,
            "vol": 0.2,
            "expiry_years": 1.0,
            "kind": "call",
        }
    )
    assert envelope.data.price > 0.0
    assert calls == []


def test_options_calculator_put_call_parity_holds() -> None:
    def _fail(request: httpx.Request) -> httpx.Response:
        raise AssertionError("pure calculators must not reach the wire")

    client = make_client(_fail)
    args = {"spot": 100.0, "strike": 95.0, "rate": 0.05, "vol": 0.2, "expiry_years": 1.0}
    call = client.options_calculator({**args, "kind": "call"}).data
    put = client.options_calculator({**args, "kind": "put"}).data
    forward_diff = args["spot"] - args["strike"] * math.exp(-args["rate"] * args["expiry_years"])
    assert call.price - put.price == pytest.approx(forward_diff, rel=1e-9)


def test_options_calculator_iv_solve_round_trips() -> None:
    def _fail(request: httpx.Request) -> httpx.Response:
        raise AssertionError("pure calculators must not reach the wire")

    client = make_client(_fail)
    priced = client.options_calculator(
        {
            "spot": 100.0,
            "strike": 100.0,
            "rate": 0.05,
            "vol": 0.3,
            "expiry_years": 1.0,
            "kind": "call",
        }
    ).data
    solved = client.options_calculator(
        {
            "spot": 100.0,
            "strike": 100.0,
            "rate": 0.05,
            "vol": 0.2,
            "expiry_years": 1.0,
            "kind": "call",
            "price": priced.price,
        }
    ).data
    assert solved.implied_vol == pytest.approx(0.3, rel=1e-6)
    assert solved.price == pytest.approx(priced.price, rel=1e-9)


def test_options_calculator_below_floor_price_is_invalid_input() -> None:
    calls: list[int] = []

    def _fail(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise AssertionError("contract violations must not reach the wire")

    client = make_client(_fail)
    envelope = client.options_calculator(
        {
            "spot": 100.0,
            "strike": 100.0,
            "rate": 0.05,
            "vol": 0.2,
            "expiry_years": 1.0,
            "kind": "call",
            "price": 0.0001,
        }
    )
    assert envelope.data.code == "invalid_input"
    assert envelope.data.retryable is False
    assert calls == []


def test_options_calculator_invalid_spot_is_invalid_input() -> None:
    calls: list[int] = []

    def _fail(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise AssertionError("contract violations must not reach the wire")

    client = make_client(_fail)
    envelope = client.options_calculator(
        {
            "spot": 0.0,
            "strike": 100.0,
            "rate": 0.05,
            "vol": 0.2,
            "expiry_years": 1.0,
            "kind": "call",
        }
    )
    assert envelope.data.code == "invalid_input"
    assert calls == []


def test_bond_calculator_par_bond_prices_at_face() -> None:
    def _fail(request: httpx.Request) -> httpx.Response:
        raise AssertionError("pure calculators must not reach the wire")

    client = make_client(_fail)
    result = client.bond_calculator(
        {"coupon": 0.05, "face": 100.0, "ytm": 0.05, "years": 10.0, "freq": 2}
    ).data
    assert result.price == pytest.approx(100.0, rel=1e-9)
    assert result.accrued == 0.0
    assert result.duration > 0.0
    assert result.convexity > 0.0
    assert result.dv01 == pytest.approx(result.duration * result.price * 0.0001, rel=1e-9)


def test_bond_calculator_invalid_face_is_invalid_input() -> None:
    calls: list[int] = []

    def _fail(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise AssertionError("contract violations must not reach the wire")

    client = make_client(_fail)
    envelope = client.bond_calculator(
        {"coupon": 0.05, "face": 0.0, "ytm": 0.05, "years": 10.0, "freq": 2}
    )
    assert envelope.data.code == "invalid_input"
    assert calls == []


def test_kelly_sizer_known_fraction_and_floor() -> None:
    def _fail(request: httpx.Request) -> httpx.Response:
        raise AssertionError("pure calculators must not reach the wire")

    client = make_client(_fail)
    assert client.kelly_sizer(
        {"win_prob": 0.6, "win_loss_ratio": 2.0}
    ).data.fraction == pytest.approx(0.4)
    # Negative edge clamps at zero (Task 1 contract), it is not an error.
    assert client.kelly_sizer({"win_prob": 0.4, "win_loss_ratio": 1.0}).data.fraction == 0.0


def test_kelly_sizer_out_of_range_prob_is_invalid_input() -> None:
    calls: list[int] = []

    def _fail(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise AssertionError("contract violations must not reach the wire")

    client = make_client(_fail)
    envelope = client.kelly_sizer({"win_prob": 1.5, "win_loss_ratio": 2.0})
    assert envelope.data.code == "invalid_input"
    assert calls == []


def _composition_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/market/quote":
        return _envelope(dict(AAPL_QUOTE))
    if path == "/market/corporate-actions":
        return _envelope(
            {
                "symbol": "AAPL",
                "dividends": [
                    {"exDate": "2026-08-14", "amount": 0.5},
                    {"exDate": "2026-05-15", "amount": 0.5},
                ],
                "splits": [],
                "earnings": [],
            }
        )
    if path == "/market/exchange-rate":
        rates = {"EUR": 0.92, "GBP": 0.79}
        code = request.url.params.get("fromCurrency", "EUR")
        return _envelope({"rate": rates[code], "source": "yahoo"})
    if path == "/cloud/econ/series/VIXCLS":
        return httpx.Response(
            200,
            json={
                "observations": [{"date": "2026-09-29", "value": 20.0}],
                "info": {"id": "VIXCLS", "title": "VIX"},
            },
        )
    # Controller ruling (130-coverage Task 5): the FRED far leg is VXVCLS
    # (FRED 3M, labeled "VIX 3M"). VIX3M as such is the Yahoo/CBOE index
    # symbol ^VIX3M, not a FRED id.
    if path == "/cloud/econ/series/VXVCLS":
        return httpx.Response(
            200,
            json={
                "observations": [{"date": "2026-09-29", "value": 22.0}],
                "info": {"id": "VXVCLS", "title": "3-Month VIX"},
            },
        )
    raise AssertionError(f"unexpected request: {request.url}")


def test_dividend_yield_sums_trailing_distributions_over_price() -> None:
    client = make_client(_composition_handler, session_cookie="gloomberb.session_token=test")
    result = client.dividend_yield({"symbol": "AAPL"}).data
    assert result.symbol == "AAPL"
    assert result.price == pytest.approx(100.0)
    assert result.trailing_dividends == pytest.approx(1.0)
    assert result.distribution_count == 2
    assert result.dividend_yield == pytest.approx(0.01)


def test_dividend_yield_warns_upstream_error_when_quote_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/market/quote":
            return httpx.Response(500, text="boom")
        return _composition_handler(request)

    client = make_client(handler, session_cookie="gloomberb.session_token=test")
    envelope = client.dividend_yield({"symbol": "AAPL"})
    assert envelope.data.code == "upstream_error"
    assert envelope.warnings, "a failed leg must warn, not just error"


def test_dividend_yield_upstream_error_without_a_session_cookie() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return _composition_handler(request)

    # No cookie: the quote leg still reads, but the session-gated
    # corporate-actions leg answers auth_required with no request.
    client = make_client(handler)
    envelope = client.dividend_yield({"symbol": "AAPL"})
    assert envelope.data.code == "upstream_error"
    assert "/market/corporate-actions" not in calls
    assert calls == ["/market/quote"]


def test_fx_cross_rates_crosses_usd_pairs() -> None:
    client = make_client(_composition_handler)
    result = client.fx_cross_rates({"currencies": ["EUR", "GBP"]}).data
    assert result.base == "USD"
    assert result.rates == {"EUR": 0.92, "GBP": 0.79}
    assert result.crosses["EUR/GBP"] == pytest.approx(0.92 / 0.79)
    assert result.crosses["GBP/EUR"] == pytest.approx(0.79 / 0.92)


def test_fx_cross_rates_rejects_non_usd_target_without_a_request() -> None:
    calls: list[int] = []

    def _fail(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise AssertionError("USD-base violations must not reach the wire")

    client = make_client(_fail)
    envelope = client.fx_cross_rates({"currencies": ["EUR"], "to_currency": "EUR"})
    assert envelope.data.code == "invalid_input"
    assert calls == []


def test_fx_cross_rates_upstream_error_when_a_leg_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("fromCurrency") == "GBP":
            return httpx.Response(500, text="boom")
        return _composition_handler(request)

    client = make_client(handler)
    envelope = client.fx_cross_rates({"currencies": ["EUR", "GBP"]})
    assert envelope.data.code == "upstream_error"
    assert "GBP" in envelope.data.message


def test_vix_term_structure_reports_contango() -> None:
    client = make_client(_composition_handler)
    result = client.vix_term_structure({}).data
    assert result.near_close == pytest.approx(20.0)
    assert result.far_close == pytest.approx(22.0)
    assert result.spread == pytest.approx(2.0)
    assert result.regime == "contango"


def test_vix_term_structure_reports_inversion() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/cloud/econ/series/VXVCLS":
            return httpx.Response(
                200,
                json={
                    "observations": [{"date": "2026-09-29", "value": 18.0}],
                    "info": {"id": "VXVCLS", "title": "3-Month VIX"},
                },
            )
        return _composition_handler(request)

    client = make_client(handler)
    result = client.vix_term_structure({}).data
    assert result.spread == pytest.approx(-2.0)
    assert result.regime == "inversion"


def test_vix_term_structure_upstream_error_when_a_series_is_missing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/cloud/econ/series/VXVCLS":
            return httpx.Response(404, json={"status": "error", "message": "no such series"})
        return _composition_handler(request)

    client = make_client(handler)
    envelope = client.vix_term_structure({})
    assert envelope.data.code == "upstream_error"


def test_calc_tools_honor_the_kill_switch_without_a_request() -> None:
    calls: list[int] = []

    def _fail(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise AssertionError("a disabled family must not reach the wire")

    client = make_client(_fail, enabled=False)
    for envelope in (
        client.options_calculator(
            {
                "spot": 100.0,
                "strike": 100.0,
                "rate": 0.05,
                "vol": 0.2,
                "expiry_years": 1.0,
                "kind": "call",
            }
        ),
        client.dividend_yield({"symbol": "AAPL"}),
    ):
        assert envelope.data.code == "upstream_error"
        assert "disabled" in envelope.data.message
    assert calls == []


def test_composition_results_are_cached_for_900s() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return _composition_handler(request)

    client = make_client(handler, session_cookie="gloomberb.session_token=test")
    first = client.dividend_yield({"symbol": "AAPL"})
    second = client.dividend_yield({"symbol": "AAPL"})
    assert first.data.dividend_yield == pytest.approx(second.data.dividend_yield)
    # One quote + one corporate-actions read; the repeat serves the envelope cache.
    assert len(calls) == 2


def test_calc_dispatch_never_claims_gloomberb_sourcing() -> None:
    def _fail(request: httpx.Request) -> httpx.Response:
        raise AssertionError("pure calculators must not reach the wire")

    execute = build_digifetch_tool_dispatcher(client=make_client(_fail))
    result = execute("digifetch_kelly_sizer", {"win_prob": 0.6, "win_loss_ratio": 2.0})
    assert isinstance(result, dict)
    assert result["ok"] is True
    payload = json.loads(str(result["content"]))
    assert payload["data"]["fraction"] == pytest.approx(0.4)
    assert "attribution" not in payload
    assert "source_url" not in payload


# ── options scenario (130-coverage Task 8: OSA) ──────────────────────────────
#
# Multi-leg European valuation over options_chain rows + the Task 1
# Black-Scholes core. The fixture chain carries one call (strike 100, expiry
# 1800000000 = 2027-01-15T08:00Z, IV 0.2, last 10.4).

_SCENARIO_EXPIRY = 1800000000.0

_SCENARIO_CHAIN = {
    "underlyingSymbol": "AAPL",
    "expirationDates": [_SCENARIO_EXPIRY],
    "calls": [
        {
            "contractSymbol": "AAPL270115C00100000",
            "strike": 100.0,
            "expiration": _SCENARIO_EXPIRY,
            "impliedVolatility": 0.2,
            "lastPrice": 10.4,
            "bid": 10.2,
            "ask": 10.6,
        }
    ],
    "puts": [],
}


def _scenario_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/market/options":
        return _envelope(dict(_SCENARIO_CHAIN))
    raise AssertionError(f"unexpected request: {request.url}")


def _scenario_args(**overrides: Any) -> dict[str, Any]:
    args: dict[str, Any] = {
        "symbol": "AAPL",
        "legs": [{"expiry": _SCENARIO_EXPIRY, "strike": 100.0, "kind": "call", "qty": 1.0}],
        "rate": 0.05,
        "spots": [100.0],
        "valuation_dates": ["2026-09-30"],
        "vol_shifts": [0.0],
    }
    args.update(overrides)
    return args


def _scenario_tau(valuation_date: str = "2026-09-30") -> float:
    epoch = datetime.strptime(valuation_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
    return (_SCENARIO_EXPIRY - epoch) / (365.25 * 24 * 3600)


def test_options_scenario_single_long_call_matches_black_scholes_at_spot_equals_strike() -> None:
    client = make_client(_scenario_handler)
    result = client.options_scenario(_scenario_args()).data
    expected = black_scholes_price(
        spot=100.0,
        strike=100.0,
        rate=0.05,
        vol=0.2,
        expiry_years=_scenario_tau(),
        kind="call",
    )
    assert result.grid[0].value == pytest.approx(expected, rel=1e-9)
    assert result.grid[0].pnl == pytest.approx(expected - 10.4, rel=1e-9)


def test_options_scenario_breakeven_is_strike_plus_premium() -> None:
    client = make_client(_scenario_handler)
    result = client.options_scenario(_scenario_args(spots=[80.0, 90.0, 100.0, 110.0, 120.0])).data
    assert result.premium_paid == pytest.approx(10.4)
    assert result.breakevens == pytest.approx([110.4], rel=1e-9)


def test_options_scenario_long_call_greeks_have_the_right_signs() -> None:
    client = make_client(_scenario_handler)
    result = client.options_scenario(_scenario_args()).data
    assert result.greeks_at_spot == pytest.approx(100.0)
    assert result.greeks_valuation_date == "2026-09-30"
    leg = result.leg_greeks[0]
    assert 0.0 < leg.delta < 1.0
    assert leg.gamma > 0.0
    assert leg.vega > 0.0
    assert leg.theta < 0.0
    assert result.portfolio_greeks.delta == pytest.approx(leg.delta)


def test_options_scenario_expired_leg_values_intrinsic() -> None:
    client = make_client(_scenario_handler)
    result = client.options_scenario(
        _scenario_args(spots=[110.0], valuation_dates=["2027-06-30"])
    ).data
    assert result.grid[0].value == pytest.approx(10.0)
    assert result.grid[0].pnl == pytest.approx(-0.4)


def test_options_scenario_vol_shift_bumps_value() -> None:
    client = make_client(_scenario_handler)
    result = client.options_scenario(_scenario_args(vol_shifts=[0.0, 0.05])).data
    base = [point for point in result.grid if point.vol_shift == 0.0][0]
    bumped = [point for point in result.grid if point.vol_shift == 0.05][0]
    assert bumped.value > base.value


def test_options_scenario_unknown_leg_is_invalid_input() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return _scenario_handler(request)

    client = make_client(handler)
    envelope = client.options_scenario(
        _scenario_args(
            legs=[{"expiry": _SCENARIO_EXPIRY, "strike": 999.0, "kind": "call", "qty": 1.0}]
        )
    )
    assert envelope.data.code == "invalid_input"
    assert calls == ["/market/options"]


def test_options_scenario_zero_qty_is_invalid_input_without_a_request() -> None:
    calls: list[int] = []

    def _fail(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise AssertionError("contract violations must not reach the wire")

    client = make_client(_fail)
    envelope = client.options_scenario(
        _scenario_args(
            legs=[{"expiry": _SCENARIO_EXPIRY, "strike": 100.0, "kind": "call", "qty": 0.0}]
        )
    )
    assert envelope.data.code == "invalid_input"
    assert calls == []


def test_options_scenario_negative_vol_from_shift_is_invalid_input() -> None:
    client = make_client(_scenario_handler)
    envelope = client.options_scenario(_scenario_args(vol_shifts=[-0.25]))
    assert envelope.data.code == "invalid_input"


def test_options_scenario_chain_failure_is_a_warned_upstream_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    client = make_client(handler)
    envelope = client.options_scenario(_scenario_args())
    assert envelope.data.code == "upstream_error"
    assert envelope.warnings, "a failed leg must warn, not just error"


def test_options_scenario_honors_the_kill_switch_without_a_request() -> None:
    calls: list[int] = []

    def _fail(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise AssertionError("a disabled family must not reach the wire")

    client = make_client(_fail, enabled=False)
    envelope = client.options_scenario(_scenario_args())
    assert envelope.data.code == "upstream_error"
    assert "disabled" in envelope.data.message
    assert calls == []


def test_options_scenario_result_is_cached() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return _scenario_handler(request)

    client = make_client(handler)
    first = client.options_scenario(_scenario_args())
    second = client.options_scenario(_scenario_args())
    assert first.data.grid[0].value == pytest.approx(second.data.grid[0].value)
    # One chain read; the repeat serves the envelope cache.
    assert len(calls) == 1


def test_scenario_dispatch_never_claims_gloomberb_sourcing() -> None:
    execute = build_digifetch_tool_dispatcher(client=make_client(_scenario_handler))
    result = execute(
        "digifetch_options_scenario",
        _scenario_args(spots=[80.0, 90.0, 100.0, 110.0, 120.0]),
    )
    assert isinstance(result, dict)
    assert result["ok"] is True
    payload = json.loads(str(result["content"]))
    assert payload["data"]["breakevens"] == pytest.approx([110.4], rel=1e-6)
    assert "attribution" not in payload
    assert "source_url" not in payload
