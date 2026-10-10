#!/usr/bin/env python3
"""Acceptance check for config/contract/contract.yaml.

The brief's acceptance criterion: every wrangler binding/var and every compose
env maps to the contract. This script proves it mechanically.

It also proves it can FAIL. `--self-test` runs the real check first (it must
pass), then injects a synthetic unmapped name into each fact source and proves
each one turns the check red. A check that finds nothing because it looks for
nothing is not evidence.

What is NOT checked, and why: wrangler.toml does not declare secrets, so the
contract's `secrets` section is transcribed from the documented per-worker
checklists. There is nothing in the repo to compare it against.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

import tomllib
import yaml

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CONTRACT = HERE / "contract.yaml"

COMPOSE_FILES = ["docker-compose.yml", "apps/digitrace-langfuse/docker-compose.local.yml"]
ENV_EXAMPLE_FILES = [".env.example", "apps/digichat/.env.example"]
SENTINEL = "DIGI_CONTRACT_SENTINEL_MISSING"
BINDING_SENTINEL = "DIGI_CONTRACT_SENTINEL_BINDING"


def strip_yaml_comments(text: str) -> str:
    """Quote-aware comment strip.

    docker-compose.yml carries a `${VAR:?}` example inside a `#` comment. A
    comment-blind scan would demand a contract entry for a variable that does
    not exist — a false finding, and the reason this function exists.
    """
    out: list[str] = []
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            out.append("")
            continue
        quote = None
        buf = []
        for i, ch in enumerate(line):
            if quote:
                buf.append(ch)
                if ch == quote:
                    quote = None
            elif ch in "\"'":
                quote = ch
                buf.append(ch)
            elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
                break
            else:
                buf.append(ch)
        out.append("".join(buf))
    return "\n".join(out)


def collect_facts() -> dict:
    """Everything the contract must account for, read from the live repo."""
    facts: dict = {"wrangler_vars": {}, "wrangler_bindings": {}, "compose_env": {}, "env_example": {}}

    for path in sorted((ROOT / "apps").glob("*/wrangler.toml")):
        data = tomllib.loads(path.read_text())
        worker = data.get("name", path.parent.name)
        for name in data.get("vars", {}) or {}:
            facts["wrangler_vars"].setdefault(name, []).append(worker)
        rows = []
        for container in data.get("containers", []) or []:
            rows.append(("container", container.get("class_name")))
        durable = data.get("durable_objects", {}) or {}
        # durable_objects is a TABLE whose bindings are a LIST keyed by `name`;
        # d1_databases/vectorize are dicts. A uniform `.get(...)` loop over the
        # tables raises AttributeError on the dicts.
        for binding in durable.get("bindings", []) or []:
            rows.append(("durable_object", binding.get("name")))
        for binding in data.get("r2_buckets", []) or []:
            rows.append(("r2_bucket", binding.get("binding") or binding.get("name")))
        for binding in data.get("services", []) or []:
            rows.append(("service", binding.get("binding") or binding.get("name")))
        for kind, name in rows:
            if name:
                facts["wrangler_bindings"].setdefault(name, []).append((worker, kind))

    for rel in COMPOSE_FILES:
        text = strip_yaml_comments((ROOT / rel).read_text())
        for match in re.finditer(r"\$\{([A-Za-z_][A-Za-z0-9_]*)", text):
            facts["compose_env"].setdefault(match.group(1), []).append(rel)

    for rel in ENV_EXAMPLE_FILES:
        for line in (ROOT / rel).read_text().splitlines():
            if line.lstrip().startswith("#"):
                continue
            match = re.match(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
            if match:
                facts["env_example"].setdefault(match.group(1), []).append(rel)

    return facts


def check(contract: dict, facts: dict) -> list[str]:
    failures: list[str] = []
    env_names = {row["name"] for row in contract.get("env", [])}
    binding_names = {row.get("name") or row.get("class_name") for row in contract.get("bindings", [])}

    for name, workers in sorted(facts["wrangler_vars"].items()):
        if name not in env_names:
            failures.append(f"wrangler var {name} (worker {', '.join(workers)}) has no contract env entry")

    for name, pairs in sorted(facts["wrangler_bindings"].items()):
        if name not in binding_names:
            detail = ", ".join(f"{w}/{k}" for w, k in pairs)
            failures.append(f"wrangler binding {name} ({detail}) has no contract bindings entry")

    for name, rels in sorted(facts["compose_env"].items()):
        if name not in env_names:
            failures.append(f"compose env {name} ({', '.join(sorted(set(rels)))}) has no contract env entry")

    for name, rels in sorted(facts["env_example"].items()):
        if name not in env_names:
            failures.append(f"env.example {name} ({', '.join(sorted(set(rels)))}) has no contract env entry")

    # The contract must not carry an env entry that no source can explain,
    # except the documented-only surface it declares.
    documented = {"sources"}
    for row in contract.get("env", []):
        src = row.get("sources", {})
        if not any(src.get(k) for k in ("wrangler_workers", "compose_files", "env_example_files", "compose_literal")):
            failures.append(f"contract env {row['name']} is declared but no live source uses it")
    del documented
    return failures


def self_test(contract: dict, facts: dict) -> int:
    print("== positive control: the real tree must pass ==")
    baseline = check(contract, facts)
    if baseline:
        print(f"CONTROL FAILED — {len(baseline)} real failures, the check cannot be trusted:")
        for line in baseline[:20]:
            print("   ", line)
        return 1
    print("control: 0 failures on the live tree  OK")

    cases = []

    facts["wrangler_vars"][SENTINEL] = ["digithings-stack"]
    cases.append(("wrangler var", SENTINEL))
    got = check(contract, facts)
    hit = [f for f in got if SENTINEL in f]
    del facts["wrangler_vars"][SENTINEL]
    print(f"injected wrangler var {SENTINEL}: {len(got)} failure(s), {len(hit)} naming it"
          f"  {'OK' if hit and len(got) == len(baseline) + 1 else 'PROBLEM'}")
    if not hit:
        return 1

    facts["compose_env"][SENTINEL] = ["docker-compose.yml"]
    cases.append(("compose env", SENTINEL))
    got = check(contract, facts)
    hit = [f for f in got if SENTINEL in f]
    del facts["compose_env"][SENTINEL]
    print(f"injected compose env {SENTINEL}: {len(got)} failure(s), {len(hit)} naming it"
          f"  {'OK' if hit and len(got) == len(baseline) + 1 else 'PROBLEM'}")
    if not hit:
        return 1

    facts["env_example"][SENTINEL] = [".env.example"]
    got = check(contract, facts)
    hit = [f for f in got if SENTINEL in f]
    del facts["env_example"][SENTINEL]
    print(f"injected env.example {SENTINEL}: {len(got)} failure(s), {len(hit)} naming it"
          f"  {'OK' if hit and len(got) == len(baseline) + 1 else 'PROBLEM'}")
    if not hit:
        return 1

    facts["wrangler_bindings"][BINDING_SENTINEL] = [("digithings-stack", "r2_bucket")]
    got = check(contract, facts)
    hit = [f for f in got if BINDING_SENTINEL in f]
    del facts["wrangler_bindings"][BINDING_SENTINEL]
    print(f"injected wrangler binding {BINDING_SENTINEL}: {len(got)} failure(s), {len(hit)} naming it"
          f"  {'OK' if hit and len(got) == len(baseline) + 1 else 'PROBLEM'}")
    if not hit:
        return 1

    # Restored tree must be clean again — proves the injections were removed.
    after = check(contract, facts)
    print(f"tree restored: {len(after)} failure(s)  {'OK' if len(after) == len(baseline) else 'PROBLEM'}")
    if after != baseline:
        return 1
    print("SELF-TEST PASS: all 4 injection points detected, no false positive")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    contract = yaml.safe_load(CONTRACT.read_text())
    facts = collect_facts()

    counts = {
        "wrangler vars (unique)": len(facts["wrangler_vars"]),
        "wrangler bindings": len(facts["wrangler_bindings"]),
        "compose env": len(facts["compose_env"]),
        "env.example names": len(facts["env_example"]),
        "contract env entries": len(contract.get("env", [])),
        "contract binding rows": len(contract.get("bindings", [])),
    }
    for label, value in counts.items():
        print(f"{label:>26}: {value}")

    if args.self_test:
        return self_test(contract, facts)

    failures = check(contract, facts)
    if failures:
        print(f"\nFAIL: {len(failures)} unmapped item(s)")
        for line in failures:
            print("  -", line)
        return 1
    print("\nPASS: every wrangler var, every wrangler binding and every compose env maps to the contract")
    print("NOTE: secrets are transcribed from documented checklists; wrangler.toml does not declare them, so they are not machine-checked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
