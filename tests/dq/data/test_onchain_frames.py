"""The on-chain ``date``/``value`` frame contract.

Four providers each built this empty frame by hand; a dtype change in one of
them drifted silently until a downstream join noticed. The shared builder is
asserted here once, and each provider's no-data path is checked against it.
"""

from __future__ import annotations

import polars as pl
import pytest
from digiquant.data.onchain import bgeometrics, bitview, coinmetrics, fear_greed
from digiquant.data.onchain._frames import empty_series_frame


@pytest.mark.unit
def test_empty_series_frame_contract() -> None:
    frame = empty_series_frame()
    assert frame.height == 0
    assert frame.columns == ["date", "value"]
    assert frame.schema == pl.Schema({"date": pl.Date, "value": pl.Float64})


@pytest.mark.unit
@pytest.mark.parametrize(
    "parse",
    [
        lambda: bitview.series_data_to_frame(None),
        lambda: fear_greed.fng_payload_to_frame(None),
        lambda: coinmetrics.asset_metrics_rows_to_frame(None, metric="price"),
        lambda: bgeometrics.bgeometrics_rows_to_frame(None),
    ],
)
def test_providers_return_the_shared_empty_frame(parse) -> None:  # type: ignore[no-untyped-def]
    frame = parse()
    assert frame.schema == empty_series_frame().schema
    assert frame.height == 0
