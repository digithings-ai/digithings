#!/usr/bin/env python3
"""Resolve digithings UI + MCP endpoints for a self-host or hosted target.

Plan section 7 wants ONE variable -- ``DT_BASE_URL`` -- with every UI deriving
its API and MCP URLs from the config contract instead of carrying its own copy
of the endpoint table. This module is that derivation.

It deliberately does NOT define a third endpoint table. ``config/contract/`` is
the source of truth (plan section 8); this file carries a *fallback* whose every
value is sourced to a ``file:line`` in the compose file, so the fallback can be
checked by a human and can only ever overlay -- never delete -- what the contract
declares. That is the same contract-first rule ``scripts/self_host_parity.py``
applies and the same feature-detection rule ``scripts/localstack/contracts.py``
applies: both accepted shapes of the S1 contract are probed, so this works
before and after S1 lands and does not pin one shape as correct.

A skip is never a pass. An endpoint with no published port resolves to
``url=None`` with the env var that would supply it, is printed in a ``skipped``
section, and turns the exit code non-zero under ``--require-all``.

Usage:
    scripts/selfhost_target.py --target selfhost
    scripts/selfhost_target.py --target hosted --format opencode
    scripts/selfhost_target.py --target selfhost --format claude
    scripts/selfhost_target.py --target selfhost --proxied

Exit codes: 0 all resolved, 1 a required endpoint skipped, 2 usage error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

# Both shapes S1 may ship, probed in order. The first that parses wins; a shape
# that exists but does not parse is a hard error, never a silent fallback.
CONTRACT_PATHS = (
    Path("config/contract/services.yaml"),
    Path("config/contract/contract.yaml"),
)

HOSTED_BASE_URL = "https://digithings.ai"
SELFHOST_BASE_URL = "http://digithings.localhost"

TARGETS = ("selfhost", "hosted")

# A token env var NAME is an identifier. Enforcing that is what makes "no
# credential in a rendered snippet" true by construction rather than by
# call-site discipline -- a caller holding a token value cannot pass it here.
_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


@dataclass(frozen=True)
class Endpoint:
    """One resolved endpoint.

    ``source`` says where the fallback value came from so a reviewer can check
    it by hand. ``port`` is the host-published port on self-host; ``None`` means
    the service is not published, which is a skip and never a default.
    """

    name: str
    hosted_subdomain: str
    service: str
    kind: str  # "api" or "mcp"
    port: int | None
    source: str
    requires: str | None = None

    @property
    def selfhost_host(self) -> str:
        return f"{self.hosted_subdomain}.digithings.localhost"


# Ports are the compose-published host ports on develop. Each carries the line it
# was read from so a drift is a one-line diff a reviewer can check.
BUILTIN: tuple[Endpoint, ...] = (
    Endpoint("graph", "graph", "digigraph", "api", 8000, "docker-compose.yml:104"),
    Endpoint(
        "api",
        "api",
        "dashboard-api",
        "api",
        None,
        "docker-compose.yml (no dashboard-api service)",
        requires="DT_API_URL",
    ),
    Endpoint("key", "key", "digikey", "api", 8005, "docker-compose.yml:26"),
    Endpoint("search", "search", "digisearch", "api", 8002, "docker-compose.yml:202"),
    Endpoint("quant", "quant", "digiquant", "api", 8001, "docker-compose.yml:167"),
    Endpoint(
        "chat",
        "chat",
        "digichat",
        "api",
        3005,
        "docker-compose.yml:541 (host port is ${DIGICHAT_PUBLISH_PORT:-3005})",
    ),
    Endpoint("mcp-search", "mcp", "digisearch-mcp", "mcp", 8765, "docker-compose.yml:401"),
    Endpoint("mcp-vault", "mcp", "digivault-mcp", "mcp", 8769, "docker-compose.yml:428"),
    Endpoint("mcp-tickets", "mcp", "zammad-mcp", "mcp", 8770, "docker-compose.yml:453"),
    Endpoint(
        "mcp-quant",
        "mcp",
        "digiquant-mcp-container",
        "mcp",
        None,
        "config/contract (FastMCP inside the stack Worker, not published)",
        requires="DT_MCP_QUANT_URL",
    ),
)


@dataclass
class Resolution:
    target: str
    base_url: str
    contract_path: str | None
    endpoints: list[dict[str, Any]] = field(default_factory=list)

    @property
    def resolved(self) -> list[dict[str, Any]]:
        return [e for e in self.endpoints if e["url"]]

    @property
    def skipped(self) -> list[dict[str, Any]]:
        return [e for e in self.endpoints if not e["url"]]


def load_contract(root: Path = REPO_ROOT) -> tuple[Path | None, dict[str, Any]]:
    """Return the first contract file that parses, plus its data.

    A file that exists but does not parse raises. Falling back to the built-in
    on a broken contract would report a healthy stack over a broken contract.
    """
    for rel in CONTRACT_PATHS:
        path = root / rel
        if not path.exists():
            continue
        data = yaml.safe_load(path.read_text()) or {}
        if not isinstance(data, dict):
            raise ValueError(f"{rel} is not a mapping")
        return rel, data
    return None, {}


def contract_ports(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map service name -> port row, tolerating either contract shape."""
    rows: dict[str, dict[str, Any]] = {}
    ports = data.get("ports")
    if isinstance(ports, list):
        for row in ports:
            if isinstance(row, dict) and isinstance(row.get("name"), str):
                rows[row["name"]] = row
    services = data.get("services")
    if isinstance(services, list):
        for row in services:
            if not isinstance(row, dict) or not isinstance(row.get("name"), str):
                continue
            entry = rows.setdefault(row["name"], {})
            for key, value in row.items():
                entry.setdefault(key, value)
    return rows


