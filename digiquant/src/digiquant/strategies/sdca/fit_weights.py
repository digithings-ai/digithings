"""Stage A weight fit for an ``SdcaAssetProfile`` — MCP/platform helper.

Cycle-window overlap search cannot honestly live inside ``run_optimize``:
that path is Stage B walk-forward (vs-flat-DCA, IS rails, curve shape).
This module loads cached OHLCV, builds valuation-z + extras for the
profile, runs ``optimize_stage_a_weights``, and regularizes the winner.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from digiquant.data.prices.history_cache import DEFAULT_CACHE_DIR, load_cached
from digiquant.strategies.sdca.asset_profile import (
    SdcaAssetProfile,
    daily_closes_from_cache,
    daily_closes_from_ohlcv,
    stage_a_search_names,
    technicals_from_ohlcv,
)
from digiquant.strategies.sdca.indicator_catalog import (
    ExtraIndicatorSources,
    SdcaCompositeWeights,
    extra_z_vectors,
    sources_from_optional_paths,
)
from digiquant.strategies.sdca.providers import resolve_sdca_risk_model
from digiquant.strategies.sdca.regularize import regularize_weights
from digiquant.strategies.sdca.stage_a import CycleOverlapScore, optimize_stage_a_weights
from digiquant.strategies.sdca.two_stage import freeze_weight_params
from digiquant.strategies.sdca.valuation import valuation_confluence_z

KNOWN_SDCA_PROFILES: tuple[str, ...] = ("btc_v1", "eth_research_v1")


class SdcaWeightFitResult(BaseModel):
    """JSON-serializable Stage A (+ regularize) summary for MCP."""

    model_config = ConfigDict(frozen=True, strict=True)

    profile: str
    symbol: str
    risk_model: str
    weights: dict[str, float]
    regularized_weights: dict[str, float]
    weight_params: dict[str, float]
    regularized_weight_params: dict[str, float]
    score: CycleOverlapScore
    num_evaluations: int = Field(ge=0)
    path: str | None = None


def resolve_sdca_profile(
    name: str = "btc_v1",
    *,
    profile_json: str | None = None,
) -> SdcaAssetProfile:
    """Named factory or a full ``SdcaAssetProfile`` JSON payload."""
    text = (profile_json or "").strip()
    if text:
        return SdcaAssetProfile.model_validate_json(text)
    if name == "btc_v1":
        return SdcaAssetProfile.btc_v1()
    if name == "eth_research_v1":
        return SdcaAssetProfile.eth_research_v1()
    raise ValueError(f"unknown sdca profile {name!r}")


def fit_sdca_weights_from_cache(
    profile: SdcaAssetProfile,
    *,
    cache_dir: Path | str | None = None,
    coefficients_path: Path | str | None = None,
    m2_path: Path | str | None = None,
    dxy_path: Path | str | None = None,
    eth_ticker: str = "ETH-USD",
    valuation_form: str = "log_quadratic",
    rolling_window: int = 90,
    output_path: Path | str | None = None,
    profile_name: str = "custom",
) -> SdcaWeightFitResult:
    """Stage A on cached OHLCV for ``profile``. Regularize the winning weights."""
    cdir = Path(cache_dir) if cache_dir is not None else DEFAULT_CACHE_DIR
    dates, close = daily_closes_from_cache(profile.symbol, cdir)
    coeff = Path(coefficients_path) if coefficients_path else None
    model = resolve_sdca_risk_model(
        profile.risk_model,
        dates=dates,
        price=close,
        coefficients_path=coeff,
        form=valuation_form,
        rolling_window=rolling_window,
    )
    rails = model.rails(dates)
    valuation_z = valuation_confluence_z(
        dates,
        close,
        rails["low"],
        rails["median"],
        rails["high"],
        trend_window=profile.oscillators.valuation_trend_window,
    ).to_list()
    search_names = stage_a_search_names(profile)
    extra_z = technicals_from_ohlcv(dates, close, oscillators=profile.oscillators)
    plugin = profile.plugin_extras()
    if plugin:
        eth_dates = eth_close = None
        if "rs_eth" in plugin:
            eth_df = load_cached(eth_ticker, cdir)
            if eth_df is not None and not eth_df.is_empty():
                eth_dates, eth_close = daily_closes_from_ohlcv(eth_df)
        sources: ExtraIndicatorSources = sources_from_optional_paths(
            m2_path=m2_path,
            dxy_path=dxy_path,
            eth_dates=eth_dates,
            eth_close=eth_close,
        )
        enabled = {name: 1.0 for name in plugin}
        try:
            plugin_weights = SdcaCompositeWeights(valuation=1.0, **enabled)
            extra_z.update(
                extra_z_vectors(
                    dates,
                    close,
                    plugin_weights,
                    sources,
                    oscillators=profile.oscillators,
                    allowlist=profile.extra_indicators,
                )
            )
        except ValueError:
            # Missing macro files: Stage A still runs on generic technicals.
            pass
    stage = optimize_stage_a_weights(
        dates.to_list(),
        valuation_z=valuation_z,
        extra_z=extra_z,
        windows=profile.cycle_windows,
        search_names=search_names,
    )
    regularized = regularize_weights(stage.weights)
    result = SdcaWeightFitResult(
        profile=profile_name,
        symbol=profile.symbol,
        risk_model=profile.risk_model,
        weights=stage.weights.model_dump(),
        regularized_weights=regularized.model_dump(),
        weight_params=freeze_weight_params(stage.weights),
        regularized_weight_params=freeze_weight_params(regularized),
        score=stage.score,
        num_evaluations=stage.num_evaluations,
        path=None,
    )
    if output_path is not None:
        dest = Path(output_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(result.model_dump_json(indent=2) + "\n")
        result = result.model_copy(update={"path": str(dest)})
    return result


__all__ = [
    "KNOWN_SDCA_PROFILES",
    "SdcaWeightFitResult",
    "fit_sdca_weights_from_cache",
    "resolve_sdca_profile",
]
