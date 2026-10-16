"""Unit tests for scripts/readiness.py — pure functions with faked payloads, no network."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "readiness.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("readiness", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mod() -> Any:
    return _load()


def _issue(n: int, labels: list[str], updated: str = "2026-09-01T00:00:00Z") -> dict:
    return {
        "number": n,
        "title": f"issue {n}",
        "labels": [{"name": name} for name in labels],
        "updatedAt": updated,
    }


@pytest.mark.unit
def test_band_of_maps_to_three_bands(mod: Any) -> None:
    assert mod.band_of(True, False) == "healthy"
    assert mod.band_of(False, True) == "watch"
    assert mod.band_of(False, False) == "sick"


@pytest.mark.unit
def test_backlog_clean_board_is_healthy(mod: Any) -> None:
    issues = [_issue(1, ["priority:high", "component:digiquant"])]
    value, band, _ = mod.m_backlog(issues)
    assert band == "healthy"
    assert "1 open" in value


@pytest.mark.unit
def test_backlog_flags_missing_and_stale(mod: Any) -> None:
    issues = [
        _issue(1, ["priority:high"]),  # missing component
        _issue(2, ["component:root"], updated="2025-01-01T00:00:00Z"),  # missing priority + stale
    ]
    value, band, detail = mod.m_backlog(issues)
    assert band == "watch"
    assert "2 open" in value
    assert "1" in detail and "2" in detail


@pytest.mark.unit
def test_backlog_sick_on_many_missing(mod: Any) -> None:
    issues = [_issue(n, ["bug"]) for n in range(10)]
    _, band, _ = mod.m_backlog(issues)
    assert band == "sick"


@pytest.mark.unit
def test_labels_detects_drift(mod: Any) -> None:
    value, band, detail = mod.m_labels(["agent-task", "component:root", "exec:cursor"])
    assert band == "sick"
    assert "exec:cursor" in detail
    assert "1 unexpected" in value


@pytest.mark.unit
def test_labels_clean_set_is_healthy(mod: Any) -> None:
    value, band, _ = mod.m_labels(["agent-task", "component:root", "priority:low"])
    assert band == "healthy"
    assert "3 labels" in value


@pytest.mark.unit
def test_ops_healthy_when_no_failures(mod: Any) -> None:
    value, band, _ = mod.m_ops([], 0)
    assert band == "healthy"
    assert "0 failed" in value


@pytest.mark.unit
def test_ops_sick_on_many_failures(mod: Any) -> None:
    failures = [{"name": "w"} for _ in range(10)]
    _, band, detail = mod.m_ops(failures, 2)
    assert band == "sick"
    assert "w" in detail


@pytest.mark.unit
def test_issue_tier_defaults_to_cursor(mod: Any) -> None:
    assert mod._issue_tier(["component:digiquant"], {}) == "cursor"
    assert mod._issue_tier(["component:digikey"], {"component:digikey": "claude"}) == "claude"


@pytest.mark.unit
def test_branches_healthy_when_current(mod: Any) -> None:
    value, band, _ = mod.m_branches({"module/digiquant": 0, "module/digikey": 3})
    assert band == "healthy"
    assert "worst behind=3" in value


@pytest.mark.unit
def test_branches_sick_when_far_behind(mod: Any) -> None:
    _, band, detail = mod.m_branches({"module/digiquant": 400})
    assert band == "sick"
    assert "module/digiquant=400" in detail


@pytest.mark.unit
def test_releases_healthy_when_none_open(mod: Any) -> None:
    value, band, _ = mod.m_releases([])
    assert band == "healthy"
    assert "0 open" in value


@pytest.mark.unit
def test_releases_healthy_when_fresh(mod: Any) -> None:
    from datetime import UTC, datetime, timedelta

    fresh = (datetime.now(UTC) - timedelta(days=3)).strftime("%Y-%m-%dT00:00:00Z")
    _, band, _ = mod.m_releases([{"number": 1, "createdAt": fresh}])
    assert band == "healthy"


@pytest.mark.unit
def test_releases_watch_on_old_pr(mod: Any) -> None:
    _, band, detail = mod.m_releases([{"number": 1, "createdAt": "2026-01-01T00:00:00Z"}])
    assert band == "sick"
    assert "1" in detail


@pytest.mark.unit
def test_bootstrap_essentials_present(mod: Any) -> None:
    _, band, detail = mod.m_bootstrap()
    assert band == "healthy"
    assert detail == "ok"


@pytest.mark.unit
def test_render_produces_eight_rows(mod: Any) -> None:
    rows = [(f"dim{i}", "v", "healthy", "d") for i in range(8)]
    table = mod.render(rows)
    assert table.count("\n| ") == 8
    assert table.startswith("| # | Dimension |")


@pytest.mark.unit
def test_render_html_is_self_contained_dashboard(mod: Any) -> None:
    rows = [
        ("Backlog hygiene", "139 open", "watch", "missing=[1]"),
        ("Label-set integrity", "28 labels", "healthy", "ok"),
        ("Ops health", "0 failed", "sick", "x <y> & z"),
    ]
    page = mod.render_html(rows, "2026-09-04 12:00 UTC")
    assert "<!DOCTYPE html>" in page
    assert "http" not in page.replace("http-equiv", "").replace("https://", "X")
    assert page.count("<section class='card'") == 3
    assert "1 watch" in page and "1 healthy" in page and "1 sick" in page
    assert "2026-09-04 12:00 UTC" in page
    assert "&lt;y&gt; &amp; z" in page  # detail is escaped
    assert "<details>" in page


@pytest.mark.unit
def test_collect_degrades_bad_section_to_unknown(mod: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> Any:
        raise RuntimeError("kaput")

    # Hermetic: never call real gh/git. Without this, fetch_issues() can fail on
    # CI (no network auth) and collect() early-returns without a Docs row.
    monkeypatch.setattr(
        mod, "fetch_issues", lambda: [_issue(1, ["priority:high", "component:root"])]
    )
    monkeypatch.setattr(mod, "_gh", lambda *a, **k: [])
    monkeypatch.setattr(mod, "_run", lambda *a, **k: "")
    monkeypatch.setattr(mod, "m_docs", boom)
    rows = mod.collect()
    docs_row = next(r for r in rows if r[0] == "Docs freshness")
    assert docs_row[1] == "error"
    assert docs_row[2] == "unknown"
    assert "kaput" in docs_row[3]
    assert len(rows) == 8


@pytest.mark.unit
def test_collect_never_raises_on_garbage_issues(mod: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mod, "fetch_issues", lambda: [{"number": 1, "labels": None, "updatedAt": "junk"}]
    )
    monkeypatch.setattr(mod, "_gh", lambda *a, **k: [])
    monkeypatch.setattr(mod, "_run", lambda *a, **k: "")
    rows = mod.collect()
    assert len(rows) == 8
    backlog = next(r for r in rows if r[0] == "Backlog hygiene")
    assert backlog[2] == "unknown"


@pytest.mark.unit
def test_dispatch_counts_tiers_and_finds_stuck(mod: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import UTC, datetime, timedelta

    old = (datetime.now(UTC) - timedelta(days=30)).strftime("%Y-%m-%dT00:00:00Z")
    issues = [
        _issue(1, ["agent-task", "component:digiquant"], updated=old),
        _issue(2, ["agent-task", "component:digikey"], updated=old),
    ]
    monkeypatch.setattr(mod, "_gh", lambda *a, **k: [])
    value, band, detail = mod.m_dispatch(issues, {"component:digikey": "claude"})
    assert "'cursor': 1" in value and "'claude': 1" in value
    assert band == "watch"
    assert "stuck=[1, 2]" in detail


@pytest.mark.unit
def test_dispatch_caps_pr_searches(mod: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import UTC, datetime, timedelta

    old = (datetime.now(UTC) - timedelta(days=30)).strftime("%Y-%m-%dT00:00:00Z")
    issues = [_issue(n, ["agent-task", "component:root"], updated=old) for n in range(30)]
    calls: list[str] = []
    monkeypatch.setattr(mod, "_gh", lambda *a, **k: (calls.append("x"), [])[1])
    _, _, detail = mod.m_dispatch(issues, {})
    assert len(calls) == mod.MAX_STUCK_CHECKS
    assert "truncated=True" in detail


@pytest.mark.unit
def test_docs_flags_adr_dupe(mod: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    adr = tmp_path / "docs" / "adr"
    adr.mkdir(parents=True)
    (adr / "0001-a.md").write_text("x")
    (adr / "0001-b.md").write_text("x")
    (adr / "0003-c.md").write_text("x")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_git_mtime", lambda p: 0)
    value, band, detail = mod.m_docs()
    assert band == "sick"
    assert "dupes=[1]" in detail


@pytest.mark.unit
def test_write_doc_missing_markers_warns_without_failing(
    mod: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Any, capsys: Any
) -> None:
    doc = tmp_path / "READINESS.md"
    doc.write_text("no markers here\n")
    monkeypatch.setattr(mod, "READINESS_DOC", doc)
    mod.write_doc("| table |")
    assert "missing markers" in capsys.readouterr().err
    assert doc.read_text() == "no markers here\n"


@pytest.mark.unit
def test_boundary_bands(mod: Any) -> None:
    _, band, _ = mod.m_ops([{"name": "w"}] * 3, 0)
    assert band == "watch"
    _, band, _ = mod.m_branches({"module/a": 5})
    assert band == "healthy"
    _, band, _ = mod.m_branches({"module/a": 50})
    assert band == "watch"
