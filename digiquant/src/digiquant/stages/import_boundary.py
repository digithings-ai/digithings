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
