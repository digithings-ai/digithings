"""Migration 058 — ``portfolio_metrics`` volatility / max_drawdown percent scale (#1748).

Two halves of one defect, so one test module:

1. **The writer.** ``update_tearsheet.py`` emitted *fractions* while
   ``portfolio_materialize.py`` (phase 9d) and ``refresh_performance_metrics.py`` emitted
   *percent* into the same two columns. Unifying the CHECK constraints without unifying the
   writers would only legitimise a mixed-unit column.
2. **The constraints.** ``002_schema_hardening.sql:153,160`` bounded the columns as
   fractions (``volatility <= 10``, ``max_drawdown >= -1``), which the two percent writers
   cannot satisfy: the first computed running drawdown (~-1.31%) raises PostgREST
   ``APIError 23514`` and, because running max drawdown is monotonically non-increasing,
   keeps raising forever.

Hermetic in the ``test_migration_050/051/056.py`` mold — pure SQL text parsing plus a
dependency-free arithmetic helper. No Postgres, no network. (A functional replay against
``postgres:16-alpine`` is recorded in the PR; CI's unit lanes have no database.)
"""

from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest

# Explicit, because tests/dq/research/test_migration_051.py omits it and has therefore never
# run in test-research-graph.yml (`pytest -m unit tests/dq/research/`). Do not drop this line.
pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_PATH = (
    REPO_ROOT / "digiquant" / "supabase" / "migrations" / "058_portfolio_metrics_percent_scale.sql"
)
ATLAS_SCRIPTS = REPO_ROOT / "digiquant" / "scripts" / "atlas"

# A 21-point NAV series (>= _MIN_NAV_HISTORY_ROWS) shaped like the live one: base 100, a
# mild run-up, a ~1.3% peak-to-trough dip, a partial recovery.
NAVS_LIVE_SHAPE = [
    100.0, 100.42, 100.91, 100.55, 101.13, 101.68, 101.22, 101.85, 102.31, 102.04, 102.63,
    103.10, 102.55, 101.95, 101.75, 102.20, 102.74, 103.31, 103.02, 103.60, 104.15,
]  # fmt: skip

# ~1.2% daily swings: an ordinary equity-portfolio volatility regime.
NAVS_ORDINARY_VOL = [
    100.0, 101.2, 99.9, 101.4, 100.1, 98.8, 100.2, 101.6, 100.3, 99.1, 100.5, 101.9,
    100.6, 99.4, 100.8, 102.2, 100.9, 99.7, 101.1, 102.5, 101.2,
]  # fmt: skip

# What the pre-058 implementation emitted for NAVS_LIVE_SHAPE, measured against
# pandas/numpy (`navs.pct_change().dropna().std() * np.sqrt(252)` with pandas' default
# ddof=1, and `((navs - navs.cummax()) / navs.cummax()).min()`). These pin both the
# 100x scale change and the fact that the sample-stddev estimator did not change.
PRE_058_FRACTION_VOLATILITY = 0.0716373550291552
PRE_058_FRACTION_MAX_DRAWDOWN = -0.013094083414160955
PRE_058_SHARPE = 7.193171873128361


@pytest.fixture(scope="module")
def sql() -> str:
    assert MIGRATION_PATH.is_file(), f"migration missing: {MIGRATION_PATH}"
    return MIGRATION_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def statements(sql: str) -> str:
    """The migration with comment lines stripped, so assertions bind to executable SQL."""
    return "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))


@pytest.fixture(scope="module")
def tearsheet() -> ModuleType:
    """``digiquant/scripts/research/update_tearsheet.py``, imported the way test_etl.py does."""
    if str(ATLAS_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(ATLAS_SCRIPTS))
    return importlib.import_module("update_tearsheet")


def _bound(statements: str, constraint: str, comparison: str) -> float:
    """Pull a numeric bound out of the migration's own ADD CONSTRAINT statement."""
    add = re.search(rf"ADD CONSTRAINT {constraint}\s*\n?\s*CHECK \((.+?)\);", statements, re.S)
    assert add, f"no ADD CONSTRAINT {constraint} in the migration"
    found = re.search(rf"{re.escape(comparison)}\s*(-?[\d.]+)", add.group(1))
    assert found, f"no `{comparison} <number>` in {constraint}: {add.group(1)!r}"
    return float(found.group(1))


