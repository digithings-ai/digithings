#!/usr/bin/env python3
"""launch_guard: refuses a CI runner run that no trusted launcher started.

DIG-4796. "A seat never runs local_ci.py / twelvex_ci.py" used to live only in
the operating-rules skill, and on 21 Oct a seat ran the runner twice. This module
turns the rule into something the process tree cannot argue with: the runner
asks it first thing, and it exits 78 (EX_CONFIG) unless the run came from a
launcher the org controls.

Two launchers are trusted:

  * the launchd daemon (`ai.digithings.local-ci`, `ai.digithings.twelvex-ci`,
    `ai.digithings.local-ci-postmerge`, `ai.digithings.twelvex-ci-postmerge`).
    The label is not taken from the environment - a seat can set
    XPC_SERVICE_NAME to anything - but from launchd's own table: `launchctl
    list` lists the jobs launchd runs and the pid of each, and the row whose
    pid is this process's pid is the job that started it. On top of that
    launchd started it (ppid 1), the process tree starts at launchd, the
    loaded job reports this very pid, the loaded job was loaded from the
    canonical plist (`~/Library/LaunchAgents/<label>.plist`), the loaded job's
    arguments are exactly the arguments the canonical plist names, and the
    script the job runs is either the runner that is running now or a trusted
    driver script that sits next to it in the runner's own directory
    (postmerge_ci.py drives local_ci.run_checks() for the post-merge check).
    The pid tie is what makes the label worthless to forge: a seat that
    orphans itself to launchd and claims the label is not the job's process,
    so it is refused;

  * the CI container (the Woodpecker worker), which runs the runner from
    /opt/local-ci under /opt/local-ci/worker_entrypoint.sh with the CI
    credential in the environment.

Everything else is refused: a hand-run from any shell, a seat's shell, a script
a seat detached. The one thing the guard cannot see is a job a seat installs
itself at the canonical plist path and reloads under a trusted label - that is
the same-uid limit the paragraph below names, and the queue-side provenance
check (DIG-4794) is what closes it. It cannot see the runner, the driver or
this module being replaced in place either: at the same uid those are the
user's own files, and a check that lives inside the files it protects does not
survive their replacement. That is the second half of the same limit, and it
is closed by the same layer. The decision reads kernel and launchd
facts only - the pid of this process, the process tree, launchd's own job
table, the pid launchd reports for the job, the canonical plist, the
container's entrypoint - never BASH_ENV, PAPERCLIP_*, ZDOTDIR, and never `gh`
- so unsetting those variables changes nothing. The tools it asks those
questions of are the system's own: launchctl and ps are run from their
absolute path and only when they are root-owned files, never from the PATH, so
a seat that puts a fake launchctl first on PATH cannot answer the guard's own
question.

What this is not: a proof. At the same uid a seat can copy the runner and run
its own copy without this module, drive the container with its own token,
rewrite the daemon's plist and reload the job under the same label, or replace
the runner, the driver and this module in the checkout they live in - that one
needs no cleverness at all, because the guard is only ever asked by the file it
guards. What the guard does buy is that the cheap forgeries fail: an unset
environment, a forged label, an orphaned process tree, a job loaded from
somewhere else, a job that asks for one PR, a shadowed launchctl. The
authoritative boundary is the queue-side provenance check (DIG-4794): only a
`local-ci` status that carries the verified Woodpecker target_url counts.

Usage:
  python3 scripts/local-ci/launch_guard.py --runner scripts/local-ci/local_ci.py

Exit code 0 means the run may proceed; 78 means it is refused.

This module is byte-identical in the digithings and twelve-x repositories.
"""
import json
import os
import plistlib
import re
import shlex
import stat
import subprocess
import sys
import time

# EX_CONFIG: the run was refused because it was not started by a trusted launcher.
EX_CONFIG = 78

# The launchd jobs that are allowed to start a runner. A label outside this set
# is refused even when launchd says the job is running this very process.
TRUSTED_LAUNCHD_LABELS = (
    "ai.digithings.local-ci",
    "ai.digithings.twelvex-ci",
    "ai.digithings.local-ci-postmerge",
    "ai.digithings.twelvex-ci-postmerge",
)

# A trusted job may run the runner itself, or a driver script that sits next to
# it in the runner's own directory and imports it: postmerge_ci.py is what the
# post-merge launchd job runs, and it calls local_ci.run_checks() in-process.
# The driver has to be the file the installed plist names and the file has to
# live next to the runner that is asking, so a job cannot be pointed at a
# script from somewhere else. That is the whole of it: at the same uid the
# driver, the runner and this module are the user's own files, and a seat that
# can write this directory can replace any of them. No check that lives inside
# those files survives that, which is why the control that closes it lives in
# the queue (DIG-4794) and not here.
TRUSTED_DRIVER_SCRIPTS = ("postmerge_ci.py",)

# The CI container's runner directory and entrypoint (see Dockerfile.worker).
CONTAINER_RUNNER_ROOT = "/opt/local-ci"
CONTAINER_ENTRYPOINT = "/opt/local-ci/worker_entrypoint.sh"

