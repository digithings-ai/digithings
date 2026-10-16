# P1.1 — Freeze the stage import allowlist

**Lane:** OpenCode free implement.

**Parent:** #4762.

## Goal

A unit test fails when a Python file under `digiquant/src/digiquant/{research,portfolio,execution}` gains or loses a cross-stage import relative to a committed allowlist. The allowlist is generated from the tree at implementation time. This package does not delete or move imports.

## Non-goals

- Do not replace `PortfolioState = ResearchState`.
- Do not make research stop importing portfolio models.
- Do not move function-body imports in `research/testing/simulator.py` to the top of the file.
- Do not add a new cross-import while generating the list.

## Files

- Create: `digiquant/src/digiquant/stages/import_boundary.py` (the scanner; pure AST, no I/O beyond reading source the caller passes)
- Create: `tests/dq/stages/test_import_boundary.py`
- Create: `tests/dq/stages/fixtures/stage_import_allowlist.txt` (generated, committed)

P0.1 creates `digiquant/src/digiquant/stages/`. If P0.1 has not merged, this package still creates `stages/__init__.py` only when that file is absent, with the docstring `"""Swappable digiquant stage handoffs (ADR-0030)."""` and no imports. If P0.1 already added `__init__.py`, do not edit it.

## Interface

```python
def cross_stage_imports(root: Path) -> list[str]:
    """Return sorted ``"{src_file} {imported_module}"`` lines.

    ``src_file`` is relative to ``root`` with forward slashes.
    A hit is an import whose module starts with ``digiquant.research``,
    ``digiquant.portfolio``, or ``digiquant.execution``, and whose stage
    segment differs from the file's top package (``research``, ``portfolio``,
    or ``execution``). Files outside those three packages are ignored.
    ``ast.walk`` includes imports inside functions.
    """
```

Allowlist line format, one per line, sorted unique:

```text
portfolio/chain.py digiquant.research.state
```

## Steps

### 1. Write the scanner

```python
"""AST scan of cross-stage imports. Used by the ADR-0030 allowlist test."""

from __future__ import annotations

import ast
from pathlib import Path

_STAGES = frozenset({"research", "portfolio", "execution"})


def _modules(tree: ast.AST) -> list[str]:
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
        elif isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
    return found


def cross_stage_imports(root: Path) -> list[str]:
    lines: set[str] = set()
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root)
        if len(rel.parts) < 2:
            continue
        top = rel.parts[0]
        if top not in _STAGES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for module in _modules(tree):
            if not module.startswith("digiquant."):
                continue
            parts = module.split(".")
            if len(parts) < 2:
                continue
            dest = parts[1]
            if dest in _STAGES and dest != top:
                lines.add(f"{rel.as_posix()} {module}")
    return sorted(lines)
```

Put this in `digiquant/src/digiquant/stages/import_boundary.py`.

### 2. Generate the allowlist

From the repo root, after the scanner is importable (`pythonpath` already includes `digiquant/src`):

```bash
python -c "
from pathlib import Path
from digiquant.stages.import_boundary import cross_stage_imports
root = Path('digiquant/src/digiquant')
text = '\n'.join(cross_stage_imports(root)) + '\n'
Path('tests/dq/stages/fixtures/stage_import_allowlist.txt').write_text(text)
print(len(text.splitlines()))
"
```

On plan day (`develop` `dc8e06365`) the direction counts were: portfolio → research 103, research → portfolio 28, execution → portfolio 4, portfolio → execution 2, research → execution 1. The allowlist is one line per (file, module), so the line count is not 138 (a file can import a module once; the 138 figure counted AST nodes, and duplicate module strings inside one file collapse). If the line count is 0, the scanner is wrong. Stop. Do not hand-write the file.

### 3. Test

```python
from __future__ import annotations

from pathlib import Path

import pytest
from digiquant.stages.import_boundary import cross_stage_imports

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3] / "digiquant" / "src" / "digiquant"
_ALLOW = Path(__file__).resolve().parent / "fixtures" / "stage_import_allowlist.txt"


def test_cross_stage_imports_match_allowlist() -> None:
    expected = [line for line in _ALLOW.read_text(encoding="utf-8").splitlines() if line]
    assert cross_stage_imports(_ROOT) == expected
```

`parents[3]` from `tests/dq/stages/test_import_boundary.py` is the repo root. Confirm with a failing assertion message if `_ROOT` does not exist, then fix the index. Do not hard-code `/workspace`.

### 4. Run

```bash
pytest -m unit tests/dq/stages/test_import_boundary.py -q
ruff check digiquant/src/digiquant/stages/import_boundary.py tests/dq/stages/test_import_boundary.py
ruff format --check digiquant/src/digiquant/stages/import_boundary.py tests/dq/stages/test_import_boundary.py
```

### 5. Commit

```bash
git add digiquant/src/digiquant/stages/import_boundary.py tests/dq/stages/test_import_boundary.py tests/dq/stages/fixtures/stage_import_allowlist.txt
git commit -m "test(digiquant): freeze stage cross-import allowlist"
```

If `stages/__init__.py` was created because P0.1 had not landed, include it in this commit only when it is the docstring-only file from the Files section.

## Acceptance checklist

- [ ] The test passes on a clean tree and fails if you temporarily add `import digiquant.execution.router` to a portfolio module (revert that edit before commit).
- [ ] No production import was added or removed.
- [ ] `simulator.py` inline imports are unchanged.
- [ ] Brokers, execution router, and cron files are untouched.

## Dependencies

- Blocked by: none. May land beside P0.1. If both create `stages/__init__.py`, keep P0.1's re-export file and drop the stub.
- Unblocks: future boundary cleanup. No other package in this epic imports the allowlist.

## Out of scope / do not touch

- Deleting a cross-import to "shrink" the list.
- `digiquant/brokers/**`, `execution/router.py`, `execution/policy.py`.
- Recommendation policy, twelve-x, dashboard, workflows.
