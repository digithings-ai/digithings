"""Pins the atlas collection gate's scope (#2183).

`tests/dq/atlas/conftest.py` skips collection of files that need digigraph
when the digiquant-only CI lane runs without it. This test exists so a
future edit can't silently widen that skip back to a whole directory (as
`data/test_*.py` used to) without a human noticing here first.

Lives at `tests/dq/`, not `tests/dq/atlas/`, on purpose: the atlas conftest's
own top-level `test_*.py` entry in `collect_ignore_glob` would otherwise
sweep this file out of collection in exactly the digiquant-only lane it's
meant to guard.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ATLAS_DIR = Path(__file__).resolve().parent / "atlas"
CONFTEST = ATLAS_DIR / "conftest.py"


def _collect_ignore_glob_literal() -> list[str]:
    """The list literal assigned to `collect_ignore_glob` in the conftest source.

    Parsed with `ast` rather than imported, because importing the module
    evaluates `_digigraph_importable()` against *this* process's environment
    -- the assignment may not even execute here. The literal in the source is
    what governs every environment, which is what this test pins.
    """
    tree = ast.parse(CONFTEST.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "collect_ignore_glob"
            and isinstance(node.value, ast.List)
        ):
            return [
                elt.value
                for elt in node.value.elts
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
            ]
    raise AssertionError("collect_ignore_glob assignment not found in conftest.py")


@pytest.mark.unit
def test_the_gate_does_not_skip_the_whole_data_directory() -> None:
    """Only test_ai_portfolios.py/test_web_grounding.py need digigraph under
    data/, and both already self-skip via `pytest.importorskip("openai")` --
    a file-level `data/test_*.py` glob swept the other three files' ~29 tests
    out with them for no reason. See the conftest docstring for the full story.
    """
    assert "data/test_*.py" not in _collect_ignore_glob_literal()


@pytest.mark.unit
def test_the_dead_phases_pattern_stays_removed() -> None:
    """`tests/dq/atlas/phases/` has never existed; the pattern matched nothing."""
    assert not (ATLAS_DIR / "phases").is_dir()
    assert "phases/test_*.py" not in _collect_ignore_glob_literal()


@pytest.mark.unit
def test_the_two_digigraph_dependent_data_files_self_guard() -> None:
    """The gate's narrowing relies on these files skipping themselves cleanly.

    If either drops its `pytest.importorskip("openai")` guard, collecting it
    without digigraph installed would error instead of skipping -- this would
    need the file-level glob back, not just a marker.
    """
    data_dir = ATLAS_DIR / "data"
    for name in ("test_ai_portfolios.py", "test_web_grounding.py"):
        source = (data_dir / name).read_text(encoding="utf-8")
        assert 'pytest.importorskip("openai")' in source, (
            f"{name} must keep its module-level importorskip guard for the "
            "narrowed collection gate to be safe"
        )
