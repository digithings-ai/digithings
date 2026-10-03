#!/usr/bin/env python3
"""Regenerate app/_mcp-tools.json from the real tool registry.

Reads digiquant/src/digiquant/mcp_server.py with `ast` (no imports, no mcp install
needed): every function decorated `@_maybe_tool("<name>")` inside create_mcp_server is a
tool, its signature gives the arguments, its docstring the description, and
READ_SCOPE_TOOLS says which scope serves it. Run from anywhere:

    python3 apps/digiquant-web/scripts/gen_mcp_manifest.py
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SERVER = ROOT / "digiquant/src/digiquant/mcp_server.py"
OUT = ROOT / "apps/digiquant-web/app/_mcp-tools.json"

PREFIX_FAMILIES = (("digifetch_", "digifetch"), ("luxalgo_", "luxalgo"), ("dashboard_", "policy"))
KEYWORD_FAMILIES = (
    ("list_strategies", "strategies"),
    ("run_", "strategies"),
    ("export", "strategies"),
    ("fetch_", "feeds"),
    ("coinmetrics", "feeds"),
    ("fit_", "models"),
    ("build_", "models"),
    ("generate_", "models"),
    ("validate_", "models"),
)


def family(name: str) -> str:
    for prefix, label in PREFIX_FAMILIES:
        if name.startswith(prefix):
            return label
    rest = name.removeprefix("digiquant_")
    for key, label in KEYWORD_FAMILIES:
        if key in rest:
            return label
    return "research"


def literal(node: ast.expr | None) -> object:
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except ValueError:
        return ast.unparse(node)


def params(fn: ast.FunctionDef) -> list[dict[str, object]]:
    args = fn.args.args
    defaults: list[ast.expr | None] = [None] * (len(args) - len(fn.args.defaults)) + list(
        fn.args.defaults
    )
    out: list[dict[str, object]] = []
    for arg, default in zip(args, defaults, strict=True):
        if arg.arg == "self":
            continue
        out.append(
            {
                "name": arg.arg,
                "type": ast.unparse(arg.annotation) if arg.annotation else "Any",
                "required": default is None,
                "default": literal(default),
            }
        )
    return out


def first_paragraph(doc: str) -> str:
    return re.sub(r"\s+", " ", doc.strip().split("\n\n")[0]).strip()


def main() -> None:
    tree = ast.parse(SERVER.read_text())
    read_scope: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "READ_SCOPE_TOOLS"
            and node.value is not None
        ):
            read_scope = {
                n.value
                for n in ast.walk(node.value)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
            }
    tools: list[dict[str, object]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for deco in node.decorator_list:
            if (
                isinstance(deco, ast.Call)
                and isinstance(deco.func, ast.Name)
                and deco.func.id == "_maybe_tool"
                and deco.args
                and isinstance(deco.args[0], ast.Constant)
            ):
                name = str(deco.args[0].value)
                doc = ast.get_docstring(node) or ""
                tools.append(
                    {
                        "name": name,
                        "family": family(name),
                        "scope": "read" if name in read_scope else "full",
                        "summary": first_paragraph(doc),
                        "params": params(node),
                    }
                )
    tools.sort(key=lambda t: (str(t["family"]), str(t["name"])))
    OUT.write_text(json.dumps(tools, indent=2) + "\n")
    print(f"{len(tools)} tools -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
