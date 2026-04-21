"""Argparse smoke tests for the Atlas CLI.

The GitHub Actions schedulers invoke this CLI; these tests protect the
flag contract. Heavy behavior (graph compilation, Supabase calls) is
covered elsewhere — here we only assert that flags parse + resolve into
the right ``AtlasInput`` kwargs.
"""

from __future__ import annotations

from datetime import date

import pytest

from digiquant_atlas.graph import build_cli_parser, resolve_cli_inputs

pytestmark = pytest.mark.unit


def _parse(*argv: str):
    return build_cli_parser().parse_args(list(argv))


def test_baseline_minimal():
    args = _parse("--run-type", "baseline", "--run-date", "2026-04-20")
    kwargs = resolve_cli_inputs(args)
    assert kwargs["run_type"] == "baseline"
    assert kwargs["run_date"] == date(2026, 4, 20)
    assert kwargs["baseline_date"] is None
    assert kwargs["watchlist"] == ()


def test_delta_with_explicit_baseline():
    args = _parse(
        "--run-type",
        "delta",
        "--run-date",
        "2026-04-20",
        "--baseline-date",
        "2026-04-18",
        "--watchlist",
        "AAPL,MSFT, TSLA",
    )
    kwargs = resolve_cli_inputs(args)
    assert kwargs["run_type"] == "delta"
    assert kwargs["baseline_date"] == date(2026, 4, 18)
    assert kwargs["watchlist"] == ("AAPL", "MSFT", "TSLA")


def test_auto_baseline_rejected_on_baseline_run():
    args = _parse(
        "--run-type",
        "baseline",
        "--run-date",
        "2026-04-20",
        "--auto-baseline",
    )
    with pytest.raises(SystemExit):
        resolve_cli_inputs(args)


def test_auto_baseline_dry_run_tolerates_missing_credentials(monkeypatch):
    # No Supabase env → _auto_resolve_baseline returns None; because
    # dry_run=True we expect a tolerant result (baseline_date stays None).
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
    from digiquant_atlas import graph as graph_mod

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


def test_run_type_choices_enforced():
    with pytest.raises(SystemExit):
        _parse("--run-type", "bogus", "--run-date", "2026-04-20")


def test_run_date_format_validated():
    with pytest.raises(SystemExit):
        _parse("--run-type", "baseline", "--run-date", "20260420")


def test_dry_run_flag_parsed():
    args = _parse("--run-type", "monthly", "--run-date", "2026-04-20", "--dry-run")
    assert args.dry_run is True
