"""A deploy may only skip packaging when image-packages/ matches the sources.

DIG-4423 measured this: `deploy_worker.sh` skipped packaging whenever
`image-packages/` merely existed, so a `digigraph/src`-only change deployed green
three times while the packaged `digigraph-0.1.0-py3-none-any.whl` was dated the
previous day and held none of the change. The guard added to the packaging script
is content-based on purpose — git checkout stamps every source file with "now", so
an mtime rule would call a freshly cloned tree stale and force a repackage, which
rewrites the container layer digests and re-uploads ~8 layers to the registry.

The tests below therefore pin the two directions that matter: identical content
at different mtimes must agree (no false refusal), and a one-byte edit must not
(the refusal that prevents the stale ship). `--check-only` is exercised directly,
with no real `image-packages/` and no network.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "package_r5_image_inputs.py"

pytestmark = pytest.mark.unit


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("package_r5_image_inputs", SCRIPT)
    assert spec and spec.loader, f"cannot import {SCRIPT}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load()


def _tree(root: Path) -> Path:
    """A minimal package tree with deterministic content."""
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        "[project]\nname = 'pkg'\nversion = '0.1.0'\n", encoding="utf-8"
    )
    (root / "src" / "pkg" / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "src" / "pkg" / "graph.py").write_text(
        "def build():\n    return VALUE\n", encoding="utf-8"
    )
    return root


def _write_provenance(tmp_path: Path, paths: dict[str, Path]) -> Path:
    target = tmp_path / "PROVENANCE.json"
    target.write_text(json.dumps(mod.provenance_document(paths)), encoding="utf-8")
    return target


def test_digest_ignores_mtimes(tmp_path: Path) -> None:
    """The anti-false-positive test: same bytes at different times, same digest.

    A checkout hands every file mtime "now"; if this failed, every fresh clone
    would be called stale and every deploy would repackage for nothing.
    """
    first = _tree(tmp_path / "first")
    second = _tree(tmp_path / "second")
    for path in sorted(second.rglob("*")):
        os.utime(path, (1_700_000_000, 1_700_000_000))
    assert mod.content_digest(first) == mod.content_digest(second)


def test_digest_changes_on_a_one_byte_edit(tmp_path: Path) -> None:
    root = _tree(tmp_path / "pkg")
    before = mod.content_digest(root)
    edited = root / "src" / "pkg" / "graph.py"
    edited.write_text(edited.read_text(encoding="utf-8") + "X", encoding="utf-8")
    assert mod.content_digest(root) != before


@pytest.mark.parametrize(
    "rel",
    [
        "__pycache__/graph.cpython-312.pyc",
        "node_modules/left-pad/index.js",
        "dist/pkg-0.1.0-py3-none-any.whl",
        "build/lib/graph.py",
        ".venv/lib/python3.12/site-packages/pkg/__init__.py",
        "src/pkg.egg-info/PKG-INFO",
        ".mypy_cache/3.12/graph.meta.json",
        ".ruff_cache/0.16.10/index",
        ".pytest_cache/v/cache/nodeids",
    ],
)
def test_digest_ignores_excluded_build_and_cache_dirs(tmp_path: Path, rel: str) -> None:
    """Build output and caches are not inputs; running the tests must not drift."""
    root = _tree(tmp_path / "pkg")
    before = mod.content_digest(root)
    junk = root / rel
    junk.parent.mkdir(parents=True, exist_ok=True)
    junk.write_text("not an input\n", encoding="utf-8")
    assert mod.content_digest(root) == before


def test_check_only_passes_when_provenance_matches(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths = {"digigraph": _tree(tmp_path / "digigraph")}
    target = _write_provenance(tmp_path, paths)
    assert mod.check_only(paths, target) == 0
    out = capsys.readouterr().out
    assert "matches 1 packaged input" in out


def test_check_only_exits_1_and_names_the_drifted_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths = {
        "digigraph": _tree(tmp_path / "digigraph"),
        "@digithings/ui": _tree(tmp_path / "ui"),
    }
    target = _write_provenance(tmp_path, paths)
    edited = paths["digigraph"] / "src" / "pkg" / "graph.py"
    edited.write_text(edited.read_text(encoding="utf-8") + "# digigraph change\n", encoding="utf-8")
    assert mod.check_only(paths, target) == 1
    out = capsys.readouterr().out
    assert "changed: digigraph" in out
    assert "@digithings/ui" not in out
    assert "rm -rf image-packages && python3 scripts/package_r5_image_inputs.py" in out


def test_check_only_exits_2_when_provenance_is_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Unknown provenance is not a pass: a pre-existing dir must be rebuilt once."""
    paths = {"digigraph": _tree(tmp_path / "digigraph")}
    missing = tmp_path / "PROVENANCE.json"
    assert mod.check_only(paths, missing) == 2
    out = capsys.readouterr().out
    assert "rm -rf image-packages && python3 scripts/package_r5_image_inputs.py" in out
