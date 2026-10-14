"""Classify every JOBS dispatch row for DIG-3566 item (1).

Uses the REPO'S OWN regex (tests/scripts/test_prices_cron_dst.py:67) as the
authoritative extraction instrument, then resolves each target workflow in the
REPO IT LIVES IN and reads its trigger kinds.
"""
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

WT = Path("/Users/chrisstefan/Code/digithings-wt-DIG3566-r5")
TX = Path("/Users/chrisstefan/Code/twelve-x")
JOBS = WT / "apps/digithings-cron/src/jobs.ts"

src = JOBS.read_text(encoding="utf-8")
# The repo's own instrument, verbatim.
PAIRS = re.findall(
    r'(?:wd|rd|cj|pj|wj|tw)\(\s*"([^"]+)"\s*,\s*"([^"]+)"',
    src,
    flags=re.DOTALL,
)
# CONTROL: a string the same matcher provably reaches inside JOBS_SOURCE.
CTL = src.count('"MONOREPO"') and src.count("wf") or 0
assert len(PAIRS) == 49, f"pair count {len(PAIRS)} != 49"
ids = [p[0] for p in PAIRS]
assert len(set(ids)) == len(ids), "duplicate job ids"

# Which builder each row belongs to, from the character position of the match.
BUILDER = re.compile(r'\b(wd|rd|cj|pj|wj|tw)\(\s*"')
kinds = []
for m in BUILDER.finditer(src):
    kinds.append((m.group(1), m.start()))
assert len(kinds) == len(PAIRS), f"builder scans {len(kinds)} != pairs {len(PAIRS)}"

# workflow id is the next string literal after the cron literal for each row.
# Per-builder arity, read off the builder signatures at jobs.ts:54-163:
#   wd(id, cron, repo, workflow, opts)  -> 4th string arg is the workflow
#   rd(id, cron, repo, workflow, opts)  -> same shape as wd
#   cj(id, cron, workflow, command, concurrency, timeoutSeconds, opts) -> 3rd
#   pj(id, cron, workflow, probe, opts) -> 3rd
#   wj(id, cron, watch, opts)          -> 3rd arg is a WATCH NAME, no workflow
#   tw(id, cron, workflow, twelvexWatch)-> 3rd
WF_IDX = {"wd": 3, "rd": 3, "cj": 2, "pj": 2, "wj": None, "tw": 2}
ARG = re.compile(r'"([^"]*)"')

rows = []
for (jid, cron), (kind, off) in zip(PAIRS, kinds):
    # Cut the call at its own closing paren so later rows' args cannot leak in.
    depth, end = 0, None
    for i in range(src.index("(", off), len(src)):
        if src[i] == "(":
            depth += 1
        elif src[i] == ")":
            depth -= 1
            if depth == 0:
                end = i
                break
    assert end is not None, f"no closing paren for {jid}"
    call = src[off:end]
    args = ARG.findall(call)
    idx = WF_IDX[kind]
    wf = args[idx] if idx is not None and idx < len(args) else None
    # wd/rd name their repo explicitly (3rd arg); the rest are fixed per builder.
    if kind in ("wd", "rd"):
        repo = "twelve-x" if args[2] == "TWELVE_X" else "digithings"
    elif kind == "tw":
        repo = "twelve-x"
    else:
        repo = "digithings"
    line = src.count("\n", 0, off) + 1
    rows.append({"id": jid, "cron": cron, "kind": kind, "repo": repo,
                 "workflow": wf, "line": line, "args": args})

# CONTROL on the new extractor: token-canary's workflow is the 4th arg of a wd row.
tk = next(r for r in rows if r["id"] == "token-canary")
assert tk["workflow"] == "token-canary.yml", f"extractor control: {tk}"
assert next(r for r in rows if r["id"] == "prices-at-open-13")["workflow"] == "pipeline-digiquant-prices.yml"
assert next(r for r in rows if r["id"] == "digiquant-house-run-watch")["workflow"] is None
assert next(r for r in rows if r["id"] == "twelve-x-asia")["repo"] == "twelve-x"
assert next(r for r in rows if r["id"] == "token-canary")["repo"] == "digithings"
print("EXTRACTOR CONTROL: token-canary ->", tk["workflow"], "| twelve-x-asia repo ->",
      next(r for r in rows if r["id"] == "twelve-x-asia")["repo"])

# Resolve each workflow in the repo it must live in. CONTROL: a known workflow.
def wf_path(repo, wf):
    root = TX if repo == "twelve-x" else WT
    return root / ".github/workflows" / wf

def exists(repo, wf):
    return wf_path(repo, wf).exists()

# CONTROL: a known-present workflow, resolved with the SAME function.
CONTROL = ("digithings", "token-canary.yml")
assert exists(*CONTROL), f"CONTROL workflow {CONTROL[1]} not found in digithings"
# NEGATIVE control: a name that cannot exist.
NEG = ("digithings", "zzz-dig3566-no-such-workflow.yml")
assert not exists(*NEG), "NEGATIVE control resolved -- existence check is broken"

def triggers(repo, wf):
    root = TX if repo == "twelve-x" else WT
    p = root / ".github/workflows" / wf
    if not p.exists():
        return None
    txt = p.read_text(encoding="utf-8", errors="replace")
    out = {}
    for key in ("schedule:", "workflow_dispatch:", "repository_dispatch:"):
        out[key.rstrip(":")] = (key in txt)
    # Is the schedule cron or dispatch-only?
    m = re.search(r"^\s*-\s*cron:\s*(.+)$", txt, re.MULTILINE)
    out["cron_expr"] = m.group(1).strip().strip("'\"") if m else None
    return out

for r in rows:
    r["wf_exists"] = exists(r["repo"], r["workflow"])
    r["triggers"] = triggers(r["repo"], r["workflow"])

Path("/tmp/rows2.json").write_text(json.dumps(rows, indent=1))
print("CONTROL fired:", CONTROL[1], "->", exists(*CONTROL))
print("rows:", len(rows), "unique ids:", len(set(r["id"] for r in rows)))
print("by kind:", dict(Counter(r["kind"] for r in rows)))
print("by repo:", dict(Counter(r["repo"] for r in rows)))
print("workflow missing:", sorted({(r["repo"], r["workflow"]) for r in rows if not r["wf_exists"]}))
print()
hdr = f'{"id":42} {"kind":4} {"repo":10} {"cron":24} {"sched":6} {"disp":5} wf'
print(hdr)
for r in rows:
    t = r["triggers"] or {}
    print(f'{r["id"]:42} {r["kind"]:4} {r["repo"]:10} {r["cron"]:24} '
          f'{str(t.get("schedule")):6} {str(t.get("workflow_dispatch")):5} {r["workflow"]}')