"""House CLI close-out sends K5 digests; overlay nested chain does not."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from digiquant.portfolio import chain as chain_mod

pytestmark = pytest.mark.unit

_CHAIN_SRC = Path(chain_mod.__file__).read_text(encoding="utf-8")


def test_helper_passes_force_digest_and_run_date() -> None:
    seen: dict[str, object] = {}

    def _fake(*, run_date: date, force_digest: bool) -> None:
        seen["run_date"] = run_date
        seen["force_digest"] = force_digest

    chain_mod.dispatch_house_notifications_after_chain(date(2026, 8, 31), dispatch=_fake)
    assert seen == {"run_date": date(2026, 8, 31), "force_digest": True}


def test_helper_swallows_dispatch_errors() -> None:
    def _boom(**_kwargs: object) -> None:
        raise RuntimeError("mailgun down")

    chain_mod.dispatch_house_notifications_after_chain(date(2026, 8, 31), dispatch=_boom)


def test_dry_run_does_not_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[int] = []
    monkeypatch.setattr(
        chain_mod,
        "dispatch_house_notifications_after_chain",
        lambda *_a, **_k: called.append(1),
    )
    code = chain_mod.cli_main(
        ["--cadence", "daily", "--run-date", "2026-04-20", "--dry-run", "--watchlist", "none"]
    )
    assert code == 0
    assert called == []


def test_run_research_then_portfolio_source_does_not_dispatch() -> None:
    """Overlay graph_invoke calls this library API; house mail must not ride along."""
    start = _CHAIN_SRC.index("def run_research_then_portfolio")
    end = _CHAIN_SRC.index("def dispatch_house_notifications_after_chain")
    assert "dispatch_house_notifications_after_chain" not in _CHAIN_SRC[start:end]
    assert "dispatch_notifications" not in _CHAIN_SRC[start:end]


def test_cli_main_dispatches_only_when_not_retry_worthy() -> None:
    cli = _CHAIN_SRC[_CHAIN_SRC.index("def cli_main") :]
    assert "if not retry_worthy:" in cli
    assert "dispatch_house_notifications_after_chain(research_input.run_date)" in cli
    dry = cli[cli.index("if args.dry_run:") : cli.index("from digiquant.research.supabase_io")]
    assert "dispatch_house_notifications_after_chain" not in dry
