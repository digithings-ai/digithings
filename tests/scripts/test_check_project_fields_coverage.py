"""Unit tests for scripts/check_project_fields_coverage.py (ci-pr-hygiene coverage job).

Every open ``agent-task`` issue must have a real phase + sonnet/opus model in
``scripts/project_fields.tsv``. A missing row, placeholder ``phase-N``, or bad
model silently lets house-keeping drift until a human notices — these tests pin
the offline validators without calling ``gh``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any  # score:allow untyped any — dynamically loaded module

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_project_fields_coverage.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("check_project_fields_coverage", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_project_fields_coverage"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def cov(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    mod = _load()
    # Failure messages call TSV.relative_to(REPO_ROOT) — keep both under tmp.
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    tsv = scripts / "project_fields.tsv"
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "TSV", tsv)
    return mod


def _write_tsv(path: Path, rows: list[str]) -> None:
    path.write_text(
        "issue\tphase\tarea\tkind\tpriority\tmodel\n" + "".join(f"{r}\n" for r in rows),
        encoding="utf-8",
    )


def test_load_tsv_indexes_rows_by_issue_number(cov: Any) -> None:
    _write_tsv(
        cov.TSV,
        [
            "10\tPhase 1 — Boot\tdigigraph\tTask\tP1\tsonnet",
            "20\tPhase 2 — Hardening\tdigikey\tEpic\tP0\topus",
            "",  # blank lines ignored
        ],
    )
    rows = cov._load_tsv()
    assert set(rows) == {10, 20}
    assert rows[10][1] == "Phase 1 — Boot"
    assert rows[20][5] == "opus"


def test_missing_tsv_file_fails_closed(cov: Any) -> None:
    # TSV path points at tmp file that was never created.
    assert cov.main() == 1


def test_no_open_agent_tasks_is_success(cov: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_tsv(cov.TSV, ["1\tPhase 1\tdigigraph\tTask\tP1\tsonnet"])
    monkeypatch.setattr(cov, "_gh_json", lambda _args: [])
    assert cov.main() == 0


def test_issue_missing_from_tsv_fails(cov: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_tsv(cov.TSV, ["1\tPhase 1\tdigigraph\tTask\tP1\tsonnet"])
    monkeypatch.setattr(
        cov,
        "_gh_json",
        lambda _args: [{"number": 99, "title": "orphan task"}],
    )
    assert cov.main() == 1


def test_row_with_too_few_columns_fails(cov: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    # Five columns — missing model.
    cov.TSV.write_text(
        "issue\tphase\tarea\tkind\tpriority\tmodel\n"
        "7\tPhase 1\tdigigraph\tTask\tP1\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        cov,
        "_gh_json",
        lambda _args: [{"number": 7, "title": "short row"}],
    )
    assert cov.main() == 1


def test_placeholder_phase_dash_N_fails(cov: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_tsv(cov.TSV, ["11\tphase-3\tdigiquant\tTask\tP1\tsonnet"])
    monkeypatch.setattr(
        cov,
        "_gh_json",
        lambda _args: [{"number": 11, "title": "still scaffolding"}],
    )
    assert cov.main() == 1


def test_invalid_model_fails(cov: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_tsv(cov.TSV, ["12\tPhase 4 — Olympus\tdigiquant\tTask\tP1\tgpt-4o"])
    monkeypatch.setattr(
        cov,
        "_gh_json",
        lambda _args: [{"number": 12, "title": "bad model"}],
    )
    assert cov.main() == 1


def test_valid_sonnet_and_opus_rows_pass(cov: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_tsv(
        cov.TSV,
        [
            "21\tPhase 4 — Olympus\tdigiquant\tTask\tP1\tsonnet",
            "22\tPhase 5 — Auth\tdigikey\tTask\tP0\topus",
        ],
    )
    monkeypatch.setattr(
        cov,
        "_gh_json",
        lambda _args: [
            {"number": 21, "title": "ok sonnet"},
            {"number": 22, "title": "ok opus"},
        ],
    )
    assert cov.main() == 0


def test_valid_models_frozenset_is_sonnet_opus_only(cov: Any) -> None:
    assert cov.VALID_MODELS == frozenset({"sonnet", "opus"})
