"""Research-only SDCA extras ported from ``claude/sdca-develop-sync`` (DIG-1597 leaf 2).

Leaf 1 (DIG-1597) landed the multi-timeframe confluence family in
``price_oscillators.py``. This leaf lands the *indicator_catalog* half: the
on-chain ratio family, the Fear & Greed sentiment read, the fast-crash
realized-vol read, and the slow/fast ``rs_eth`` confluence.

Scope discipline, asserted here rather than only described:

- **Dormant by default.** Every new weight defaults to ``0.0`` and the new ids
  are *not* published into ``MACRO_INDICATOR_NAMES`` / ``EXTRA_INDICATOR_NAMES``
  / ``BTC_PLUGIN_INDICATOR_NAMES``. Those tuples drive the production Stage A /
  weight-search default scope and the BTC asset-profile allowlist, so widening
  them is a behaviour change, not a port. The branch's own docstrings call
  these "research-only pending validation"; that is the state landed here.
- **Additive only.** ``valuation`` stays ``valuation`` (the branch renamed it to
  ``power_law``); ``build_extra_indicators`` keeps ``rs_eth`` on the plain
  ``rs_eth_z``; ``PRICE_OSCILLATOR_NAMES`` keeps its three published members.
  Those rewires need ``SdcaOscillatorSpec`` fields that do not exist on develop
  and are deferred to their own leaves with measured deltas.
- **The ``two_stage.freeze_weight_params`` trap.** It indexes
  ``WEIGHT_PARAM_BY_NAME`` for *every* ``SdcaCompositeWeights`` field, so a new
  weight field without a matching entry raises ``KeyError`` at stage B. Pinned
  by :class:`TestWeightParamCoverage`.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Callable
from datetime import date
from pathlib import Path

import polars as pl
import pytest
from digiquant.strategies.sdca.indicator_catalog import (
    BTC_PLUGIN_INDICATOR_NAMES,
    EXTRA_INDICATOR_NAMES,
    INDICATOR_DISPLAY_NAMES,
    MACRO_INDICATOR_NAMES,
    PRICE_OSCILLATOR_NAMES,
    WEIGHT_PARAM_BY_NAME,
    ExtraIndicatorSources,
    SdcaCompositeWeights,
    align_to_dates,
    build_extra_indicators,
    causal_rolling_z,
    composite_weights_from_params,
    extra_z_vectors,
    fast_crash_vol_z,
    fear_greed_z,
    indicator_display_name,
    missing_extra_names,
    onchain_addr_ratio_z,
    onchain_asopr_z,
    onchain_mvrv_z,
    onchain_puell_z,
    onchain_rhodl_z,
    parse_indicator_weights_json,
    rs_eth_confluence_z,
    rs_eth_z,
    sources_from_optional_paths,
)
from digiquant.strategies.sdca.price_oscillators import (
    SdcaOscillatorSpec,
    sma_band_confluence_z,
)
from digiquant.strategies.sdca.two_stage import freeze_weight_params
from pydantic import ValidationError

pytestmark = pytest.mark.unit

# The seven weight ids this leaf adds. All dormant (0.0) and unpublished.
RESEARCH_ONLY_NAMES: tuple[str, ...] = (
    "onchain_mvrv",
    "onchain_asopr",
    "onchain_puell",
    "onchain_rhodl",
    "onchain_addr_ratio",
    "fear_greed",
    "fast_crash_vol",
)

# Short windows so the fixtures stay small; the production defaults are
# DEFAULT_ROLLING_WINDOW=90 / _MIN_SAMPLES=20 and are asserted separately.
_W = 10
_M = 4
_ROOT = date(2020, 1, 1)


def _dates(n: int, start: date = _ROOT) -> pl.Series:
    return pl.Series("date", [start + _dt.timedelta(days=i) for i in range(n)], dtype=pl.Date)


def _geom(n: int, step: float, start: float) -> pl.Series:
    """Geometric series -- strictly positive and monotone, so every log is defined."""
    return pl.Series("value", [start * step**i for i in range(n)], dtype=pl.Float64)


def _z_list(series: pl.Series) -> list[float | None]:
    return series.to_list()


def _src(n: int) -> dict[str, pl.Series]:
    """Every source series this leaf can read, all positive and monotone."""
    dates = _dates(n)
    return {
        "eth_dates": dates,
        "eth_close": _geom(n, 1.02, 2000.0),
        "onchain_mvrv_dates": dates,
        "onchain_mvrv_values": _geom(n, 1.005, 3.0),
        "onchain_asopr_dates": dates,
        "onchain_asopr_values": _geom(n, 1.002, 1.05),
        "onchain_puell_dates": dates,
        "onchain_puell_values": _geom(n, 1.003, 2.5),
        "onchain_rhodl_dates": dates,
        "onchain_rhodl_values": _geom(n, 1.001, 4.0),
        "onchain_addr_ratio_dates": dates,
        "onchain_addr_ratio_values": _geom(n, 1.004, 900_000.0),
        "fear_greed_dates": dates,
        "fear_greed_values": _geom(n, 1.0005, 45.0),
    }


def _sources(n: int) -> ExtraIndicatorSources:
    return ExtraIndicatorSources(**_src(n))  # type: ignore[arg-type]


# --------------------------------------------------------------------------------------
# Weight model
# --------------------------------------------------------------------------------------


class TestResearchOnlyWeights:
    def test_defaults_are_zero_and_blend_is_unchanged(self) -> None:
        w = SdcaCompositeWeights()
        for name in RESEARCH_ONLY_NAMES:
            assert getattr(w, name) == pytest.approx(0.0)
        assert w.enabled_extras() == {}
        assert w.normalized().valuation == pytest.approx(1.0)

    @pytest.mark.parametrize("name", RESEARCH_ONLY_NAMES)
    def test_positive_weight_enables(self, name: str) -> None:
        w = SdcaCompositeWeights(valuation=1.0, **{name: 0.5})
        assert w.enabled_extras() == {name: pytest.approx(0.5)}
        assert (name, 0.5) in w.extra_items()

    @pytest.mark.parametrize("name", RESEARCH_ONLY_NAMES)
    def test_negative_weight_rejected(self, name: str) -> None:
        with pytest.raises(ValueError):
            SdcaCompositeWeights(valuation=1.0, **{name: -0.1})

    def test_new_weights_join_the_simplex(self) -> None:
        w = SdcaCompositeWeights(
            valuation=1.0,
            onchain_mvrv=1.0,
            fear_greed=1.0,
            fast_crash_vol=1.0,
        ).normalized()
        assert w.valuation == pytest.approx(0.25)
        assert w.onchain_mvrv == pytest.approx(0.25)
        assert w.fear_greed == pytest.approx(0.25)
        assert w.fast_crash_vol == pytest.approx(0.25)
        assert sum(w.model_dump().values()) == pytest.approx(1.0)

    @pytest.mark.parametrize("name", RESEARCH_ONLY_NAMES)
    def test_parsed_from_params_and_json(self, name: str) -> None:
        assert getattr(composite_weights_from_params({f"{name}_weight": 0.25}), name) == (
            pytest.approx(0.25)
        )
        assert getattr(parse_indicator_weights_json(f'{{"{name}": 0.25}}'), name) == (
            pytest.approx(0.25)
        )

    def test_published_defaults_are_untouched(self) -> None:
        """Research weights must not leak into the params/JSON default path."""
        assert composite_weights_from_params({"buy_max_rate": 10.0}).enabled_extras() == {}
        assert parse_indicator_weights_json("").enabled_extras() == {}
        assert parse_indicator_weights_json("null").enabled_extras() == {}
        with pytest.raises(ValueError, match="JSON object"):
            parse_indicator_weights_json("[1, 2]")


class TestWeightParamCoverage:
    """``two_stage.freeze_weight_params`` indexes this map for every model field."""

    def test_every_weight_field_has_a_param(self) -> None:
        assert set(SdcaCompositeWeights.model_fields) == set(WEIGHT_PARAM_BY_NAME)

    @pytest.mark.parametrize("name", RESEARCH_ONLY_NAMES)
    def test_new_weights_have_params(self, name: str) -> None:
        assert WEIGHT_PARAM_BY_NAME[name] == f"{name}_weight"

    def test_freeze_weight_params_round_trips(self) -> None:
        w = SdcaCompositeWeights(valuation=1.0, onchain_puell=0.5, fast_crash_vol=0.25)
        frozen = freeze_weight_params(w)
        assert frozen["valuation_weight"] == pytest.approx(1.0)
        assert frozen["onchain_puell_weight"] == pytest.approx(0.5)
        assert frozen["fast_crash_vol_weight"] == pytest.approx(0.25)

    def test_every_extra_item_is_a_published_param(self) -> None:
        params = set(WEIGHT_PARAM_BY_NAME.values())
        for name, _ in SdcaCompositeWeights(valuation=1.0, fear_greed=1.0).extra_items():
            assert f"{name}_weight" in params


class TestDormantNames:
    """The new ids stay out of the published name tuples on purpose."""

    @pytest.mark.parametrize("name", RESEARCH_ONLY_NAMES)
    def test_not_published(self, name: str) -> None:
        published = (
            set(EXTRA_INDICATOR_NAMES)
            | set(MACRO_INDICATOR_NAMES)
            | set(BTC_PLUGIN_INDICATOR_NAMES)
            | set(PRICE_OSCILLATOR_NAMES)
        )
        assert name not in published

    def test_published_tuples_are_exactly_develops(self) -> None:
        assert MACRO_INDICATOR_NAMES == ("m2", "rs_eth", "dxy")
        assert PRICE_OSCILLATOR_NAMES == ("weekly_rsi", "weekly_macd", "sma_band")
        assert EXTRA_INDICATOR_NAMES == (
            "m2",
            "rs_eth",
            "dxy",
            "weekly_rsi",
            "weekly_macd",
            "sma_band",
        )


class TestDefaultCompositeIsTheValuationRailAlone:
    """The port's counterpart to the branch's ``TestDefaultMatchesPowerLawOnly``.

    The branch carried a test asserting its default composite is power-law-only.
    It was not ported, and — unlike the four rewires this port defers — it had
    **no pin recording that leaving it out was a choice**, so a future leaf
    could change the default composite silently. This class is that pin.

    It also corrects the record on *why* it was not ported. QA's open item 2
    recorded that "develop's default differs (``valuation`` is the only non-zero
    default)", implying the branch's assertion was false against develop. It is
    not false — it is the same assertion under a different spelling. On develop
    ``valuation`` **is** the power-law rail: ``indicator_catalog``'s own module
    docstring calls it ``power-law valuation_z``, and ``indicator_display_name``
    renders it to users as ``"power law"`` (pinned in
    :meth:`TestDisplayNames.test_develop_labels_still_win`). So "default is
    power-law-only" and "default is valuation-only" say the same thing here. The
    spelling gap is the deferred ``valuation`` → ``power_law`` rename, already
    pinned by ``test_deferred_power_law_rename_is_not_ported``; it is not a
    behavioural difference and does not need a second pin of its own.

    What genuinely was unpinned is the *value*: that ``valuation`` is the one and
    only non-zero default across every field on the model. That is what these
    tests assert, and it is the assertion that catches a future weight being
    given a non-zero default — the dormancy invariant from leaf 2's scope note,
    extended from the seven new ids to all fourteen fields.
    """

    def test_valuation_is_the_only_non_zero_default(self) -> None:
        """Fails if any field, old or new, is given a non-zero default.

        This is the whole point. ``SdcaCompositeWeights`` has 14 fields; the
        assertion is deliberately over the whole model rather than over
        ``RESEARCH_ONLY_NAMES``, so it also guards the seven develop weights
        that predate this port.
        """
        w = SdcaCompositeWeights()
        non_zero = {
            name: getattr(w, name) for name in type(w).model_fields if getattr(w, name) != 0.0
        }
        assert non_zero == {"valuation": pytest.approx(1.0)}, (
            "the default composite must be the valuation rail alone; got "
            f"{sorted(non_zero)} -- a non-zero default silently changes what "
            "digiquant publishes without any measured delta"
        )

    def test_the_default_enables_no_extras_at_all(self) -> None:
        """``enabled_extras()`` is empty, but ``extra_items()`` is the full catalogue.

        The two views differ and the distinction is load-bearing: ``extra_items()``
        yields every extra field at its weight *including the zeros*, and it is
        what ``weight_search._extra_weight_names()`` derives the searchable-name
        set from. So "no extra is enabled" must not be pinned as "no extra is
        listed" — that would assert the searchable set is empty, which is
        exactly the QA-G4 gap (a research extra silently dropping out of the
        searchable set) wearing a different hat.
        """
        w = SdcaCompositeWeights()
        assert w.enabled_extras() == {}
        listed = dict(w.extra_items())
        assert len(listed) == 13, "the extra catalogue is 13 names on develop plus this leaf"
        assert set(listed.values()) == {0.0}
        for name in RESEARCH_ONLY_NAMES:
            assert listed[name] == pytest.approx(0.0), f"{name} must be listed, at weight 0"

    def test_the_default_normalizes_to_a_pure_valuation_point(self) -> None:
        """``normalized()`` is a no-op on the default — it is already on the simplex."""
        w = SdcaCompositeWeights()
        n = w.normalized()
        assert n.valuation == pytest.approx(1.0)
        assert sum(n.model_dump().values()) == pytest.approx(1.0)
        for name in RESEARCH_ONLY_NAMES:
            assert getattr(n, name) == pytest.approx(0.0)

    def test_the_valuation_id_is_the_power_law_rail(self) -> None:
        """Why "valuation-only" and "power-law-only" are the same sentence.

        This is what justifies treating the branch's un-ported assertion as
        *satisfied* rather than as a gap. If someone ever changes the chart
        label away from ``"power law"``, the equivalence this class relies on is
        no longer documented anywhere and this test is the thing that notices.
        """
        assert INDICATOR_DISPLAY_NAMES["valuation"] == "power law"
        assert indicator_display_name("valuation") == "power law"
        assert WEIGHT_PARAM_BY_NAME["valuation"] == "valuation_weight"

    def test_the_default_is_reachable_through_both_parsing_paths(self) -> None:
        """Both published defaults resolve to the same valuation-only point.

        ``composite_weights_from_params`` and ``parse_indicator_weights_json``
        are the MCP / settings entry points. If either defaulted a different way,
        the "default" that callers actually get would drift from the model
        default this class pins.
        """
        from_params = composite_weights_from_params({})
        from_json = parse_indicator_weights_json("{}")
        for w in (from_params, from_json):
            assert w.valuation == pytest.approx(1.0)
            assert w.enabled_extras() == {}
            assert sum(w.normalized().model_dump().values()) == pytest.approx(1.0)


class TestDisplayNames:
    @pytest.mark.parametrize("name", RESEARCH_ONLY_NAMES)
    def test_new_ids_are_labelled(self, name: str) -> None:
        assert INDICATOR_DISPLAY_NAMES[name] != name.replace("_", " ")
        assert indicator_display_name(name) == INDICATOR_DISPLAY_NAMES[name]

    def test_develop_labels_still_win(self) -> None:
        assert indicator_display_name("valuation") == "power law"
        assert indicator_display_name("m2") == "M2 liquidity"

    def test_unknown_id_falls_back(self) -> None:
        assert indicator_display_name("not_an_indicator") == "not an indicator"


# --------------------------------------------------------------------------------------
# On-chain ratio family (shared log-ratio core)
# --------------------------------------------------------------------------------------

_ONCHAIN_WRAPPERS: dict[str, Callable[..., pl.Series]] = {
    "onchain_mvrv": onchain_mvrv_z,
    "onchain_asopr": onchain_asopr_z,
    "onchain_puell": onchain_puell_z,
    "onchain_rhodl": onchain_rhodl_z,
}


class TestOnchainRatioFamily:
    @pytest.mark.parametrize(("name", "fn"), list(_ONCHAIN_WRAPPERS.items()))
    def test_aliased_to_its_own_id(self, name: str, fn: Callable[..., pl.Series]) -> None:
        n = 120
        src = _src(n)
        z = fn(
            _dates(n),
            src[f"{name}_dates"],  # type: ignore[index]
            src[f"{name}_values"],  # type: ignore[index]
            window=_W,
            min_samples=_M,
        )
        assert z.name == name
        assert len(z) == n

    @pytest.mark.parametrize(("name", "fn"), list(_ONCHAIN_WRAPPERS.items()))
    def test_elevated_ratio_is_sell_favourable(
        self, name: str, fn: Callable[..., pl.Series]
    ) -> None:
        """A rising ratio is an overheated chain -> sign-flipped z goes negative."""
        n = 120
        src = _src(n)
        z = _z_list(
            fn(
                _dates(n),
                src[f"{name}_dates"],  # type: ignore[index]
                src[f"{name}_values"],  # type: ignore[index]
                window=_W,
                min_samples=_M,
            )
        )
        assert z[-1] is not None and z[-1] < 0.0

    @pytest.mark.parametrize(("name", "fn"), list(_ONCHAIN_WRAPPERS.items()))
    def test_depressed_ratio_is_buy_favourable(
        self, name: str, fn: Callable[..., pl.Series]
    ) -> None:
        n = 120
        falling = _geom(n, 0.995, 6.0)
        z = _z_list(
            fn(_dates(n), _dates(n), falling, window=_W, min_samples=_M)  # type: ignore[arg-type]
        )
        assert z[-1] is not None and z[-1] > 0.0

    def test_shares_one_core_so_the_family_agrees(self) -> None:
        """Four indicators, one formula: identical inputs must give identical z."""
        n = 120
        src = _src(n)
        series = src["onchain_mvrv_values"]
        outs = [
            _z_list(fn(_dates(n), _dates(n), series, window=_W, min_samples=_M))  # type: ignore[arg-type]
            for fn in _ONCHAIN_WRAPPERS.values()
        ]
        for other in outs[1:]:
            assert outs[0] == other

    def test_log_transformed_not_level(self) -> None:
        """A ratio is log-transformed first, so the z is scale-invariant."""
        n = 120
        base = _geom(n, 1.01, 4.0)
        z_base = _z_list(onchain_mvrv_z(_dates(n), _dates(n), base, window=_W, min_samples=_M))  # type: ignore[arg-type]
        z_scaled = _z_list(
            onchain_mvrv_z(_dates(n), _dates(n), base * 37.0, window=_W, min_samples=_M)  # type: ignore[arg-type]
        )
        assert len(z_base) == len(z_scaled)
        for a, b in zip(z_base, z_scaled, strict=True):
            assert a == pytest.approx(b, abs=1e-9)

    def test_window_two_pins_std_semantics_and_sign(self) -> None:
        """window=2/min_samples=1 has a closed form: z = ±1/sqrt(2) on a monotone series."""
        n = 40
        rising = _geom(n, 1.01, 2.0)
        z = _z_list(onchain_mvrv_z(_dates(n), _dates(n), rising, window=2, min_samples=1))  # type: ignore[arg-type]
        expected = -(2**-0.5)
        assert z[0] is None
        for value in z[1:]:
            assert value == pytest.approx(expected)

        falling = _geom(n, 0.99, 2.0)
        z_down = _z_list(onchain_mvrv_z(_dates(n), _dates(n), falling, window=2, min_samples=1))  # type: ignore[arg-type]
        assert z_down[-1] == pytest.approx(-expected)

    def test_bounded_to_three(self) -> None:
        n = 120
        values = pl.Series("value", [1.0] * 60 + [1e6] * 60, dtype=pl.Float64)
        z = _z_list(onchain_mvrv_z(_dates(n), _dates(n), values, window=_W, min_samples=_M))  # type: ignore[arg-type]
        present = [v for v in z if v is not None]
        assert present
        assert min(present) >= -3.0
        assert max(present) <= 3.0

    def test_constant_ratio_is_flat_zero(self) -> None:
        """A dead-flat ratio has zero dispersion; the sigma floor must give z == 0."""
        n = 120
        flat = pl.Series("value", [2.5] * n, dtype=pl.Float64)
        z = _z_list(onchain_mvrv_z(_dates(n), _dates(n), flat, window=_W, min_samples=_M))  # type: ignore[arg-type]
        # Not exactly 0: the sigma floor makes z = (x - mean)/1e-12, and the
        # rolling mean of a constant float series can differ from it by an ULP.
        for value in z[_M - 1 :]:
            assert value == pytest.approx(0.0, abs=1e-3)

    def test_warmup_before_min_samples_is_null(self) -> None:
        n = 120
        z = _z_list(
            onchain_mvrv_z(_dates(n), _dates(n), _geom(n, 1.01, 2.0), window=_W, min_samples=_M)  # type: ignore[arg-type]
        )
        assert all(value is None for value in z[: _M - 1])
        assert z[_M - 1] is not None

    def test_too_short_window_rejected(self) -> None:
        n = 40
        with pytest.raises(ValueError, match="rolling window"):
            onchain_mvrv_z(_dates(n), _dates(n), _geom(n, 1.01, 2.0), window=1)  # type: ignore[arg-type]


class TestOnchainNonPositiveValues:
    """A handful of pre-history days report 0 -- a coverage gap, never ``-inf``."""

    @pytest.mark.parametrize("bad", [0.0, -1.0])
    def test_zero_or_negative_source_does_not_poison_the_log(self, bad: float) -> None:
        n = 120
        values = pl.Series("value", [bad] * 10 + [2.0 + 0.01 * i for i in range(n - 10)])
        z = _z_list(onchain_mvrv_z(_dates(n), _dates(n), values, window=_W, min_samples=_M))  # type: ignore[arg-type]
        assert all(value is None or value == value for value in z)
        present = [v for v in z if v is not None]
        assert present
        assert all(-3.0 <= v <= 3.0 for v in present)

    def test_gap_is_forward_filled_not_treated_as_minus_infinity(self) -> None:
        """With a gap in the middle, forward-fill must carry the last good level."""
        n = 120
        good = [2.0 + 0.01 * i for i in range(n)]
        holed = pl.Series("value", [*good[:60], 0.0, *good[61:]], dtype=pl.Float64)
        holed_z = _z_list(onchain_mvrv_z(_dates(n), _dates(n), holed, window=_W, min_samples=_M))  # type: ignore[arg-type]
        # The forward-filled equivalent: day 60 carries day 59's level, not -inf.
        # good[:60] + [good[59]] + good[61:] -- day 60's own value is replaced,
        # keeping the length at 120.
        filled = pl.Series("value", [*good[:60], good[59], *good[61:]], dtype=pl.Float64)
        filled_z = _z_list(onchain_mvrv_z(_dates(n), _dates(n), filled, window=_W, min_samples=_M))  # type: ignore[arg-type]
        assert holed_z[60] == pytest.approx(filled_z[60])
        assert holed_z == pytest.approx(filled_z, abs=1e-9)

    def test_all_non_positive_is_entirely_null(self) -> None:
        n = 60
        values = pl.Series("value", [0.0] * n, dtype=pl.Float64)
        z = _z_list(onchain_mvrv_z(_dates(n), _dates(n), values, window=_W, min_samples=_M))  # type: ignore[arg-type]
        assert all(value is None for value in z)


class TestOnchainAddrRatio:
    def test_aliased_and_length(self) -> None:
        n = 120
        src = _src(n)
        z = onchain_addr_ratio_z(
            _dates(n),
            _geom(n, 1.01, 50_000.0),
            src["onchain_addr_ratio_dates"],
            src["onchain_addr_ratio_values"],
            window=_W,
            min_samples=_M,
        )
        assert z.name == "onchain_addr_ratio"
        assert len(z) == n

    def test_zero_addresses_nulled_before_the_divide(self) -> None:
        """Pre-adoption days report 0 addresses; the divide must never see them."""
        n = 120
        price = _geom(n, 1.01, 50_000.0)
        addr = pl.Series("value", [0.0] * 10 + [900_000.0 + 1000.0 * i for i in range(n - 10)])
        z = _z_list(
            onchain_addr_ratio_z(_dates(n), price, _dates(n), addr, window=_W, min_samples=_M)  # type: ignore[arg-type]
        )
        assert all(value is None or value == value for value in z)
        present = [v for v in z if v is not None]
        assert present
        assert all(-3.0 <= v <= 3.0 for v in present)

    def test_rising_price_per_address_is_sell_favourable(self) -> None:
        """Falling active addresses with steady price -> expensive per address -> -z."""
        n = 120
        price = pl.Series("value", [50_000.0] * n, dtype=pl.Float64)
        addr = _geom(n, 0.995, 900_000.0)
        z = _z_list(
            onchain_addr_ratio_z(_dates(n), price, _dates(n), addr, window=_W, min_samples=_M)  # type: ignore[arg-type]
        )
        assert z[-1] is not None and z[-1] < 0.0

    def test_falling_price_per_address_is_buy_favourable(self) -> None:
        n = 120
        price = _geom(n, 0.995, 50_000.0)
        addr = pl.Series("value", [900_000.0] * n, dtype=pl.Float64)
        z = _z_list(
            onchain_addr_ratio_z(_dates(n), price, _dates(n), addr, window=_W, min_samples=_M)  # type: ignore[arg-type]
        )
        assert z[-1] is not None and z[-1] > 0.0


# --------------------------------------------------------------------------------------
# Fear & Greed
# --------------------------------------------------------------------------------------


class TestFearGreed:
    def test_aliased_and_uses_the_default_window(self) -> None:
        n = 200
        src = _src(n)
        z = fear_greed_z(_dates(n), src["fear_greed_dates"], src["fear_greed_values"])
        assert z.name == "fear_greed"
        assert len(z) == n

    def test_extreme_greed_is_sell_favourable(self) -> None:
        n = 120
        z = _z_list(fear_greed_z(_dates(n), _dates(n), _geom(n, 1.01, 50.0)))  # type: ignore[arg-type]
        assert z[-1] is not None and z[-1] < 0.0

    def test_extreme_fear_is_buy_favourable(self) -> None:
        n = 120
        z = _z_list(fear_greed_z(_dates(n), _dates(n), _geom(n, 0.99, 50.0)))  # type: ignore[arg-type]
        assert z[-1] is not None and z[-1] > 0.0

    def test_window_two_pins_sign(self) -> None:
        n = 40
        z = _z_list(
            fear_greed_z(_dates(n), _dates(n), _geom(n, 1.01, 45.0), window=2, min_samples=1)  # type: ignore[arg-type]
        )
        assert z[-1] == pytest.approx(-(2**-0.5))

    def test_level_not_log(self) -> None:
        """Unlike the ratio family, the index is a level series -- no log transform."""
        n = 120
        values = _geom(n, 1.01, 45.0)
        aligned = align_to_dates(_dates(n), _dates(n), values, forward_fill=True)
        expected = (-causal_rolling_z(aligned, window=_W, min_samples=_M)).to_list()
        assert (
            _z_list(
                fear_greed_z(_dates(n), _dates(n), values, window=_W, min_samples=_M)  # type: ignore[arg-type]
            )
            == expected
        )

    def test_sparse_source_is_forward_filled(self) -> None:
        """A weekly index must fill the gaps; without the fill the z would be null."""
        n = 120
        weekly_dates = _dates(n)[::7]
        weekly_values = _geom(len(weekly_dates), 1.01, 45.0)
        z = _z_list(fear_greed_z(_dates(n), weekly_dates, weekly_values, window=_W, min_samples=_M))
        present = [v for v in z if v is not None]
        assert present
        assert all(-3.0 <= v <= 3.0 for v in present)

    def test_warmup_is_null(self) -> None:
        n = 120
        z = _z_list(fear_greed_z(_dates(n), _dates(n), _geom(n, 1.01, 45.0)))  # type: ignore[arg-type]
        assert all(value is None for value in z[:19])


# --------------------------------------------------------------------------------------
# Fast crash volatility
# --------------------------------------------------------------------------------------


class TestFastCrashVol:
    def _calm_then_spike_then_calm(self) -> pl.Series:
        """Geometric drift, a violent burst, then geometric drift again.

        Two warmups must both clear the burst before the z can read zero:
        the 14-day vol window and then the 90-day z window. The burst ends at
        step 94, so the tail is 130 days -- 14 to wash the vol clean plus 90 for
        the z window, with margin.
        """
        prices: list[float] = [50_000.0]
        steps = [1.001] * 60 + [1.08, 0.93, 1.07, 0.94, 1.06, 0.95, 1.05] * 5 + [1.001] * 130
        for step in steps:
            prices.append(prices[-1] * step)
        return pl.Series("value", prices, dtype=pl.Float64)

    def test_length_mismatch_rejected(self) -> None:
        with pytest.raises(ValueError, match="same length"):
            fast_crash_vol_z(_dates(10), _geom(11, 1.01, 50_000.0))

    def test_aliased_and_uses_the_default_windows(self) -> None:
        n = 200
        price = _geom(n, 1.001, 50_000.0)
        z = fast_crash_vol_z(_dates(n), price)
        assert z.name == "fast_crash_vol"
        assert len(z) == n
        # 14d realized vol needs 7 returns, then a 90d z needs 20 -- so the
        # first score lands well past the raw-vol warmup, never on day 0.
        assert all(value is None for value in z[:20])
        assert z[-1] is not None

    def test_vol_spike_is_sell_favourable(self) -> None:
        price = self._calm_then_spike_then_calm()
        n = len(price)
        z = _z_list(fast_crash_vol_z(_dates(n), price))
        spike = z[60:100]
        present = [v for v in spike if v is not None]
        assert present
        assert min(present) < 0.0

    def test_decays_back_to_zero_once_swings_shrink(self) -> None:
        """The point of tracking return magnitude: it must not stay pinned."""
        price = self._calm_then_spike_then_calm()
        n = len(price)
        z = _z_list(fast_crash_vol_z(_dates(n), price))
        assert z[-1] is not None
        assert z[-1] == pytest.approx(0.0, abs=1e-3)

    def test_bounded_to_three(self) -> None:
        price = self._calm_then_spike_then_calm()
        n = len(price)
        z = _z_list(fast_crash_vol_z(_dates(n), price))
        present = [v for v in z if v is not None]
        assert present
        assert all(-3.0 <= v <= 3.0 for v in present)

    def test_windows_are_tunable(self) -> None:
        n = 120
        price = self._calm_then_spike_then_calm()[:n]
        z = _z_list(
            fast_crash_vol_z(
                _dates(n), price, window=5, min_samples=3, z_window=20, z_min_samples=5
            )
        )
        assert z[4] is None
        assert z[7] is not None

    def test_flat_price_is_flat_zero(self) -> None:
        n = 120
        price = pl.Series("value", [50_000.0] * n, dtype=pl.Float64)
        z = _z_list(fast_crash_vol_z(_dates(n), price))
        present = [v for v in z if v is not None]
        assert present
        assert all(v == pytest.approx(0.0, abs=1e-6) for v in present)


# --------------------------------------------------------------------------------------
# rs_eth slow/fast confluence
# --------------------------------------------------------------------------------------


class TestRsEthConfluence:
    def _inputs(self, n: int) -> tuple[pl.Series, pl.Series, pl.Series, pl.Series]:
        """BTC drifting up, ETH with a mid-sample shock.

        The ETH halving makes the two windows disagree in the middle of the
        sample (the fast 20d leg has seen the shock, the slow 60d leg has not)
        and agree again at both ends -- so the blend's agreement-boost and
        disagreement-damp branches are both exercised.
        """
        src = _src(n)
        eth = src["eth_close"]
        assert eth is not None
        return (_dates(n), _geom(n, 1.01, 50_000.0), src["eth_dates"], _shocked(eth, n))

    def test_aliased_to_rs_eth(self) -> None:
        n = 200
        dates, btc, eth_dates, eth_close = self._inputs(n)
        z = rs_eth_confluence_z(dates, btc, eth_dates, eth_close)
        assert z.name == "rs_eth"
        assert len(z) == n

    def test_is_the_agreement_scaled_blend_of_two_rs_eth_legs(self) -> None:
        n = 200
        dates, btc, eth_dates, eth_close = self._inputs(n)
        z = _z_list(
            rs_eth_confluence_z(
                dates,
                btc,
                eth_dates,
                eth_close,
                slow_window=60,
                slow_min_samples=20,
                fast_window=20,
                fast_min_samples=10,
            )
        )
        slow = rs_eth_z(dates, btc, eth_dates, eth_close, window=60, min_samples=20).to_list()
        fast = rs_eth_z(dates, btc, eth_dates, eth_close, window=20, min_samples=10).to_list()
        assert len(z) == len(slow) == len(fast)
        agree = disagree = 0
        for out, s, f in zip(z, slow, fast, strict=True):
            if s is None and f is None:
                assert out is None
                continue
            if s is None or f is None:
                # A silent timeframe is a passthrough, not a disagreement.
                assert out == pytest.approx(f if f is not None else s)
                continue
            base = 0.5 * s + 0.5 * f
            if (s > 0) == (f > 0):
                frac = min(abs(s), abs(f)) / max(abs(s), abs(f))
                expect = base * (1.0 + 0.5 * frac)
                agree += 1
            else:
                expect = base * 0.5
                disagree += 1
            # The boost can push past the [-3, 3] clip, so clip the expectation too.
            assert out == pytest.approx(max(-3.0, min(3.0, expect)), abs=1e-9)
            assert -3.0 <= out <= 3.0
        # Non-vacuity: the fixture must exercise both branches.
        assert agree > 0
        assert disagree > 0

    def test_differs_from_the_single_window_rs_eth(self) -> None:
        n = 200
        dates, btc, eth_dates, eth_close = self._inputs(n)
        assert (
            rs_eth_confluence_z(dates, btc, eth_dates, eth_close).to_list()
            != rs_eth_z(dates, btc, eth_dates, eth_close).to_list()
        )

    def test_waits_for_the_slow_leg(self) -> None:
        """The fast leg is enough to emit a value before the slow one warms up."""
        n = 200
        dates, btc, eth_dates, eth_close = self._inputs(n)
        z = rs_eth_confluence_z(
            dates,
            btc,
            eth_dates,
            eth_close,
            slow_window=60,
            slow_min_samples=20,
            fast_window=20,
            fast_min_samples=10,
        ).to_list()
        slow = rs_eth_z(dates, btc, eth_dates, eth_close, window=60, min_samples=20).to_list()
        fast = rs_eth_z(dates, btc, eth_dates, eth_close, window=20, min_samples=10).to_list()
        # slow_window/min_samples is the binding warmup. A ``min_samples=20``
        # rolling z first emits at index 19, so index 18 is the last null.
        last_null_slow = max(i for i, v in enumerate(slow) if v is None)
        assert last_null_slow == 18
        assert slow[19] is not None
        assert fast[19] is not None
        assert z[last_null_slow] is not None, "fast leg should carry the vote"
        assert z[last_null_slow] == pytest.approx(fast[last_null_slow])
        assert all(v is None for v in z[:9])

    def test_dormant_build_keeps_plain_rs_eth_z(self) -> None:
        """``rs_eth`` is rewired to the confluence in a later leaf, not this one."""
        n = 200
        dates, btc, eth_dates, eth_close = self._inputs(n)
        extras = build_extra_indicators(
            dates,
            btc,
            SdcaCompositeWeights(valuation=1.0, rs_eth=1.0),
            ExtraIndicatorSources(eth_dates=eth_dates, eth_close=eth_close),
        )
        built = {ind.name: ind.z.to_list() for ind in extras}
        assert built["rs_eth"] == rs_eth_z(dates, btc, eth_dates, eth_close).to_list()

    def test_bounded_to_three(self) -> None:
        n = 300
        dates, btc, eth_dates, eth_close = self._inputs(n)
        z = rs_eth_confluence_z(dates, btc, eth_dates, eth_close).to_list()
        present = [v for v in z if v is not None]
        assert present
        assert all(-3.0 <= v <= 3.0 for v in present)


# --------------------------------------------------------------------------------------
class TestRsEthConfluenceWindowValidation:
    """What ``rs_eth_confluence_z`` actually promises about window/sample pairs.

    **This class corrects the record on an open item rather than papering over
    it.** QA's open item 1 was scoped as: "``fast_min_samples > fast_window`` is
    rejected in one confluence function and silently accepted in the other."
    Both halves of that turned out to be wrong when measured:

    * **Nothing is "silently accepted".** ``min_samples > window`` raises in both
      functions. It raises ``polars.exceptions.InvalidOperationError`` with the
      message ``min_periods should be <= window_size``, from two frames inside
      polars rather than at the argument.
    * **Neither confluence function rejects it at all.** The ``ValueError``
      guard QA found lives on ``SdcaOscillatorSpec._ordered`` and covers
      ``sma_band_min_samples > sma_band_window`` — a *spec* field. Develop's spec
      carries no ``rs_eth_*`` fields at all, so there is nothing for an
      ``rs_eth_*`` validator to hang off, and ``sma_band_confluence_z`` — which
      also takes plain keyword-only args rather than a spec — does no such
      check either.

    So adding a ``ValueError`` to ``rs_eth_confluence_z`` would have made the
    pair *more* inconsistent, not less. The real contract is the symmetric one
    below, and it is worth pinning: a caller who inverts the pair gets a loud
    polars error on both legs rather than a silently all-null or mis-windowed
    z, and the error is raised by the leg whose arguments were actually wrong.

    What the branch's lost ``TestOscillatorSpecRsEthFast`` was really protecting
    is pinned too, further down: that ``SdcaOscillatorSpec`` still refuses an
    inverted min-samples pair, and that it exposes no ``rs_eth_*`` fields for a
    future leaf to attach such a validator to.
    """

    @staticmethod
    def _inputs(n: int = 200) -> tuple[pl.Series, pl.Series, pl.Series, pl.Series]:
        src = _src(n)
        eth = src["eth_close"]
        assert eth is not None
        return (_dates(n), _geom(n, 1.01, 50_000.0), src["eth_dates"], eth)

    def test_an_inverted_fast_pair_raises_rather_than_returning_a_wrong_number(self) -> None:
        dates, btc, eth_dates, eth_close = self._inputs()
        with pytest.raises(pl.exceptions.InvalidOperationError):
            rs_eth_confluence_z(
                dates, btc, eth_dates, eth_close, fast_window=20, fast_min_samples=21
            )

    def test_the_inverted_slow_pair_raises_too(self) -> None:
        """Both legs are unguarded symmetrically — not just the fast one."""
        dates, btc, eth_dates, eth_close = self._inputs()
        with pytest.raises(pl.exceptions.InvalidOperationError):
            rs_eth_confluence_z(
                dates, btc, eth_dates, eth_close, slow_window=20, slow_min_samples=21
            )

    def test_an_equal_pair_is_accepted(self) -> None:
        """``min_samples == window`` is the tightest legal pair, and it is legal.

        Polars' own rule is ``min_periods <= window_size``, so this pins the
        inclusive edge on the legal side — the mirror of the raising cases.
        """
        dates, btc, eth_dates, eth_close = self._inputs()
        z = rs_eth_confluence_z(
            dates, btc, eth_dates, eth_close, fast_window=20, fast_min_samples=20
        )
        assert z.name == "rs_eth"
        assert z.null_count() < len(z)

    def test_sma_band_confluence_behaves_identically(self) -> None:
        """The symmetry claim itself, measured against the sibling function.

        This is the assertion that keeps QA's original framing from creeping
        back: if a future edit adds a ``ValueError`` to ``rs_eth_confluence_z``
        and not to ``sma_band_confluence_z``, this test fails and the divergence
        has to be a deliberate, visible act.
        """
        n = 200
        dates = _dates(n)
        close = _geom(n, 1.01, 50_000.0)
        for fn in (sma_band_confluence_z, rs_eth_confluence_z):
            kwargs = {"fast_window": 20, "fast_min_samples": 21}
            args = (
                (dates, close)
                if fn is sma_band_confluence_z
                else (
                    dates,
                    close,
                    dates,
                    close,
                )
            )
            with pytest.raises(pl.exceptions.InvalidOperationError):
                fn(*args, **kwargs)

    def test_a_leg_with_an_inverted_pair_never_silently_returns_all_nulls(self) -> None:
        """The failure mode a caller must never hit is a plausible-looking z.

        A guard that instead of raising clipped ``min_samples`` down to
        ``window`` would produce a *number* here — an all-but-undefined blend
        rather than an error. Assert the series is unreachable, not merely
        null-heavy.
        """
        dates, btc, eth_dates, eth_close = self._inputs()
        with pytest.raises(pl.exceptions.InvalidOperationError):
            rs_eth_confluence_z(
                dates, btc, eth_dates, eth_close, fast_window=10, fast_min_samples=10_000
            )

    def test_the_fast_kwargs_reach_the_fast_leg(self) -> None:
        """Why the raising cases matter: ``fast_*`` is not silently ignored.

        If ``fast_window`` / ``fast_min_samples`` were dropped, the inverted-pair
        tests would pass vacuously (nothing would ever raise) *and* every
        ``rs_eth_confluence_z`` call would quietly collapse onto the slow leg.
        Pin the kwargs as load-bearing by checking the blend really moves when
        the fast window changes.
        """
        dates, btc, eth_dates, eth_close = self._inputs(300)
        narrow = _z_list(
            rs_eth_confluence_z(
                dates,
                btc,
                eth_dates,
                eth_close,
                slow_window=90,
                slow_min_samples=30,
                fast_window=20,
                fast_min_samples=10,
            )
        )
        wide = _z_list(
            rs_eth_confluence_z(
                dates,
                btc,
                eth_dates,
                eth_close,
                slow_window=90,
                slow_min_samples=30,
                fast_window=60,
                fast_min_samples=30,
            )
        )
        assert narrow != wide

    def test_the_spec_still_refuses_an_inverted_min_samples_pair(self) -> None:
        """The surviving half of the branch's lost ``TestOscillatorSpecRsEthFast``.

        Develop's ``SdcaOscillatorSpec`` has no ``rs_eth_*`` fields, so the only
        inherited coverage available is the sibling validator it does have.
        """
        with pytest.raises(ValidationError, match="sma_band_min_samples"):
            SdcaOscillatorSpec(sma_band_window=20, sma_band_min_samples=21)

    def test_the_spec_carries_no_rs_eth_fields(self) -> None:
        """Record *why* there is no spec-level ``rs_eth_*`` validator to port.

        If a future leaf adds ``rs_eth_fast_window`` here, this test is the one
        that has to be revisited — at that point ``rs_eth_confluence_z`` can take
        a spec and the two functions can agree on validation again.
        """
        assert [f for f in SdcaOscillatorSpec.model_fields if "rs_eth" in f] == []


# build_extra_indicators / extra_z_vectors wiring
# --------------------------------------------------------------------------------------


class TestBuildExtraIndicatorsWiring:
    def _all_weighted(self) -> SdcaCompositeWeights:
        return SdcaCompositeWeights(valuation=1.0, **{name: 1.0 for name in RESEARCH_ONLY_NAMES})

    def test_default_weights_materialize_nothing(self) -> None:
        """Dormancy: the default model must not need any new source."""
        n = 200
        extras = build_extra_indicators(
            _dates(n), _geom(n, 1.01, 50_000.0), SdcaCompositeWeights(), ExtraIndicatorSources()
        )
        assert extras == []
        assert missing_extra_names(SdcaCompositeWeights(), {}) == ()

    @pytest.mark.parametrize("name", RESEARCH_ONLY_NAMES)
    def test_positive_weight_materializes(self, name: str) -> None:
        n = 200
        src = _src(n)
        extras = build_extra_indicators(
            _dates(n),
            _geom(n, 1.01, 50_000.0),
            SdcaCompositeWeights(valuation=1.0, **{name: 0.5}),
            ExtraIndicatorSources(**src),  # type: ignore[arg-type]
            window=_W,
            min_samples=_M,
        )
        assert [ind.name for ind in extras] == [name]
        assert extras[0].weight == pytest.approx(0.5)
        assert extras[0].enabled is True
        assert len(extras[0].z) == n

    @pytest.mark.parametrize("name", RESEARCH_ONLY_NAMES)
    def test_positive_weight_without_source_raises(self, name: str) -> None:
        """``fast_crash_vol`` is the exception: it reads only ``btc_price``."""
        n = 200
        kwargs = {"fast_crash_vol": {}} if name == "fast_crash_vol" else {}
        call = lambda: build_extra_indicators(  # noqa: E731
            _dates(n),
            _geom(n, 1.01, 50_000.0),
            SdcaCompositeWeights(valuation=1.0, **{name: 1.0}),
            ExtraIndicatorSources(**kwargs),  # type: ignore[arg-type]
        )
        if name == "fast_crash_vol":
            assert [ind.name for ind in call()] == ["fast_crash_vol"]
        else:
            with pytest.raises(ValueError, match=f"positive weight for '{name}'"):
                call()

    @pytest.mark.parametrize("name", RESEARCH_ONLY_NAMES)
    def test_zero_weight_never_touches_the_source(self, name: str) -> None:
        """A dormant id must not raise even with no source loaded at all."""
        n = 200
        extras = build_extra_indicators(
            _dates(n),
            _geom(n, 1.01, 50_000.0),
            SdcaCompositeWeights(valuation=1.0),
            ExtraIndicatorSources(),
        )
        assert name not in {ind.name for ind in extras}

    @pytest.mark.parametrize("name", RESEARCH_ONLY_NAMES)
    def test_allowlist_gate_blocks(self, name: str) -> None:
        n = 200
        with pytest.raises(ValueError, match="allowlist"):
            build_extra_indicators(
                _dates(n),
                _geom(n, 1.01, 50_000.0),
                SdcaCompositeWeights(valuation=1.0, **{name: 1.0}),
                _sources(n),
                allowlist=("m2", "rs_eth", "dxy"),
            )

    def test_allowlisted_research_extra_is_allowed(self) -> None:
        n = 200
        extras = build_extra_indicators(
            _dates(n),
            _geom(n, 1.01, 50_000.0),
            SdcaCompositeWeights(valuation=1.0, fear_greed=1.0),
            _sources(n),
            window=_W,
            min_samples=_M,
            allowlist=("m2", "rs_eth", "dxy", "fear_greed"),
        )
        assert [ind.name for ind in extras] == ["fear_greed"]

    def test_extra_z_vectors_default_is_develops_key_set(self) -> None:
        n = 200
        vectors = extra_z_vectors(
            _dates(n), _geom(n, 1.01, 50_000.0), SdcaCompositeWeights(), ExtraIndicatorSources()
        )
        assert set(vectors) == set(PRICE_OSCILLATOR_NAMES)

    def test_extra_z_vectors_carries_enabled_research_extras(self) -> None:
        n = 200
        vectors = extra_z_vectors(
            _dates(n),
            _geom(n, 1.01, 50_000.0),
            self._all_weighted(),
            _sources(n),
            window=_W,
            min_samples=_M,
        )
        for name in RESEARCH_ONLY_NAMES:
            assert name in vectors
            assert len(vectors[name]) == n

    def test_missing_extra_names_reports_an_unmaterialized_extra(self) -> None:
        assert missing_extra_names(SdcaCompositeWeights(valuation=1.0, fear_greed=1.0), {}) == (
            "fear_greed",
        )
        have = {"fear_greed": [0.0]}
        assert missing_extra_names(SdcaCompositeWeights(valuation=1.0, fear_greed=1.0), have) == ()


# --------------------------------------------------------------------------------------
# sources_from_optional_paths
# --------------------------------------------------------------------------------------


_PATH_KWARGS: tuple[tuple[str, str], ...] = (
    ("onchain_mvrv_path", "onchain_mvrv"),
    ("onchain_asopr_path", "onchain_asopr"),
    ("onchain_puell_path", "onchain_puell"),
    ("onchain_rhodl_path", "onchain_rhodl"),
    ("fear_greed_path", "fear_greed"),
)


class TestSourcesFromOptionalPaths:
    def _csv(self, path: Path, n: int = 5) -> Path:
        frame = pl.DataFrame(
            {
                "date": [str(_ROOT + _dt.timedelta(days=i)) for i in range(n)],
                "value": [1.0 + i for i in range(n)],
            }
        )
        frame.write_csv(path)
        return path

    def test_no_paths_leaves_everything_none(self) -> None:
        sources = sources_from_optional_paths()
        for _, field in _PATH_KWARGS:
            assert getattr(sources, f"{field}_dates") is None
            assert getattr(sources, f"{field}_values") is None

    @pytest.mark.parametrize(("kwarg", "field"), _PATH_KWARGS)
    def test_each_path_loads(self, kwarg: str, field: str, tmp_path: Path) -> None:
        path = self._csv(tmp_path / f"{field}.csv")
        sources = sources_from_optional_paths(**{kwarg: path})
        loaded_dates = getattr(sources, f"{field}_dates")
        loaded_values = getattr(sources, f"{field}_values")
        assert loaded_dates is not None and len(loaded_dates) == 5
        assert sorted(loaded_dates.to_list()) == sorted(
            [_ROOT + _dt.timedelta(days=i) for i in range(5)]
        )
        assert loaded_values is not None
        # Sorted, not in file order: ``load_date_value_frame`` ends in ``unique``,
        # which does not guarantee order. Today every consumer goes through
        # ``align_to_dates``, which sorts before joining, so this is masked.
        assert sorted(loaded_values.to_list()) == [1.0, 2.0, 3.0, 4.0, 5.0]

    @pytest.mark.parametrize(("kwarg", "field"), _PATH_KWARGS)
    def test_loaded_source_drives_the_indicator(
        self, kwarg: str, field: str, tmp_path: Path
    ) -> None:
        """End to end: path -> sources -> weight -> materialized z."""
        n = 200
        path = self._csv(tmp_path / f"{field}.csv", n=40)
        sources = sources_from_optional_paths(**{kwarg: path})
        extras = build_extra_indicators(
            _dates(n),
            _geom(n, 1.01, 50_000.0),
            SdcaCompositeWeights(valuation=1.0, **{field: 1.0}),
            sources,
            window=_W,
            min_samples=_M,
        )
        assert [ind.name for ind in extras] == [field]
        assert extras[0].z.to_list()[-1] is not None

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="not found"):
            sources_from_optional_paths(fear_greed_path=tmp_path / "nope.csv")

    def test_eth_series_still_passthrough(self) -> None:
        n = 5
        src = _src(n)
        sources = sources_from_optional_paths(
            eth_dates=src["eth_dates"], eth_close=src["eth_close"]
        )
        assert sources.eth_dates is not None and len(sources.eth_dates) == n
        assert sources.eth_close is not None and len(sources.eth_close) == n


# --------------------------------------------------------------------------------------
# Causality
# --------------------------------------------------------------------------------------

_FULL_N = 400
_CUT = 260
_MIN_SPREAD = 0.01
_SHOCK_AT = 150


def _shocked(series: pl.Series, n: int) -> pl.Series:
    """Halve everything from a *fixed* index onward so the fixture is n-independent.

    Pure geometric fixtures make the ratio's log nearly linear, so its rolling
    z barely moves and the causality guard would be testing almost nothing. The
    index must not scale with ``n``: the truncation test compares an n=260 run
    against the first 260 days of an n=400 run, so a relative split would put
    the level shift at a different day in each and the prefix would not match.
    """
    values = list(series.to_list())
    at = min(_SHOCK_AT, n)
    values[at:] = [v / 2.0 for v in values[at:]]
    return pl.Series("value", values, dtype=pl.Float64)


def _z_cases(n: int) -> dict[str, pl.Series]:
    """Every z-function this leaf adds, evaluated on ``n`` days."""
    dates = _dates(n)
    price = _geom(n, 1.004, 50_000.0)
    src = _src(n)
    eth_dates = src["eth_dates"]
    eth_close = src["eth_close"]
    assert eth_dates is not None and eth_close is not None
    cases = {
        name: fn(dates, src[f"{name}_dates"], src[f"{name}_values"], window=_W, min_samples=_M)  # type: ignore[index,arg-type]
        for name, fn in _ONCHAIN_WRAPPERS.items()
    }
    addr_dates = src["onchain_addr_ratio_dates"]
    addr_values = src["onchain_addr_ratio_values"]
    assert addr_dates is not None and addr_values is not None
    cases["onchain_addr_ratio"] = onchain_addr_ratio_z(
        dates,
        _shocked(price, n),
        addr_dates,
        addr_values,
        window=_W,
        min_samples=_M,
    )
    fg_dates = src["fear_greed_dates"]
    fg_values = src["fear_greed_values"]
    assert fg_dates is not None and fg_values is not None
    cases["fear_greed"] = fear_greed_z(dates, fg_dates, fg_values, window=_W, min_samples=_M)
    cases["fast_crash_vol"] = fast_crash_vol_z(
        dates,
        _shocked(price, n),
        window=5,
        min_samples=3,
        z_window=30,
        z_min_samples=8,
    )
    cases["rs_eth_confluence"] = rs_eth_confluence_z(
        dates,
        price,
        eth_dates,
        eth_close,
        slow_window=40,
        slow_min_samples=12,
        fast_window=12,
        fast_min_samples=5,
    )
    return cases


class TestNoLookAhead:
    @pytest.mark.parametrize("name", sorted(_z_cases(_FULL_N)))
    def test_truncated_history_matches_the_prefix(self, name: str) -> None:
        full = _z_cases(_FULL_N)[name]
        cut = _z_cases(_CUT)[name]
        assert len(cut) == _CUT
        prefix = full[:_CUT]
        assert prefix.to_list() == cut.to_list()

    def test_no_case_is_vacuous(self) -> None:
        """Every case must actually produce values, or the truncation test proves nothing."""
        for name, series in _z_cases(_FULL_N).items():
            present = [v for v in series.to_list() if v is not None]
            assert present, f"{name} produced no non-null values"
            assert len(present) > _FULL_N // 2, f"{name} is mostly null"

    def test_independent_assertion_the_tail_moves(self) -> None:
        """Guard against a fixture where every z is ~0 and 'causal' is unfalsifiable."""
        for name, series in _z_cases(_FULL_N).items():
            present = [v for v in series.to_list() if v is not None]
            spread = max(present) - min(present)
            # Smooth geometric fixtures legitimately produce small spreads; the
            # point is only that the series is not constant.
            assert spread > _MIN_SPREAD, f"{name} is flat (spread {spread})"
