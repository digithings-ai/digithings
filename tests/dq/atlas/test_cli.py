"""Argparse smoke tests for the Atlas CLI.

The GitHub Actions schedulers invoke this CLI; these tests protect the
flag contract. Heavy behavior (graph compilation, Supabase calls) is
covered elsewhere — here we only assert that flags parse + resolve into
the right ``AtlasInput`` kwargs.
"""

from __future__ import annotations

import warnings
from datetime import date

import pytest

from digiquant.olympus.atlas.graph import build_cli_parser, resolve_cli_inputs

pytestmark = pytest.mark.unit


def _parse(*argv: str):
    return build_cli_parser().parse_args(list(argv))


def test_cadence_daily_minimal():
    args = _parse("--cadence", "daily", "--run-date", "2026-04-20")
    kwargs = resolve_cli_inputs(args)
    assert kwargs["cadence"] == "daily"
    assert kwargs["refresh_scope"] == "none"
    assert kwargs["run_date"] == date(2026, 4, 20)
    assert kwargs["baseline_date"] is None
    assert "SPY" in kwargs["watchlist"]


def test_refresh_scope_all():
    args = _parse(
        "--cadence",
        "daily",
        "--run-date",
        "2026-04-20",
        "--refresh-scope",
        "all",
    )
    kwargs = resolve_cli_inputs(args)
    assert kwargs["refresh_scope"] == "all"


def test_explicit_watchlist_overrides_md_fallback():
    args = _parse("--cadence", "daily", "--run-date", "2026-04-20", "--watchlist", "AAPL")
    kwargs = resolve_cli_inputs(args)
    assert kwargs["watchlist"] == ("AAPL",)


def test_watchlist_none_disables_fanout():
    args = _parse("--cadence", "daily", "--run-date", "2026-04-20", "--watchlist", "none")
    kwargs = resolve_cli_inputs(args)
    assert kwargs["watchlist"] == ()


def test_delta_with_explicit_baseline():
    args = _parse(
        "--cadence",
        "daily",
        "--run-date",
        "2026-04-20",
        "--baseline-date",
        "2026-04-18",
        "--watchlist",
        "AAPL,MSFT, TSLA",
    )
    kwargs = resolve_cli_inputs(args)
    assert kwargs["cadence"] == "daily"
    assert kwargs["baseline_date"] == date(2026, 4, 18)
    assert kwargs["watchlist"] == ("AAPL", "MSFT", "TSLA")


def test_deprecated_run_type_baseline_maps_refresh_scope_all():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        args = _parse("--run-type", "baseline", "--run-date", "2026-04-20")
        kwargs = resolve_cli_inputs(args)
    assert kwargs["cadence"] == "daily"
    assert kwargs["refresh_scope"] == "all"
    assert any("--run-type" in str(w.message) for w in caught)


def test_auto_baseline_rejected_without_run_type_delta_shim():
    args = _parse(
        "--cadence",
        "daily",
        "--run-date",
        "2026-04-20",
        "--auto-baseline",
    )
    with pytest.raises(SystemExit):
        resolve_cli_inputs(args)