def merge_contract(
    builtin: tuple[Endpoint, ...], rows: dict[str, dict[str, Any]]
) -> list[Endpoint]:
    """Overlay contract rows onto the built-ins BY NAME.

    A contract row may change a port or a subdomain. It may not delete a
    built-in: a name the contract does not mention keeps its sourced value. If
    the contract omits a port for a service the built-in has one for, the
    built-in port is kept -- an omission is not a deletion.
    """
    merged: list[Endpoint] = []
    for ep in builtin:
        row = rows.get(ep.service)
        if not row:
            merged.append(ep)
            continue
        port = row.get("host_port", ep.port)
        if port is not None and not isinstance(port, int):
            raise ValueError(f"contract host_port for {ep.service} is not an int: {port!r}")
        subdomain = ep.hosted_subdomain
        note = row.get("note")
        if isinstance(note, str) and "public route" in note:
            token = note.split("public route", 1)[1].strip().split()[0]
            subdomain = token.split(".", 1)[0]
        merged.append(
            Endpoint(
                name=ep.name,
                hosted_subdomain=subdomain,
                service=ep.service,
                kind=ep.kind,
                port=port,
                source=f"{ep.source} + contract",
                requires=ep.requires,
            )
        )
    return merged


def pick_target(flag: str | None, env: dict[str, str] | None = None) -> str:
    """Flag beats DT_TARGET beats the hosted default. Never guesses."""
    env = os.environ if env is None else env
    value = flag or env.get("DT_TARGET") or "hosted"
    if value not in TARGETS:
        raise ValueError(f"unknown target {value!r}; expected one of {', '.join(TARGETS)}")
    return value