# The tools the guard shells out to, and the only paths it will run them from.
# PATH is never consulted: a seat that puts its own `launchctl` first on PATH
# would otherwise answer the guard's own question - the forged job would report
# the seat's pid, the forged plist path would look canonical, and the forged
# arguments would match. Only a root-owned file that nobody else can write is
# accepted, so the fake has to be root's file to be believed.
TRUSTED_TOOL_PATHS = {
    "launchctl": ("/bin/launchctl", "/usr/bin/launchctl"),
    "ps": ("/bin/ps", "/usr/bin/ps"),
}

# How far up the process tree the guard looks. A launchd job is one hop away;
# the container entrypoint is at pid 1. Ten is plenty and keeps the walk cheap.
MAX_ANCESTORS = 10

# The log the guard appends its decision to. One JSON line per decision, so a
# refused run is evidence and not a rumour.
LOG_NAME = "launch-guard.jsonl"


# ------------------------------------------------------------- system tools --

def _is_system_binary(path):
    """True when the path is a regular file owned by root that nobody else can write.

    The link itself is checked, not the file behind it: a symlink in the way
    would point at a file the seat owns, and a seat cannot make a file
    root-owned, so the link is refused rather than followed.
    """
    try:
        info = os.lstat(path)
    except OSError:
        return False
    if not stat.S_ISREG(info.st_mode):
        return False
    if info.st_uid != 0:
        return False
    return not info.st_mode & (stat.S_IWGRP | stat.S_IWOTH)


