#!/usr/bin/env python3
"""R0 private-terms guard (#6751, second tier of the client-literals guard).

The public repo (R0) must not name clients or private vendors. The first-tier
guard (``check_r0_no_client_literals.py``) spells its patterns out in source,
which is itself a leak once that file is public. This tier reads its terms
from a list that never ships in R0:

* in the mono: ``config/private/r0-private-terms.txt`` (mapped out of R0 by
  ``scripts/split/manifest.py``);
* in R0 CI: the ``R0_PRIVATE_TERMS`` environment variable (a repository
  secret, one regex per line), or a file named by ``--terms``.

Which paths count as R0 comes from the split manifest itself, so this guard
and the manifest cannot disagree about what ships.

A path whose own name matches a term counts one extra line, because the
name ships with the file. Every R0 path that still matches a term is grandfathered in
``scripts/r0_private_terms_baseline.json`` with its matching-line count. The
gate fails when a path matches without an entry (NEW), when a count moved
(COUNT: lower it in the same diff that removes the lines), or when an entry no
longer matches (STALE). With ``--base-ref`` it also fails when the baseline
grew against the base branch (GROWTH): the list may only shrink. A base branch
that does not have the baseline yet is skipped, which only happens on the
change that introduces this guard.

Output names paths and line counts, never a term or a matched value: CI logs on the public repo are public.

Exit codes: 0 clean, 1 findings, 2 tool error (no terms, unreadable baseline).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TERMS_REL = "config/private/r0-private-terms.txt"
BASELINE_REL = "scripts/r0_private_terms_baseline.json"
TERMS_ENV = "R0_PRIVATE_TERMS"
MANIFEST_REL = "scripts/split/manifest.py"
#: Derived lists of R0 paths. They repeat path names the census already
#: counts against the path itself, so scanning them would double-count.
DERIVED_LISTS = frozenset({BASELINE_REL, "scripts/split/r0-allowlist.txt"})


class ToolError(RuntimeError):
    """The gate could not measure; it fails closed."""


def parse_terms(text: str) -> list[re.Pattern[str]]:
    terms = []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            terms.append(re.compile(line, re.IGNORECASE))
    return terms


def load_terms(root: Path, terms_file: str | None) -> list[re.Pattern[str]]:
    if terms_file:
        text = Path(terms_file).read_text(encoding="utf-8")
    elif os.environ.get(TERMS_ENV):
        text = os.environ[TERMS_ENV]
    elif (root / TERMS_REL).exists():
        text = (root / TERMS_REL).read_text(encoding="utf-8")
    else:
        raise ToolError(f"no terms: set {TERMS_ENV}, pass --terms, or provide {TERMS_REL}")
    terms = parse_terms(text)
    if not terms:
        raise ToolError("the terms list is empty")
    return terms


def load_manifest(root: Path):
    path = root / MANIFEST_REL
    spec = importlib.util.spec_from_file_location("split_manifest", path)
    if spec is None or spec.loader is None:
        raise ToolError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def r0_paths(root: Path) -> list[str]:
    """Tracked paths that ship in R0.

    In the mono the split manifest decides. R0 itself has no manifest (the
    split tooling is mono-only), and there every tracked path is public.
    """
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"], capture_output=True, text=True, check=True
    )
    paths = [p for p in out.stdout.split("\0") if p]
    if not (root / MANIFEST_REL).exists():
        return sorted(paths)
    mod = load_manifest(root)
    return sorted(p for p in paths if (mod.match_rule(p) or ("",))[0] == "R0")


def count_lines(path: Path, terms: list[re.Pattern[str]]) -> int:
    try:
        raw = path.read_bytes()
    except OSError:
        return 0
    if b"\x00" in raw[:8192]:
        return 0
    text = raw.decode("utf-8", errors="replace")
    return sum(1 for line in text.splitlines() if any(t.search(line) for t in terms))


def census(root: Path, terms: list[re.Pattern[str]]) -> dict[str, int]:
    found = {}
    for rel in r0_paths(root):
        if rel in DERIVED_LISTS:
            continue
        # A path whose own name matches counts one extra line: the name ships too.
        n = count_lines(root / rel, terms) + (1 if any(t.search(rel) for t in terms) else 0)
        if n:
            found[rel] = n
    return found


def parse_baseline(raw: str, source: str) -> dict[str, int]:
    try:
        entries = json.loads(raw)["entries"]
    except (ValueError, KeyError, TypeError) as exc:
        raise ToolError(f"{source}: malformed baseline ({exc})") from exc
    if not isinstance(entries, dict) or not all(isinstance(v, int) for v in entries.values()):
        raise ToolError(f"{source}: entries must map path -> int")
    return entries


def check(found: dict[str, int], baseline: dict[str, int]) -> list[str]:
    fails = []
    for rel in sorted(found):
        if rel not in baseline:
            fails.append(f"NEW {rel}: {found[rel]} matching line(s); remove them, or map the path out of R0")
        elif baseline[rel] != found[rel]:
            fails.append(f"COUNT {rel}: baseline {baseline[rel]}, measured {found[rel]}")
    for rel in sorted(set(baseline) - set(found)):
        fails.append(f"STALE {rel}: no longer matches; delete its entry")
    return fails


def growth(baseline: dict[str, int], base: dict[str, int]) -> list[str]:
    fails = []
    for rel in sorted(baseline):
        if rel not in base:
            fails.append(f"GROWTH {rel}: new baseline entry; remove the lines instead")
        elif baseline[rel] > base[rel]:
            fails.append(f"GROWTH {rel}: count {base[rel]} -> {baseline[rel]}")
    return fails


def base_baseline(root: Path, base_ref: str) -> dict[str, int] | None:
    out = subprocess.run(
        ["git", "-C", str(root), "show", f"{base_ref}:{BASELINE_REL}"], capture_output=True, text=True
    )
    if out.returncode != 0:
        probe = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", f"{base_ref}^{{commit}}"],
            capture_output=True,
            text=True,
        )
        if probe.returncode != 0:
            raise ToolError(f"cannot resolve base ref {base_ref}")
        return None
    return parse_baseline(out.stdout, f"{base_ref}:{BASELINE_REL}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(REPO_ROOT))
    ap.add_argument("--terms", help="file with one regex per line (default: env, then the mono file)")
    ap.add_argument("--base-ref", help="also fail if the baseline grew against this ref")
    ap.add_argument("--write-baseline", action="store_true", help="rewrite the baseline from the census")
    args = ap.parse_args(argv)
    root = Path(args.root)
    try:
        terms = load_terms(root, args.terms)
        found = census(root, terms)
        if args.write_baseline:
            body = {
                "_comment": "Grandfathered R0 paths that still match a private term (#6751). "
                "May only shrink. Regenerate with --write-baseline after removing lines.",
                "entries": dict(sorted(found.items())),
            }
            (root / BASELINE_REL).write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
            print(f"r0-private-terms: wrote {len(found)} entries to {BASELINE_REL}")
            return 0
        baseline = parse_baseline((root / BASELINE_REL).read_text(encoding="utf-8"), BASELINE_REL)
        fails = check(found, baseline)
        if args.base_ref:
            base = base_baseline(root, args.base_ref)
            if base is not None:
                fails += growth(baseline, base)
    except (ToolError, OSError, subprocess.CalledProcessError) as exc:
        print(f"r0-private-terms: TOOL ERROR: {exc}", file=sys.stderr)
        return 2
    if fails:
        print(f"r0-private-terms: {len(fails)} finding(s)")
        for f in fails:
            print(f"  FAIL  {f}")
        return 1
    total = sum(found.values())
    print(f"r0-private-terms: clean; {len(found)} grandfathered path(s), {total} line(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
