"""Structured outputs for digiquant (Pydantic). All data exchange uses these models."""

from __future__ import annotations

import hashlib
import tomllib
from importlib import metadata as _metadata
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, computed_field

from digiquant.stats import HonestRateBlock

# --- Engine provenance (DIG-945 decision, DIG-3391 build) ---
#
# Every published BacktestResult carries the build that produced it: the
# resolved nautilus_trader version plus the lock it was resolved from. The
# stamp is populated once, in run_backtest, from the live process — never
# copied from another run, never asserted in CI, never hand-written.

#: Distribution name as known to importlib.metadata (hyphenated, not the
#: underscore import name).
NAUTILUS_DIST_NAME = "nautilus-trader"

#: Optional-dependency extra in digiquant/pyproject.toml that owns the pin.
NAUTILUS_EXTRA_NAME = "nautilus"

#: Marker appended to ``missing`` when the engine could not be resolved.
ENGINE_PROVENANCE_MISSING = "engine_provenance"

#: Placeholder used when a stamp input cannot be read (missing manifest or
#: lockfile). It names the gap explicitly rather than fabricating a value.
UNKNOWN_STAMP = "unknown"


def _digiquant_pyproject_path() -> Path | None:
    """Locate digiquant's own pyproject.toml by walking up from this file.

    The manifest is identified by its project name, not by depth: in an
    installed layout the walk may meet another pyproject first, and that
    zero is not this pin.
    """
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "pyproject.toml"
        if not candidate.is_file():
            continue
        try:
            with open(candidate, "rb") as handle:
                manifest = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError):
            continue
        project = manifest.get("project")
        if isinstance(project, dict) and project.get("name") == "digiquant":
            return candidate
    return None


def read_nautilus_pin(pyproject_path: Path | str | None = None) -> str:
    """Specifier text of nautilus_trader from the nautilus extra, read off the manifest.

    Never retype the pin: the returned string is the entry as written in
    digiquant/pyproject.toml (currently ``nautilus_trader==1.230.0``,
    ADR-0033). ``"unknown"`` when the manifest or the entry cannot be read.
    """
    path = Path(pyproject_path) if pyproject_path is not None else _digiquant_pyproject_path()
    if path is not None:
        try:
            with open(path, "rb") as handle:
                manifest = tomllib.load(handle)
            project = manifest.get("project") or {}
            extras = project.get("optional-dependencies") or {}
            entries = extras.get(NAUTILUS_EXTRA_NAME) or []
            for entry in entries:
                text = str(entry).strip()
                if text.startswith("nautilus_trader"):
                    return text
        except (OSError, tomllib.TOMLDecodeError, AttributeError):
            pass
    return UNKNOWN_STAMP


def read_root_lock_digest(pyproject_path: Path | str | None = None) -> tuple[str, str]:
    """``(file, sha256_12)`` of the repo-root uv.lock — the one lock (ADR-0033).

    The digest is taken over the lockfile bytes at generation time. ``"unknown"``
    when the lockfile cannot be read.
    """
    path = Path(pyproject_path) if pyproject_path is not None else _digiquant_pyproject_path()
    if path is not None:
        lock = path.parent.parent / "uv.lock"
        try:
            return ("uv.lock", hashlib.sha256(lock.read_bytes()).hexdigest()[:12])
        except OSError:
            pass
    return ("uv.lock", UNKNOWN_STAMP)


def resolved_nautilus_version() -> str | None:
    """Installed nautilus-trader version in this process, or None when absent.

    ``None`` covers the Workers MCP image, which ships no nautilus extra —
    and any install whose metadata is missing. Callers treat it as fail-closed.
    """
    try:
        return _metadata.version(NAUTILUS_DIST_NAME)
    except _metadata.PackageNotFoundError:
        return None


def _pin_matches_resolved(pin: str, resolved: str) -> bool:
    """True only when an exact ``==`` pin names exactly the resolved version.

    The pin is exact by ADR-0033, so only ``==`` can match; an unreadable pin
    (``"unknown"``) never matches.
    """
    text = pin.strip()
    if not text.startswith("nautilus_trader"):
        return False
    rest = text[len("nautilus_trader") :].strip()
    if rest.startswith("=="):
        return rest[2:].strip() == resolved.strip() and bool(resolved.strip())
    return False


class EngineProvenanceLock(BaseModel):
    """Identity of the lock the engine was resolved from."""

    file: str = Field(..., description="Lockfile name (the one root uv.lock, ADR-0033)")
    sha256_12: str = Field(
        ..., description="First 12 hex of the lockfile bytes at generation time"
    )