def trusted_tool(name):
    """The absolute path of a system tool, or None when there is no trustworthy one.

    PATH is never consulted, and a file the seat owns is never believed: the
    guard asks the system about the system, so the answer has to come from a
    file the seat cannot write. When no such file exists the tool is not
    available, and the guard says so rather than guessing.
    """
    for path in TRUSTED_TOOL_PATHS.get(name, ()):
        if _is_system_binary(path):
            return path
    return None


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
    tool = trusted_tool("ps")
    if tool is None:
        return None
    try:
        proc = subprocess.run([tool] + args, capture_output=True, text=True, timeout=10,
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


def parse_launchctl_list(text):
    """The pid -> label table out of `launchctl list`.

    This is launchd's own table of the jobs it runs. The row whose pid is this
    process's pid is the job that started it - the label in the environment is
    not used for the decision, because a seat can set that to anything.
    """
    jobs = {}
    for line in (text or "").splitlines():
        fields = line.split("\t")
        if len(fields) < 3:
            continue
        pid_text = fields[0].strip()
        label = fields[2].strip()
        if not pid_text.isdigit() or not label:
            continue
        jobs.setdefault(int(pid_text), label)
    return jobs


def canonical_plist_path(label):
    """Where the house tooling installs a launchd job's plist.

    scripts/local-ci/install.sh writes it and dt-daemon-liveness bootstraps
    from it, so a job loaded from anywhere else was not installed by the org.
    """
    return os.path.join(os.path.expanduser("~"), "Library", "LaunchAgents",
                        f"{label}.plist")


def installed_plist_arguments(label):
    """The ProgramArguments of the canonical installed plist, or None.

    The installed plist is what the house says the job runs. The loaded job
    has to agree with it, so a job that was loaded from somewhere else - or a
    job whose arguments were changed after the fact - is not the job the org
    installed.
    """
    try:
        with open(canonical_plist_path(label), "rb") as fh:
            plist = plistlib.load(fh)
    except (OSError, ValueError):
        return None
    arguments = plist.get("ProgramArguments")
    if not isinstance(arguments, list) or not arguments:
        return None
    return [str(argument) for argument in arguments]


def _launchctl(args, timeout=15):
    """Run the system's launchctl and return its stdout, or None."""
    tool = trusted_tool("launchctl")
    if tool is None:
        return None
    try:
        proc = subprocess.run([tool] + args, capture_output=True, text=True,
                              timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def launchctl_job_labels():
    """The pid -> label table launchd reports, or None when it cannot be read."""
    out = _launchctl(["list"])
    if out is None:
        return None
    return parse_launchctl_list(out)


def launchctl_job(label, uid=None):
    """The loaded job's facts, or None when the job is not loaded."""
    if not label:
        return None
    if uid is None:
        uid = os.getuid()
    out = _launchctl(["print", f"gui/{uid}/{label}"])
    if out is None:
        return None
    return parse_launchctl_print(out)


# -------------------------------------------------------------------- facts --

def collect_facts(runner_path):
    """Everything the decision reads. No environment value is ever recorded."""
    label = os.environ.get("XPC_SERVICE_NAME")
    jobs = launchctl_job_labels() or {}
    own_label = jobs.get(os.getpid())
    return {
        "runner": os.path.realpath(runner_path),
        "pid": os.getpid(),
        "ppid": os.getppid(),
        "uid": os.getuid(),
        "ancestors": collect_ancestors(),
        "dockerenv": os.path.exists("/.dockerenv"),
        "xpc_service_name": label,
        "ci_token": bool(os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")),
        "launchd_label": own_label,
        "launchd_job": launchctl_job(own_label) if own_label else None,
        "installed_arguments": (installed_plist_arguments(own_label)
                                if own_label else None),
    }


# ------------------------------------------------------------------ decision --

def _runs_the_entrypoint(parent):
    """True when the parent process is the worker's entrypoint script itself.

    The entrypoint has to be one of the arguments of the parent's own command
    line, not a substring of it: a command that mentions the path on the way
    to something else is not the entrypoint. The ps fallback answers with a
    single string - the whole command line - so that one is split before it is
    compared.
    """
    argv = (parent or {}).get("argv") or []
    if CONTAINER_ENTRYPOINT in argv:
        return True
    if len(argv) != 1:
        return False
    try:
        parts = shlex.split(argv[0])
    except ValueError:
        parts = argv[0].split()
    return CONTAINER_ENTRYPOINT in parts


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
    if not _runs_the_entrypoint(parent):
        return False, ("inside a container, but the runner was not started by the "
                       "worker entrypoint")
    if not facts.get("ci_token"):
        return False, ("the trusted launcher (the CI container) started this run but "
                       "carries no CI credential, so it cannot be the trusted pipeline")
    return True, "the CI container worker entrypoint started this run"


def _script_is_trusted(script, runner):
    """True when the script a job runs is the runner, or a trusted driver beside it.

    The post-merge launchd job runs postmerge_ci.py, which imports the runner
    and calls its run_checks() in-process; that is the same launcher as far as
    the org is concerned. The driver has to live in the runner's own directory
    and to be one of the known driver scripts, so a job cannot be pointed at a
    script from elsewhere. It does not make the driver tamper-proof: a seat
    that can write the runner's directory can replace the driver in place, or
    replace the runner and never ask this module at all. The guard cannot see
    that - those files are the user's own at the same uid - and the queue-side
    provenance check (DIG-4794) is the layer that refuses a status it cannot
    attribute.
    """
    if not script or not runner:
        return False
    try:
        script_path = os.path.realpath(script)
    except OSError:
        return False
    if script_path == runner:
        return True
    if os.path.dirname(script_path) != os.path.dirname(runner):
        return False
    return os.path.basename(script_path) in TRUSTED_DRIVER_SCRIPTS


def _decide_launchd(facts):
    """The launchd daemon: launchd started this very process, from the trusted job."""
    label = facts.get("launchd_label")
    if not label:
        return False, ("no launchd job is running this process: launchd lists no job "
                       "with this pid")
    if label not in TRUSTED_LAUNCHD_LABELS:
        return False, (f"the launchd job {label} is running this process, but it is not "
                       "a trusted runner job")
    if facts.get("ppid") != 1:
        return False, (f"the launchd job {label} runs this process, but the parent pid "
                       f"is {facts.get('ppid')} and not launchd")
    ancestors = facts.get("ancestors") or []
    if not ancestors or ancestors[0].get("pid") != 1:
        return False, (f"the launchd job {label} runs this process, but the process "
                       "tree does not start at launchd")
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
    installed = facts.get("installed_arguments")
    if not installed:
        return False, (f"the canonical plist {expected_plist} is missing or unreadable, "
                       "so the job is not the one install.sh wrote; reinstall it with "
                       "scripts/local-ci/install.sh")
    arguments = job.get("arguments") or []
    if arguments != installed:
        return False, (f"the launchd job {label} runs {arguments} and the canonical plist "
                       f"says {installed}, so the loaded job is not the installed one")
    if len(installed) != 2:
        return False, (f"the canonical plist for {label} runs {len(installed)} arguments; "
                       "the house jobs run the runner with none")
    program, script = installed
    if not os.path.basename(program).startswith("python"):
        return False, f"the launchd job {label} does not run a python interpreter"
    if not _script_is_trusted(script, facts.get("runner")):
        return False, (f"the launchd job {label} runs {script}, which is neither the "
                       "runner that is running now nor a trusted driver next to it")
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
        allowed, reason = _decide_launchd(facts)
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
        "launchd_label": facts.get("launchd_label"),
        "job_pid": job.get("pid"),
        "job_path": job.get("path"),
        "installed_arguments": facts.get("installed_arguments"),
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

# The decision is asked for once per process and then remembered: the runner
# asks the guard at every entry point that does work (main, the lock, the
# worktree, the checks), and the facts cannot change under it.
_DECISIONS = {}


def reset_decisions():
    """Forget the remembered decisions. Only the tests need this."""
    _DECISIONS.clear()


def enforce(runner_path, ctx, facts=None):
    """Refuse the run unless a trusted launcher started it. Exits 78 on refusal."""
    key = os.path.realpath(runner_path) if runner_path else ""
    decision = _DECISIONS.get(key)
    if decision is None:
        if facts is None:
            facts = collect_facts(runner_path)
        allowed, reason = decide(facts)
        append_decision(ctx, _record(facts, allowed, reason))
        decision = (allowed, reason)
        _DECISIONS[key] = decision
    allowed, reason = decision
    if allowed:
        return True
    name = os.path.basename((facts or {}).get("runner") or runner_path or "the runner")
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
