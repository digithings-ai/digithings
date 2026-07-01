"""Standalone decision-resolver script (Pillar 3A).

The script is a thin runner over decision_log.resolve_pending: builds a Supabase client,
resolves due rows, reports counts. Loaded from its file path (it lives under scripts/, not
the importable package) and exercised with monkeypatched deps — no live Supabase/LLM.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = (
    Path(__file__).resolve().parents[3] / "digiquant" / "scripts" / "atlas" / "resolve_decisions.py"
)


def _load_script():
    spec = importlib.util.spec_from_file_location("resolve_decisions_script", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


resolve_decisions = _load_script()


def _patch_deps(monkeypatch, *, resolved: int, remaining: int) -> None:
    import digiquant.olympus.atlas.decision_log as dl
    import digiquant.olympus.atlas.supabase_io as sio

    # from_env is a classmethod; patch with staticmethod so it's invoked with no implicit cls.
    monkeypatch.setattr(sio.SupabaseConfig, "from_env", staticmethod(lambda: object()))
    monkeypatch.setattr(sio, "build_client", lambda _cfg: object())
    monkeypatch.setattr(dl, "resolve_pending", lambda **_k: resolved)
    monkeypatch.setattr(sio, "query_pending_decisions", lambda **_k: [{}] * remaining)


def test_resolves_and_reports(monkeypatch, capsys) -> None:
    _patch_deps(monkeypatch, resolved=3, remaining=2)
    rc = resolve_decisions.main(["--run-date", "2026-06-12"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "resolved 3" in out
    assert "2 still due-pending" in out
    assert "2026-06-12" in out


def test_zero_due_is_success(monkeypatch, capsys) -> None:
    _patch_deps(monkeypatch, resolved=0, remaining=0)
    assert resolve_decisions.main(["--run-date", "2026-06-12"]) == 0
    assert "resolved 0" in capsys.readouterr().out


def test_bad_run_date_returns_2(capsys) -> None:
    assert resolve_decisions.main(["--run-date", "not-a-date"]) == 2
    assert "bad --run-date" in capsys.readouterr().err


def test_client_failure_returns_1(monkeypatch, capsys) -> None:
    import digiquant.olympus.atlas.supabase_io as sio

    def _boom():
        raise sio.SupabaseNotConfiguredError("missing SUPABASE_URL")

    monkeypatch.setattr(sio.SupabaseConfig, "from_env", staticmethod(_boom))
    assert resolve_decisions.main([]) == 1  # default run-date = today
    assert "Supabase client unavailable" in capsys.readouterr().err


def test_resolver_crash_returns_1(monkeypatch, capsys) -> None:
    import digiquant.olympus.atlas.decision_log as dl
    import digiquant.olympus.atlas.supabase_io as sio

    monkeypatch.setattr(sio.SupabaseConfig, "from_env", staticmethod(lambda: object()))
    monkeypatch.setattr(sio, "build_client", lambda _cfg: object())

    def _boom(**_k):
        raise RuntimeError("price_history unreachable")

    monkeypatch.setattr(dl, "resolve_pending", _boom)
    assert resolve_decisions.main(["--run-date", "2026-06-12"]) == 1
    assert "resolve_pending failed" in capsys.readouterr().err