def test_auto_baseline_dry_run_tolerates_missing_credentials(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    args = _parse(
        "--run-type",
        "delta",
        "--run-date",
        "2026-04-20",
        "--auto-baseline",
        "--dry-run",
    )
    kwargs = resolve_cli_inputs(args)
    assert kwargs["baseline_date"] is None


def test_auto_baseline_live_raises_without_credentials(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    args = _parse(
        "--run-type",
        "delta",
        "--run-date",
        "2026-04-20",
        "--auto-baseline",
    )
    with pytest.raises(SystemExit):
        resolve_cli_inputs(args)


def test_auto_baseline_resolves_from_stub(monkeypatch):
    from digiquant.olympus.atlas import graph as graph_mod

    monkeypatch.setattr(graph_mod, "_auto_resolve_baseline", lambda run_date: date(2026, 4, 15))
    args = _parse(
        "--run-type",
        "delta",
        "--run-date",
        "2026-04-20",
        "--auto-baseline",
    )
    kwargs = resolve_cli_inputs(args)
    assert kwargs["baseline_date"] == date(2026, 4, 15)


def test_auto_resolve_baseline_queries_daily_snapshots(monkeypatch):
    """_auto_resolve_baseline must query daily_snapshots (not documents)."""
    from digiquant.olympus.atlas import graph as graph_mod

    calls = []

    class FakeResp:
        data = [{"date": "2026-04-12"}]

    class FakeQuery:
        def select(self, *a, **kw):
            return self

        def eq(self, col, val):
            calls.append((col, val))
            return self

        def lt(self, *a, **kw):
            return self

        def order(self, *a, **kw):
            return self

        def limit(self, *a, **kw):
            return self

        def execute(self):
            return FakeResp()

    class FakeClient:
        def table(self, name):
            calls.append(("table", name))
            return FakeQuery()

    monkeypatch.setenv("SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "fake-key")

    import digiquant.olympus.atlas.supabase_io as sio

    monkeypatch.setattr(sio, "build_client", lambda cfg: FakeClient())
    monkeypatch.setattr(sio.SupabaseConfig, "from_env", staticmethod(lambda: None))

    result = graph_mod._auto_resolve_baseline(date(2026, 4, 20))

    assert result == date(2026, 4, 12), f"Expected 2026-04-12, got {result}"
    assert ("table", "daily_snapshots") in calls, (
        f"Expected query on daily_snapshots, got tables: {calls}"
    )
    assert ("run_type", "baseline") in calls, f"Expected eq(run_type, baseline), got: {calls}"


def test_cadence_choices_enforced():
    with pytest.raises(SystemExit):
        _parse("--cadence", "weekly", "--run-date", "2026-04-20")


def test_run_date_format_validated():
    with pytest.raises(SystemExit):
        _parse("--cadence", "daily", "--run-date", "20260420")


def test_dry_run_flag_parsed():
    args = _parse("--cadence", "daily", "--run-date", "2026-04-20", "--dry-run")
    assert args.dry_run is True


def test_deprecated_run_type_monthly_rejected():
    args = _parse("--run-type", "monthly", "--run-date", "2026-04-20")
    with pytest.raises(SystemExit):
        resolve_cli_inputs(args)


# ── _make_default_config_loader ──────────────────────────────────────────────


def test_make_default_config_loader_returns_callable():
    from digiquant.olympus.atlas.graph import _make_default_config_loader

    loader = _make_default_config_loader(())
    assert callable(loader)


def test_make_default_config_loader_cli_watchlist_takes_priority():
    from digiquant.olympus.atlas.graph import _make_default_config_loader
    from digiquant.olympus.atlas.state import AtlasConfigBundle

    loader = _make_default_config_loader(("AAPL", "MSFT"))
    result = loader()
    assert isinstance(result, AtlasConfigBundle)
    assert result.watchlist == ["AAPL", "MSFT"]


def test_make_default_config_loader_reads_watchlist_md_when_no_cli():
    from digiquant.olympus.atlas.graph import _make_default_config_loader
    from digiquant.olympus.atlas.state import AtlasConfigBundle

    loader = _make_default_config_loader(())
    result = loader()
    assert isinstance(result, AtlasConfigBundle)
    assert "SPY" in result.watchlist


def test_make_default_config_loader_reads_macro_series():
    from digiquant.olympus.atlas.graph import _make_default_config_loader

    loader = _make_default_config_loader(("SPY",))
    result = loader()
    assert "DGS10" in result.macro_series


def test_parse_watchlist_md_dedupes():
    from digiquant.olympus.atlas.graph import _parse_watchlist_md

    tickers = _parse_watchlist_md()
    assert len(tickers) == len(set(tickers)), "duplicate tickers in watchlist.md parse output"


def test_parse_macro_series_yaml_nonempty():
    from digiquant.olympus.atlas.graph import _parse_macro_series_yaml

    ids = _parse_macro_series_yaml()
    assert len(ids) > 0, "expected at least one macro series from config/macro_series.yaml"


def test_parse_watchlist_md_missing_file(tmp_path, monkeypatch):
    import digiquant.olympus.atlas.graph as gmod

    monkeypatch.setattr(gmod, "_atlas_config_root", lambda: tmp_path)
    from digiquant.olympus.atlas.graph import _parse_watchlist_md

    assert _parse_watchlist_md() == []


def test_parse_macro_series_yaml_missing_file(tmp_path, monkeypatch):
    import digiquant.olympus.atlas.graph as gmod

    monkeypatch.setattr(gmod, "_atlas_config_root", lambda: tmp_path)
    from digiquant.olympus.atlas.graph import _parse_macro_series_yaml

    assert _parse_macro_series_yaml() == []