class TestPercentScaleConstraints:
    def test_replaces_both_fraction_scale_checks_by_name(self, statements: str) -> None:
        for constraint in ("chk_metrics_vol_range", "chk_metrics_dd_range"):
            assert f"DROP CONSTRAINT IF EXISTS {constraint}" in statements
            assert f"ADD CONSTRAINT {constraint}" in statements

    def test_widens_volatility_to_percent(self, statements: str) -> None:
        assert _bound(statements, "chk_metrics_vol_range", "volatility >=") == 0
        assert _bound(statements, "chk_metrics_vol_range", "volatility <=") == 1000

    def test_widens_drawdown_to_percent(self, statements: str) -> None:
        assert _bound(statements, "chk_metrics_dd_range", "max_drawdown >=") == -100
        assert _bound(statements, "chk_metrics_dd_range", "max_drawdown <=") == 0

    def test_keeps_the_null_tolerance(self, statements: str) -> None:
        """metrics rows exist for every calendar day; risk fields are NULL until
        nav_history reaches 20 rows, so the columns must stay nullable."""
        assert statements.count("volatility IS NULL OR") == 1
        assert statements.count("max_drawdown IS NULL OR") == 1

    def test_drops_then_rescales_then_adds(self, statements: str) -> None:
        """Order is load-bearing: rescaling 0.15 -> 15 while the old `volatility <= 10`
        bound is still installed aborts the migration."""
        drop = statements.index("DROP CONSTRAINT IF EXISTS chk_metrics_vol_range")
        rescale = statements.index("SET volatility = volatility * 100")
        add = statements.index("ADD CONSTRAINT chk_metrics_vol_range")
        assert drop < rescale < add

    def test_rescale_is_scoped_to_the_fraction_writer(self, statements: str) -> None:
        rescale = statements[statements.index("UPDATE public.portfolio_metrics") :]
        rescale = rescale[: rescale.index(";")]
        assert "SET volatility = volatility * 100" in rescale
        assert "max_drawdown = max_drawdown * 100" in rescale
        assert "computed_from = 'tearsheet'" in rescale
        # Magnitude bounds keep an already-percent row (phase 9d inherits the
        # computed_from DEFAULT) out of the rescale.
        assert "coalesce(volatility, 0) <= 10" in rescale
        assert "coalesce(max_drawdown, 0) >= -1" in rescale

    def test_rescale_is_replay_guarded_and_reports_its_rowcount(self, statements: str) -> None:
        """Applying 058 out-of-band records supabase_migrations, not
        olympus_schema_migrations, so db-migrate.yml:68-69 would replay the checked-in
        copy. A second multiplication by 100 must not happen."""
        guard = statements[: statements.index("UPDATE public.portfolio_metrics")]
        assert "col_description" in guard
        assert "ILIKE '%percent%'" in guard
        assert "GET DIAGNOSTICS" in statements
        assert "RAISE NOTICE" in statements

    def test_records_the_percent_contract_on_both_columns(self, statements: str) -> None:
        """The comments are the replay guard's marker as well as the documentation, so
        they must mention percent and must be set after the rescale."""
        for column in ("volatility", "max_drawdown"):
            comment = re.search(
                rf"COMMENT ON COLUMN public\.portfolio_metrics\.{column} IS(.+?);",
                statements,
                re.S,
            )
            assert comment, f"no COMMENT ON COLUMN for {column}"
            assert "percent" in comment.group(1)
            assert statements.index("UPDATE public.portfolio_metrics") < comment.start()

    def test_has_no_top_level_transaction_block(self, sql: str) -> None:
        """db-migrate.yml:79 greps for a bare begin-statement to decide whether a
        migration wraps itself. Matching sends the file down the self-wrapping branch,
        where the olympus_schema_migrations INSERT runs in its OWN transaction — the DDL
        could commit without the version being recorded. Staying unmatched keeps both in
        one `psql --single-transaction`. Comments count: the grep reads the whole file.
        """
        assert not re.search(r"(^|\s)begin\s*;", sql, re.I | re.M)
        assert "COMMIT;" not in sql.upper()


