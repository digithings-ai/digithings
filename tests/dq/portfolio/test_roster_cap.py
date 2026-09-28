from __future__ import annotations

import pytest
from digiquant.portfolio.roster_cap import capped_tickers, configured_max_analysts


@pytest.mark.unit
class TestCappedTickersAdaptive:
    def test_adaptive_param_overrides_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIGIQUANT_MAX_ANALYSTS", "100")  # env says no real cap
        out = capped_tickers(["A", "B", "C", "D"], held=(), min_new=1, adaptive_max_analysts=2)
        assert len(out) == 2  # adaptive cap wins

    def test_none_adaptive_uses_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIGIQUANT_MAX_ANALYSTS", "2")
        out = capped_tickers(["A", "B", "C", "D"], held=(), min_new=1, adaptive_max_analysts=None)
        assert len(out) == 2  # env cap, exactly today's behavior

    def test_adaptive_zero_means_no_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIGIQUANT_MAX_ANALYSTS", "2")
        out = capped_tickers(["A", "B", "C", "D"], held=(), min_new=1, adaptive_max_analysts=0)
        assert len(out) == 4  # 0 == no cap, overriding the env's 2


@pytest.mark.unit
class TestCanonicalCapName:
    """DIGIQUANT_MAX_ANALYSTS is the sole cap name (#4295: no read-aliases remain)."""

    def test_canonical_name_is_honoured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIGIQUANT_MAX_ANALYSTS", "2")
        assert configured_max_analysts() == 2
