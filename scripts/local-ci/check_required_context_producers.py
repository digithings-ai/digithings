#!/usr/bin/env python3
"""DIG-4507 recurrence guard: one required context, one producer.

THE RULE (one answer, recorded 2026-10-20): a commit reaches main reviewed
when the repo's own gate script says so
(`scripts/check_review_coverage.py`). That script's in-session arm accepts
the `reviewed:agent` label TOGETHER WITH a comment carrying the
`<!-- in-session-review -->` marker. The label alone is not evidence - it is
applied automatically as soon as any marker appears, including a
changes-requested verdict - so the evidence is the marker comment plus the
label, and the label on its own satisfies nothing.

THE DEFECT THIS GUARDS: two implementations published the same required
context name on digithings-ai/digithings - the repo workflow
`.github/workflows/ci-review-coverage.yml` (its job name IS the context, and
it is published as a github-actions check-run) and this host daemon (a
commit status posted with a user token, so `creator: null`). The main
branch protection pins the context to one GitHub App, so only the workflow's
check-run can satisfy it; the daemon's row could only contradict it, and its
`pending` placeholder read as "not reported" for the whole judgement
window, so the same commit read green in one place and blocked in another.
The daemon stopped publishing that name on 2026-10-20 (DIG-4507). This
guard keeps it stopped.

THE INVARIANT: for every repo whose main-branch protection is readable,
every required context must have exactly ONE producer, and when the
protection pins an app id the single producer must be a repo workflow
(app-owned), never a host status row. A repo whose protection cannot be read
(a private repo on a free plan answers 403) is reported UNREADABLE and never
failed - an unreadable gate is not a broken gate.

The context names are read at runtime from the protection and are never
written into this file, so the guard can never flag itself. A host source
file that merely mentions a required context name counts as a producer site:
a name in host source is either a publisher or a dormant copy of one, and a
dormant copy is the same defect waiting to be switched back on.

The module works in both layouts it is published to. In the repository the
workflow tree is `<repo>/.github/workflows`; in the daemon's host checkout
the workflows were checked out under `wt/` and `wt-twelvex/`. A repo whose
workflow tree is absent is not gated from this installation and is skipped,
except that the primary repo always gets checked so a broken layout fails
closed rather than passing on nothing.
"""

import json
import os
import subprocess

DIGITHINGS = "digithings-ai/digithings"
TWELVE_X = "digithings-ai/twelve-x"

WORKFLOW_SUFFIXES = (".yml", ".yaml")


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def _gh_bin():
    """Resolve the gh binary: launchd's own PATH has no /opt/homebrew/bin."""
    import shutil
    found = shutil.which("gh")
    if found:
        return found
    for cand in ("/opt/homebrew/bin/gh", "/usr/local/bin/gh", "/usr/bin/gh"):
        if os.path.exists(cand):
            return cand
    return "gh"


def gh_protection(repo):
    """Return (readable, payload). readable=False means UNREADABLE, not broken."""
    try:
        p = subprocess.run(
            [_gh_bin(), "api", "repos/%s/branches/main/protection" % repo],
            capture_output=True, text=True, timeout=60)
    except Exception:
        return False, None
    if p.returncode != 0:
        return False, None
    try:
        return True, json.loads(p.stdout)
    except ValueError:
        return False, None


def required_contexts(protection):
    """[(context, app_id_or_None)] from a branch-protection payload."""
    rsc = (protection or {}).get("required_status_checks") or {}
    apps = {}
    for chk in rsc.get("checks") or []:
        ctx = chk.get("context")
        if ctx:
            apps[ctx] = chk.get("app_id")
    out = []
    for c in rsc.get("contexts") or []:
        out.append((c, apps.get(c)))
    for c, a in apps.items():
        if c not in [x[0] for x in out]:
            out.append((c, a))
    return out


