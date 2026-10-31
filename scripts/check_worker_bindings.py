#!/usr/bin/env python3
"""Refuse a placeholder binding id in a Worker config that a deploy lane ships.

WHY THIS EXISTS. The first `digitrace-ingest` deploy (run 40525849901,
2026-10-27) paid the whole production approval, bundled the Worker, and then
died inside the Cloudflare API:

    KV namespace '00000000000000000000000000000000' not found. [code: 10041]

`apps/digitrace-ingest/wrangler.toml` still carried the documented placeholder.
Nothing in the repo could have said so. `wrangler deploy --dry-run` is the only
gate before the API call, and a dry run does not ask the account whether a
namespace exists -- it bundles the Worker and stops. So an all-zero id is
invisible to every existing check right up to the one place a failure is
expensive: an approved production deploy.

WHAT THIS CHECKS. Only the id fields whose value must exist in the account:

- ``[[kv_namespaces]] id``          -- 32 hex characters
- ``[[d1_databases]] database_id``  -- a UUID
- ``[[hyperdrive]] id``             -- a UUID

A value is a placeholder when it is all zeros at the binding's width, when it is
one of the template words (``REPLACE_ME``, ``CHANGEME``, ``TODO``), or when it
is a ``<...>`` template. A documented *local-only* stand-in such as digidata-api's
``00000000-0000-0000-0000-00000000d1a1`` is not all zeros, so it is not flagged:
the rule is "this id cannot exist in any account", not "this id looks unfamiliar".

MODES

``--config PATH``  check one config. A deploy lane runs this immediately before
                   ``wrangler deploy``, so a placeholder fails in seconds with
                   the command that fixes it instead of at the API call.
``--all``          check every ``apps/*/wrangler.toml``. An audit mode: it is
                   deliberately not wired into CI while dormant, never-deployed
                   configs still carry a placeholder.

Exit 0 when every checked config is clean, 1 when at least one is not, 2 on a
usage error (a missing or unreadable config), so a typo cannot read as a pass.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Table name -> (id key, what the id must be, the command that mints a real one).
BINDING_KINDS: dict[str, tuple[str, str, str]] = {
    "kv_namespaces": (
        "id",
        "a KV namespace id",
        "npx wrangler kv namespace create <name>",
    ),
    "d1_databases": (
        "database_id",
        "a D1 database id",
        "npx wrangler d1 create <name>",
    ),
    "hyperdrive": (
        "id",
        "a Hyperdrive config id",
        "npx wrangler hyperdrive create <name> --connection-string=...",
    ),
}

TEMPLATE_WORDS = {"replace_me", "replaceme", "changeme", "change_me", "todo", "tbd"}

_HEADER_RE = re.compile(r"^\s*\[\[?\s*([A-Za-z0-9_.\"'-]+)\s*\]\]?\s*(?:#.*)?$")
_VALUE_RE = re.compile(r'^\s*([A-Za-z0-9_-]+)\s*=\s*"([^"]*)"')


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    table: str
    binding: str
    key: str
    value: str
    hint: str


def is_placeholder(value: str) -> bool:
    """True when ``value`` cannot be a real id in any account.

    The judgement is deliberately narrow. A false positive blocks a deploy lane
    that would have worked, so only shapes that provably cannot exist are
    flagged: all zeros of a binding's width, an unresolved template, or a
    ``<...>`` slot.
    """
    text = value.strip()
    if not text:
        return True
    if text.lower() in TEMPLATE_WORDS:
        return True
    if text.startswith("<") and text.endswith(">"):
        return True
    digits = text.replace("-", "")
    return set(digits) == {"0"}


def _table_name(header: str) -> str:
    """``env.production.kv_namespaces`` -> ``kv_namespaces``; keep quotes out."""
    return header.split(".")[-1].strip("\"'")


def scan_text(text: str, path: str) -> list[Finding]:
    """Find placeholder binding ids in one wrangler config's text."""
    findings: list[Finding] = []
    table = ""
    binding = ""
    for number, raw in enumerate(text.splitlines(), start=1):
        header = _HEADER_RE.match(raw)
        if header:
            table = _table_name(header.group(1))
            binding = ""
            continue
        if table not in BINDING_KINDS:
            continue
        key = BINDING_KINDS[table][0]
        value = _VALUE_RE.match(raw)
        if not value:
            continue
        name, literal = value.group(1), value.group(2)
        if name == "binding":
            binding = literal
        elif name == key and is_placeholder(literal):
            _, what, command = BINDING_KINDS[table]
            app_dir = str(Path(path).parent) if path.endswith("wrangler.toml") else "this app"
            findings.append(
                Finding(
                    path=path,
                    line=number,
                    table=table,
                    binding=binding or "?",
                    key=key,
                    value=literal,
                    hint=(
                        f"{binding or 'this binding'} expects {what} that exists in the "
                        f"account this lane deploys to. Create it first, then put the "
                        f"returned id here -- from {app_dir}: {command}"
                    ),
                )
            )
    return findings


def scan_config(path: Path, display: str | None = None) -> list[Finding]:
    return scan_text(path.read_text(encoding="utf-8"), display or str(path))


def configs_in(root: Path) -> list[Path]:
    apps = root / "apps"
    if not apps.is_dir():
        return []
    return sorted(apps.glob("*/wrangler.toml"))


def _format(findings: list[Finding]) -> str:
    lines = []
    for finding in findings:
        lines.append(
            f"{finding.path}:{finding.line}: [[{finding.table}]] binding={finding.binding} "
            f"{finding.key}={finding.value}"
        )
        lines.append(f"  {finding.hint}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Refuse a placeholder binding id in a Worker config.",
    )
    parser.add_argument(
        "--config",
        action="append",
        default=[],
        metavar="PATH",
        help="check one wrangler config (repeatable). A deploy lane uses this.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="check every apps/*/wrangler.toml (audit mode).",
    )
    parser.add_argument(
        "--root",
        default=str(REPO_ROOT),
        help="repository root (default: the directory above this script).",
    )
    args = parser.parse_args(argv)

    if not args.config and not args.all:
        parser.error("give at least one --config PATH, or --all")

    targets: list[tuple[Path, str]] = []
    for value in args.config:
        path = Path(value)
        if not path.is_absolute():
            path = Path(args.root) / path
        targets.append((path, value))
    if args.all:
        root = Path(args.root)
        targets.extend((path, str(path.relative_to(root))) for path in configs_in(root))

    findings: list[Finding] = []
    missing: list[str] = []
    for path, display in targets:
        if not path.is_file():
            missing.append(display)
            continue
        findings.extend(scan_config(path, display))

    if missing:
        print("check_worker_bindings: config not found: " + ", ".join(missing), file=sys.stderr)
        return 2

    if findings:
        print(_format(findings))
        print(
            f"\ncheck_worker_bindings: {len(findings)} placeholder binding id(s). "
            "A placeholder cannot exist in the account, so the deploy lane would fail at "
            "the Cloudflare API call, after the approval.",
            flush=True,
        )
        return 1

    print(f"check_worker_bindings: {len(targets)} config(s) clean.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
