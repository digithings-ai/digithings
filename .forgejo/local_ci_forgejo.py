#!/usr/bin/env python3
"""Forgejo Actions driver for the repository's own local-ci gate.

Runs ``run_checks()`` from ``scripts/local-ci/local_ci.py`` in-process so the
Forgejo job exercises exactly the same gates, scope rules and step budgets as
the host runner. Posts nothing anywhere: Forgejo Actions reports the job
result itself.

Stdlib only, Python 3.12.
"""
import json
import os
import re
import subprocess
import sys
import traceback

# Repo root: the Forgejo checkout. GITHUB_WORKSPACE is set by the runner;
# fall back to the current working directory for a manual invocation.
root = os.environ.get("GITHUB_WORKSPACE") or os.getcwd()

# Make the host runner importable, then pull it in.
_scripts = os.path.join(root, "scripts", "local-ci")
if not os.path.isdir(_scripts):
    _scripts = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "scripts", "local-ci")
sys.path.insert(0, _scripts)
import local_ci as lc  # noqa: E402

# Trust boundary: in the host, the runner refuses any launcher except launchd
# or its worker container (lc._guard) and only runs in a worktree it created
# (lc.wt_is_ours). In this job the trust boundary is the Forgejo runner
# itself, and nothing here posts a status, so both checks are replaced in
# process. postmerge_ci.py already drives run_checks() in-process the same way.
lc.WT = root
lc._guard = lambda *a, **k: None
lc.wt_is_ours = lambda _p: True


def _is_commit(sha):
    if not sha:
        return False
    try:
        r = subprocess.run(
            ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
            cwd=root, capture_output=True, text=True,
        )
        return r.returncode == 0
    except OSError:
        return False


def _git_diff_names(a, b):
    try:
        r = subprocess.run(
            ["git", "diff", "--name-only", a, b],
            cwd=root, capture_output=True, text=True,
        )
    except OSError:
        return None
    if r.returncode != 0:
        return None
    out = [line for line in (r.stdout or "").splitlines() if line.strip()]
    return out


def _make_gh(files, body_value):
    repo = lc.REPO

    def _gh(*args):
        args = list(args)
        # Gate 1: changed-files fetch used by worker_gate / bun_gate.
        if (len(args) == 4 and args[0] == "api"
                and isinstance(args[1], str)
                and re.fullmatch(
                    r"repos/.+/pulls/\d+/files", args[1]) is not None
                and args[2:] == ["--paginate", "--slurp"]):
            if not files:
                return None
            return json.dumps([[{"filename": f} for f in files]])
        # Gate 2: PR body fetch used by pr_body().
        if (len(args) == 9 and args[0] == "pr" and args[1] == "view"
                and args[3] == "-R" and args[5] == "--json"
                and args[6] == "body" and args[7] == "-q"
                and args[8] == ".body"):
            return "" if body_value is None else str(body_value)
        sys.stderr.write(f"local-ci-forgejo: unexpected gh call {args}\n")
        return None

    return _gh


def main():
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    event_path = os.environ.get("GITHUB_EVENT_PATH", "")
    with open(event_path) as fh:
        event = json.load(fh)

    if event_name == "pull_request":
        pr_data = event["pull_request"]
        number = pr_data["number"]
        title = pr_data.get("title") or ""
        body = pr_data.get("body")
        if body is None:
            body = ""
        head_sha = pr_data["head"]["sha"]
        base = pr_data["base"]["ref"]

        # merge-base, mirroring GitHub's pulls/<n>/files.
        try:
            mb = subprocess.run(
                ["git", "merge-base", f"origin/{base}", head_sha],
                cwd=root, capture_output=True, text=True,
            )
            if mb.returncode != 0:
                files = None
            else:
                merge_base = (mb.stdout or "").strip()
                files = _git_diff_names(merge_base, head_sha)
        except OSError:
            files = None

        lc.gh = _make_gh(files, body)
        pr = {"number": number, "headRefOid": head_sha,
              "baseRefName": base, "title": title}

        nfiles = len(files) if files else 0
        print(f"local-ci-forgejo: mode=pull_request head={head_sha} base={base} changed_files={nfiles}")

    elif event_name == "push":
        tip = os.environ.get("GITHUB_SHA")
        prev = (event or {}).get("before")
        if (not prev or prev == "0" * 40 or not _is_commit(prev)):
            try:
                rp = subprocess.run(
                    ["git", "rev-parse", f"{tip}^1"],
                    cwd=root, capture_output=True, text=True,
                )
                prev = (rp.stdout or "").strip() if rp.returncode == 0 else prev
            except OSError:
                pass
        files = _git_diff_names(prev, tip) if prev else None

        class _NoTemplate:
            @staticmethod
            def check_template(_b):
                return (True, [])

        lc.pr_template = _NoTemplate
        lc.gitleaks_log_opts = lambda _b, s, _o: f"--no-merges {prev}..{s}"
        lc.gh = _make_gh(files, "")

        pr = {"number": 0, "headRefOid": tip, "baseRefName": "develop",
              "baseCommit": prev, "postMerge": True,
              "title": "chore(develop): post-merge tip check"}

        nfiles = len(files) if files else 0
        print(f"local-ci-forgejo: mode=push head={tip} base=develop changed_files={nfiles}")

    else:
        raise RuntimeError(f"unsupported event: {event_name!r}")

    summary = {}
    fails = lc.run_checks(pr, sys.stdout, summary)
    sys.stdout.flush()

    if not fails:
        print("local-ci: PASS")
        sys.exit(0)
    print("local-ci: FAIL: " + ", ".join(sorted(set(fails))))
    sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        sys.exit(2)