def workflow_producers(workflow_dir, ctx):
    """Workflow files whose JOB name is exactly ctx - the check-run name."""
    hits = []
    if not os.path.isdir(workflow_dir):
        return hits
    for name in sorted(os.listdir(workflow_dir)):
        if not name.endswith(WORKFLOW_SUFFIXES):
            continue
        p = os.path.join(workflow_dir, name)
        for line in _read(p).splitlines():
            if line.strip() == "name: " + ctx:
                hits.append(p)
                break
    return hits


def host_producers(host_dir, ctx):
    """Host python sources that carry the context name (publisher or dormant copy)."""
    hits = []
    if not os.path.isdir(host_dir):
        return hits
    for name in sorted(os.listdir(host_dir)):
        if not name.endswith(".py"):
            continue
        p = os.path.join(host_dir, name)
        if ctx in _read(p):
            hits.append(p)
    return hits


def default_repos():
    """The repos this installation can check, with the workflow tree it can see.

    The repository layout resolves `<module>/../../.github/workflows`; the host
    layout resolves the checked-out `wt/` and `wt-twelvex/` trees. Only a repo
    whose tree exists is checked, so the digithings repository does not claim
    to guard twelve-x from a checkout that has no twelve-x workflows.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.abspath(os.path.join(here, os.pardir, os.pardir))
    candidates = [
        (DIGITHINGS, [os.path.join(repo_root, ".github", "workflows"),
                      os.path.join(here, "wt", ".github", "workflows")]),
        (TWELVE_X, [os.path.join(here, "wt-twelvex", ".github", "workflows")]),
    ]
    out = []
    for repo, paths in candidates:
        for path in paths:
            if os.path.isdir(path):
                out.append({"repo": repo, "workflows": path})
                break
        else:
            if repo == DIGITHINGS:
                # Fail closed: a missing primary tree is a broken checkout, and
                # the check must name the violation rather than pass on nothing.
                out.append({"repo": repo, "workflows": paths[0]})
    return out


def check_repo(spec, host_dir, reader):
    """Per-repo findings. reader(repo) -> (readable, payload)."""
    readable, payload = reader(spec["repo"])
    if not readable:
        return {"repo": spec["repo"], "readable": False, "contexts": [], "violations": []}
    violations = []
    contexts = []
    wf_dir = os.path.join(host_dir, spec["workflows"])
    for ctx, app in required_contexts(payload):
        contexts.append(ctx)
        wf = workflow_producers(wf_dir, ctx)
        host = host_producers(host_dir, ctx)
        producers = [(p, "workflow") for p in wf] + [(p, "host") for p in host]
        if len(producers) != 1:
            violations.append({
                "repo": spec["repo"], "context": ctx, "reason": "not exactly one producer",
                "producers": producers})
        elif app is not None and producers[0][1] != "workflow":
            violations.append({
                "repo": spec["repo"], "context": ctx, "app_id": app,
                "reason": "required context is pinned to an app; the only producer is a host status row",
                "producers": producers})
    return {"repo": spec["repo"], "readable": True, "contexts": contexts, "violations": violations}


def run(repos=None, host_dir=None, reader=None):
    """Full report. Never raises for an unreadable repo; returns violations list."""
    repos = default_repos() if repos is None else repos
    host_dir = host_dir or os.path.dirname(os.path.abspath(__file__))
    reader = reader or gh_protection
    out = []
    for spec in repos:
        out.append(check_repo(spec, host_dir, reader))
    violations = [v for r in out for v in r["violations"]]
    return {"violations": violations, "repos": out}


def main():
    rep = run()
    for r in rep["repos"]:
        if not r["readable"]:
            print("required-context producers: %s protection UNREADABLE (not failed)" % r["repo"])
        else:
            print("required-context producers: %s %d required context(s) checked" % (r["repo"], len(r["contexts"])))
    for v in rep["violations"]:
        print("VIOLATION %s [%s] %s :: %s" % (v["repo"], v["context"], v["reason"], v["producers"]))
    print("violations: %d" % len(rep["violations"]))
    return 1 if rep["violations"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
