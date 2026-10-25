#!/usr/bin/env python3
"""Pin digikey's HTTP route surface so a Workers port cannot drift from it.

DIG-2914 moves digikey off `DigiStackContainer` onto a Worker. The Python
service is the reference implementation until the cut, so its route inventory
is recorded in `config/digikey-route-manifest.json` and checked here.

The check is static (AST, no imports): importing `digikey.server` pulls in
SQLAlchemy, psycopg and a key loader, none of which this check needs.

Usage:
    python scripts/check_digikey_route_parity.py            # check
    python scripts/check_digikey_route_parity.py --update   # rewrite manifest

Exit 1 on drift, so CI fails when a route is added, removed or renamed without
the manifest and the Worker port following it.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = REPO_ROOT / "digikey" / "src" / "digikey" / "server.py"
DEFAULT_MANIFEST = REPO_ROOT / "config" / "digikey-route-manifest.json"

METHODS = {"get", "post", "put", "patch", "delete"}


def _const(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _annotation_name(node: ast.AST | None) -> str | None:
    """Render a parameter annotation as a short name (`AdminIssueBody`, `str`)."""
    if node is None:
        return None
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        inner = _annotation_name(node.value) or "?"
        return f"{inner}[...]"
    return None


def _auth_for(function: ast.FunctionDef | ast.AsyncFunctionDef, path: str) -> str:
    """Classify the route's auth requirement from its own body.

    `_require_admin(request)` is the admin gate; licence routes carry
    `license_id` and verify a licence JWT; everything else is public
    (health, jwks) or bearer-gated by the shared middleware.
    """
    called = {
        node.func.id
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    if "_require_admin" in called:
        return "admin"
    if "_require_license" in called or "verify_license_token" in called or "license_id" in path:
        return "license"
    if "verify_secret" in called:
        return "api_key"
    return "public"


def _body_model(function: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    """The single Pydantic body parameter, if the handler takes one."""
    params = [*function.args.args, *function.args.kwonlyargs]
    models = []
    for arg in params:
        name = _annotation_name(arg.annotation)
        if name and name not in {"Request", "Response", "Session", "str", "int"}:
            models.append(name)
    # Path/query params are `str`/`int`; a body model is the only other type.
    return models[0] if models else None


def routes_from_source(source: Path) -> list[dict[str, str | None]]:
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    routes: list[dict[str, str | None]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            func = decorator.func
            if not isinstance(func, ast.Attribute) or func.attr not in METHODS:
                continue
            path = _const(decorator.args[0]) if decorator.args else None
            if path is None:
                continue
            keywords = {kw.arg: kw.value for kw in decorator.keywords if kw.arg}
            response_model = keywords.get("response_model")
            summary = keywords.get("summary")
            routes.append(
                {
                    "method": func.attr.upper(),
                    "path": path,
                    "handler": node.name,
                    "auth": _auth_for(node, path),
                    "request_model": _body_model(node),
                    "response_model": _annotation_name(response_model)
                    if response_model is not None
                    else None,
                    "summary": _const(summary) if summary is not None else None,
                }
            )
    routes.sort(key=lambda r: (r["path"] or "", r["method"] or ""))
    return routes


def build_manifest(source: Path, manifest_path: Path) -> dict:
    try:
        source_ref = str(source.resolve().relative_to(REPO_ROOT))
    except ValueError:
        # Synthetic sources in tests live outside the repo.
        source_ref = str(source)
    return {
        "service": "digikey",
        "source": source_ref,
        "note": (
            "Reference route surface for the DIG-2914 Workers port. Regenerate with "
            "`python scripts/check_digikey_route_parity.py --update`."
        ),
        "routes": routes_from_source(source),
    }


def load_manifest(manifest_path: Path) -> dict:
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def diff_routes(expected: list[dict], actual: list[dict]) -> list[str]:
    def key(route: dict) -> tuple[str, str]:
        return (route.get("path") or "", route.get("method") or "")

    expected_by_key = {key(r): r for r in expected}
    actual_by_key = {key(r): r for r in actual}
    problems: list[str] = []
    for route_key in sorted(set(expected_by_key) - set(actual_by_key)):
        problems.append(f"missing from source: {route_key[1]} {route_key[0]}")
    for route_key in sorted(set(actual_by_key) - set(expected_by_key)):
        problems.append(f"not in manifest:     {route_key[1]} {route_key[0]}")
    for route_key in sorted(set(expected_by_key) & set(actual_by_key)):
        before, after = expected_by_key[route_key], actual_by_key[route_key]
        for field in ("handler", "auth", "request_model", "response_model", "summary"):
            if before.get(field) != after.get(field):
                problems.append(
                    f"changed {route_key[1]} {route_key[0]}: "
                    f"{field} {before.get(field)!r} -> {after.get(field)!r}"
                )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--update",
        action="store_true",
        help="Rewrite the manifest from the source instead of checking it.",
    )
    args = parser.parse_args(argv)

    if not args.source.is_file():
        print(f"source not found: {args.source}", file=sys.stderr)
        return 2

    manifest = build_manifest(args.source, args.manifest)
    if args.update:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {args.manifest} ({len(manifest['routes'])} routes)")
        return 0

    if not args.manifest.is_file():
        print(
            f"manifest not found: {args.manifest}\n"
            f"run: python scripts/check_digikey_route_parity.py --update",
            file=sys.stderr,
        )
        return 2

    problems = diff_routes(load_manifest(args.manifest)["routes"], manifest["routes"])
    if problems:
        print(f"digikey route manifest drift ({len(problems)}):", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        print(
            "\nUpdate the manifest and the Worker port together:\n"
            "  python scripts/check_digikey_route_parity.py --update",
            file=sys.stderr,
        )
        return 1

    print(f"digikey route parity OK ({len(manifest['routes'])} routes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
