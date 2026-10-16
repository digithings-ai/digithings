"""ADDM rolling Sharpe Z-score drift detection."""

from __future__ import annotations

import statistics
import time
from collections import deque

from pydantic import BaseModel, Field

# Default window for rolling Sharpe history.
_DEFAULT_WINDOW = 30
# Z-score threshold for declaring drift.
_DEFAULT_Z_THRESHOLD = 2.0
# Strategies with no new observations for this many seconds are pruned from memory.
_DEFAULT_TTL_SECONDS: float = 86400 * 7  # 7 days

# Per-strategy rolling Sharpe history: strategy_id -> deque of Sharpe values.
_sharpe_history: dict[str, deque[float]] = {}
# Last-access timestamps for TTL pruning.
_sharpe_last_access: dict[str, float] = {}


def _prune_stale_history(ttl: float = _DEFAULT_TTL_SECONDS) -> None:
    """Remove history entries that have not been updated within *ttl* seconds."""
    cutoff = time.time() - ttl
    stale = [sid for sid, t in _sharpe_last_access.items() if t < cutoff]
    for sid in stale:
        _sharpe_history.pop(sid, None)
        _sharpe_last_access.pop(sid, None)


class AddmResult(BaseModel):
    """Result of drift check."""

    drift_detected: bool = Field(False, description="True if model/strategy drift detected")
    implemented: bool = Field(False, description="True if drift check was performed")
    score: float | None = Field(None, description="Drift score if computed")
    message: str = Field("", description="Optional detail")


def record_sharpe(strategy_id: str, sharpe: float, window: int = _DEFAULT_WINDOW) -> None:
    """Append a new Sharpe observation for the given strategy to the rolling window."""
    if strategy_id not in _sharpe_history:
        _sharpe_history[strategy_id] = deque(maxlen=window)
    _sharpe_history[strategy_id].append(sharpe)
    _sharpe_last_access[strategy_id] = time.time()


def clear_history(strategy_id: str | None = None) -> None:
    """Clear rolling history. Pass strategy_id to clear one; None to clear all."""
    if strategy_id is None:
        _sharpe_history.clear()
        _sharpe_last_access.clear()
    else:
        _sharpe_history.pop(strategy_id, None)
        _sharpe_last_access.pop(strategy_id, None)


def check_drift(
    strategy_id: str,
    baseline_run_id: str | None = None,
    current_sharpe: float | None = None,
    z_threshold: float = _DEFAULT_Z_THRESHOLD,
    window: int = _DEFAULT_WINDOW,
) -> AddmResult:
    """
    Rolling Sharpe Z-score drift detection.

    Appends ``current_sharpe`` to the history for ``strategy_id`` (if provided),
    then computes a Z-score against the rolling window. Drift is declared when
    ``|z| >= z_threshold``.

    Requires at least 3 observations in the window to produce a meaningful result.
    Returns ``implemented=False`` when insufficient history exists.

    Parameters
    ----------
    strategy_id:
        Identifier for the strategy being monitored.
    baseline_run_id:
        Unused (reserved for future DB-backed baseline lookup).
    current_sharpe:
        The Sharpe ratio for the most recent period. If provided, it is recorded
        before drift is evaluated.
    z_threshold:
        Number of standard deviations from the mean that triggers a drift alert.
    window:
        Maximum number of historical observations to retain.
    """
    _prune_stale_history()
    if current_sharpe is not None:
        record_sharpe(strategy_id, current_sharpe, window=window)

    history = list(_sharpe_history.get(strategy_id, []))

    if len(history) < 3:
        return AddmResult(
            drift_detected=False,
            implemented=False,
            score=None,
            message=(
                f"Insufficient Sharpe history for '{strategy_id}' "
                f"({len(history)} obs, need ≥ 3). Record more observations with record_sharpe()."
            ),
        )

    mean = statistics.mean(history)
    stdev = statistics.stdev(history)

    if stdev == 0.0:
        return AddmResult(
            drift_detected=False,
            implemented=True,
            score=0.0,
            message=f"All {len(history)} Sharpe observations are identical (σ=0); no drift.",
        )

    latest = history[-1]
    z = (latest - mean) / stdev
    drift = abs(z) >= z_threshold

    return AddmResult(
        drift_detected=drift,
        implemented=True,
        score=round(z, 4),
        message=(
            f"Sharpe Z-score={z:.3f} (latest={latest:.3f}, μ={mean:.3f}, σ={stdev:.3f}, "
            f"n={len(history)}, threshold=±{z_threshold}). "
            + ("DRIFT DETECTED." if drift else "No drift.")
        ),
    )
