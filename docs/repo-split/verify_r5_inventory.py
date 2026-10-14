#!/usr/bin/env python3
"""Re-derive an R5 file inventory from git and compare it with a markdown document.

Usage: verify_r5_inventory.py <repo> <ref> <markdown>

Every fenced block under a "### " heading that names a path and a count is
parsed as a package-relative file list and compared, as a SET, with
`git ls-tree -r <ref> -- <prefix>`. The document is never trusted for the
counts: the measured number is printed beside the claimed number.

Exit 0 = every list is exact. Exit 1 = at least one mismatch (prints the
missing and the extra paths). Exit 2 = the instrument could not run.
"""
import os
import re
import subprocess
import sys


def git(repo, *args):
    p = subprocess.run(["git", "-C", repo] + list(args),
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("git %s -> rc=%d %s" % (" ".join(args), p.returncode, p.stderr.strip()[:200]))
    return p.stdout


def ls_tree(repo, ref, prefix):
    out = git(repo, "ls-tree", "-r", ref, "--name-only", "--", prefix)
    rows = [r for r in out.split("\n") if r.strip()]
    if prefix.endswith("/"):
        return sorted(r[len(prefix):] for r in rows)
    return sorted(r[len(prefix) + 1:] for r in rows)


def sections(md):
    """Yield (heading, prefix, claimed_count, [paths]) for every list section."""
    cur = None
    in_fence = False
    for line in md.split("\n"):
        if line.startswith("### "):
            cur = {"h": line.strip(), "paths": [], "in": False}
            continue
        if cur is not None and line.startswith("## "):
            cur = None
            continue
        if cur is None:
            continue
        if line.startswith("```"):
            cur["in"] = not cur["in"]
            continue
        if cur["in"] and line.strip():
            cur["paths"].append(line.strip())
            continue
        if cur["paths"]:
            yield cur
            cur = None
    if cur is not None and cur["paths"]:
        yield cur


def main():
    if len(sys.argv) != 4:
        print("usage: verify_r5_inventory.py <repo> <ref> <markdown>", file=sys.stderr)
        return 2
    repo, ref, md_path = sys.argv[1], sys.argv[2], sys.argv[3]
    if not os.path.exists(md_path):
        print("MARKDOWN ABSENT: %s" % md_path, file=sys.stderr)
        return 2
    md = open(md_path, encoding="utf-8").read()
    head = git(repo, "rev-parse", "--verify", ref + "^{commit}").strip()

    # Positive control: the instrument must be able to enumerate a real tree,
    # and must answer "absent" for a path it cannot exist at.
    ctl_live = len(ls_tree(repo, ref, "apps/digichat-cloudflare"))
    ctl_ghost = git(repo, "ls-tree", "-r", ref, "--name-only", "--",
                    "apps/__no_such_package__/__").split("\n")
    ctl_ghost = len([r for r in ctl_ghost if r.strip()])
    print("CONTROL ls-tree on a live package = %d paths (must be > 0)" % ctl_live)
    print("CONTROL ls-tree on an impossible path = %d paths (must be 0)" % ctl_ghost)
    if ctl_live == 0 or ctl_ghost != 0:
        print("CONTROL FAILED - the instrument is not trustworthy, stop.")
        return 2

    failures = 0
    checked = 0
    print("ref = %s" % head)
    print("%-52s %8s %8s  %s" % ("section", "claimed", "measured", "verdict"))
    seen_prefixes = []
    # SCOPE: only "### A.N" headings are full file inventories. Other fenced
    # blocks in the same document (e.g. "### E.2 docs/ops triage") are
    # deliberately partial subsets and are NOT inventories. Comparing them to
    # ls-tree reports a mismatch that is the verifier's fault, not the
    # document's -- which is what happened on the first run.
    skipped = 0
    for s in sections(md):
        if not s["h"].startswith("### A."):
            skipped += 1
            print("%-52s %8s %8s  %s" % (s["h"][:52], "-", "-", "SKIP (not an inventory section)"))
            continue
        tokens = re.findall(r"`([^`]+)`", s["h"])
        prefix = None
        for t in tokens:
            t = t.strip()
            if t.endswith("/") or ("/" in t and " " not in t and t.count("/") >= 1):
                prefix = t
                break
        if prefix is None:
            print("%-52s %8s %8s  %s" % (s["h"][:52], "-", "-", "SKIP (no path token; table section)"))
            continue
        claimed = None
        m = re.search(r"—\s*(\d+)\s+files", s["h"])
        if m:
            claimed = int(m.group(1))
        meas = ls_tree(repo, ref, prefix)
        seen_prefixes.append(prefix)
        doc = sorted(p for p in s["paths"] if p and not p.startswith("#"))
        missing = [p for p in meas if p not in doc]
        extra = [p for p in doc if p not in meas]
        checked += 1
        if missing or extra:
            failures += 1
            verdict = "MISMATCH missing=%d extra=%d" % (len(missing), len(extra))
            for p in missing[:8]:
                print("      - in git, absent from doc: %s" % p)
            for p in extra[:8]:
                print("      + in doc, absent from git: %s" % p)
        else:
            verdict = "EXACT SET" + ("" if claimed is None else " (claim holds)" if claimed == len(meas) else "  CLAIM WRONG")
            if claimed is not None and claimed != len(meas):
                failures += 1
        print("%-52s %8s %8d  %s" % (s["h"][:52], claimed if claimed is not None else "-", len(meas), verdict))
    print("sections_checked=%d failures=%d sections_skipped_out_of_scope=%d" % (checked, failures, skipped))
    print("VERDICT=%s" % ("PASS" if failures == 0 and checked > 0 else "FAIL"))
    return 0 if failures == 0 and checked > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
