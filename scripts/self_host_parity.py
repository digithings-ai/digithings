#!/usr/bin/env python3
"""Self-host <-> hosted parity checks (DIG-2767, plan section 8 arms a, b and d).

Three checks, three different jobs in one file so they cannot drift apart:

* ``--mode contract``  (arm a) every wrangler binding/var and every compose env
  key maps to a name declared in ``config/contract/``. While ``config/contract/``
  does not exist -- slice S1 has not landed -- this prints ``NOT RUN`` and exits
  3. It never passes vacuously and never guesses the contract's shape.
* ``--mode drift``     (arm d) a new Worker, binding, var or compose env key is
  drift. The committed surface lives in ``config/self-host/parity-baseline.json``
  and a diff against it fails the check.
* ``--mode migrations``(arm b) the apply report from
  ``scripts/self_host_migrations_check.sh --json-out`` must match the recorded
  set of migrations that do NOT apply from an empty database. It is an
  equivalence, not a ratchet: a NEW failure fails, and so does a recorded entry
  that has STOPPED failing (which means the repo fixed it and the baseline is
  now lying about the state of the world).

Only NAMES and binding KINDS are recorded. No value of any variable, binding id,
account id or key is ever read into the baseline or printed.

Usage:
    scripts/self_host_parity.py --mode drift [--update-baseline]
    scripts/self_host_parity.py --mode migrations --report path.json
    scripts/self_host_parity.py --mode contract
    scripts/self_host_parity.py --mode all [--report path.json]

Exit codes: 0 pass, 1 check failed, 2 usage error, 3 not run (missing input).
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = REPO_ROOT / "config" / "self-host" / "parity-baseline.json"
CONTRACT_DIR = REPO_ROOT / "config" / "contract"
# Discovered by census on 2026-10-10 (`git ls-files`). tests/scripts/
# test_self_host_parity.py pins these three counts, so a new compose or
# .env.example file cannot slip in uncovered without turning the test red.
EXPECTED_WRANGLER_FILES = 7
COMPOSE_FILES = (
    "docker-compose.yml",
    "apps/digitrace-langfuse/docker-compose.local.yml",
    "docs/templates/project/docker-compose.yml",
    "infra/digichat-release/compose.digichat-release.yml",
    "infra/digichat-release/compose.profile-a-bundle.override.yml",
    "infra/digichat-release/compose.profile-a-bundle.yml",
    "infra/digichat-release/compose.profile-a.yml",
    "infra/digichat-release/compose.profile-b.yml",
    "infra/self-host/compose.ghcr.yml",
)
ENV_EXAMPLE_FILES = (
    ".env.example",
    "apps/digichat/.env.example",
    "apps/digichat/reference/assistant-ui-templates/base/.env.example",
    "apps/digichat/reference/assistant-ui-templates/expo-react-native/.env.example",
    "digiquant/src/digiquant/research/config/local.env.example",
    "digiquant/src/digiquant/research/config/mcp.secrets.env.example",
    "docs/templates/project/.env.example",
)

# A wrangler key that declares a binding, rather than a plain variable. A new key
# in any of these namespaces is a new capability on the hosted side, so it is
# exactly the drift this check exists to surface.
BINDING_KINDS = {
    "r2_buckets": "r2_bucket",
    "durable_objects": "durable_object_namespace",
    "kv_namespaces": "kv_namespace",
    "d1_databases": "d1_database",
    "services": "service",
    "queues": "queue",
    "containers": "container",
    "analytics_engine_datasets": "analytics_engine_dataset",
    "hyperdrive": "hyperdrive",
    "mtls_certificates": "mtls_certificate",
}
# Container and DO namespacing tables: key is a table name, value is a per-entry key.
NAMESPACED_BINDING_TABLES = {
    "durable_objects": "bindings",
    "kv_namespaces": "id",
}


class ComposeLoader(yaml.SafeLoader):
    """A loader that tolerates Docker Compose's own YAML tags.

    `infra/digichat-release/compose.digichat-release.yml` line 19 uses
    `build: !reset null`, which is a Compose merge directive, not YAML. A plain
    SafeLoader raises on it, so without this the parity check dies on a file that
    is perfectly valid Compose. Unknown tags are read as their scalar value;
    only env KEY names are ever extracted, so the value never matters.
    """


def _unknown_tag(loader: yaml.SafeLoader, tag_suffix: str, node: yaml.Node) -> Any:
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_mapping(node)


ComposeLoader.add_multi_constructor("", _unknown_tag)


def die(msg: str, code: int = 2) -> None:
    print(f"SELF-HOST PARITY: {msg}", file=sys.stderr)
    raise SystemExit(code)


def note(msg: str) -> None:
    print(f"  {msg}")


# ---------------------------------------------------------------- wrangler side
def read_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as fh:
        return tomllib.load(fh)


def wrangler_surface() -> dict[str, dict[str, str]]:
    """Map worker path -> {name: kind} for vars and bindings. Names and kinds only."""
    surface: dict[str, dict[str, str]] = {}
    for path in sorted(REPO_ROOT.rglob("wrangler.toml")):
        if "node_modules" in path.parts:
            continue
        try:
            data = read_toml(path)
        except tomllib.TOMLDecodeError as exc:
            die(f"{path.relative_to(REPO_ROOT)} is not valid TOML: {exc}")
        rel = str(path.relative_to(REPO_ROOT))
        entries: dict[str, str] = {}
        workers = data.get("workers", None)
        # Pages projects keep vars at top level; Workers use [[workers]] or [vars].
        for key, value in (data.get("vars") or {}).items():
            entries[key] = "var"
        for key in ("main", "name", "compatibility_date", "pages_build_output_dir", "account_id"):
            del key  # never recorded: values of these are environment facts
        if isinstance(workers, list):
            for entry in workers:
                for key, _ in (entry.get("vars") or {}).items():
                    entries[key] = "var"
        for table, kind in BINDING_KINDS.items():
            rows = data.get(table)
            # `[[durable_objects.bindings]]` parses as a DICT holding a list,
            # not as a list of tables, so reading it as a list silently drops
            # every Durable Object binding. Handle both shapes.
            if isinstance(rows, dict):
                rows = [
                    row
                    for inner in rows.values()
                    if isinstance(inner, list)
                    for row in inner
                    if isinstance(row, dict)
                ]
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                if table == "containers":
                    name = row.get("class_name") or row.get("name")
                elif table == "durable_objects":
                    name = row.get("name")
                else:
                    name = row.get("binding") or row.get("name")
                if name:
                    entries[str(name)] = kind
                inner = NAMESPACED_BINDING_TABLES.get(table)
                if inner and inner in row:
                    entries[str(row[inner])] = kind
        surface[rel] = dict(sorted(entries.items()))
    return surface


# ---------------------------------------------------------------- compose side
def compose_env_keys(path: Path) -> list[str]:
    """Env KEY names from a compose file. Both `- KEY=` list style and `KEY:` map style."""
    try:
        data = yaml.load(path.read_text(), Loader=ComposeLoader) or {}
    except yaml.YAMLError as exc:
        die(f"{path.relative_to(REPO_ROOT)} is not valid YAML: {exc}")
    keys: set[str] = set()
    for service in (data.get("services") or {}).values():
        if not isinstance(service, dict):
            continue
        env = service.get("environment")
        if isinstance(env, dict):
            keys.update(str(k) for k in env)
        elif isinstance(env, list):
            for item in env:
                if isinstance(item, str):
                    keys.add(item.split("=", 1)[0].strip())
                elif isinstance(item, dict):
                    keys.update(str(k) for k in item)
    return sorted(keys)


def env_example_keys(path: Path) -> list[str]:
    keys: list[str] = []
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key and key.replace("_", "").isalnum() and key[0].isalpha():
            keys.append(key)
    return sorted(set(keys))


def surface_signature() -> dict[str, Any]:
    compose: dict[str, list[str]] = {}
    for rel in COMPOSE_FILES:
        path = REPO_ROOT / rel
        if path.exists():
            compose[rel] = compose_env_keys(path)
    envs: dict[str, list[str]] = {}
    for rel in ENV_EXAMPLE_FILES:
        path = REPO_ROOT / rel
        if path.exists():
            envs[rel] = env_example_keys(path)
    return {
        "wrangler": wrangler_surface(),
        "composeEnv": compose,
        "envExample": envs,
    }


# ------------------------------------------------------------------- baseline io
def load_baseline() -> dict[str, Any]:
    if not BASELINE_PATH.exists():
        die(f"baseline missing: {BASELINE_PATH.relative_to(REPO_ROOT)}")
    return json.loads(BASELINE_PATH.read_text())


def save_baseline(data: dict[str, Any]) -> None:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


# ----------------------------------------------------------------- arm (d) drift
def diff_surface(recorded: dict[str, Any], current: dict[str, Any]) -> list[str]:
    """Every way the committed surface and the tree disagree.

    A pure function on purpose: the interesting cases (a new binding, a new
    compose env key, a deleted file) are cheap to state here and expensive to
    arrange in a real checkout, and a check that can only be exercised against
    the real tree is a check nobody breaks.
    """
    problems: list[str] = []
    for section in ("wrangler", "composeEnv", "envExample"):
        old, new = recorded.get(section, {}), current.get(section, {})
        for path in sorted(set(new) | set(old)):
            if path not in old:
                problems.append(f"NEW {section} file: {path} (added without a baseline entry)")
                continue
            if path not in new:
                problems.append(
                    f"REMOVED {section} file: {path} (delete its baseline entry deliberately)"
                )
                continue
            if section == "wrangler":
                for name, kind in sorted(new[path].items()):
                    prev = old[path].get(name)
                    if prev != kind:
                        detail = f"kind {prev} -> {kind}" if prev else f"new {kind}"
                        problems.append(f"NEW binding/var {name} in {path} ({detail})")
                for name in sorted(set(old[path]) - set(new[path])):
                    problems.append(f"REMOVED binding/var {name} from {path}")
            else:
                for key in sorted(set(new[path]) - set(old[path])):
                    problems.append(f"NEW env key {key} in {path}")
                for key in sorted(set(old[path]) - set(new[path])):
                    problems.append(f"REMOVED env key {key} from {path}")
    return problems


def mode_drift(update: bool) -> int:
    baseline = load_baseline()
    recorded = baseline.get("surface")
    current = surface_signature()
    if update:
        baseline["surface"] = current
        save_baseline(baseline)
        note(f"baseline updated: {BASELINE_PATH.relative_to(REPO_ROOT)}")
        return 0
    if recorded is None:
        die("baseline has no `surface` block; run --update-baseline once and commit it")

    problems = diff_surface(recorded, current)

    counts = {
        "wrangler files": len(current["wrangler"]),
        "wrangler names": sum(len(v) for v in current["wrangler"].values()),
        "compose env keys": sum(len(v) for v in current["composeEnv"].values()),
        "env.example keys": sum(len(v) for v in current["envExample"].values()),
    }
    print("SELF-HOST PARITY: DRIFT")
    for label, value in counts.items():
        note(f"{label:<18} {value}")
    if problems:
        print("SELF-HOST PARITY: FAIL: surface drifted from the baseline")
        for line in problems:
            print(f"  {line}")
        note("Add the capability to config/contract/ (slice S1) and then --update-baseline.")
        return 1
    note("no drift against config/self-host/parity-baseline.json")
    print("SELF-HOST PARITY: PASS (drift)")
    return 0


# ------------------------------------------------------------- arm (b) migrations
def compare_failures(
    measured: dict[str, str], known: dict[str, dict[str, Any]]
) -> tuple[list[str], list[str], list[str]]:
    """Compare the measured from-empty gaps with the recorded ones.

    Returns (new, stale, changed). `stale` is the important half: an equivalence
    that only fails on additions is a ratchet that hides its own repairs, and a
    recorded gap that stopped happening means the baseline is now lying.
    """
    new = sorted(set(measured) - set(known))
    stale = sorted(set(known) - set(measured))
    changed = sorted(
        m
        for m in set(measured) & set(known)
        if known[m].get("error") and measured[m] and known[m]["error"] != measured[m]
    )
    return new, stale, changed


def mode_migrations(report_path: Path | None) -> int:
    if report_path is None:
        print("SELF-HOST PARITY: MIGRATIONS NOT RUN (no --report given)")
        note("arm (b) needs the report written by scripts/self_host_migrations_check.sh --json-out")
        return 3
    if not report_path.exists():
        die(f"migration report not found: {report_path}")
    report = json.loads(report_path.read_text())
    failures = report.get("failures") or []
    baseline = load_baseline().get("migrations") or {}
    known = {row["migration"]: row for row in baseline.get("knownFromEmptyFailures", [])}

    measured = {row["migration"]: row.get("error", "") for row in failures}
    print("SELF-HOST PARITY: MIGRATIONS")
    note(f"applied         {report.get('appliedMigrations')}/{report.get('totalMigrations')}")
    note(f"server          {report.get('serverVersion')}")
    note(f"pinned major    {report.get('pinnedMajorVersion') or 'unknown'}")
    note(f"known gaps      {len(known)} (config/self-host/parity-baseline.json)")

    new, stale, changed = compare_failures(measured, known)
    for m in sorted(measured):
        note(f"does not apply  {m}: {measured[m]}")
    if new or stale or changed:
        print("SELF-HOST PARITY: FAIL: the from-empty migration gaps changed")
        for m in new:
            note(f"NEW failure      {m}: {measured[m]}")
        for m in stale:
            note(f"STALE baseline   {m}: no longer fails -- delete the entry and say why")
        for m in changed:
            note(f"CHANGED error    {m}: {known[m]['error']} -> {measured[m]}")
        return 1
    note("the set of from-empty gaps matches the baseline exactly")
    print("SELF-HOST PARITY: PASS (migrations, against a recorded set of known gaps)")
    return 0


# ---------------------------------------------------------------- arm (a) contract
def mode_contract() -> int:
    print("SELF-HOST PARITY: CONTRACT")
    if not CONTRACT_DIR.exists():
        print("SELF-HOST PARITY: NOT RUN (arm a) -- config/contract/ does not exist")
        note("Slice S1 (DIG-2769) owns config/contract/. Until it lands there is no")
        note("source of truth to map against, and this check must not invent one.")
        return 3
    files = sorted(CONTRACT_DIR.glob("*.y*ml"))
    if not files:
        print("SELF-HOST PARITY: NOT RUN (arm a) -- config/contract/ has no yaml files")
        return 3
    declared: set[str] = set()
    secrets: set[str] = set()
    for path in files:
        data = yaml.safe_load(path.read_text()) or {}
        for section, bucket in (
            ("env", declared),
            ("vars", declared),
            ("bindings", declared),
            ("secrets", secrets),
        ):
            rows = data.get(section) or []
            if isinstance(rows, dict):
                bucket.update(str(k) for k in rows)
            elif isinstance(rows, list):
                for row in rows:
                    if isinstance(row, dict) and row.get("name"):
                        bucket.add(str(row["name"]))
                    elif isinstance(row, str):
                        bucket.add(row)
    surface = surface_signature()
    unmapped: list[str] = []
    for path, entries in surface["wrangler"].items():
        for name in entries:
            if name not in declared and name not in secrets:
                unmapped.append(f"wrangler {path}: {name}")
    for path, keys in surface["composeEnv"].items():
        for key in keys:
            if key not in declared and key not in secrets:
                unmapped.append(f"compose {path}: {key}")
    note(f"declared        {len(declared)} env/vars/bindings + {len(secrets)} secrets")
    note(f"unmapped        {len(unmapped)}")
    if unmapped:
        print(
            "SELF-HOST PARITY: FAIL: names on the deployment surfaces are not in config/contract/"
        )
        for line in unmapped[:80]:
            print(f"  {line}")
        if len(unmapped) > 80:
            note(f"... and {len(unmapped) - 80} more")
        return 1
    print("SELF-HOST PARITY: PASS (contract)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Self-host <-> hosted parity checks.")
    ap.add_argument("--mode", choices=("contract", "drift", "migrations", "all"), default="all")
    ap.add_argument("--report", type=Path, help="migration apply report (--json-out)")
    ap.add_argument("--update-baseline", action="store_true", help="rewrite the surface baseline")
    args = ap.parse_args(argv)

    if args.update_baseline and args.mode not in ("drift", "all"):
        die("--update-baseline is only meaningful with --mode drift")
    codes: list[tuple[str, int]] = []
    if args.mode in ("contract", "all"):
        codes.append(("contract", mode_contract()))
    if args.mode in ("drift", "all"):
        codes.append(("drift", mode_drift(args.update_baseline)))
    if args.mode in ("migrations", "all"):
        codes.append(("migrations", mode_migrations(args.report)))
    if len(codes) == 1:
        # A single --mode returns that mode's own exit code, so a caller (or CI)
        # can tell NOT RUN (3) from PASS (0) without reading the prose.
        return codes[0][1]
    failed = [name for name, code in codes if code == 1]
    not_run = [name for name, code in codes if code == 3]
    if not_run:
        note(f"NOT RUN: {', '.join(not_run)} -- see the reason above; this is not a pass")
    if failed:
        print(f"SELF-HOST PARITY: FAIL ({', '.join(failed)})")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