class TestWriterEmitsPercent:
    """``update_tearsheet.py`` is the writer that disagreed with the other two."""

    def test_volatility_is_percent(self, tearsheet: ModuleType) -> None:
        metrics = tearsheet.compute_nav_risk_metrics(NAVS_LIVE_SHAPE)
        assert metrics.volatility_pct == pytest.approx(PRE_058_FRACTION_VOLATILITY * 100, abs=1e-6)

    def test_max_drawdown_is_percent_and_non_positive(self, tearsheet: ModuleType) -> None:
        metrics = tearsheet.compute_nav_risk_metrics(NAVS_LIVE_SHAPE)
        assert metrics.max_drawdown_pct == pytest.approx(
            PRE_058_FRACTION_MAX_DRAWDOWN * 100, abs=1e-6
        )
        assert metrics.max_drawdown_pct <= 0

    def test_sharpe_is_unchanged_by_the_percent_unification(self, tearsheet: ModuleType) -> None:
        """Sharpe divides an annualized mean return by the *fraction*-scale volatility.
        Dividing by the percent value instead would shrink every published Sharpe 100x."""
        metrics = tearsheet.compute_nav_risk_metrics(NAVS_LIVE_SHAPE)
        assert metrics.sharpe == pytest.approx(PRE_058_SHARPE, abs=1e-6)

    def test_uses_the_sample_stddev_estimator(self, tearsheet: ModuleType) -> None:
        """The replaced code used pandas' ``Series.std()``, i.e. ddof=1. The population
        estimator would divide by n instead of n-1 and change every volatility number in
        addition to rescaling it: 20 returns, so sqrt(20/19) = 1.0260 too small."""
        metrics = tearsheet.compute_nav_risk_metrics(NAVS_LIVE_SHAPE)
        population_scale = (20 / 19) ** 0.5
        assert metrics.volatility_pct == pytest.approx(7.163736, abs=1e-6)
        assert metrics.volatility_pct / population_scale == pytest.approx(6.982, abs=1e-3)

    def test_degenerate_series_return_zeros_rather_than_raising(
        self, tearsheet: ModuleType
    ) -> None:
        """A recovery script must not abort on a malformed digest: a zero NAV made the
        replaced pandas expression emit inf/nan, and naive plain-math division would
        raise ZeroDivisionError."""
        for navs in ([], [100.0], [0.0, 0.0], [0.0, 100.0, 0.0]):
            metrics = tearsheet.compute_nav_risk_metrics(navs)
            assert metrics.sharpe == 0.0
            assert metrics.volatility_pct >= 0.0
            assert metrics.max_drawdown_pct <= 0.0


class TestWriterAgreesWithTheConstraints:
    """The point of the package: what the writer emits must be storable, and the reason
    it was not is the scale, not the bounds."""

    @pytest.mark.parametrize("navs", [NAVS_LIVE_SHAPE, NAVS_ORDINARY_VOL])
    def test_percent_output_satisfies_the_058_bounds(
        self, tearsheet: ModuleType, statements: str, navs: list[float]
    ) -> None:
        metrics = tearsheet.compute_nav_risk_metrics(navs)
        assert (
            _bound(statements, "chk_metrics_vol_range", "volatility >=")
            <= metrics.volatility_pct
            <= _bound(statements, "chk_metrics_vol_range", "volatility <=")
        )
        assert (
            _bound(statements, "chk_metrics_dd_range", "max_drawdown >=")
            <= metrics.max_drawdown_pct
            <= _bound(statements, "chk_metrics_dd_range", "max_drawdown <=")
        )

    def test_percent_output_would_violate_the_pre_058_bounds(self, tearsheet: ModuleType) -> None:
        """This is the #1748 fuse. 002_schema_hardening.sql:153,160 bounded the columns
        as fractions; the first realistic percent-scale drawdown breaks the drawdown
        bound and an ordinary volatility regime breaks the volatility bound, which is
        APIError 23514 on every subsequent metrics write."""
        live = tearsheet.compute_nav_risk_metrics(NAVS_LIVE_SHAPE)
        assert live.max_drawdown_pct < -1, "pre-058 CHECK required max_drawdown >= -1"

        ordinary = tearsheet.compute_nav_risk_metrics(NAVS_ORDINARY_VOL)
        assert ordinary.volatility_pct > 10, "pre-058 CHECK required volatility <= 10"
        assert ordinary.max_drawdown_pct < -1
