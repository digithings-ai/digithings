"""Unit tests for quant pipeline graph singleton cache."""

from __future__ import annotations

import pytest

pytest.importorskip("nautilus_trader")

from digiquant.graph import pipeline as pl


@pytest.mark.unit
def test_build_pipeline_graph_returns_same_instance() -> None:
    pl._pipeline_graph_cache = None
    g1 = pl.build_pipeline_graph()
    g2 = pl.build_pipeline_graph()
    assert g1 is g2