class EngineProvenance(BaseModel):
    """The build inside the artifact (DIG-945 contract, owned next to the model)."""

    engine: Literal["nautilus_trader"] = Field(
        "nautilus_trader", description="Execution engine (constant)"
    )
    resolved_version: str | None = Field(
        None,
        description="importlib.metadata version in the producing process; "
        "None when the extra is absent (fail-closed)",
    )
    pin: str = Field(
        ...,
        description="Specifier text from the nautilus extra in digiquant/pyproject.toml "
        "(read off the manifest, never retyped)",
    )
    lock: EngineProvenanceLock = Field(..., description="Root uv.lock identity at generation time")
    arithmetic: Literal["balance_path"] = Field(
        "balance_path",
        description="Sharpe, drawdown and total return derive from one balance path "
        "(DIG-462/DIG-427)",
    )
    returns_series_verified: bool = Field(
        ...,
        description="The _verified_returns_series outcome for this run",
    )


def build_engine_provenance(*, returns_series_verified: bool) -> EngineProvenance:
    """Assemble the block from the live process. The only constructor."""
    pin = read_nautilus_pin()
    lock_file, lock_sha = read_root_lock_digest()
    return EngineProvenance(
        resolved_version=resolved_nautilus_version(),
        pin=pin,
        lock=EngineProvenanceLock(file=lock_file, sha256_12=lock_sha),
        returns_series_verified=returns_series_verified,
    )


def engine_provenance_note(provenance: EngineProvenance | None) -> str:
    """The one rendering of the block. Every tearsheet appends this line as-is.

    A second hand-formatted version line is a second answer to the same question
    and will drift; there is exactly one builder.
    """
    if provenance is None:
        return "Engine provenance: unavailable — not citable."
    base = (
        f"Engine {provenance.engine} "
        f"(arithmetic {provenance.arithmetic}; "
        f"pin {provenance.pin}; lock {provenance.lock.file} {provenance.lock.sha256_12})"
    )
    if provenance.resolved_version is None:
        return f"{base}; engine unresolved — not citable."
    if not _pin_matches_resolved(provenance.pin, provenance.resolved_version):
        return (
            f"{base}; resolved {provenance.resolved_version} != pin — "
            "engine drifted from the pinned build."
        )
    verified = (
        "returns series verified"
        if provenance.returns_series_verified
        else "returns series not verified on this path"
    )
    return f"{base}; resolved {provenance.resolved_version} == pin; {verified}."


def apply_engine_provenance(
    result: BacktestResult, provenance: EngineProvenance
) -> BacktestResult:
    """Attach the block, fail-closed when the engine is unresolved.

    ``resolved_version=None`` withholds citability: ``engine_provenance`` joins
    ``missing`` and the status drops to ``partial`` (an ``error`` stays an
    error). A resolved engine — matching the pin or drifted — leaves status
    and missing untouched: drift is visible on the artifact, not a refusal.
    Returns a copy; the input is unchanged.
    """
    missing = list(result.missing)
    status = result.status
    if provenance.resolved_version is None and ENGINE_PROVENANCE_MISSING not in missing:
        missing.append(ENGINE_PROVENANCE_MISSING)
    if ENGINE_PROVENANCE_MISSING in missing and status == "ok":
        status = "partial"
    return result.model_copy(
        update={"engine_provenance": provenance, "missing": missing, "status": status}
    )


