from __future__ import annotations

import pytest

from digiquant.olympus.hermes.roster_cap import capped_tickers


@pytest.mark.unit
class TestCappedTickersAdaptive:
    def test_adaptive_param_overrides_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "100")  # env says no real cap
        out = capped_tickers(["A", "B", "C", "D"], held=(), min_new=1, adaptive_max_analysts=2)
        assert len(out) == 2  # adaptive cap wins

    def test_none_adaptive_uses_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "2")
        out = capped_tickers(["A", "B", "C", "D"], held=(), min_new=1, adaptive_max_analysts=None)
        assert len(out) == 2  # env cap, exactly today's behavior

    def test_adaptive_zero_means_no_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "2")
        out = capped_tickers(["A", "B", "C", "D"], held=(), min_new=1, adaptive_max_analysts=0)
        assert len(out) == 4  # 0 == no cap, overriding the env's 2
