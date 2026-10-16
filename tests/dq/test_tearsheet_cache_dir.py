"""Pin tearsheet OHLCV cache path to digiquant/data/price-history (#3472).

fetch_coinbase / export_sdca_macro write under DIGIQUANT_ROOT; generate must
read the same tree. Repo-root data/price-history is a different directory.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_GENERATE = _REPO / "digiquant" / "scripts" / "generate_tearsheets.py"
_FETCH = _REPO / "digiquant" / "scripts" / "fetch_coinbase.py"
_EXPORT = _REPO / "digiquant" / "scripts" / "export_sdca_macro.py"
_WORKFLOW = _REPO / ".github" / "workflows" / "pipeline-digiquant-tearsheets.yml"

_spec = importlib.util.spec_from_file_location("generate_tearsheets_cache_dir", _GENERATE)
assert _spec is not None and _spec.loader is not None
gts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gts)

pytestmark = pytest.mark.unit


def _default_cache_from_script(path: Path) -> Path:
    """Resolve ``DEFAULT_CACHE = ROOT / ...`` without importing ccxt."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    root_expr: ast.AST | None = None
    cache_expr: ast.AST | None = None
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        name = node.targets[0]
        if not isinstance(name, ast.Name):
            continue
        if name.id == "ROOT":
            root_expr = node.value
        elif name.id == "DEFAULT_CACHE":
            cache_expr = node.value
    assert root_expr is not None and cache_expr is not None

    def _eval(expr: ast.AST) -> Path:
        if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Div):
            return _eval(expr.left) / _eval(expr.right)
        if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
            return Path(expr.value)
        if isinstance(expr, ast.Name) and expr.id == "ROOT":
            # Path(__file__).resolve().parent.parent  → digiquant/
            return path.resolve().parent.parent
        if (
            isinstance(expr, ast.Call)
            and isinstance(expr.func, ast.Attribute)
            and expr.func.attr == "resolve"
        ):
            # Path(__file__).resolve() …
            return path.resolve()
        if isinstance(expr, ast.Attribute) and expr.attr == "parent":
            return _eval(expr.value).parent
        if (
            isinstance(expr, ast.Call)
            and isinstance(expr.func, ast.Name)
            and expr.func.id == "Path"
        ):
            assert len(expr.args) == 1
            arg = expr.args[0]
            if isinstance(arg, ast.Name) and arg.id == "__file__":
                return path
            raise AssertionError(f"unexpected Path() arg in {path}: {ast.dump(arg)}")
        raise AssertionError(f"unexpected DEFAULT_CACHE AST in {path}: {ast.dump(expr)}")

    return _eval(cache_expr)


def test_generate_default_cache_is_under_digiquant_root() -> None:
    expected = gts.DIGIQUANT_ROOT / "data" / "price-history"
    assert gts.DEFAULT_CACHE == expected
    assert gts.DEFAULT_CACHE != gts.REPO_ROOT / "data" / "price-history"


def test_fetch_and_export_default_caches_match_generate() -> None:
    fetch_cache = _default_cache_from_script(_FETCH)
    export_cache = _default_cache_from_script(_EXPORT)
    assert fetch_cache == gts.DEFAULT_CACHE
    assert export_cache == gts.DEFAULT_CACHE


def test_nightly_workflow_passes_cache_dir() -> None:
    text = _WORKFLOW.read_text(encoding="utf-8")
    assert "--cache-dir digiquant/data/price-history" in text
    assert "generate_tearsheets.py" in text