def resolve(
    target: str | None = None,
    base_url: str | None = None,
    proxied: bool = False,
    root: Path = REPO_ROOT,
    env: dict[str, str] | None = None,
) -> Resolution:
    env = os.environ if env is None else env
    chosen = pick_target(target, env)
    if base_url:
        origin = base_url.rstrip("/")
    elif env.get("DT_BASE_URL"):
        origin = env["DT_BASE_URL"].rstrip("/")
    else:
        origin = SELFHOST_BASE_URL if chosen == "selfhost" else HOSTED_BASE_URL

    rel, data = load_contract(root)
    endpoints = merge_contract(BUILTIN, contract_ports(data))

    rows: list[dict[str, Any]] = []
    for ep in endpoints:
        if chosen == "hosted":
            url = f"{origin}/{ep.hosted_subdomain}"
        elif ep.port is None:
            override = env.get(ep.requires or "")
            url = override.rstrip("/") if override else None
        elif proxied:
            url = f"http://{ep.selfhost_host}"
        else:
            url = f"http://{ep.selfhost_host}:{ep.port}"
        rows.append(
            {
                "name": ep.name,
                "kind": ep.kind,
                "service": ep.service,
                "url": url,
                "source": ep.source,
                "requires": ep.requires,
            }
        )
    return Resolution(chosen, origin, str(rel) if rel else None, rows)


def render_env(res: Resolution) -> str:
    out = [
        "# Generated by scripts/selfhost_target.py -- do not edit by hand.",
        f"# target={res.target} base_url={res.base_url}",
        f"# contract={res.contract_path or 'none (fallback ports in use)'}",
    ]
    for row in res.resolved:
        out.append(f"DT_URL_{row['name'].upper().replace('-', '_')}={row['url']}")
    for row in res.skipped:
        out.append(f"# SKIPPED {row['name']}: set {row['requires']} (source: {row['source']})")
    return "\n".join(out) + "\n"


def render_opencode(res: Resolution) -> dict[str, Any]:
    return {
        "$schema": "https://opencode.ai/config.json",
        "mcp": {
            "servers": {
                row["name"]: {"type": "remote", "url": row["url"]}
                for row in res.resolved
                if row["kind"] == "mcp"
            }
        },
    }


def render_claude(res: Resolution, token_env: str) -> dict[str, Any]:
    """Claude mcp.json shape, matching .cursor/mcp.json in this repo.

    The digikey token is referenced by env var NAME and never interpolated, so
    a generated snippet cannot leak a credential into a log or a commit. The
    guard below is a shape check, not a guarantee: a value that is itself
    identifier-shaped would pass. The contract is that the caller passes a name.
    """
    if not _ENV_NAME.fullmatch(token_env) or any(c in token_env for c in ".-/ \t"):
        raise ValueError(
            f"token_env must be an env var NAME, got {token_env!r}. "
            "A token value passed here would be written into the snippet."
        )
    servers: dict[str, Any] = {}
    for row in res.resolved:
        if row["kind"] != "mcp":
            continue
        entry: dict[str, Any] = {"type": "http", "url": row["url"]}
        if row["name"] == "mcp-search":
            entry["headers"] = {"Authorization": f"Bearer ${{{token_env}}}"}
        servers[row["name"]] = entry
    return {"mcpServers": servers}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--target", choices=list(TARGETS))
    ap.add_argument("--base-url")
    ap.add_argument(
        "--proxied",
        action="store_true",
        help="omit host ports (Caddy/Traefik serves *.digithings.localhost)",
    )
    ap.add_argument("--format", default="env", choices=["env", "json", "opencode", "claude"])
    ap.add_argument(
        "--token-env",
        default="DIGIKEY_LOCAL_TOKEN",
        help="env var name referenced by the Claude snippet, never its value",
    )
    ap.add_argument("--require-all", action="store_true", help="exit 1 if any endpoint skipped")
    args = ap.parse_args(argv)

    try:
        res = resolve(args.target, args.base_url, args.proxied)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.format == "env":
        sys.stdout.write(render_env(res))
    elif args.format == "json":
        json.dump(
            {
                "target": res.target,
                "base_url": res.base_url,
                "contract": res.contract_path,
                "endpoints": res.endpoints,
            },
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
    else:
        payload = (
            render_opencode(res)
            if args.format == "opencode"
            else render_claude(res, args.token_env)
        )
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")

    for row in res.skipped:
        print(
            f"SKIPPED {row['name']}: set {row['requires']} (source: {row['source']})",
            file=sys.stderr,
        )
    if res.skipped and args.require_all:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
