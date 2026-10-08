#!/usr/bin/env python3
"""QA mutation harness v2 for PR #5232 re-verification (DIG-2383).

Same mutation mechanics as v1 (mut.py), but records HOW MANY tests failed and
WHICH tests, because "CAUGHT by 1 test" and "CAUGHT by 44" are very different
verdicts for a test-kit review. v1 only recorded pass/fail.

Mutant schema (as v1) plus:
  node  optional pytest node id instead of the whole suite
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import pathlib
import re
import subprocess
import sys
import time

REPO = pathlib.Path(
    "/Users/chrisstefan/Code/digithings/.paperclip/worktrees/"
    "DIG-1597-port-the-sdca-research-subsystem-from-claude-sdca-develop-sync"
)
PY = "/Users/chrisstefan/Code/digithings/.venv/bin/python"

FAILED_RE = re.compile(r"^(FAILED|ERROR) (\S+)", re.MULTILINE)
SUMMARY_RE = re.compile(r"^=+ (.*(?:failed|passed|error).*) =+$", re.MULTILINE)


def env() -> dict[str, str]:
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


def run_suite(node: str | None = None) -> tuple[int, str]:
    target = node if node else "tests/dq/strategies/sdca/"
    cmd = [PY, "-m", "pytest", target, "-q", "--no-header", "-p", "no:randomly",
           "-rf", "--tb=no"]
    r = subprocess.run(cmd, cwd=REPO, env=env(), capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def parse(out: str) -> tuple[list[str], str]:
    failed = sorted({m.group(2) for m in FAILED_RE.finditer(out)})
    summ = SUMMARY_RE.findall(out)
    tail = summ[-1].strip() if summ else out.strip().splitlines()[-1] if out.strip() else ""
    return failed, tail


def tree_clean() -> bool:
    r = subprocess.run(["git", "status", "--porcelain"], cwd=REPO,
                       capture_output=True, text=True)
    return r.stdout.strip() == ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("batch")
    ap.add_argument("--skip-baseline", action="store_true")
    ap.add_argument("--show-failures", type=int, default=0,
                    help="print the failing test ids for the first N caught mutants")
    args = ap.parse_args()

    here = pathlib.Path(__file__).parent
    mutants = json.loads((here / f"{args.batch}.json").read_text())

    if not args.skip_baseline:
        t0 = time.time()
        rc, out = run_suite()
        failed, tail = parse(out)
        print(f"BASELINE rc={rc} in {time.time()-t0:.1f}s | {tail}")
        if rc != 0:
            print("BASELINE NOT GREEN - aborting, mutants would be meaningless")
            return 3

    results = []
    shown = 0
    for m in mutants:
        path = REPO / m["file"]
        original = path.read_text()
        find, repl = m["find"], m["replace"]
        occ, expect = m.get("occ", 0), m.get("expect", 1)

        count = original.count(find)
        if count != expect:
            verdict = f"ANCHOR-ERROR count={count} expected={expect}"
            results.append({"id": m["id"], "file": m["file"], "claim": m["claim"],
                            "verdict": verdict, "n_failed": 0, "failed": []})
            print(f"[{m['id']}] {verdict}", flush=True)
            continue

        idx = -1
        for _ in range(occ + 1):
            idx = original.find(find, idx + 1)
        patched = original[:idx] + repl + original[idx + len(find):]

        try:
            ast.parse(patched)
        except SyntaxError as exc:
            path.write_text(original)
            results.append({"id": m["id"], "file": m["file"], "claim": m["claim"],
                            "verdict": f"SYNTAX-ERROR {exc}", "n_failed": 0, "failed": []})
            print(f"[{m['id']}] SYNTAX-ERROR {exc}", flush=True)
            continue

        path.write_text(patched)
        t0 = time.time()
        rc, out = run_suite(m.get("node"))
        dt = time.time() - t0
        path.write_text(original)
        subprocess.run(["git", "checkout", "--", m["file"]], cwd=REPO, capture_output=True)

        failed, tail = parse(out)
        if rc == 0:
            verdict = "SURVIVED"
        elif rc == 1:
            verdict = "CAUGHT"
        else:
            verdict = f"INTERRUPTED rc={rc}"

        results.append({
            "id": m["id"], "file": m["file"], "claim": m["claim"],
            "verdict": verdict, "n_failed": len(failed), "failed": failed,
            "summary": tail, "seconds": round(dt, 1),
        })
        print(f"[{m['id']}] {verdict} n_failed={len(failed)} ({dt:.1f}s) - {m['claim']}",
              flush=True)
        if verdict == "CAUGHT" and shown < args.show_failures:
            shown += 1
            for t in failed:
                print(f"        {t}")

    caught = [r for r in results if r["verdict"] == "CAUGHT"]
    survived = [r for r in results if r["verdict"] == "SURVIVED"]
    broken = [r for r in results if r["verdict"] not in ("CAUGHT", "SURVIVED")]

    print()
    print(f"CAUGHT {len(caught)} / SURVIVED {len(survived)} / BROKEN {len(broken)}")
    for r in survived:
        print(f"  SURVIVED: {r['id']} - {r['claim']}")
    for r in caught:
        print(f"  CAUGHT x{r['n_failed']:>3}: {r['id']}")
    for r in broken:
        print(f"  {r['verdict']}: {r['id']}")
    print("TREE CLEAN" if tree_clean() else "TREE DIRTY")

    (here / f"{args.batch}.results.json").write_text(
        json.dumps({"head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO,
                                           capture_output=True, text=True).stdout.strip(),
                    "results": results}, indent=2)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())