"""Dry-run coverage for scripts/seed_knowledge_vault.py (#1142)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "seed_knowledge_vault.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("seed_knowledge_vault", _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _write_note(root: Path, name: str, text: str) -> None:
    (root / f"{name}.md").write_text(text, encoding="utf-8")


def test_build_rows_includes_vault_namespace(tmp_path: Path) -> None:
    mod = _load_module()
    _write_note(
        tmp_path,
        "mpt",
        "---\ntitle: MPT\ntags: [theory]\ntype: theory\n---\nsee [[capm]]\n",
    )
    rows = mod.build_rows(str(tmp_path), vault="finance")
    assert len(rows) == 1
    assert rows[0]["vault"] == "finance"
    assert rows[0]["slug"] == "mpt"
    assert rows[0]["vault_path"] == "mpt"
    assert rows[0]["wikilinks"] == ["capm"]
    assert rows[0]["tags"] == ["theory"]


def test_seed_dry_run_prints_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    mod = _load_module()
    _write_note(tmp_path, "a", "---\ntitle: A\n---\nbody\n")
    rc = mod.main(["--vault-dir", str(tmp_path), "--vault", "product", "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload[0]["vault"] == "product"
    assert payload[0]["vault_path"] == "a"
