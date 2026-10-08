#!/usr/bin/env python3
"""QA mutation harness for PR #5232 (DIG-1597 / DIG-1659).

Reads a JSON batch of mutants, applies each one by literal string replacement,
runs the sdca suite, and classifies: CAUGHT (suite failed) / SURVIVED (suite
passed) / SYNTAX-ERROR / ANCHOR-ERROR. Reverts after every mutant.

Mutant schema:
  id       str   label
  file     str   repo-relative path
  find     str   literal anchor
  replace  str   replacement
  claim    str   the PR claim this mutant attacks
  expect   int   required occurrence count of `find` (default 1)
  occ      int   zero-based index of the occurrence to patch (default 0)
  node     str   optional pytest node id to run instead of the whole suite
"""
from __future__ import annotations

import argparse
import ast
import json
import pathlib
import subprocess
import sys
import time

REPO = pathlib.Path(
    "/Users/chrisstefan/Code/digithings/.paperclip/worktrees/"
    "DIG-1597-port-the-sdca-research-subsystem-from-claude-sdca-develop-sync"
)
PY = "/Users/chrisstefan/Code/digithings/.venv/bin/python"


def env() -> dict[str, str]:
    import os

    e = dict(os.environ)
    e["PYTHONPATH"] = ":".join(
        [
            str(REPO / "digiquant/src"),
            str(REPO / "digibase/src"),
            str(REPO / "digikey/src"),
            str(REPO / "digidata/src"),
        ]
    )
    return e


def run_suite(node: str | None = None) -> int:
    target = node if node else "tests/dq/strategies/sdca/"
    cmd = [PY, "-m", "pytest", target, "-q", "--no-header", "-p", "no:randomly"]
    return subprocess.run(cmd, cwd=REPO, env=env(), capture_output=True, text=True).returncode


def tree_clean() -> bool:
    r = subprocess.run(
        ["git", "status", "--porcelain"], cwd=REPO, capture_output=True, text=True
    )
    return r.stdout.strip() == ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("batch")
    ap.add_argument("--skip-baseline", action="store_true")
    args = ap.parse_args()

    here = pathlib.Path(__file__).parent
    batch_path = here / f"{args.batch}.json"
    mutants = json.loads(batch_path.read_text())

    if not args.skip_baseline:
        t0 = time.time()
        rc = run_suite()
        print(f"BASELINE rc={rc} in {time.time()-t0:.1f}s")
        if rc != 0:
            print("BASELINE NOT GREEN - aborting, mutants would be meaningless")
            return 3

    results = []
    for m in mutants:
        path = REPO / m["file"]
        original = path.read_text()
        find, repl = m["find"], m["replace"]
        occ = m.get("occ", 0)
        expect = m.get("expect", 1)

        count = original.count(find)
        if count != expect:
            verdict = f"ANCHOR-ERROR count={count} expected={expect}"
            results.append({**{k: m.get(k) for k in ("id", "file", "claim")},
                            "verdict": verdict})
            print(f"[{m['id']}] {verdict}", flush=True)
            continue

        idx = -1
        for _ in range(occ + 1):
            idx = original.find(find, idx + 1)
        patched = original[:idx] + repl + original[idx + len(find):]

        try:
            ast.parse(patched)
        except SyntaxError as exc:
            verdict = f"SYNTAX-ERROR {exc}"
            path.write_text(original)
            results.append({**{k: m.get(k) for k in ("id", "file", "claim")},
                            "verdict": verdict})
            print(f"[{m['id']}] {verdict}", flush=True)
            continue

        path.write_text(patched)
        t0 = time.time()
        rc = run_suite(m.get("node"))
        dt = time.time() - t0
        path.write_text(original)
        subprocess.run(["git", "checkout", "--", m["file"]], cwd=REPO, capture_output=True)

        if rc == 0:
            verdict = "SURVIVED"
        elif rc == 1:
            verdict = "CAUGHT"
        else:
            verdict = f"INTERRUPTED rc={rc}"

        results.append({
            "id": m["id"], "file": m["file"], "claim": m["claim"],
            "verdict": verdict, "seconds": round(dt, 1),
        })
        print(f"[{m['id']}] {verdict} ({dt:.1f}s) - {m['claim']}", flush=True)

    caught = [r for r in results if r["verdict"] == "CAUGHT"]
    survived = [r for r in results if r["verdict"] == "SURVIVED"]
    broken = [r for r in results if r["verdict"] not in ("CAUGHT", "SURVIVED")]

    print()
    print(f"CAUGHT {len(caught)} / SURVIVED {len(survived)} / BROKEN {len(broken)}")
    for r in survived:
        print(f"  SURVIVED: {r['id']} - {r['claim']}")
    for r in broken:
        print(f"  {r['verdict']}: {r['id']}")
    print("TREE CLEAN" if tree_clean() else "TREE DIRTY")

    (here / f"{args.batch}.results.json").write_text(
        json.dumps({"results": results}, indent=2)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
