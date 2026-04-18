"""Unit tests for digiquant.addm — rolling Sharpe Z-score drift detection."""

from __future__ import annotations

import time

import pytest

from digiquant.addm import (
    _DEFAULT_TTL_SECONDS,
    _DEFAULT_Z_THRESHOLD,
    _sharpe_history,
    _sharpe_last_access,
    check_drift,
    clear_history,
    record_sharpe,
    _prune_stale_history,
)


@pytest.fixture(autouse=True)
def _clean_history():
    """Ensure global state is clean before and after every test."""
    clear_history()
    yield
    clear_history()


# ---------------------------------------------------------------------------
# record_sharpe
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRecordSharpe:
    def test_creates_deque_for_new_strategy(self) -> None:
        record_sharpe("s1", 0.5)
        assert "s1" in _sharpe_history
        assert list(_sharpe_history["s1"]) == [0.5]

    def test_appends_to_existing_deque(self) -> None:
        record_sharpe("s2", 0.1)
        record_sharpe("s2", 0.2)
        record_sharpe("s2", 0.3)
        assert list(_sharpe_history["s2"]) == [0.1, 0.2, 0.3]

    def test_window_limits_deque_length(self) -> None:
        for i in range(5):
            record_sharpe("s3", float(i), window=3)
        assert len(_sharpe_history["s3"]) == 3

    def test_updates_last_access_timestamp(self) -> None:
        before = time.time()
        record_sharpe("s4", 0.5)
        after = time.time()
        ts = _sharpe_last_access["s4"]
        assert before <= ts <= after

    def test_negative_sharpe_recorded(self) -> None:
        record_sharpe("s5", -1.5)
        assert list(_sharpe_history["s5"]) == [-1.5]


# ---------------------------------------------------------------------------
# clear_history
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestClearHistory:
    def test_clear_single_strategy(self) -> None:
        record_sharpe("a", 1.0)
        record_sharpe("b", 2.0)
        clear_history("a")
        assert "a" not in _sharpe_history
        assert "a" not in _sharpe_last_access
        assert "b" in _sharpe_history

    def test_clear_all_strategies(self) -> None:
        record_sharpe("a", 1.0)
        record_sharpe("b", 2.0)
        clear_history()
        assert len(_sharpe_history) == 0
        assert len(_sharpe_last_access) == 0

    def test_clear_nonexistent_strategy_is_safe(self) -> None:
        clear_history("does_not_exist")  # should not raise

    def test_clears_both_dicts_on_all(self) -> None:
        for s in ["x", "y", "z"]:
            record_sharpe(s, 1.0)
        clear_history()
        assert not _sharpe_history
        assert not _sharpe_last_access


# ---------------------------------------------------------------------------
# check_drift — insufficient history
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCheckDriftInsufficientHistory:
    def test_zero_observations_returns_not_implemented(self) -> None:
        r = check_drift("new_strat")
        assert r.implemented is False
        assert r.drift_detected is False

    def test_one_observation_returns_not_implemented(self) -> None:
        r = check_drift("one_obs", current_sharpe=1.0)
        assert r.implemented is False

    def test_two_observations_returns_not_implemented(self) -> None:
        record_sharpe("two_obs", 0.5)
        r = check_drift("two_obs", current_sharpe=0.6)
        assert r.implemented is False

    def test_message_mentions_insufficient(self) -> None:
        r = check_drift("no_data")
        assert "insufficient" in r.message.lower() or "need" in r.message.lower()


# ---------------------------------------------------------------------------
# check_drift — Z-score computation
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCheckDriftZScore:
    def _prime(self, strategy_id: str, values: list[float]) -> None:
        for v in values:
            record_sharpe(strategy_id, v)

    def test_no_drift_when_latest_is_near_mean(self) -> None:
        self._prime("stable", [1.0, 1.1, 0.9, 1.0, 1.05])
        r = check_drift("stable", current_sharpe=1.02)
        assert r.implemented is True
        assert r.drift_detected is False
        assert r.score is not None and abs(r.score) < _DEFAULT_Z_THRESHOLD

    def test_drift_detected_when_z_exceeds_threshold(self) -> None:
        # Normal cluster around 1.0, then extreme outlier
        self._prime("drifted", [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
        r = check_drift("drifted", current_sharpe=100.0, z_threshold=2.0)
        assert r.implemented is True
        assert r.drift_detected is True

    def test_drift_detected_on_negative_outlier(self) -> None:
        self._prime("neg_drift", [1.0] * 10)
        r = check_drift("neg_drift", current_sharpe=-100.0, z_threshold=2.0)
        assert r.drift_detected is True

    def test_zero_stdev_returns_no_drift(self) -> None:
        self._prime("flat", [1.0, 1.0, 1.0, 1.0, 1.0])
        r = check_drift("flat", current_sharpe=1.0)
        assert r.implemented is True
        assert r.drift_detected is False
        assert r.score == 0.0

    def test_custom_z_threshold_respected(self) -> None:
        self._prime("custom_thresh", [0.0, 0.0, 0.0, 0.0, 0.0])
        # Z-score with threshold=100 → never drift
        r = check_drift("custom_thresh", current_sharpe=5.0, z_threshold=100.0)
        assert r.drift_detected is False
        # Z-score with threshold=0.01 → always drift (if any deviation)
        r2 = check_drift("custom_thresh", current_sharpe=5.0, z_threshold=0.01)
        assert r2.drift_detected is True

    def test_score_is_rounded_to_four_decimals(self) -> None:
        self._prime("rounded", [1.0, 1.2, 0.8, 1.1, 0.9])
        r = check_drift("rounded", current_sharpe=1.05)
        if r.score is not None:
            assert r.score == round(r.score, 4)

    def test_check_drift_records_current_sharpe(self) -> None:
        self._prime("rec_test", [1.0, 1.0, 1.0])
        history_before = len(list(_sharpe_history.get("rec_test", [])))
        check_drift("rec_test", current_sharpe=1.5)
        history_after = len(list(_sharpe_history.get("rec_test", [])))
        assert history_after == history_before + 1

    def test_check_drift_without_current_sharpe_does_not_record(self) -> None:
        self._prime("no_new", [1.0, 1.0, 1.0])
        before = len(list(_sharpe_history["no_new"]))
        check_drift("no_new")
        after = len(list(_sharpe_history["no_new"]))
        assert after == before


# ---------------------------------------------------------------------------
# TTL pruning
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPruneStaleHistory:
    def test_prune_removes_entries_older_than_ttl(self) -> None:
        record_sharpe("old_strat", 1.0)
        # Manually backdate last access
        _sharpe_last_access["old_strat"] = time.time() - 1000
        _prune_stale_history(ttl=500)
        assert "old_strat" not in _sharpe_history
        assert "old_strat" not in _sharpe_last_access

    def test_prune_keeps_recent_entries(self) -> None:
        record_sharpe("fresh_strat", 1.0)
        _prune_stale_history(ttl=86400)  # 1 day TTL — just recorded, should survive
        assert "fresh_strat" in _sharpe_history

    def test_default_ttl_is_7_days(self) -> None:
        assert _DEFAULT_TTL_SECONDS == 86400 * 7

    def test_check_drift_triggers_prune(self) -> None:
        record_sharpe("stale_on_check", 1.0)
        # Set last_access to 8 days ago — beyond the 7-day default TTL.
        _sharpe_last_access["stale_on_check"] = time.time() - (86400 * 8)
        check_drift("new_strat_trigger")  # triggers prune
        assert "stale_on_check" not in _sharpe_history
