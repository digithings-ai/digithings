"""Structured trading preferences for DigiClone / quant workflows."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TradingProfile(BaseModel):
    """User or tenant preferences; maps into DigiQuant optimization constraints."""

    horizon_days: int | None = Field(
        default=None, ge=1, description="Typical holding / evaluation horizon in days"
    )
    allow_short: bool = Field(default=True)
    allow_long: bool = Field(default=True)
    max_drawdown_pct: float | None = Field(
        default=None,
        description="Max acceptable drawdown as negative fraction, e.g. -0.2 for -20%",
    )
    min_trades: int | None = Field(default=None, ge=0)
    min_sharpe: float | None = Field(default=None)
    notes: str = Field(default="", description="Freeform; not sent to DigiQuant")


def trading_profile_from_state(raw: dict[str, Any] | None) -> TradingProfile | None:
    if not raw or not isinstance(raw, dict):
        return None
    try:
        return TradingProfile.model_validate(raw)
    except Exception:
        return None


def profiling_questions_for_workflow(
    brief: object | None,
    trading_profile: dict[str, Any] | None,
) -> list[str]:
    """Merge model profiling questions with gap-filling prompts from an incomplete TradingProfile."""
    seen: set[str] = set()
    ordered: list[str] = []

    def add(q: str) -> None:
        s = (q or "").strip()
        if not s or s in seen:
            return
        seen.add(s)
        ordered.append(s)

    if isinstance(brief, dict):
        raw_list = brief.get("profiling_questions")
        if isinstance(raw_list, list):
            for x in raw_list:
                add(str(x))
    elif brief is not None:
        qs_attr = getattr(brief, "profiling_questions", None)
        if isinstance(qs_attr, list):
            for x in qs_attr:
                add(str(x))

    prof = trading_profile_from_state(trading_profile)
    if prof:
        if prof.horizon_days is None:
            add(
                "What typical holding horizon (in days) should we assume for backtests and research summaries?"
            )
        if prof.max_drawdown_pct is None:
            add(
                "What maximum drawdown is acceptable (e.g. -0.15 for -15% peak-to-trough), if we enforce portfolio risk bounds?"
            )
        if prof.min_trades is None:
            add(
                "Do you want a minimum number of trades in-sample so we do not overfit sparse fills?"
            )
    return ordered


def optimization_constraints_dict_from_profile(
    raw: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Derive DigiQuant OptimizationConstraints-shaped dict from a TradingProfile dict."""
    profile = trading_profile_from_state(raw)
    if profile is None:
        return None
    d: dict[str, Any] = {}
    if profile.min_trades is not None:
        d["min_trades"] = profile.min_trades
    if profile.max_drawdown_pct is not None:
        d["max_drawdown_pct"] = profile.max_drawdown_pct
    if profile.min_sharpe is not None:
        d["min_sharpe"] = profile.min_sharpe
    return d or None
