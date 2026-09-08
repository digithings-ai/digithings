"""Unit tests for scripts/generate_ci_path_filters.py CI path-filter sync.

The ruff-and-scripts CI job runs ``generate_ci_path_filters.py --check`` so
``scripts/ci_paths.yaml`` stays the single source of truth for dorny filters in
``ci.yml``. A broken marker split, wrong YAML→YAML indentation, or inverted
check exit code would either fail every PR or (worse) stop detecting drift and
let path filters silently diverge from the yaml source.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any  # score:allow untyped any — dynamically loaded module

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "generate_ci_path_filters.py"


def _load() -> Any:
    name = "generate_ci_path_filters_under_test"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


gpf = _load()


def test_render_filters_emits_dorny_indent_and_quoted_globs() -> None:
    block = gpf.render_filters({"digibase": ["digibase/**", "tests/db/**"]})
    assert block == (
        "            digibase:\n"
        "              - 'digibase/**'\n"
        "              - 'tests/db/**'\n"
    )


def test_patch_ci_yml_replaces_only_between_markers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ci = tmp_path / "ci.yml"
    ci.write_text(
        "jobs:\n"
        "  changes:\n"
        "    steps:\n"
        f"            {gpf.START}\n"
        "            old:\n"
        "              - 'gone/**'\n"
        f"            {gpf.END}\n"
        "  ruff:\n"
        "    runs-on: ubuntu-latest\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(gpf, "CI_YML", ci)
    new_block = gpf.render_filters({"digikey": ["digikey/**"]})
    rebuilt = gpf.patch_ci_yml(new_block)
    assert "old:" not in rebuilt
    assert "digikey:" in rebuilt
    assert "ruff:" in rebuilt
    assert rebuilt.count(gpf.START) == 1
    assert rebuilt.count(gpf.END) == 1


def test_patch_ci_yml_requires_both_markers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "ci.yml"
    fake.write_text("no markers here\n", encoding="utf-8")
    monkeypatch.setattr(gpf, "CI_YML", fake)
    with pytest.raises(SystemExit, match="missing"):
        gpf.patch_ci_yml("            digibase:\n")


def test_load_filters_reads_repo_ci_paths_yaml() -> None:
    data = gpf.load_filters()
    assert "digibase" in data
    assert "digiquant" in data
    assert any(p.startswith("digibase/") for p in data["digibase"])


def test_check_mode_ok_when_ci_yml_matches_yaml(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    filters = {"digibase": ["digibase/**"]}
    block = gpf.render_filters(filters)
    ci = tmp_path / "ci.yml"
    ci.write_text(
        f"prefix\n            {gpf.START}\n{block}            {gpf.END}\nsuffix\n",
        encoding="utf-8",
    )
    yaml_src = tmp_path / "ci_paths.yaml"
    yaml_src.write_text("digibase:\n  - digibase/**\n", encoding="utf-8")
    monkeypatch.setattr(gpf, "CI_YML", ci)
    monkeypatch.setattr(gpf, "SOURCE", yaml_src)
    monkeypatch.setattr(sys, "argv", ["generate_ci_path_filters.py", "--check"])
    assert gpf.main() == 0


def test_check_mode_fails_on_drift(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ci = tmp_path / "ci.yml"
    ci.write_text(
        f"            {gpf.START}\n"
        "            digibase:\n"
        "              - 'stale/**'\n"
        f"            {gpf.END}\n",
        encoding="utf-8",
    )
    yaml_src = tmp_path / "ci_paths.yaml"
    yaml_src.write_text("digibase:\n  - digibase/**\n", encoding="utf-8")
    monkeypatch.setattr(gpf, "CI_YML", ci)
    monkeypatch.setattr(gpf, "SOURCE", yaml_src)
    monkeypatch.setattr(sys, "argv", ["generate_ci_path_filters.py", "--check"])
    assert gpf.main() == 1


def test_print_mode_does_not_write(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    yaml_src = tmp_path / "ci_paths.yaml"
    yaml_src.write_text("digikey:\n  - digikey/**\n", encoding="utf-8")
    ci = tmp_path / "ci.yml"
    original = f"            {gpf.START}\n            x:\n              - 'y'\n            {gpf.END}\n"
    ci.write_text(original, encoding="utf-8")
    monkeypatch.setattr(gpf, "SOURCE", yaml_src)
    monkeypatch.setattr(gpf, "CI_YML", ci)
    monkeypatch.setattr(sys, "argv", ["generate_ci_path_filters.py", "--print"])
    assert gpf.main() == 0
    out = capsys.readouterr().out
    assert "digikey:" in out
    assert ci.read_text(encoding="utf-8") == original
