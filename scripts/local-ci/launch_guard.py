#!/usr/bin/env python3
"""launch_guard: refuses a CI runner run that no trusted launcher started.

DIG-4796. "A seat never runs local_ci.py / twelvex_ci.py" used to live only in
the operating-rules skill, and on 21 Oct a seat ran the runner twice. This module
turns the rule into something the process tree cannot argue with: the runner
asks it first thing, and it exits 78 (EX_CONFIG) unless the run came from a
launcher the org controls.

Two launchers are trusted:

  * the launchd daemon (`ai.digithings.local-ci`, `ai.digithings.twelvex-ci`).
    launchd starts it with ppid 1, sets XPC_SERVICE_NAME to the job label,
    loads it from the plist scripts/local-ci/install.sh writes, the loaded
    job's arguments are exactly the interpreter and the runner file that is
    running now - no extra arguments, so a job that asks for one PR is not the
    daemon and is refused - and the pid launchctl reports for the job is the
    pid of this very process. That last fact is what makes the label
    worthless to forge: a seat that orphans itself to launchd and claims the
    label is not the job's process, so it is refused;

  * the CI container (the Woodpecker worker), which runs the runner from
    /opt/local-ci under /opt/local-ci/worker_entrypoint.sh with the CI
    credential in the environment.

Everything else is refused: a hand-run from any shell, a seat's shell, a script
a seat detached, a job a seat installed. The decision reads kernel and launchd
facts only - the pid of this process, the process tree, the pid launchd reports
for the job, the container's entrypoint - never BASH_ENV, PAPERCLIP_*,
ZDOTDIR, and never `gh` - so unsetting those variables changes nothing.

What this is not: a proof. At the same uid a seat can copy the runner and run
its own copy without this module, drive the container with its own token, or
rewrite the daemon's plist and reload the job under the same label. What the
guard does buy is that the cheap forgeries fail: an unset environment, a
forged label, an orphaned process tree, a job loaded from somewhere else, a job
that asks for one PR. The authoritative boundary is the queue-side provenance
check (DIG-4794): only a `local-ci` status that carries the verified
Woodpecker target_url counts.

Usage:
  python3 scripts/local-ci/launch_guard.py --runner scripts/local-ci/local_ci.py

Exit code 0 means the run may proceed; 78 means it is refused.

This module is byte-identical in the digithings and twelve-x repositories.
"""
import json
import os
import re
import subprocess
import sys
import time

# EX_CONFIG: the run was refused because it was not started by a trusted launcher.
EX_CONFIG = 78

# The launchd jobs that are allowed to start a runner. A label outside this set
# is refused even when the process claims it.
TRUSTED_LAUNCHD_LABELS = ("ai.digithings.local-ci", "ai.digithings.twelvex-ci")

# The CI container's runner directory and entrypoint (see Dockerfile.worker).
CONTAINER_RUNNER_ROOT = "/opt/local-ci"
CONTAINER_ENTRYPOINT = "/opt/local-ci/worker_entrypoint.sh"

# How far up the process tree the guard looks. A launchd job is one hop away;
# the container entrypoint is at pid 1. Ten is plenty and keeps the walk cheap.
MAX_ANCESTORS = 10

# The log the guard appends its decision to. One JSON line per decision, so a
# refused run is evidence and not a rumour.
LOG_NAME = "launch-guard.jsonl"


# --------------------------------------------------------------- process facts --

def _proc_cmdline(pid):
    """The argv of a pid from /proc, or None when /proc does not have it."""
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as fh:
            raw = fh.read()
    except OSError:
        return None
    parts = [p.decode("utf-8", "replace") for p in raw.split(b"\0") if p]
    return parts or None


