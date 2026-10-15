#!/usr/bin/env python3
"""Enumerate the deployed digithings web routes and attach their target URLs.

Plan section 7 asks ``dt ui-audit`` to rerun a phone and desktop audit of the
web routes against the local stack. The audit command does not exist yet and no
file in the repository records the route list, so this module supplies the one
input every version of that audit needs: the routes, enumerated from the
app-router trees rather than hand-written, plus the base URL each one is served
from for a given target.

Two rules keep this module honest.

It does not define a URL table. Base URLs come from
:mod:`selfhost_target`, which is the single resolver for section 7's one
variable. A second table here would be the parallel source of truth that
section 8's contract drift check exists to catch.

An app with no published endpoint is a skip, never a default. ``dashboard`` has
no container in the compose file, so on the self-host target it resolves to
``url: None`` and names the env var that would supply it. The same discipline
``selfhost_target`` applies to unpublished ports applies here to whole apps.

Usage::

    python3 scripts/ui_routes.py --target selfhost
    python3 scripts/ui_routes.py --target hosted --json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

# The three deployed Next.js app-router trees. Section 7's "57 routes" is these.
DEPLOYED_APPS = ("dashboard", "digithings-web", "digiquant-web")

# `reference` ships template apps that are never deployed. It is enumerated
# separately so the exclusion is visible instead of silent.
REFERENCE_APPS = ("reference",)

# Which resolver endpoint serves each app, or how the app is reached when it
# has no endpoint. An entry naming an env var has no endpoint in the resolver and
# is a skip unless the env var is set.
APP_ENDPOINT = {
    "dashboard": ("api", "DT_API_URL"),
    "digiquant-web": ("quant", None),
    "digichat": ("chat", None),
    # digithings-web is a static site served from the target origin itself, not
    # from a subdomain endpoint, so it falls back to the base URL. DT_WEB_URL
    # overrides that when it is deployed somewhere else.
    "digithings-web": ("__base__", "DT_WEB_URL"),
}


def _load_resolver():
    """Import the sibling resolver without requiring the package on sys.path."""
    path = Path(__file__).resolve().parent / "selfhost_target.py"
    name = "selfhost_target"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        # Register before exec: the module defines a dataclass, which needs
        # sys.modules[name] to already exist while its class body runs.
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def route_path(page: Path, app_root: Path) -> str:
    """Turn ``apps/x/app/a/(group)/b/page.tsx`` into ``/a/b``.

    Route groups in parentheses do not appear in the URL. Dynamic segments keep
    their brackets because they are part of the path pattern.
    """
    rel = page.relative_to(app_root).parent
    parts = [p for p in rel.parts if not (p.startswith("(") and p.endswith(")"))]
    return "/" + "/".join(parts)


@dataclass
class AppRoutes:
    app: str
    deployed: bool
    url: str | None = None
    requires: str | None = None
    routes: list[str] = field(default_factory=list)


def enumerate_routes(root: Path = REPO_ROOT) -> dict[str, AppRoutes]:
    """Collect every ``page.tsx`` under each app's app-router tree."""
    out: dict[str, AppRoutes] = {}
    for app in DEPLOYED_APPS + REFERENCE_APPS:
        app_root = root / "apps" / app / "app"
        found = AppRoutes(app=app, deployed=app in DEPLOYED_APPS)
        if app_root.is_dir():
            found.routes = sorted(
                route_path(p, app_root) for p in app_root.rglob("page.tsx")
            )
        out[app] = found
    return out


def attach_urls(
    apps: dict[str, AppRoutes], target: str | None = None, env: dict[str, str] | None = None
) -> dict[str, AppRoutes]:
    """Give each app its base URL, taken from the resolver, never from here."""
    resolver = _load_resolver()
    res = resolver.resolve(target=target, env=env)
    by_name = {e["name"]: e for e in res.endpoints}
    # The resolver defaults a None env to os.environ; mirror that so the env
    # lookups below are safe whichever the caller passed.
    env = os.environ if env is None else env

    for name, found in apps.items():
        if not found.deployed:
            # A non-deployed app gets no URL and no env var. Offering a
            # `requires` for an app that is never served invents an obligation.
            found.url = None
            found.requires = None
            continue
        endpoint, env_var = APP_ENDPOINT.get(name, (None, None))
        if endpoint is not None and endpoint in by_name and by_name[endpoint]["url"]:
            found.url = by_name[endpoint]["url"].rstrip("/")
            found.requires = None
        elif env_var and env_var in env:
            found.url = env[env_var].rstrip("/")
            found.requires = None
        elif endpoint == "__base__":
            found.url = res.base_url.rstrip("/")
            found.requires = None
        else:
            found.url = None
            found.requires = env_var or f"DT_{name.upper().replace('-', '_')}_URL"
    return apps


def build(
    target: str | None = None,
    root: Path = REPO_ROOT,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    apps = attach_urls(enumerate_routes(root), target=target, env=env)
    deployed = {k: v for k, v in apps.items() if v.deployed}
    return {
        "target": target or os.environ.get("DT_TARGET") or "selfhost",
        "deployed_apps": sorted(deployed),
        "route_count": sum(len(v.routes) for v in deployed.values()),
        "apps": {
            k: {
                "deployed": v.deployed,
                "url": v.url,
                "requires": v.requires,
                "routes": v.routes,
            }
            for k, v in sorted(apps.items())
        },
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [
        f"target: {report['target']}",
        f"deployed apps: {', '.join(report['deployed_apps'])}",
        f"routes: {report['route_count']}",
        "",
    ]
    for name, info in report["apps"].items():
        mark = "deployed" if info["deployed"] else "not deployed"
        lines.append(f"{name} ({mark})")
        if info["url"]:
            lines.append(f"  base: {info['url']}")
        elif not info["deployed"]:
            lines.append("  base: not deployed")
        else:
            lines.append(f"  base: SKIPPED - set {info['requires']}")
        for route in info["routes"]:
            lines.append(f"    {route}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", choices=("selfhost", "hosted"), default=None)
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--root", default=str(REPO_ROOT))
    args = parser.parse_args(argv)

    report = build(target=args.target, root=Path(args.root))
    print(json.dumps(report, indent=2) if args.json else render_text(report))

    # A skip is never a pass. Exit 1 when any deployed app has no base URL, so a
    # caller cannot read a partial report as a complete one.
    skipped = [n for n, i in report["apps"].items() if i["deployed"] and not i["url"]]
    return 1 if skipped else 0


if __name__ == "__main__":
    raise SystemExit(main())