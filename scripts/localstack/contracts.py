"""The local-stack service catalogue.

Every default URL in ``BUILTIN_CHECKS`` is **sourced**: the ``source`` field
records the file and line, or the documented tool default, it came from. A
reader can re-derive each one. An unsourced default is a defect, so the ones we
could not source are declared with ``url=None`` and a ``requires`` key instead
of an invented path -- they report ``skipped`` until configured and never
``passed``.

On top of the built-in list this module **feature-detects** the S1 config
contract so that when the contract lands (DIG-2759 / DIG-2769, two competing
implementations) the gate picks it up with no code change. Two shapes are
accepted because two S1 PRs are open and this leaf must not invent a third:

* ``config/contract/services.yaml``  (PR #5352)
* ``config/contract/contract.yaml``  (PR #5359)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

PROFILES: tuple[str, ...] = ("core", "quant", "chat", "trace", "all")

#: Contract paths probed, in priority order. Both are read-only probes.
CONTRACT_PATHS: tuple[str, ...] = (
    "config/contract/services.yaml",
    "config/contract/contract.yaml",
)

#: Statuses a check can report. ``skipped`` is load-bearing: it is how a check
#: that could not run is distinguished from one that passed.
PASSED = "passed"
FAILED = "failed"
SKIPPED = "skipped"


@dataclass(frozen=True)
class Check:
    """One health probe."""

    name: str
    kind: str
    #: Absolute or relative URL, or ``None`` when the check needs configuration.
    url: str | None
    #: Which ``--profile`` values include this check.
    profiles: tuple[str, ...]
    #: Where the default came from -- a ``file:line`` or a documented default.
    source: str
    #: Config key that must be set for this check to run. ``None`` = always runnable.
    requires: str | None = None
    method: str = "GET"
    expect_status: tuple[int, ...] = (200,)
    #: Path used to read back a value written by a ``roundtrip`` check.
    read_path: str | None = None

    def in_profile(self, profile: str) -> bool:
        return profile in self.profiles or "all" in self.profiles

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "url": self.url,
            "profiles": list(self.profiles),
            "source": self.source,
            "requires": self.requires,
            "method": self.method,
            "expect_status": list(self.expect_status),
            "read_path": self.read_path,
        }


_ALL = ("all",)
_CORE = ("core",)
_QUANT = ("core", "quant")
_CHAT = ("core", "chat")
_TRACE = ("core", "trace")


BUILTIN_CHECKS: tuple[Check, ...] = (
    # ── supabase (plan section 6: REST + auth) ───────────────────────────────
    # Supabase CLI local defaults, documented in the plan; overridable via the
    # contract or DT_SUPABASE_URL / DT_SUPABASE_AUTH_URL.
    Check(
        name="supabase-rest",
        kind="http",
        url="http://127.0.0.1:54321/rest/v1/",
        profiles=_CORE,
        source="supabase local default API_PORT 54321 (plan section 3, step 3)",
    ),
    Check(
        name="supabase-auth",
        kind="http",
        url="http://127.0.0.1:54321/auth/v1/health",
        profiles=_CORE,
        source="supabase local default API_PORT 54321 (plan section 3, step 3)",
    ),
    # ── python services: every path below read out of the service source ────
    Check(
        name="digikey",
        kind="http",
        url="http://127.0.0.1:8005/healthz",
        profiles=_ALL,
        source="digikey/src/digikey/server.py:116",
    ),
    Check(
        name="digigraph",
        kind="http",
        url="http://127.0.0.1:8000/healthz",
        profiles=_ALL,
        source="digigraph/src/digigraph/server.py:321",
    ),
    Check(
        name="digisearch",
        kind="http",
        url="http://127.0.0.1:8002/healthz",
        profiles=_ALL,
        source="digisearch/src/digisearch/server.py:558",
    ),
    Check(
        name="digivault",
        kind="http",
        url="http://127.0.0.1:8004/healthz",
        profiles=("core", "quant", "all"),
        source="digivault/src/digivault/server.py:532",
    ),
    Check(
        name="digitrace",
        kind="http",
        url="http://127.0.0.1:8003/healthz",
        profiles=_TRACE,
        source="digitrace/src/digitrace/server.py:59",
    ),
    Check(
        name="digichat",
        kind="http",
        url="http://127.0.0.1:3000/api/health",
        profiles=_CHAT,
        source="Makefile target digichat-health (curl -sf 127.0.0.1:3000/api/health)",
    ),
    # ── checks with no source we are willing to fake ────────────────────────
    # The wrangler-dev port table is owned by S3 (PR #5353), the contract by S1.
    Check(
        name="dashboard-api",
        kind="http",
        url=None,
        profiles=("core", "chat", "all"),
        source="apps/dashboard-api/src/index.ts serves /healthz; port owned by S3",
        requires="DT_DASHBOARD_API_URL",
    ),
    Check(
        name="mcp-tools-list",
        kind="jsonrpc",
        url=None,
        profiles=("core", "quant", "all"),
        source=(
            "no MCP HTTP tools/list path is declared in our source; the mcp "
            "library owns the protocol and S3 owns the transport port"
        ),
        requires="DT_MCP_URL",
        method="POST",
    ),
    Check(
        name="digitrace-ingest-roundtrip",
        kind="roundtrip",
        url=None,
        profiles=_TRACE,
        source=(
            "digitrace/src/digitrace/server.py exposes /healthz and /v1/status "
            "only; there is no ingest route in source to round-trip against"
        ),
        requires="DT_DIGITRACE_INGEST_URL",
    ),
    Check(
        name="r2-put-get",
        kind="roundtrip",
        url=None,
        profiles=_ALL,
        source="R2 local binding ids are generated by S3 (PR #5353)",
        requires="DT_R2_URL",
    ),
    Check(
        name="kv-put-get",
        kind="roundtrip",
        url=None,
        profiles=_ALL,
        source="KV local binding ids are generated by S3 (PR #5353)",
        requires="DT_KV_URL",
    ),
    Check(
        name="d1-put-get",
        kind="roundtrip",
        url=None,
        profiles=_ALL,
        source="D1 local binding ids are generated by S3 (PR #5353)",
        requires="DT_D1_URL",
    ),
)


def _load_yaml(path: Path) -> Any:
    """Load YAML, or JSON if the file is JSON. Never guesses."""
    text = path.read_text(encoding="utf-8")
    try:
        import yaml
    except ModuleNotFoundError as exc:  # pragma: no cover - env guard
        raise RuntimeError(
            f"contract {path} found but PyYAML is not installed; "
            "run through the repo venv (uv run --frozen)"
        ) from exc
    try:
        return yaml.safe_load(text)
    except Exception:  # pragma: no cover - fall through to the JSON reader
        return json.loads(text)


def _normalise_profiles(raw: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    if raw is None:
        return default
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, list) and all(isinstance(x, str) for x in raw):
        return tuple(raw)
    return default


def _compose_url(port: Any, path: Any, host: str = "127.0.0.1") -> str | None:
    if port is None:
        return None
    suffix = path if isinstance(path, str) and path.startswith("/") else ""
    return f"http://{host}:{int(port)}{suffix or '/healthz'}"


def checks_from_contract(doc: Any) -> tuple[Check, ...]:
    """Build checks from either accepted S1 contract shape.

    Accepts a bare list, or a mapping whose ``services`` value is the list.
    Per-row keys are tolerant (``url``/``health_url``, ``port``+``health_path``)
    because two S1 PRs are open and neither has merged. Rows we cannot read are
    skipped rather than guessed at.
    """
    rows: Any = doc
    if isinstance(doc, dict):
        rows = doc.get("services")
        if rows is None:
            rows = doc.get("checks")
    if not isinstance(rows, list):
        return ()

    out: list[Check] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("name") or row.get("id")
        if not isinstance(name, str):
            continue
        url = row.get("url") or row.get("health_url")
        if not isinstance(url, str) or not url:
            url = _compose_url(row.get("port"), row.get("health_path"))
        out.append(
            Check(
                name=name,
                kind=str(row.get("kind") or "http"),
                url=url,
                profiles=_normalise_profiles(row.get("profiles"), _ALL),
                source=f"config contract row {name!r}",
                requires=row.get("requires"),
                method=str(row.get("method") or "GET").upper(),
            )
        )
    return tuple(out)


def load_checks(root: Path) -> tuple[tuple[Check, ...], str]:
    """Return ``(checks, origin)`` for the stack rooted at ``root``.

    ``origin`` names where the catalogue came from, so a gate run can always
    say whether it used a contract or the built-in defaults.
    """
    for rel in CONTRACT_PATHS:
        candidate = root / rel
        if not candidate.is_file():
            continue
        checks = checks_from_contract(_load_yaml(candidate))
        if checks:
            return merge_contract(checks), rel
    return BUILTIN_CHECKS, "built-in defaults"


def merge_contract(checks: tuple[Check, ...]) -> tuple[Check, ...]:
    """Overlay contract rows onto the built-ins, matched by name.

    A contract can retune or replace a built-in row. It cannot delete one: the
    plan names the surfaces, so a contract that simply omits ``digichat`` must
    not silently stop probing it.
    """
    by_name = {c.name: c for c in checks}
    merged: list[Check] = []
    for builtin in BUILTIN_CHECKS:
        override = by_name.pop(builtin.name, None)
        if override is None:
            merged.append(builtin)
            continue
        merged.append(
            replace(
                builtin,
                url=override.url or builtin.url,
                profiles=override.profiles,
                method=override.method,
                kind=override.kind if override.kind else builtin.kind,
            )
        )
    merged.extend(by_name.values())
    return tuple(merged)


def select(checks: tuple[Check, ...], profile: str) -> tuple[Check, ...]:
    """Checks in ``profile``; ``all`` selects everything."""
    if profile == "all":
        return checks
    return tuple(c for c in checks if c.in_profile(profile))


def resolve(check: Check, config: dict[str, str]) -> tuple[str | None, str | None]:
    """Resolve a check's URL from configuration.

    Returns ``(url, skip_reason)``. Exactly one is ``None``. A check that needs
    configuration and has none is *skipped with a reason* -- never passed.
    """
    if check.requires:
        value = config.get(check.requires)
        if not value:
            return None, f"{check.requires} not set"
        # Returned exactly as configured: a local binding route is keyed on the
        # path it is given, so appending or stripping a trailing slash here
        # would silently address a route that does not exist.
        return value, None
    return check.url, None
