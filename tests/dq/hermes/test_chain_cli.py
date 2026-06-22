"""CLI smoke tests for the Atlas → Hermes chain entry point."""

from __future__ import annotations

import warnings
from datetime import date

import pytest

from digiquant.olympus.hermes import chain as chain_mod

pytestmark = pytest.mark.unit


def _parse(*argv: str):
    return chain_mod._build_cli_parser().parse_args(list(argv))


def test_cadence_daily_minimal():
    args = _parse("--cadence", "daily", "--run-date", "2026-04-20")
    assert args.cadence == "daily"
    assert args.run_date == date(2026, 4, 20)
    assert args.refresh_scope == "none"


def test_refresh_scope_explicit():
    args = _parse(
        "--cadence",
        "daily",
        "--run-date",
        "2026-04-20",
        "--refresh-scope",
        "all",
    )
    assert args.refresh_scope == "all"


def test_deprecated_run_type_baseline_maps_refresh_scope_all():
    from digiquant.olympus.atlas.graph import resolve_cli_inputs

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        args = _parse("--run-type", "baseline", "--run-date", "2026-04-20")
        kwargs = resolve_cli_inputs(args)
    assert kwargs["cadence"] == "daily"
    assert kwargs["refresh_scope"] == "all"
    assert any("--run-type" in str(w.message) for w in caught)


def test_deprecated_run_type_delta_defaults_daily_none():
    from digiquant.olympus.atlas.graph import resolve_cli_inputs

    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        args = _parse("--run-type", "delta", "--run-date", "2026-04-20")
        kwargs = resolve_cli_inputs(args)
    assert kwargs["cadence"] == "daily"
    assert kwargs["refresh_scope"] == "none"


def test_deprecated_run_type_monthly_rejected():
    from digiquant.olympus.atlas.graph import resolve_cli_inputs

    args = _parse("--run-type", "monthly", "--run-date", "2026-04-20")
    with pytest.raises(SystemExit):
        resolve_cli_inputs(args)


def test_chain_dry_run_compiles_daily_graph(capsys):
    code = chain_mod.cli_main(
        ["--cadence", "daily", "--run-date", "2026-04-20", "--dry-run", "--watchlist", "none"]
    )
    assert code == 0
    import json

    payload = json.loads(capsys.readouterr().out)
    assert payload["cadence"] == "daily"
    assert payload["compiled"]["atlas"] is True
    assert payload["compiled"]["hermes"] is True
    assert "monthly" not in json.dumps(payload)