def _proc_ppid(pid):
    """The parent pid of a pid from /proc, or None."""
    try:
        with open(f"/proc/{pid}/stat", "rb") as fh:
            raw = fh.read().decode("utf-8", "replace")
    except OSError:
        return None
    # "pid (comm) state ppid ..." - comm may contain spaces and parentheses, so
    # the fields after it are the ones after the LAST ')'.
    cut = raw.rfind(")")
    if cut < 0:
        return None
    fields = raw[cut + 1:].split()
    if len(fields) < 2:
        return None
    try:
        return int(fields[1])
    except ValueError:
        return None


def _ps(args):
    """Run ps and return its stdout, or None when ps could not answer."""
    try:
        proc = subprocess.run(["ps"] + args, capture_output=True, text=True, timeout=10,
                              check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def read_ppid(pid):
    """The parent pid of a pid, from /proc where available, else from ps."""
    ppid = _proc_ppid(pid)
    if ppid is not None:
        return ppid
    out = _ps(["-o", "ppid=", "-p", str(pid)])
    if not out:
        return None
    try:
        return int(out.split()[0])
    except (IndexError, ValueError):
        return None


def read_cmdline(pid):
    """The argv of a pid as a list of strings (one string when only ps answered)."""
    argv = _proc_cmdline(pid)
    if argv is not None:
        return argv
    out = _ps(["-o", "command=", "-p", str(pid)])
    return [out] if out else []


def collect_ancestors(max_depth=MAX_ANCESTORS):
    """The chain of ancestors of this process, nearest first."""
    chain = []
    pid = os.getpid()
    for _ in range(max_depth):
        ppid = read_ppid(pid)
        if not ppid or ppid <= 0:
            break
        chain.append({"pid": ppid, "argv": read_cmdline(ppid)})
        if ppid == 1:
            break
        pid = ppid
    return chain


# ----------------------------------------------------------------- launchd --

def parse_launchctl_print(text):
    """Pull the program, the arguments, the plist path and the pid out of launchctl print.

    The pid is the one launchd reports for the job while it is running: the pid
    of the process the job's own program is running in. It is the fact that
    ties a run to a job - the label alone can be claimed by anybody.
    """
    job = {"program": None, "arguments": [], "path": None, "pid": None}
    lines = (text or "").splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        top = re.match(r"^\t(path|program|pid) = (.*)$", line)
        if top:
            key = top.group(1)
            value = top.group(2).strip()
            if key == "pid":
                # A pid is a number or it is nothing: launchctl prints one for
                # the running job and omits it for a job that is not running.
                if value.isdigit():
                    job["pid"] = int(value)
            else:
                job[key] = value
        elif re.match(r"^\targuments = \{$", line):
            index += 1
            while index < len(lines) and lines[index].strip() != "}":
                argument = lines[index].strip()
                if argument:
                    job["arguments"].append(argument)
                index += 1
        index += 1
    return job


def canonical_plist_path(label):
    """Where the house tooling installs a launchd job's plist.

    scripts/local-ci/install.sh writes it and dt-daemon-liveness bootstraps
    from it, so a job loaded from anywhere else was not installed by the org.
    """
    return os.path.join(os.path.expanduser("~"), "Library", "LaunchAgents",
                        f"{label}.plist")


def launchctl_job(label, uid=None):
    """The loaded job's facts, or None when the job is not loaded."""
    if uid is None:
        uid = os.getuid()
    try:
        proc = subprocess.run(
            ["launchctl", "print", f"gui/{uid}/{label}"],
            capture_output=True, text=True, timeout=15, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return parse_launchctl_print(proc.stdout)


# -------------------------------------------------------------------- facts --

def collect_facts(runner_path):
    """Everything the decision reads. No environment value is ever recorded."""
    label = os.environ.get("XPC_SERVICE_NAME")
    job = launchctl_job(label) if label in TRUSTED_LAUNCHD_LABELS else None
    return {
        "runner": os.path.realpath(runner_path),
        "pid": os.getpid(),
        "ppid": os.getppid(),
        "uid": os.getuid(),
        "ancestors": collect_ancestors(),
        "dockerenv": os.path.exists("/.dockerenv"),
        "xpc_service_name": label,
        "ci_token": bool(os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")),
        "launchd_job": job,
    }


# ------------------------------------------------------------------ decision --

def _decide_container(facts):
    """The CI container: the worker entrypoint, under /opt/local-ci, with a token.

    The entrypoint has to be the runner's own parent, not merely somewhere up
    the tree: the worker starts the runner as a direct child of
    worker_entrypoint.sh, so that is the only shape the pipeline has. A run
    that some other process in the container started - a shell, an exec of the
    runner - has a different parent and is refused.
    """
    runner = facts.get("runner") or ""
    if not runner.startswith(CONTAINER_RUNNER_ROOT + os.sep):
        return False, (f"the runner is not under {CONTAINER_RUNNER_ROOT}, so this is not "
                       "the CI container")
    ancestors = facts.get("ancestors") or []
    parent = ancestors[0] if ancestors else None
    started_by_entrypoint = bool(parent) and any(
        CONTAINER_ENTRYPOINT in argument for argument in (parent.get("argv") or []))
    if not started_by_entrypoint:
        return False, ("inside a container, but the runner was not started by the "
                       "worker entrypoint")
    if not facts.get("ci_token"):
        return False, ("the trusted launcher (the CI container) started this run but "
                       "carries no CI credential, so it cannot be the trusted pipeline")
    return True, "the CI container worker entrypoint started this run"


def _decide_launchd(facts, label):
    """The launchd daemon: launchd started this very process, from the trusted job."""
    if facts.get("ppid") != 1:
        return False, (f"the launchd job {label} claims this run, but the parent pid is "
                       f"{facts.get('ppid')} and not launchd")
    ancestors = facts.get("ancestors") or []
    if not ancestors or ancestors[0].get("pid") != 1:
        return False, (f"the launchd job {label} claims this run, but the process tree "
                       "does not start at launchd")
    job = facts.get("launchd_job")
    if not job:
        return False, f"the launchd job {label} is not loaded"
    job_pid = job.get("pid")
    if job_pid is None:
        return False, (f"the launchd job {label} is not running, so it did not start "
                       "this run")
    if job_pid != facts.get("pid"):
        return False, (f"the launchd job {label} is running as pid {job_pid} and this "
                       f"run is pid {facts.get('pid')}, so this is not the job's process")
    expected_plist = canonical_plist_path(label)
    if job.get("path") != expected_plist:
        return False, (f"the launchd job {label} was loaded from "
                       f"{job.get('path') or 'an unknown path'} and not from the canonical "
                       f"{expected_plist}; reinstall it with scripts/local-ci/install.sh")
    arguments = job.get("arguments") or []
    if len(arguments) != 2:
        return False, (f"the launchd job {label} runs {len(arguments)} arguments; the "
                       "daemon runs the runner with none")
    program, runner_argument = arguments
    if not os.path.basename(program).startswith("python"):
        return False, f"the launchd job {label} does not run a python interpreter"
    try:
        same = os.path.realpath(runner_argument) == facts.get("runner")
    except OSError:
        same = False
    if not same:
        return False, (f"the launchd job {label} runs a different file than the runner "
                       "that is running now")
    return True, f"the launchd daemon {label} started this run"


def decide(facts):
    """Deny by default. Returns (allowed, reason).

    Every refusal names the trusted launcher. A run that the launchd daemon or
    the CI container did not start is refused, and the reason says so in the
    same words whichever path the check took: the reason is read in a log by a
    human deciding whether the run may go on, and it must not depend on where
    the run happened.
    """
    if facts.get("dockerenv"):
        allowed, reason = _decide_container(facts)
    else:
        label = facts.get("xpc_service_name")
        if label and label in TRUSTED_LAUNCHD_LABELS:
            allowed, reason = _decide_launchd(facts, label)
        elif label:
            allowed, reason = False, (f"XPC_SERVICE_NAME is {label!r}, which is not a "
                                      "trusted runner job")
        else:
            allowed, reason = False, ("the runner was not started by a trusted "
                                      "launcher: no launchd job and no CI container")
    if not allowed and "trusted launcher" not in reason:
        reason = f"{reason}: no trusted launcher started this run"
    return allowed, reason


# ------------------------------------------------------------------- logging --

def log_path(ctx):
    """Where the decision is recorded."""
    home = os.path.expanduser("~")
    return os.path.join(home, ".config", "digithings", "logs", ctx or "local-ci", LOG_NAME)


def _record(facts, allowed, reason):
    job = facts.get("launchd_job") or {}
    return {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "allowed": bool(allowed),
        "reason": reason,
        "runner": facts.get("runner"),
        "pid": facts.get("pid"),
        "ppid": facts.get("ppid"),
        "uid": facts.get("uid"),
        "dockerenv": facts.get("dockerenv"),
        "xpc_service_name": facts.get("xpc_service_name"),
        "ci_token": facts.get("ci_token"),
        "job_pid": job.get("pid"),
        "job_path": job.get("path"),
        "ancestors": [
            {"pid": a.get("pid"), "argv": (a.get("argv") or [])[:3]}
            for a in (facts.get("ancestors") or [])
        ],
    }


def append_decision(ctx, record):
    """Append the decision to the log. Never raises: the log is evidence, not a gate."""
    path = log_path(ctx)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
    except OSError:
        pass
    return path


# ------------------------------------------------------------------ enforcing --

def enforce(runner_path, ctx, facts=None):
    """Refuse the run unless a trusted launcher started it. Exits 78 on refusal."""
    if facts is None:
        facts = collect_facts(runner_path)
    allowed, reason = decide(facts)
    append_decision(ctx, _record(facts, allowed, reason))
    if allowed:
        return True
    name = os.path.basename(facts.get("runner") or runner_path or "the runner")
    sys.stderr.write(f"launch_guard: refusing to run {name}: {reason}\n")
    sys.stderr.write("launch_guard: the runner runs from its launchd job or from the "
                     "CI container only (DIG-4796).\n")
    sys.exit(EX_CONFIG)


# ------------------------------------------------------------------------ cli --

def _parse_args(argv):
    options = {"runner": None, "ctx": "local-ci", "facts_json": None}
    index = 0
    while index < len(argv):
        argument = argv[index]
        if argument in ("-r", "--runner") and index + 1 < len(argv):
            options["runner"] = argv[index + 1]
            index += 2
            continue
        if argument == "--ctx" and index + 1 < len(argv):
            options["ctx"] = argv[index + 1]
            index += 2
            continue
        if argument == "--facts-json" and index + 1 < len(argv):
            options["facts_json"] = argv[index + 1]
            index += 2
            continue
        if argument in ("-h", "--help"):
            sys.stdout.write((__doc__ or "") + "\n")
            raise SystemExit(0)
        raise SystemExit(f"launch_guard: unknown argument {argument!r}")
    return options


def main(argv=None):
    """The diagnostic CLI. It decides and prints; it never runs a check."""
    options = _parse_args(list(sys.argv[1:] if argv is None else argv))
    if not options["runner"]:
        sys.stderr.write("launch_guard: --runner PATH is required\n")
        return 2
    if options["facts_json"]:
        # A test seam: the facts are handed over instead of collected. The runner
        # never passes this, so a run cannot choose its own facts.
        with open(options["facts_json"], "r", encoding="utf-8") as fh:
            facts = json.load(fh)
    else:
        facts = collect_facts(options["runner"])
    allowed, reason = decide(facts)
    report = {"allowed": allowed, "reason": reason, "facts": facts}
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if allowed:
        return 0
    name = os.path.basename(facts.get("runner") or options["runner"] or "the runner")
    sys.stderr.write(f"launch_guard: refusing to run {name}: {reason}\n")
    sys.stderr.write("launch_guard: the runner runs from its launchd job or from the "
                     "CI container only (DIG-4796).\n")
    return EX_CONFIG


if __name__ == "__main__":
    sys.exit(main())