class BacktestResult(BaseModel):
    """Result of a single backtest run. Used by digigraph and MCP."""

    run_id: str = Field(..., description="Unique run identifier")
    strategy_name: str = Field(..., description="Strategy or idea label")
    symbols: list[str] = Field(default_factory=list, description="Instruments used")
    start_time: str = Field(..., description="Backtest start (ISO)")
    end_time: str = Field(..., description="Backtest end (ISO)")
    total_pnl: float = Field(0.0, description="Total PnL (account currency)")
    total_return_pct: float = Field(0.0, description="Total return %")
    sharpe_ratio: float | None = Field(None, description="Sharpe ratio if computable")
    max_drawdown_pct: float | None = Field(
        None,
        description="Max drawdown as negative percent, e.g. -15 for -15%",
    )
    num_trades: int = Field(
        0,
        description="Fill count: rows in generate_order_fills_report(). NOT a trade count "
        "and NOT a win-rate denominator — use honest_rate.n.",
    )
    per_symbol_pnl: dict[str, float] = Field(
        default_factory=dict,
        description="Per-symbol PnL breakdown for multi-symbol backtests",
    )
    missing: list[str] = Field(
        default_factory=list,
        description=(
            "Names that could not be produced, the machine-readable form of the "
            "'missing metrics' clause in message. Empty when status is ok."
        ),
    )
    honest_rate: HonestRateBlock | None = Field(
        None,
        description="Win rate with its denominator and interval. None when no realized-PnL "
        "series was extracted — never a fabricated zero and never num_trades.",
    )
    honest_rate_by_symbol: dict[str, HonestRateBlock] = Field(
        default_factory=dict,
        description="Per-symbol honest_rate blocks for multi-symbol backtests",
    )
    engine_provenance: EngineProvenance | None = Field(
        None,
        description="Build that produced this result (DIG-945): resolved engine "
        "version + pin + lock. None only for results built before the stamp "
        "existed — never a fabricated block. None engine (extra absent) is "
        "fail-closed via missing/status, see apply_engine_provenance.",
    )
    status: str = Field("ok", description="ok | partial | error")
    message: str = Field("", description="Optional message or error")

    @computed_field
    @property
    def success(self) -> bool:
        """A completed backtest. ``partial`` (valid PnL, missing optional metric) is still success."""
        return self.status != "error"


class OptimizationConstraints(BaseModel):
    """Hard limits for optimization; candidates violating these are rejected."""

    min_trades: int | None = Field(None, description="Minimum number of trades required")
    max_drawdown_pct: float | None = Field(
        None,
        description="Max drawdown as negative percent, e.g. -15 for -15%",
    )
    min_sharpe: float | None = Field(None, description="Minimum Sharpe ratio")
    min_return_pct: float | None = Field(None, description="Minimum total return %")
    max_trades_per_year: float | None = Field(None, description="Cap trade frequency")
    min_trades_per_year: float | None = Field(None, description="Ensure minimum activity")


class OptimizeResult(BaseModel):
    """Result of parameter optimization. Phase 2: grid over backtest runs."""

    run_id: str = Field(..., description="Optimization run identifier")
    strategy_name: str = Field(..., description="Strategy label")
    symbols: list[str] = Field(default_factory=list, description="Instruments")
    best_params: dict[str, float | int | str] = Field(
        default_factory=dict, description="Best parameter set"
    )
    best_backtest: BacktestResult | None = Field(
        None, description="Backtest result for best params"
    )
    num_evaluations: int = Field(0, description="Number of param sets evaluated")
    status: str = Field("ok", description="ok | partial | error")
    message: str = Field("", description="Optional message")


class ExportResult(BaseModel):
    """Result of strategy export to a target platform."""

    run_id: str = Field(..., description="Export run identifier")
    target: str = Field(..., description="nautilus | tradingview | alpaca | quantconnect")
    strategy_name: str = Field(..., description="Strategy label")
    artifact_path: str | None = Field(None, description="Path to exported artifact if written")
    status: str = Field("ok", description="ok | partial | error")
    message: str = Field("", description="Optional message")


class BarsBar(BaseModel):
    """One OHLCV bar for dashboard charts (display only — never a backtest input)."""

    timestamp: str = Field(..., description="Bar timestamp (ISO date or datetime from upstream)")
    open: float | None = Field(None, description="Opening price")
    high: float | None = Field(None, description="High price")
    low: float | None = Field(None, description="Low price")
    close: float = Field(..., description="Closing price")
    volume: float | None = Field(None, description="Volume (if reported upstream)")


class BarsResponse(BaseModel):
    """Keyless OHLCV bars for dashboard charts (GET /bars).

    Display-only read over the anonymous Gloomberb price-history path:
    free-tier data may be delayed (see ``delay_note``) and must never feed
    the validate → backtest → optimize → export pipeline. Carries no Sharpe,
    PnL, or drawdown — no performance claims originate here.
    """

    symbol: str = Field(..., description="Requested symbol (as normalized upstream)")
    timeframe: str = Field(..., description="Requested timeframe (Gloomberb resolution)")
    limit: int = Field(..., description="Requested max bars")
    count: int = Field(..., description="Bars actually returned (<= limit)")
    bars: list[BarsBar] = Field(default_factory=list, description="Newest-last OHLCV bars")
    source: str = Field("gloomberb", description="Upstream family (Sourced from Gloomberb)")
    stale: bool = Field(False, description="Upstream cache-stale signal")
    delay_note: str | None = Field(
        None, description="Free-tier delay notice (up to 15 minutes on equities)"
    )
