#!/usr/bin/env python3
"""local-ci: runs digithings PR checks on Chris's Mac and posts commit status `local-ci`.
Replaces GitHub Actions PR checks (Actions minutes exhausted, Chris 14 Oct 2026 22:10).
Same-repo PRs into develop only (never forks). Concurrency 1 via lock. Skips when reclaimable
memory is critically low or the disk guard pauses worktrees. Logs: ~/.config/digithings/logs/local-ci/.
Never prints secrets.
A swap/disk-guard skip posts `failure` on the queued PRs, never silence, so merges block
loudly (DIG-3660 must-fix 5). Fork code never executes on this Mac: fork PRs get a `failure`
naming the maintainer re-push path. Static gates only, plus two path-gated lanes:
PR title, PR template,
gitleaks, PII scan, R0 client-literal scan,
guard scripts, actionlint, uv sync, ruff, mypy, doc checks, worker dry-run build (path-gated)
and the bun suites under `bun_suites` in scripts/ci_paths.yaml (path-gated, DIG-5203).
NOT gated (DIG-3605 owns the
rest): per-package pytest suites, compose-validate, npm/pip audit, token-canary,
secret-staleness, invite-key rollout, answer-check, cron dispatch, secret sync.
Also judges same-repo develop->main promotion PRs with the same logic
ci-review-coverage.yml runs via scripts/check_review_coverage.py (DIG-3743),
and keeps the per-PR log as evidence only. It publishes no row for main's
required review context: that verdict has one producer, the workflow
(DIG-4507), and this runner asserts that with the producer guard.
An explicit --pr N run resolves the pull request in any state: a closed or a
merged one still gets a verdict that names it and its state, never a silent
skip (DIG-4812).
A failure that names only the PR metadata gates (`pr-title`, `pr-template`) is
re-checked on the same head once the title or the body is corrected: that
remedy does not touch the tree, so no commit and no review is thrown away for
it (DIG-5695). A failure that names a code gate stays terminal.
A run that no trusted launcher started is refused before anything happens:
the launchd daemon or the CI container only (launch_guard.py, DIG-4796).
Usage: local_ci.py [--pr N] [--dry-run]"""
import ast
import concurrent.futures
import hashlib
import io
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone

try:
    import review_applied
except ImportError:  # fail closed in run_applied, never crash the tick
    review_applied = None
try:
    import pr_template
except ImportError:  # fail closed in run_checks, never crash the tick
    pr_template = None
try:
    import launch_guard
except ImportError:  # fail closed everywhere: a run without the guard does not run at all
    launch_guard = None
try:
    import import_preflight
except ImportError:  # the install check itself is missing: _require_install refuses
    import_preflight = None


def _guard(ctx="local-ci"):
    """Ask the launch guard that a trusted launcher started this run (DIG-4796).

    The guard is asked at every entry point that does work, not only in main():
    the post-merge launchd job drives run_checks() in-process and never goes
    through main(), so a guard that only lived in main() would not be asked on
    the path the live job takes. A run that no trusted launcher started is
    refused with exit 78 before the lock, the worktree, the log or GitHub.

    A launcher that is trusted is not enough: the install has to be complete,
    so the same entry points then check every module the runner imports
    (DIG-5585). A helper that was never copied in binds to None and fails
    closed, which reads as a real verdict on every PR; the tick is refused
    instead, naming the module.
    """
    if launch_guard is None:
        sys.stderr.write("local_ci: the launch_guard module is missing; refusing to "
                         "run rather than run unguarded (DIG-4796)\n")
        sys.exit(78)
    launch_guard.enforce(__file__, ctx)
    _require_install()


#: Set once the install has been checked in this process: the guard is asked at
#: every entry point, and rescanning the same files each time buys nothing.
_INSTALL_CHECKED = False


def _require_install(runner_path=None):
    """Refuse to tick when a module this runner imports is absent (DIG-5585).

    The runner imports its helpers with a ``None`` fallback and each helper
    fails closed, so a module that was never copied in does not stop the tick:
    it makes every verdict read as a real failure. On 24 Oct a checkout
    without ``scripts/review_pass_filter.py`` left eight PRs red on
    ``review-applied`` while the status blamed the review (DIG-4674).

    A broken install is refused before anything else happens: no lock, no
    worktree, no GitHub write. The refusal names the missing module and the
    module that imports it, and exits 78 (EX_CONFIG).
    """
    global _INSTALL_CHECKED
    if runner_path is None:
        if _INSTALL_CHECKED:
            return
        runner_path = __file__
    if import_preflight is None:
        lines = ["local-ci: the import_preflight module is missing; refusing to tick "
                 "rather than tick without the install check (DIG-5585)"]
    else:
        missing = import_preflight.check(runner_path)
        if not missing:
            _INSTALL_CHECKED = True
            return
        lines = import_preflight.report(missing, runner_path)
    for line in lines:
        sys.stderr.write(line + "\n")
        try:
            log(line)
        except OSError:
            # A log directory that cannot be written must not turn a refusal
            # into a traceback: the refusal is the message.
            pass
    sys.exit(78)


HOME = os.path.expanduser("~")
REPO = "digithings-ai/digithings"
MAIN = os.environ.get("LOCAL_CI_MAIN") or f"{HOME}/Code/digithings"
WT = os.environ.get("LOCAL_CI_WT") or f"{HOME}/Code/local-ci/wt"
LOGD = f"{HOME}/.config/digithings/logs/local-ci"
LOCK = f"{HOME}/.config/digithings/state/local-ci.lock"
PAUSE = f"{HOME}/.config/digithings/state/worktree-pause"
# The claim ledger (DIG-5135). A run posts a `pending` row before it starts the
# gates, so a run that dies leaves the head with a `pending` row and no verdict.
# Nothing re-queued such a head, so one lost run cost that PR its required
# check for good - the queue then refuses the PR for ever. The ledger names the
# holder of every claim: a head whose holder is gone is owed its receipt again
# and is queued; a head whose holder is alive is left alone.
CLAIMS = f"{HOME}/.config/digithings/state/local-ci-claims"
# A `pending` row with no ledger entry - posted by a runner that predates the
# ledger, or by the CI container, which keeps its own state directory - is given
# this long before it is treated as lost. The window has to be longer than the
# longest a producer can spend on one head, because a row that is younger than
# that may still have a producer behind it: the runner's own step budgets sum
# to about 15000 s (gitleaks 600 s, uv sync 900 s, npm ci 600 s, mypy 600 s,
# eight worker dry-runs of 300 s each, eight bun suites at 900 s each and the
# rest), so anything shorter would take a head from a run that is still going.
CLAIM_STALE_SECS = 21600
# A claim held for longer than this is void: a run that legitimately takes
# longer than this is hung, and a hung run owes the head a receipt. The window
# is longer than the worst case a living run can take (about 4.2 h of step
# budgets), so a slow but alive run keeps the head it is checking and no
# second run is started on top of it.
CLAIM_MAX_SECS = 28800
# The life of the tick lock: a lock whose holder is gone is taken over after
# this. It is shorter than the life of a claim on purpose. A tick that takes
# over a stale lock must not take the head of a run that is still gating, and
# the claim is what says that run is still there.
LOCK_MAX_AGE = 7200
# The tick lock is a directory, and the host's liveness supervisor reads the
# mtime of that directory to decide whether the holder is wedged: it kills a
# live holder that has held the lock for 1800 s (com.digithings.daemon-liveness,
# MAX_HOLDER_SECONDS). A tick that gates one PR runs far longer than that - the
# runner's own step budgets sum to about 15000 s - so the supervisor killed a
# healthy runner mid-run: the receipt never landed, the head kept a `pending`
# row and the PR lost its required check until the next tick (DIG-5135).
# The runner renews the lock while it works. A working tick stays fresh, and a
# runner that has really wedged stops renewing, so the supervisor still kills
# it - the rule turns from a guess about how long a tick may take into the
# thing it was always meant to be: proof that the holder is alive.
LOCK_HEARTBEAT_SECS = 60
# How often the renewal says so in the log. The supervisor also warns when the
# log has not advanced for three intervals, so the tick says it is alive well
# inside that window.
LOCK_HEARTBEAT_LOG_EVERY = 5
# The runner keeps its own checkout on origin/develop (DIG-5135). The refresh
# is throttled so a tick every three minutes does not fetch every three
# minutes, and it is never applied to a linked worktree: that is somebody
# else's checkout.
REFRESH_STATE = f"{HOME}/.config/digithings/state/local-ci-refresh"
REFRESH_MIN_SECS = 900
# What install.sh writes when it installs the runner: the checkout the runner
# may keep current, and whether the runner may move it at all. Without this
# marker the runner never moves a checkout (DIG-5135).
RUNNER_MARKER = f"{HOME}/.config/digithings/state/local-ci-runner.json"
CTX = "local-ci"; MAX_PER_TICK = 2; MIN_AVAIL_MB = 2048; MIN_FREE_PCT = 20.0
# The app's own status row, posted with the app's installation token (DIG-4809).
# The pipeline mints the token before the worker starts and writes it to this
# file; the worker then posts the same verdict twice, once per identity, so
# the two rows can be compared for 48 hours. The app token is the only
# identity allowed to post this row: with no token there is no row at all,
# because a row under another identity would be worse than no row.
APP_CTX = "local-ci/app"
APP_TOKEN_FILE = f"{HOME}/.config/digithings/secrets/app-token"
# Primary memory gate (DIG-3783): skip below this system-wide free percentage,
# the same signal the board driver uses. vm_stat reclaimable MB is the fallback.
# One promotion review per tick: the range is ~1000 commits and takes minutes.
REVIEW_MAX_PER_TICK = 1
# A judgement is repeated at most hourly: reviews, approvals and labels may land
# after it, but re-walking a ~1000-commit range every 3 min tick would burn the
# Mac for nothing.
REVIEW_RECHECK_SECS = 3600
SKIP_PREFIX = "local-ci skipped:"
# A failure whose gates are all PR metadata (DIG-5695). These are the only
# gates whose remedy does not touch the tree: the author edits the title or the
# body, the head and every review on it stay as they are, and the head is worth
# one more look on the same sha. A failure that names any other gate stays
# terminal: re-queueing a code failure would loop the daemon on every tick and
# re-run a whole lane for nothing.
METADATA_GATES = frozenset({"pr-title", "pr-template"})
# Memory gate (DIG-3706, fixed DIG-3783): vm.swapusage "free" is headroom inside
# already-allocated swap files, which macOS grows on demand, so it false-trips
# while the Mac is healthy (727-855MB free vs 900MB gate, with 81% system-wide
# memory free). Gate on the same signal the board driver uses: `memory_pressure`
# "System-wide memory free percentage" (skip below MIN_FREE_PCT). vm_stat
# reclaimable (free + speculative + purgeable + inactive) is the fallback when
# that will not parse, and is logged every tick. Inactive pages hold the file
# cache the kernel reclaims on demand; without them the number stayed tiny
# (~345MB at 69% system-wide free) while the Mac was healthy. DIG-3706's
# re-queue of skipped PRs is unchanged. kern.memorystatus_level scale is
# undocumented (web unreachable to verify), so it is logged for tuning, never
# gated on.
FORK_DESC = "fork code never runs on this Mac; maintainer: re-push to a same-repo branch"
GATED_NOTE = "static gates passed (pytest/audits not gated, see DIG-3605)"
TYPES = "feat|fix|docs|chore|refactor|perf|test|ci|build|revert|style"

# Ruff path list used by the lint gate. The gate reads the list from the tree
# under test (its own .github/workflows/ci.yml) so a module rename cannot leave
# the gate naming a directory that no longer exists (DIG-4602). The list below
# is the fallback only: it is used when the tree's ci.yml cannot be read, and
# every entry that does not exist in the tree is dropped. ruff 0.16 fails on a
# missing path (E902), so naming a directory that is not there turns every
# other PR red; linting fewer paths only under-lints.
RUFF_PATHS_CANDIDATES = ("digibase/src", "digibot/src", "digigraph/src",
                         "digiquant/src", "digisearch/src", "digitrace/src",
                         "tests")

# Worker dry-run build gate (DIG-4010): same worker app paths and build command as
# ci.yml `worker-build` (PR #5802). Trips only on PRs touching a gated path.
WORKER_APPS = ("digithings-cron", "dashboard-api", "digidata-api", "digiquant-runner",
               "digitrace-langfuse", "digitrace-ingest", "digichat-cloudflare",
               "digithings-stack-cloudflare",
               # twelvex-runner is in the ci.yml worker-build matrix but was missing
               # here, so the local gate built one Worker less than CI does. It is
               # the build that proves the app's workspace imports bundle (DIG-4753).
               "twelvex-runner")
WORKER_GATE_PATTERNS = tuple(f"apps/{a}/**" for a in WORKER_APPS) + (
    "apps/**/wrangler.toml", "package.json", "package-lock.json",
)
# A dry-run that has not finished in 5 minutes is wedged, not slow (DIG-4453).
WORKER_DRY_RUN_TIMEOUT = 300
# Bun suites (DIG-5203). The packages below declare `"test": "bun test"`, and the
# only lanes that ran them were the GitHub workflows test-bun-suites.yml and
# test-clients-tui.yml (DIG-2940 / DIG-2072). Both are retired with Actions
# (DIG-3604 / DIG-4454), so the required `local-ci` check said nothing about a
# clients/** or packages/** change: #6271 (head 3c551ad0af) carried a green
# receipt while digichat-tui's suite (70 pass, 1 fail) only ever ran by hand.
# The suite list is read from scripts/ci_paths.yaml `bun_suites`, the file that
# already carried the paths for the retired lane, so the gate cannot drift from
# the list of suites the repository believes it has; BUN_SUITE_DIRS is the
# fallback for a checkout where the block is missing or empty.
BUN_SUITE_DIRS = ("clients/digichat-tui", "clients/digiquant-tui", "clients/digivoice-tui",
                  "clients/digichat-devkit", "packages/surface-config", "packages/hero-banner",
                  # DIG-5212: the recorded-frame contract both TUI clients and the
                  # dashboard import. Its suite is the only place that contract
                  # is tested, so the fallback list must cover it too.
                  "packages/tui-frame",
                  # The pre-move digivoice TUI: clients/digivoice-tui is the live
                  # client (#5548), this is the legacy tree the retired lane also
                  # ran. Kept so the gate never drops a suite the lane covered.
                  "digivoice/tui")
# The bun the suites were written against. An unpinned tool changing behaviour
# under a green build is the #1701/#1705/#1711 failure mode the retired lanes
# pinned 1.4.2 for; the host's bun is checked against this before any suite runs,
# and a bump is its own PR.
BUN_PIN = "1.4.2"
BUN_INSTALL_TIMEOUT = 600
BUN_TEST_TIMEOUT = 300
# --- how many independent gates run at once --------------------------------
# Every gate below is its own process with its own temp paths, its own cwd and
# its own report file, so nothing about them needs the others to have finished.
# They ran one after another until this pool existed, and the tick paid every
# step's full latency in series: on 2026-10-25 the same 25 steps measured 100 s
# on an idle Mac and 51 min while the agent fleet was building (local-ci.log
# 17:23:05 -> 18:14:09), because each step queued behind the others for a slot.
# The pool is bounded well under the host's core count so one tick cannot crowd
# out the rest of the machine - the failure mode the serial version had.
STEP_POOL = 6
os.makedirs(LOGD, exist_ok=True)
# --- VPN proxy (DIG-4453) ------------------------------------------------------
# Measured 2026-10-19: `npm exec -- wrangler deploy --dry-run` never returns when
# HTTP_PROXY/HTTPS_PROXY point at the local wireproxy (127.0.0.1:18450). The wrangler
# CLI then sits idle in its event loop holding 7 ESTABLISHED sockets to the proxy and
# the step only ends when its timeout fires. With the proxy dropped the same command
# exits 0 in 2.5 s ("Total Upload: 106.66 KiB ... --dry-run: exiting now.").
# The launchd tick inherits no proxy, so only agent-launched runs wedged - and a
# wedged run holds the lock for 7 apps x the dry-run budget, which starves
# develop's only required context (local-ci) and blocks every develop PR.
PROXY_KEYS = ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy")


def build_env(base=None):
    """The gate's environment: PATH widened, VPN proxy dropped.

    The gate must behave the same whoever starts it, so the proxy goes here and
    not per step (twelvex_ci.py bypasses it per step for the hosts the proxy does
    not carry; nothing this gate runs needs it).
    """
    b = dict(os.environ if base is None else base)
    b["PATH"] = f"/opt/homebrew/bin:/usr/local/bin:{b.get('PATH', '/usr/bin:/bin')}"
    for k in PROXY_KEYS:
        b.pop(k, None)
    # The app token belongs to the app row alone. Handed over in the
    # environment, it would ride along into every child the gate starts (npm,
    # wrangler, uv, git, the check scripts). The app row builds its own
    # environment with the token in it (DIG-4809).
    b.pop("CI_APP_TOKEN", None)
    return b


ENV = build_env()

# A scanner has to finish before the tree is judged, and the budget for that is
# the machine's, not the guard's. On 2026-10-22 the post-merge run on develop
# 8cfd404816a6 turned three scanners red on a 600 s timeout while the tree was
# clean (DIG-5318). This is the scanner's own ceiling AND its step budget: a
# scanner is not in STEP_BUDGETS, so before DIG-5724 it took the 180 s default
# and min(180, 600) made this knob inert. On PR #6525 (2026-10-27) five
# clean-tree scanners were killed at 182-183 s while the tree was clean; the
# 600 s default is 3.3x that worst measurement, and LOCAL_CI_SCAN_TIMEOUT
# raises both numbers at once for a slower host.
SCAN_TIMEOUT = int(os.environ.get("LOCAL_CI_SCAN_TIMEOUT", "600") or 600)

# A step's own wall-clock ceiling (2026-10-26). The gate does 99.6 s of real
# work across all 25 steps, yet two runs recorded 32 m and 44 m: a check that
# measures 10 s alone had hung, and the runner waited out a per-call timeout of
# 1800 s. The cost was never the work, so every step now has a ceiling of
# STEP_BUDGET seconds. A step that overruns is killed by process group (`sh`
# already gives the child its own session), recorded as
# `<step> exceeded <N>s and was killed`, and the tick moves on to the next step.
# A step that legitimately needs longer names itself in STEP_BUDGETS (`*` is a
# prefix, for the bun and worker-build families); an explicit `budget=` argument
# wins over both. Tree scanners pass SCAN_TIMEOUT as that explicit budget
# (DIG-5724), so their own knob reaches them. LOCAL_CI_STEP_BUDGET raises the
# default for every other step on the host, and a caller `timeout` that is
# tighter than the budget still wins.
STEP_BUDGET = int(os.environ.get("LOCAL_CI_STEP_BUDGET", "180") or 180)
STEP_BUDGETS = {
    # A whole-history secret scan and a workspace dependency install are the
    # slow steps; a full type-check is the other one.
    "gitleaks": 600,
    "uv-sync": 900,
    "mypy": 600,
    "ruff": 300,
    # One npm install per worker-build run, then one dry-run per worker app.
    "worker-build:npm-ci": 600,
    "worker-build:*": 300,
    # Bun suites (DIG-5203): install from the committed lockfile, then run.
    "bun-install:*": 600,
    "bun:*": 300,
}
# A step is attempted at most this many times, and the attempts share the one
# budget: a timeout kill spends it, so a stalled step is not retried into a
# second stall window.
RETRY_CAP = 2
# No new attempt starts with less than this left of the budget.
RETRY_MIN_SECS = 5


def no_fsmonitor_env(base):
    """``base`` plus a git override that switches the fsmonitor daemon off.

    The scanners read the tree through git, and git must not read it through
    the fsmonitor daemon. The daemon is a per-clone cache of the working tree
    and a busy machine can wedge it: in the post-merge worktree (4.3 GB,
    node_modules + .venv) `git ls-files` spent 5.2 s of wall clock on 0.01 s of
    CPU inside the daemon, and then failed outright with "could not read IPC
    response" (DIG-5318). With the daemon off the same call takes 0.02 s, and
    a tree scan never depends on a cache that can be stale, slow or broken.
    """
    env = dict(base)
    try:
        count = int(env.get("GIT_CONFIG_COUNT", "0") or 0)
    except ValueError:
        count = 0
    env["GIT_CONFIG_COUNT"] = str(count + 1)
    env[f"GIT_CONFIG_KEY_{count}"] = "core.fsmonitor"
    env[f"GIT_CONFIG_VALUE_{count}"] = "false"
    return env


SCAN_ENV = no_fsmonitor_env(ENV)

def log(m):
    with open(f"{LOGD}/local-ci.log", "a") as f: f.write(time.strftime("%F %T ") + m + "\n")

def sh(cmd, cwd=None, timeout=1800, out=None, name=None, env=None):
    """Run a command under a wall-clock timeout that takes the WHOLE tree down.

    `subprocess.run(timeout=)` kills only the direct child: the wrangler and
    esbuild grandchildren survive, are re-parented to pid 1 and leak (8 leaked
    trees measured 2026-10-19). The child gets its own process group so the
    timeout can break the tree, and its identity is recorded for the watchdog.

    `env` replaces the gate's environment for this one call. The app status
    posts with the app's own token, and that token belongs in the child's
    environment and not in the gate's (DIG-4809).
    """
    try:
        p = subprocess.Popen(cmd, cwd=cwd, env=ENV if env is None else env, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True,
                             start_new_session=True, shell=isinstance(cmd, str))
    except OSError as e:
        if out: out.write(f"LAUNCH FAILED {cmd}: {e}\n")
        return 127, ""
    _write_child_state(p.pid, name or (cmd if isinstance(cmd, str) else " ".join(cmd)), timeout)
    try:
        stdout, stderr = p.communicate(timeout=timeout)
        rc = p.returncode
    except subprocess.TimeoutExpired:
        _kill_step_tree(p)
        try:
            stdout, stderr = p.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            stdout, stderr = "", ""
        rc = 124
        if out: out.write(f"TIMEOUT {timeout}s {cmd}\n")
    finally:
        _clear_child_state(p.pid)
    if out: out.write(f"$ {cmd if isinstance(cmd,str) else ' '.join(cmd)}\n{stdout[-20000:]}{stderr[-20000:]}\n[rc={rc}]\n")
    return rc, stdout

def gh(*a):
    rc, o = sh(["gh", *a], timeout=120)
    return o if rc == 0 else None

def swap_free_mb():
    rc, o = sh(["sysctl", "vm.swapusage"])
    m = re.search(r"free = ([\d.]+)M", o or "")
    return float(m.group(1)) if m else 99999

def sysctl_num(key):
    rc, o = sh(["sysctl", "-n", key])
    try: return float((o or "").strip())
    except ValueError: return float("nan")

def parse_vm_stat_available_mb(o):
    """Reclaimable memory in MB from vm_stat text: free + speculative +
    purgeable + inactive. Inactive pages hold the file cache macOS reclaims on
    demand (DIG-3783: 991,764 inactive pages ~= 15.5GB while free+spec+purgeable
    read ~345MB at 69% system-wide free). 99999.0 on parse failure (fail-open)."""
    o = o or ""
    m = re.search(r"page size of (\d+) bytes", o)
    ps = int(m.group(1)) if m else 16384
    tot = 0
    for k in ("Pages free", "Pages speculative", "Pages purgeable", "Pages inactive"):
        m = re.search(rf"^{re.escape(k)}:\s*(\d+)\.", o, re.M)
        if m: tot += int(m.group(1))
        else: return 99999.0
    return round(tot * ps / (1024 * 1024), 1)

def parse_memory_pressure_pct(o):
    """System-wide memory free percentage from `memory_pressure` output, or None
    when the line is absent/unparseable (caller falls back to the MB gate)."""
    m = re.search(r"System-wide memory free percentage:\s*([\d.]+)%", o or "")
    try: return float(m.group(1)) if m else None
    except ValueError: return None

def mem_free_pct():
    """System-wide memory free percentage (same signal the board driver uses).
    None when unreadable."""
    rc, o = sh(["memory_pressure"])
    return parse_memory_pressure_pct(o or "")

def mem_available_mb():
    """Reclaimable memory (free + speculative + purgeable + inactive) in MB.
    Huge on parse failure (fail-open, as before)."""
    rc, o = sh(["vm_stat"])
    return parse_vm_stat_available_mb(o or "")

def build_target_url():
    """The build that made this status green, as a URL, or "".

    `LOCAL_CI_TARGET_URL` is the explicit name; `CI_PIPELINE_URL` is what
    Woodpecker injects into every step, so the worker running inside the
    pipeline needs no configuration. A run on the host has neither and posts a
    status that names no build - the merge queue reads that back and refuses it,
    naming the missing build as the reason (DIG-4794).
    """
    return (os.environ.get("LOCAL_CI_TARGET_URL") or os.environ.get("CI_PIPELINE_URL") or "").strip()


def log_soft(msg):
    """A log line that never breaks the caller.

    The app row goes out after the `local-ci` row. A log directory that cannot
    be written must not cost the row, and must not stop the tick.
    """
    try:
        log(msg)
    except OSError:
        pass


#: The shape of a GitHub App installation token. GitHub issues the opaque
#: form - `ghs_` and a body with no separator - and the App plan writes the
#: token down as `ghs_<appid>_<jwt>`. Both are accepted, and nothing else is:
#: the row is posted under the app's bot, so a token that is not an app token
#: would post it under the wrong identity (DIG-4809).
APP_TOKEN_SHAPE = re.compile(r"^ghs_(?:[0-9]+_)?[A-Za-z0-9_\-\.]{20,}$")


def _read_token_file(path):
    """The token in the file at `path`, or "" when there is none.

    The read is defensive on purpose. A file that cannot be opened, is not a
    regular file (a FIFO would block the tick for ever) or holds bytes that are
    not text must leave the row unposted instead of stopping the tick: a
    broken token file must never cost the `local-ci` row as well (DIG-4809).
    """
    try:
        if not os.path.isfile(path):
            return ""
        with open(path, "rb") as f:
            raw = f.readline()
    except OSError:
        return ""
    try:
        return raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        return ""


def _token_sources():
    """Every place the app token can come from, in the order it is tried."""
    for path in (os.environ.get("LOCAL_CI_APP_TOKEN_FILE"), APP_TOKEN_FILE):
        if path:
            yield _read_token_file(path)
    yield (os.environ.get("CI_APP_TOKEN") or "").strip()


def app_token():
    """The app installation token the pipeline minted, or "" when there is none.

    Read from the file the pipeline wrote for the worker alone, never printed
    and never taken from the command line. Only the first line of the file is
    the token: a file with more content must not put two lines into it. The
    chain is the named file, the default file, then the environment as the
    fallback for a run that hands the token over directly. A named file that
    does not exist falls through to the default one instead of ending the
    search, and a token that is not an app installation token is passed over
    as well: a file holding the wrong secret must not hide a good one behind
    it (DIG-4809).
    """
    for tok in _token_sources():
        if tok and is_app_installation_token(tok):
            return tok
    return ""


def raw_app_token():
    """The first token the chain offers, whatever shape it has.

    The shape of a token that was found is a diagnosis, not a result: the
    reason a row was skipped is in the log, and the reason it says "not an
    app installation token" has to be the token the worker actually read
    (DIG-4809).
    """
    for tok in _token_sources():
        if tok:
            return tok
    return ""


def is_app_installation_token(tok):
    """True when the token is shaped like a GitHub App installation token.

    The app row goes out under `digithings-ci[bot]`. A token that is not an
    installation token - the repository's own token, say - would post that row
    under the wrong identity, so it is refused (DIG-4809).
    """
    return bool(APP_TOKEN_SHAPE.match(tok or ""))


def status_fields(state, desc):
    """The fields of one status row: the verdict, the description and the build.

    Both rows are built from this one call, so the `local-ci` row and the
    `local-ci/app` row cannot disagree about anything but the context.
    """
    fields = {"state": state, "description": desc[:139]}
    target = build_target_url()
    if target:
        fields["target_url"] = target
    return fields


def status_args(sha, ctx, fields):
    """The `gh api` arguments for one status row."""
    args = ["api", "-X", "POST", f"repos/{REPO}/statuses/{sha}",
            "-f", f"state={fields['state']}", "-f", f"context={ctx}",
            "-f", f"description={fields['description']}"]
    if "target_url" in fields:
        args += ["-f", f"target_url={fields['target_url']}"]
    return args


def _failure_reason(text, tok):
    """One line of the failed command's answer, with the token taken out.

    A failed row has to be diagnosable: an installation without the
    `statuses: write` permission says so in its answer, and "rc=1" alone does
    not (DIG-4809).
    """
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    detail = ""
    for ln in reversed(lines):
        if ln.startswith("$ ") or ln.startswith("[rc="):
            continue
        detail = ln
        break
    if tok:
        detail = detail.replace(tok, "<redacted>")
    return detail[:200]


def app_status(sha, fields):
    """Post the same verdict under `local-ci/app`, with the app's own token.

    The token goes into the child's environment, never into its arguments, so
    it cannot land in a process listing or in the log line the runner writes
    for every command it starts. With no token there is no row: the app is the
    only identity allowed to post this one. A token that is not an app
    installation token is refused the same way, because it would post the row
    under the wrong identity (DIG-4809).

    True when the row is in, False when the post was refused, None when there
    is no token to post it with. A refused app row is the app's own business:
    the head keeps the receipt it earned on `local-ci` and stays out of the
    queue, because a second context that refuses its row must not keep a head
    waiting for a check that already ran (DIG-4809, DIG-5135).
    """
    tok = app_token()
    if not tok:
        if raw_app_token():
            log_soft("app status: skipped, the token is not an app installation token")
        else:
            log_soft("app status: skipped, no app token")
        return None
    env = dict(ENV)
    env["GH_TOKEN"] = tok
    env["GITHUB_TOKEN"] = tok
    buf = io.StringIO()
    rc, _ = sh(["gh", *status_args(sha, APP_CTX, fields)], timeout=120, env=env, out=buf)
    if rc != 0:
        reason = _failure_reason(buf.getvalue(), tok)
        log_soft(f"app status: failed (rc={rc}){': ' + reason if reason else ''}")
        return False
    log_soft(f"app status: {fields['state']} {APP_CTX}")
    return True


def status(sha, state, desc, app=True):
    """Post the `local-ci` status, naming the build when there is one.

    The name is what makes the status evidence: a commit status is worth what
    its writer is worth, and the queue reads the build back from Woodpecker
    before it trusts the green (DIG-4794).

    The same verdict goes out under `local-ci/app`, posted with the app's own
    token. Both rows are built from one set of fields, so they are always the
    same verdict (DIG-4809). The app row follows the repo row: a repo row
    that was refused leaves no app row behind, so the two can never carry
    different verdicts. `app=False` posts the repo row alone, for the heads
    that are not commits of this repository at all.
    """
    fields = status_fields(state, desc)
    if gh(*status_args(sha, CTX, fields)) is None:
        if app:
            log_soft(f"local-ci status: {state} was refused, {APP_CTX} not posted")
        return False
    if app:
        # The app row is a second context, not the required check. A refused app
        # row is logged and the head keeps the receipt it earned on `local-ci`:
        # a head must not stay in the queue for ever because a second context
        # refused its row. The app row is the app's own business (DIG-4809).
        if app_status(sha, fields) is False:
            log_soft(f"local-ci status: {state} is in, {APP_CTX} was refused")
    return True


def review_judged_at(pr):
    """When local-ci last judged this promotion head: the mtime of its per-PR log.

    Since DIG-4507 the runner publishes no verdict for main's required review
    context, so there is no status row of ours to read back. The per-PR log is
    the record of the judgement, and its mtime is the timestamp the hourly
    re-check keys on.
    """
    n = pr.get("number"); sha = pr.get("headRefOid") or ""
    if not n or not sha: return None
    try: return os.path.getmtime(f"{LOGD}/pr{n}-review-{sha[:12]}.log")
    except OSError: return None


def _status_age_secs_or_none(created_at):
    """Age of a status row in seconds, or None when the row says nothing about it."""
    try:
        ts = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - ts).total_seconds()
    except (ValueError, TypeError):
        return None


def _status_age_secs(created_at):
    age = _status_age_secs_or_none(created_at)
    return float("inf") if age is None else age


def is_promotion_pr(pr):
    """Same-repo PRs into main carrying develop (promotion title). Only these get
    the local review-coverage verdict; other main PRs are out of scope."""
    if pr.get("baseRefName") != "main" or bool(pr.get("isCrossRepository")):
        return False
    title = pr.get("title") or ""
    return title == "chore: promote develop to main" or re.match(
        r"^chore\([^)]*\):\s*release\s|^chore\(release\):\s", title) is not None


def pending_reviews(prs):
    """Promotion PRs local-ci has not judged in the last hour.

    The judgement is evidence only (see review_judged_at): the verdict that
    gates main comes from the ci-review-coverage workflow, which is the single
    producer of that required context since DIG-4507.

    A judged head is re-walked once an hour on purpose, success included: the
    walk is capped at REVIEW_MAX_PER_TICK per tick, so an open promotion costs
    at most one extra walk per hour and the evidence stays fresh while reviews,
    approvals and labels land on the head.
    """
    out = []
    for p in prs:
        if not is_promotion_pr(p):
            continue
        t = review_judged_at(p)
        if t is None or (time.time() - t) >= REVIEW_RECHECK_SECS:
            out.append(p)
    out.sort(key=lambda p: p["updatedAt"], reverse=True)
    return out


def compare_commit_set(base, sha, out):
    """Complete GitHub compare payload for base...sha, or None.

    A shallow clone cannot express the promotion range locally: `git log
    origin/main..head` stops at the graft boundary and can return one commit,
    which would report a false green over a ~1000-commit promotion (DIG-4389).
    Mirrors gitleaks_log_opts: ask GitHub, and fail closed when the answer is
    missing or truncated. Never posts a verdict it cannot stand behind.
    """
    data = _gh_json(["api", f"repos/{REPO}/compare/{base}...{sha}"])
    if not isinstance(data, dict):
        out.write("review-coverage FAIL: shallow clone and GitHub compare was unreadable\n")
        return None
    commits = data.get("commits")
    total = data.get("total_commits")
    if not isinstance(commits, list) or not isinstance(total, int):
        out.write("review-coverage FAIL: shallow clone and GitHub compare had no commit list\n")
        return None
    if total != len(commits):
        out.write(f"review-coverage FAIL: GitHub compare truncated ({len(commits)} of {total}); "
                  "the local clone must be unshallowed\n")
        return None
    return data


def run_review_coverage(pr, out):
    """Run the repo's own gate (the logic ci-review-coverage.yml runs) over
    origin/main..head. Returns (ok, total, unreviewed). Counts come from the
    script's --json, never from scraping human output: a 1000-commit run prints
    ~100KB, so any line-capped read silently drops verdict rows (DIG-3743).

    On a shallow clone the local range is not the promotion range, so the
    commit set comes from GitHub's compare API instead (DIG-4389).
    """
    sha = pr["headRefOid"]
    sh(["git", "fetch", "-q", "origin", "main"], cwd=WT, timeout=600, out=out)
    out.write(f"\n===== review-coverage origin/main..{sha[:12]}\n")
    cmd = [sys.executable, "scripts/check_review_coverage.py"]
    compare_path = None
    rc, shallow = sh(["git", "rev-parse", "--is-shallow-repository"], cwd=WT)
    if rc != 0 or (shallow or "").strip() == "true":
        data = compare_commit_set("main", sha, out)
        if data is None:
            return False, -1, -1
        fd, compare_path = tempfile.mkstemp(prefix="review-coverage-", suffix=".json")
        with os.fdopen(fd, "w") as handle:
            json.dump(data, handle)
        cmd += ["--commits-json", compare_path, "--head", sha]
        out.write(f"shallow clone: judging {len(data.get('commits') or [])} commits "
                  "from GitHub compare\n")
    else:
        cmd += ["--base", "origin/main", "--head", sha]
    cmd.append("--json")
    try:
        proc = subprocess.run(
            cmd, cwd=WT, env=ENV, capture_output=True, text=True, timeout=1800)
    except subprocess.TimeoutExpired:
        out.write("TIMEOUT check_review_coverage.py --json\n")
        return False, -1, -1
    finally:
        if compare_path:
            try: os.unlink(compare_path)
            except OSError: pass
    out.write(f"$ check_review_coverage.py --json [rc={proc.returncode}]\n")
    try: data = json.loads(proc.stdout or "")
    except ValueError: data = None
    if not isinstance(data, dict):
        out.write((proc.stdout or "")[-20000:]); out.write((proc.stderr or "")[-5000:])
        return False, -1, -1
    checked = data.get("commits") or []
    unrev = data.get("unreviewed") or []
    out.write(f"checked {len(checked)} commits, {len(unrev)} unreviewed\n")
    for row in unrev:
        out.write(f"  UNREVIEWED {row.get('sha', '?')} #{row.get('pr', '?')} "
                  f"{str(row.get('subject', ''))[:72]} -- {str(row.get('why', ''))[:200]}\n")
    out.write("FULL_JSON_FOLLOWS\n")
    out.write(proc.stdout)
    if proc.stderr:
        out.write(proc.stderr[-5000:])
    ok = proc.returncode == 0 and not unrev
    return ok, len(checked), len(unrev)


def process_review(pr, dry):
    sha = pr["headRefOid"]; n = pr["number"]
    logf = f"{LOGD}/pr{n}-review-{sha[:12]}.log"
    log(f"PR #{n} review-coverage {sha[:12]} start")
    t0 = time.time()
    with open(logf, "w") as out:
        ok_wt, why = prepare_wt(n, sha, pr["baseRefName"], out)
        ok, total, unreviewed = run_review_coverage(pr, out) if ok_wt else (False, -1, -1)
    mins = (time.time() - t0) / 60
    if ok: st, desc = "success", f"review coverage: all {total} commits reviewed ({mins:.0f}m)"
    else: st, desc = "failure", f"review coverage: {unreviewed} unreviewed of {total} (see log) ({mins:.0f}m)"
    log(f"PR #{n} review-coverage {sha[:12]} {st}: {desc} log={logf}")
    return st

def gitleaks_log_opts(base, sha, out):
    """Range gitleaks should scan.

    A full clone uses `origin/<base>..<sha>`. A shallow clone makes that range
    include commits already on the real base, because those commits are not
    reachable from the shallow tip. Ask GitHub for the compare set then, and
    scan only those non-merge commits. Return None to fail closed when that
    list is missing or truncated. Never prints a secret.
    """
    rc, shallow = sh(["git", "rev-parse", "--is-shallow-repository"], cwd=WT)
    if rc == 0 and (shallow or "").strip() != "true":
        return f"--no-merges origin/{base}..{sha}"
    data = _gh_json(["api", f"repos/{REPO}/compare/{base}...{sha}"])
    if not isinstance(data, dict):
        out.write("gitleaks FAIL: shallow clone and GitHub compare was unreadable\n")
        return None
    commits = data.get("commits")
    total = data.get("total_commits")
    if not isinstance(commits, list) or not isinstance(total, int):
        out.write("gitleaks FAIL: shallow clone and GitHub compare had no commit list\n")
        return None
    if total != len(commits):
        out.write(f"gitleaks FAIL: GitHub compare truncated ({len(commits)} of {total})\n")
        return None
    shas = []
    for c in commits:
        if not isinstance(c, dict):
            out.write("gitleaks FAIL: compare commit was not an object\n")
            return None
        if len(c.get("parents") or []) != 1:
            continue
        sid = str(c.get("sha") or "")
        if not re.fullmatch(r"[0-9a-f]{40}", sid):
            out.write("gitleaks FAIL: compare commit sha was not 40 hex\n")
            return None
        shas.append(sid)
    out.write(f"gitleaks shallow range: {len(shas)} non-merge commits of {total}\n")
    if not shas:
        return "--no-walk --max-count=0"
    return "--no-walk --no-merges " + " ".join(shas)


def parse_ci_paths_block(text, key):
    """Parse one `key:` path-filter block out of scripts/ci_paths.yaml text.

    Returns the `- <pattern>` entries in order, or [] when the block is absent.
    The block ends at the next top-level key, so a key's entries can never leak
    into the next key's list.
    """
    out = []
    in_block = False
    for line in (text or "").splitlines():
        if not line.startswith((" ", "\t")):
            if line.startswith(f"{key}:"):
                in_block = True
            elif in_block:
                break
            continue
        if in_block:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if s.startswith("- "):
                pat = s[2:].strip().strip("'\"")
                if pat:
                    out.append(pat)
    return out


def parse_workers_patterns(text):
    """Parse the `workers:` path-filter block out of scripts/ci_paths.yaml text."""
    return parse_ci_paths_block(text, "workers")


def glob_to_regex(pat):
    """Translate a ci path-filter glob to a regex, mirroring picomatch/dorny semantics."""
    i, n, b = 0, len(pat), []
    while i < n:
        c = pat[i]
        if c == "*":
            if pat[i:i + 2] == "**":
                if pat[i:i + 3] == "**/":
                    b.append("(?:.*/)?")
                    i += 3
                else:
                    b.append(".*")
                    i += 2
            else:
                b.append("[^/]*")
                i += 1
        elif c == "?":
            b.append("[^/]")
            i += 1
        else:
            b.append(re.escape(c))
            i += 1
    return re.compile("^" + "".join(b) + "$")


def path_gate_hit(files, patterns):
    """First (pattern, path) hit of changed files against gate patterns, else None.

    Pattern-major: the first pattern (in ci_paths.yaml order) matching any file wins.
    """
    rxs = [(p, glob_to_regex(p)) for p in patterns]
    for p, rx in rxs:
        for f in files:
            if rx.match(f):
                return p, f
    return None


# The worker dry-run gate was the first caller of this matcher; the name is kept
# because the local suite and the post-merge driver reference it (DIG-5203).
worker_gate_hit = path_gate_hit


def worker_patterns(wt):
    """Gate patterns for the worker dry-run build: live ci_paths.yaml `workers:` block,
    falling back to WORKER_GATE_PATTERNS when the file or block is missing/empty."""
    try:
        with open(os.path.join(wt, "scripts", "ci_paths.yaml")) as f:
            pats = parse_workers_patterns(f.read())
    except OSError:
        pats = []
    return pats or list(WORKER_GATE_PATTERNS)


def changed_file_names(raw):
    """Filenames from a `gh api .../pulls/<n>/files --paginate --slurp` payload.

    Accepts the slurp shape [[{...}, ...], ...] or a flat [{...}, ...] list.
    Returns None when the payload is unusable (caller fails closed).
    """
    if isinstance(raw, list) and raw and all(isinstance(p, list) for p in raw):
        pages = raw
    elif isinstance(raw, list) and raw and all(isinstance(p, dict) for p in raw):
        pages = [raw]
    else:
        return None
    names = []
    for page in pages:
        for row in page:
            fn = row.get("filename") if isinstance(row, dict) else None
            if not fn:
                return None
            names.append(fn)
    return names or None


def worker_gate(pr, wt):
    """Path gate for the worker dry-run build. Returns (n_files, (pattern, path))
    on a hit, (n_files, None) on a miss, (None, None) when the file list is unusable."""
    raw = gh("api", f"repos/{REPO}/pulls/{pr['number']}/files", "--paginate", "--slurp")
    try:
        files = changed_file_names(json.loads(raw or ""))
    except ValueError:
        files = None
    if files is None:
        return None, None
    return len(files), worker_gate_hit(files, worker_patterns(wt))


def bun_suite_patterns(wt):
    """Gate patterns for the bun suites: the live ci_paths.yaml `bun_suites` block,
    falling back to one `<dir>/**` glob per BUN_SUITE_DIRS when it is missing or empty."""
    try:
        with open(os.path.join(wt, "scripts", "ci_paths.yaml")) as f:
            pats = parse_ci_paths_block(f.read(), "bun_suites")
    except OSError:
        pats = []
    return pats or [f"{d}/**" for d in BUN_SUITE_DIRS]


def bun_suite_dirs(patterns):
    """Suite directories named by the gate patterns, in list order.

    A suite entry is `<root>/<name>/**`: exactly two segments, no wildcard. Any
    other entry (`clients/**`, a file, a glob) can still fire the gate but never
    becomes a suite, so a broad trigger cannot make the gate run `bun test` in a
    directory that is not a package.
    """
    out = []
    for p in patterns:
        d = p[:-3] if p.endswith("/**") else ""
        if not d or "*" in d or "?" in d or len(d.split("/")) != 2:
            continue
        if d not in out:
            out.append(d)
    return out


def bun_test_packages(wt, roots=("clients", "packages")):
    """Directories under `roots/*` whose manifest declares `"test": "bun test"`.

    Read from the tree, not only from the list, because a new client written
    with a bun suite has to be gated the moment it lands. The retired lane kept
    a `client-coverage` job for exactly this; a hand-maintained list reopens the
    hole as soon as somebody adds a client and forgets the list. `apps/*` is
    deliberately not scanned: its suites are vitest and belong to the web lane.
    """
    found = []
    for root in roots:
        base = os.path.join(wt, root)
        try:
            names = sorted(os.listdir(base))
        except OSError:
            continue
        for n in names:
            try:
                with open(os.path.join(base, n, "package.json")) as f:
                    pkg = json.load(f)
            except (OSError, ValueError):
                continue
            if (pkg.get("scripts") or {}).get("test") == "bun test":
                found.append(f"{root}/{n}")
    return found


def bun_suites_to_run(wt):
    """Every suite the gate runs: the ones named in `bun_suites`, then any
    bun-suite package the list has not caught up with yet, in that order."""
    out = bun_suite_dirs(bun_suite_patterns(wt))
    for d in bun_test_packages(wt):
        if d not in out:
            out.append(d)
    return out


def short_suite_name(d):
    """Receipt name of a suite: `clients/digichat-tui` -> `digichat-tui`."""
    for root in ("clients/", "packages/"):
        if d.startswith(root):
            return d[len(root):]
    return d


def bun_gate(pr, wt):
    """Path gate for the bun suites. Returns (n_files, (pattern, path)) on a hit,
    (n_files, None) on a miss, (None, None) when the file list is unusable."""
    raw = gh("api", f"repos/{REPO}/pulls/{pr['number']}/files", "--paginate", "--slurp")
    try:
        files = changed_file_names(json.loads(raw or ""))
    except ValueError:
        files = None
    if files is None:
        return None, None
    return len(files), path_gate_hit(files, bun_suite_patterns(wt))


def bun_bin():
    """Absolute path of the bun the suites run with, or None when the host has none.

    bun is installed under the user's home (`~/.local/bin`, `~/.bun/bin`), which
    the launchd job's PATH does not carry, so the gate resolves it once here. A
    missing binary is then a named failure ("bun-suites: bun not found") instead
    of seven identical suite failures that read like broken tests (DIG-5203).
    """
    found = shutil.which("bun", path=ENV.get("PATH", ""))
    if found:
        return found
    for p in (f"{HOME}/.bun/bin/bun", f"{HOME}/.local/bin/bun",
              "/opt/homebrew/bin/bun", "/usr/local/bin/bun"):
        if os.access(p, os.X_OK):
            return p
    return None


def root_workspace_globs(wt):
    """The root package.json's `workspaces` globs, or [] when it cannot be read."""
    try:
        with open(os.path.join(wt, "package.json")) as f:
            ws = json.load(f).get("workspaces")
    except (OSError, ValueError):
        return []
    if isinstance(ws, dict):
        ws = ws.get("packages")
    return [g for g in ws or [] if isinstance(g, str)]


def is_root_workspace(d, globs):
    """True when the root npm install owns `d` (`packages/*`, `apps/*`).

    Those packages are workspaces of the root package.json, so their
    dependencies come from the root `npm ci`. `bun install` inside one of them
    walks up to the repo root and installs the whole monorepo (and writes a root
    bun.lock) — the retired lane exempted surface-config and hero-banner for
    exactly that reason. The clients and digivoice/tui are not workspaces: they
    are standalone bun packages with their own lockfile.
    """
    return any(glob_to_regex(g).match(d) for g in globs)


def run_bun_suites(wt, step, out, fails):
    """Run every bun suite that `bun_suites` names, plus any the tree adds.

    Called only when a PR touched a `bun_suites` path. Every suite runs even
    after an earlier one failed (the retired lanes used fail-fast: false for the
    same reason): one red suite must not hide another suite's verdict. Returns
    the receipt names of the suites that reached their test run, so the status
    line can name them (DIG-5203).

    `fails` is the caller's gate list: `step` records a failed install or test
    there, and the checks below record a suite that could not start at all.
    """
    ran = []
    bun = bun_bin()
    if bun is None:
        fails.append("bun-suites: bun not found")
        out.write("bun-suites FAIL: no bun on this host, so no suite ran\n")
        return ran
    rc, ver = sh([bun, "--version"], cwd=wt, timeout=60, out=out, name="bun-version")
    ver = (ver or "").strip()
    if rc != 0 or ver != BUN_PIN:
        fails.append(f"bun-version {'unreadable' if rc != 0 else ver} != {BUN_PIN}")
        out.write(f"bun-version FAIL: {ver or 'unreadable'} != {BUN_PIN}; no suite ran. "
                  "Bump BUN_PIN in its own PR.\n")
        return ran
    workspaces = root_workspace_globs(wt)
    for d in bun_suites_to_run(wt):
        name = short_suite_name(d)
        try:
            with open(os.path.join(wt, d, "package.json")) as f:
                pkg = json.load(f)
        except (OSError, ValueError) as exc:
            fails.append(f"bun:{name} (manifest unreadable)")
            out.write(f"bun FAIL: {d}/package.json unreadable ({exc}); the suite did not run\n")
            continue
        if (pkg.get("scripts") or {}).get("test") != "bun test":
            fails.append(f"bun:{name} (no bun test script)")
            out.write(f'bun FAIL: {d} no longer declares `"test": "bun test"`\n')
            continue
        if is_root_workspace(d, workspaces):
            install = False
        else:
            # A standalone bun package installs from its committed lockfile:
            # --frozen-lockfile fails when the lockfile is stale rather than
            # re-resolving silently, the same shape every other lane uses. With
            # no lockfile at all there is nothing to install from, so the suite
            # fails here instead of testing whatever is lying around.
            if not os.path.exists(os.path.join(wt, d, "bun.lock")):
                fails.append(f"bun-install:{name} (no bun.lock)")
                out.write(f"bun-install FAIL: {d} is not a root workspace and commits no "
                          "bun.lock, so --frozen-lockfile cannot install it\n")
                continue
            install = True
        if install and not step(f"bun-install:{name}", [bun, "install", "--frozen-lockfile"],
                                BUN_INSTALL_TIMEOUT, os.path.join(wt, d)):
            continue
        ran.append(name)
        step(f"bun:{name}", [bun, "run", "test"], BUN_TEST_TIMEOUT, os.path.join(wt, d))
    return ran


def worker_build(wt, step, out=None):
    """Run the ci.yml worker-build dry-run over all WORKER_APPS. Failures record via step.

    Each app gets its own ``--outdir``: the dry-run writes the bundle it just
    built into that directory, so one shared directory would have the apps
    overwriting each other once they run at the same time (STEP_POOL).

    ``out`` is the tick's log. When it is given the apps are built in the pool;
    without it they run one at a time through ``step``, which is the shape the
    unit tests drive.

    Returns the failed step names (for tests/observability); run_checks discards it.
    """
    if not step("worker-build:npm-ci", ["npm", "ci", "--no-audit", "--no-fund"], 1800):
        return ["worker-build:npm-ci"]
    outdirs = {app: tempfile.mkdtemp(prefix=f"wrangler-dry-run-{app}-") for app in WORKER_APPS}
    try:
        specs = [gate_spec(f"worker-build:{app}",
                           ["npm", "exec", "--", "wrangler", "deploy", "--dry-run",
                            "--containers-rollout=none", "--outdir", outdirs[app]],
                           WORKER_DRY_RUN_TIMEOUT, os.path.join(wt, "apps", app), None, ())
                 for app in WORKER_APPS]
        if out is None:
            failed = []
            for name, cmd, timeout, cwd in ((s[0], s[1], s[2], s[3]) for s in specs):
                if not step(name, cmd, timeout, cwd):
                    failed.append(name)
            return failed
        return run_step_pool(specs, out)
    finally:
        for d in outdirs.values():
            shutil.rmtree(d, ignore_errors=True)


# The checks worktree checkout (DIG-5285). A healthy checkout of this tree
# takes well under a second; the step was allowed 900 s, so a stalled git - a
# lazy promisor fetch on a partial clone, a busy Mac - held the gate for a
# quarter of an hour and then failed the whole check on a transient stall. The
# budget is now minutes, a checkout that does not land is retried in place
# before anything is thrown away, and the reason a check failed says which of
# the two happened.
WT_CHECKOUT_TIMEOUT = 300
WT_REBUILD_TIMEOUT = 600
WT_META_TIMEOUT = 60
WT_CACHES = (".venv", "node_modules")


def wt_head():
    """HEAD sha of the checks worktree, or None when git cannot read it
    (missing dir, pruned worktree metadata, broken index)."""
    rc, o = sh(["git", "rev-parse", "HEAD"], cwd=WT) if os.path.isdir(WT) else (1, "")
    o = (o or "").strip()
    return o if rc == 0 and re.fullmatch(r"[0-9a-f]{40}", o) else None


def _wt_gitdir(path):
    """The gitdir a linked worktree points at, or None when `path` is not one.

    Read from the .git file, not from git: a broken worktree is exactly the
    case where this has to work.
    """
    gitfile = os.path.join(path, ".git")
    if not os.path.isfile(gitfile):
        return None
    try:
        with open(gitfile, encoding="utf-8", errors="replace") as fh:
            text = fh.read(4096)
    except OSError:
        return None
    if "gitdir:" not in text:
        return None
    return os.path.realpath(text.split("gitdir:", 1)[1].strip())


def wt_is_rebuildable(path):
    """True when the runner may destroy `path` and build it again.

    The sentinel file is not proof of ownership: the runner writes it into
    whatever directory LOCAL_CI_WT names, so an operator's own directory would
    look like ours after one successful run (DIG-5285). The proof is git: a
    worktree of MAIN's repository may be removed, a worktree of another
    repository may not, and an operator-supplied path that is no worktree at
    all may not either (DIG-4490).
    """
    gitdir = _wt_gitdir(path)
    if gitdir is None:
        # Not a worktree at all: an orphan directory. Only the runner's own
        # default path may be cleared out.
        default = os.path.join(HOME, "Code", "local-ci", "wt")
        return (not os.environ.get("LOCAL_CI_WT")
                and os.path.realpath(path) == os.path.realpath(default))
    rc, o = sh(["git", "rev-parse", "--git-common-dir"], cwd=MAIN)
    if rc != 0:
        return False
    common = (o or "").strip()
    if not common:
        return False
    if not os.path.isabs(common):
        common = os.path.join(MAIN, common)
    return os.path.dirname(gitdir) == os.path.join(os.path.realpath(common), "worktrees")


def _wt_unlock():
    """Release the worktree lock. A locked worktree cannot be removed, and the
    post-merge worktree has been locked since 20 Oct. git exits 128 when the
    worktree was not locked; that is not an error, so it stays out of the log."""
    return sh(["git", "worktree", "unlock", WT], cwd=MAIN, timeout=WT_META_TIMEOUT)[0] == 0


def _wt_stash_caches(out):
    """Move the preserved, heavy directories aside so a rebuild does not throw
    them away: prepare_wt keeps .venv and node_modules out of `git clean`, and
    a rebuild that drops them costs a full uv sync and npm ci."""
    stash = os.path.join(os.path.dirname(WT), ".ci-cache-stash")
    os.makedirs(stash, exist_ok=True)
    moved = []
    for name in WT_CACHES:
        src = os.path.join(WT, name)
        if os.path.isdir(src):
            dst = os.path.join(stash, name)
            shutil.rmtree(dst, ignore_errors=True)
            try:
                os.rename(src, dst)
                moved.append((name, dst))
            except OSError as exc:
                out.write(f"could not move {name} aside: {exc}\n")
    return stash, moved


def _wt_restore_caches(stash, moved, out):
    for name, src in moved:
        dst = os.path.join(WT, name)
        if os.path.exists(dst):
            continue
        try:
            os.rename(src, dst)
        except OSError as exc:
            out.write(f"could not move {name} back: {exc}\n")
    shutil.rmtree(stash, ignore_errors=True)


def _wt_remove(out):
    """Remove the checks worktree and its admin entry. Returns (ok, reason).

    `git worktree remove` is scoped to this one worktree; `git worktree prune`
    is repository-wide and would take the admin entry of an operator's
    worktree on an unmounted volume with it (DIG-5285).

    A worktree with modified tracked files is not removed: that is somebody's
    work, not checkout material (DIG-4490).
    """
    rc, o = sh(["git", "status", "--porcelain", "--untracked-files=no"], cwd=WT,
               timeout=WT_META_TIMEOUT)
    if rc == 0 and (o or "").strip():
        return False, "the worktree has uncommitted changes"
    _wt_unlock()
    rc, _ = sh(["git", "worktree", "remove", "--force", "--force", WT], cwd=MAIN,
               timeout=WT_META_TIMEOUT, out=out)
    if rc == 0:
        return True, ""
    if os.path.exists(WT):
        # git does not know this path as a worktree any more (its admin entry
        # is gone), so the directory is all that is left, and the add below
        # needs the path to be free.
        shutil.rmtree(WT, ignore_errors=True)
    if os.path.exists(WT):
        return False, f"the worktree remove failed (rc={rc})"
    return True, ""


def _wt_mark_ours(sha, out):
    """Mark the worktree as the runner's, so a later stall can heal itself."""
    try:
        with open(os.path.join(WT, ".local-ci-worktree"), "w", encoding="utf-8") as fh:
            fh.write(sha + "\n")
    except OSError as exc:  # a read-only worktree still works; it just cannot be rebuilt
        out.write(f"could not mark the worktree as ours: {exc}\n")


def _wt_rebuild(sha, out):
    """Rebuild the checks worktree at `sha`. Returns (ok, reason).

    The caches come along: the rebuild moves .venv and node_modules aside and
    puts them back, because prepare_wt keeps them out of `git clean` on
    purpose and dropping them costs a full uv sync and npm ci.
    """
    stash, moved = _wt_stash_caches(out)
    ok, why = _wt_remove(out)
    if not ok:
        _wt_restore_caches(stash, moved, out)
        return False, why
    rc, _ = sh(["git", "worktree", "add", "--detach", "-f", WT, sha], cwd=MAIN,
               timeout=WT_REBUILD_TIMEOUT, out=out)
    _wt_restore_caches(stash, moved, out)
    if rc != 0:
        return False, f"the worktree add failed (rc={rc})"
    out.write(f"worktree rebuilt at {sha[:12]}\n")
    _wt_mark_ours(sha, out)
    return True, ""


def checkout_wt(sha, out):
    """Put the checks worktree on `sha`. Returns (ok, reason).

    Three failures, three answers (DIG-5285):
    - the checkout timed out: git stalled, most likely fetching a blob over
      the network on a partial clone. A rebuild repeats the same fetch, so the
      checkout is retried in place - git keeps what it already fetched - and a
      second stall is reported as a stall.
    - the checkout failed or landed on another HEAD: the worktree itself is
      broken. It is rebuilt once and the checkout is retried there.
    - the worktree is not the runner's: never rebuilt.
    """
    if not os.path.isdir(WT):
        return False, f"the checks worktree {WT} does not exist; the worktree add failed"
    rc, _ = sh(["git", "checkout", "-q", "--detach", "-f", sha], cwd=WT,
               timeout=WT_CHECKOUT_TIMEOUT, out=out)
    head = wt_head()
    if rc == 0 and head == sha:
        return True, ""
    why = f"checkout rc={rc} HEAD {(head or 'unreadable')[:12]} != {sha[:12]}"
    if rc == 124:
        # A stall, not a broken worktree. git keeps what it fetched, so a
        # second attempt often finishes; a rebuild would fetch it all again.
        out.write(f"worktree checkout stalled ({why}); retrying in place\n")
        rc, _ = sh(["git", "checkout", "-q", "--detach", "-f", sha], cwd=WT,
                   timeout=WT_CHECKOUT_TIMEOUT, out=out)
        head = wt_head()
        if rc == 0 and head == sha:
            return True, ""
        return False, (f"git stalled in the worktree checkout for {sha[:12]} "
                       f"(rc={rc}, HEAD {(head or 'unreadable')[:12]}); the checkout did not "
                       f"finish within {WT_CHECKOUT_TIMEOUT}s")
    if not wt_is_rebuildable(WT):
        return False, f"{why}; {WT} is not a worktree this runner created; refusing to rebuild over it"
    out.write(f"worktree checkout did not land ({why}); rebuilding the worktree and retrying\n")
    ok, why2 = _wt_rebuild(sha, out)
    if not ok:
        return False, f"{why}; {why2}"
    head = wt_head()
    if head == sha:
        # `git worktree add --detach -f` checks the commit out itself.
        return True, ""
    rc, _ = sh(["git", "checkout", "-q", "--detach", "-f", sha], cwd=WT,
               timeout=WT_CHECKOUT_TIMEOUT, out=out)
    head = wt_head()
    if rc == 0 and head == sha:
        return True, ""
    return False, (f"{why}; the rebuilt worktree also failed "
                   f"(rc={rc}, HEAD {(head or 'unreadable')[:12]})")


def prepare_wt(n, sha, base, out):
    """Put the checks worktree on exactly `sha`. Returns (ok, reason).

    Fails closed (stale-worktree incident, 17 Oct 2026): from 15 Oct to
    17 Oct every `git checkout` here failed silently and all gates ran on
    one frozen tree, so local-ci posted green for code it never checked.
    Now every step's rc is logged, a worktree git cannot read is rebuilt,
    and HEAD must equal the PR head before any gate runs. origin/main is
    fetched too: check_vendor_content.py baselines on merge-base(HEAD, origin/main).
    A checkout that stalls is retried in place and a worktree that lands on
    another HEAD is rebuilt (DIG-5285); the reason it failed carries the rc
    and both HEADs."""
    _guard()
    out.write(f"===== worktree {sha[:12]}\n")
    sh(["git", "fetch", "-q", "origin", base, "main", f"pull/{n}/head"], cwd=MAIN, timeout=600, out=out)
    if os.path.isdir(WT) and wt_head() is None:
        if not wt_is_rebuildable(WT):
            return False, (f"{WT} is not a worktree this runner created; refusing to rebuild "
                           "over it (set LOCAL_CI_WT to the runner's own worktree directory)")
        out.write("worktree unreadable by git; rebuilding\n")
        ok, why2 = _wt_rebuild(sha, out)
        if not ok:
            return False, why2
    if not os.path.exists(WT):
        rc, _ = sh(["git", "worktree", "add", "--detach", "-f", WT, sha], cwd=MAIN,
                   timeout=WT_REBUILD_TIMEOUT, out=out)
        if rc != 0:
            return False, f"the worktree add failed (rc={rc})"
        _wt_mark_ours(sha, out)
    ok, why = checkout_wt(sha, out)
    if not ok:
        out.write(f"worktree FAIL: {why}; no gate ran\n")
        log(f"PR #{n} worktree checkout failed: {why}")
        return False, why
    sh(["git", "clean", "-fdq", "-e", ".venv", "-e", "node_modules"], cwd=WT, out=out)
    _wt_mark_ours(sha, out)
    head = wt_head()
    if head != sha:
        out.write(f"worktree FAIL: HEAD {head} != PR head {sha}; no gate ran\n")
        log(f"PR #{n} worktree checkout failed: HEAD {head} != {sha}")
        return False, f"HEAD {(head or 'unreadable')[:12]} != {sha[:12]}"
    return True, ""


def success_desc(mins, bun=None):
    """The success description: the verdict, then what the bun gate did (DIG-5203).

    A commit status description is capped at 140 characters (`status_fields`
    keeps 139), so the suite names are dropped before they can be cut in half:
    a receipt that names three suites and half of a fourth is worse than one
    that names none, and the run log always names every suite in full.

    "gates passed" rather than GATED_NOTE when the suites ran: the receipt is no
    longer a static-only receipt, and claiming it was would be the same false
    green this gate exists to remove. When no `bun_suites` path changed, the
    static note stays and the receipt says so: `bun: none` is the skip made
    visible, not a silence.
    """
    tail = f" ({mins:.0f}m)"
    ran = (bun or {}).get("ran") or []
    if not ran:
        return f"{GATED_NOTE}; bun: none{tail}"
    head = f"gates passed; bun {len(ran)}/{len(ran)}: {', '.join(ran)}"
    if len(head + tail) > 139:
        head = f"gates passed; bun {len(ran)}/{len(ran)} (suites in the log)"
    return head + tail


def _ruff_paths_from_ci_yml(text):
    """Path list of the `ruff check` step in a ci.yml, or None.

    Pure text, no YAML dependency: the daemon runs under /usr/bin/python3 and
    must not depend on a package it may not have. Backslash line
    continuations are joined, comment lines are skipped, and the path tokens
    that follow `ruff check` are collected. Returns None when the file has no
    ruff step, when it has two different path lists, or when a path leaves the
    tree. Ambiguity is never guessed.
    """
    joined = []
    pending = ""
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        if pending:
            s = pending + " " + s
            pending = ""
        if s.endswith("\\"):
            pending = s[:-1].strip()
            continue
        joined.append(s)
    if pending:
        joined.append(pending)
    found = []
    for line in joined:
        m = re.search(r"(?:^|\s)ruff\s+check\b(.*)$", line)
        if not m:
            continue
        rest = re.split(r"&&|\|\||[|;&]", m.group(1), maxsplit=1)[0]
        paths = []
        for tok in rest.split():
            if tok.startswith("-"):
                continue
            if tok.startswith("/") or ".." in tok.split("/"):
                return None
            paths.append(tok)
        if paths:
            found.append(tuple(paths))
    if not found:
        return None
    if len(set(found)) > 1:
        return None
    return list(found[0])


def ruff_paths_for_tree(wt):
    """Ruff path list for the tree under test, or None with the reason.

    The gate lints the same paths the tree's own ci.yml lints. A rename
    (digiclaw -> digibot, DIG-4602) moved a path out from under a hardcoded
    list, and ruff 0.16 fails on a missing path (E902), so a stale list
    turns every other PR red.
    """
    path = os.path.join(wt, ".github", "workflows", "ci.yml")
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        return None, "ci.yml not readable (%s)" % e
    paths = _ruff_paths_from_ci_yml(text)
    if paths is None:
        return None, "no single ruff check path list in ci.yml"
    return paths, "read from .github/workflows/ci.yml"


def ruff_paths_fallback(wt):
    """The fallback ruff path list: the candidates that exist in this tree.

    ruff 0.16 fails on a path that does not exist (E902), so a candidate that
    the tree does not have is dropped rather than named. Linting fewer paths
    only under-lints. Returns None when no candidate exists, so the caller
    fails closed instead of linting nothing.
    """
    paths = [p for p in RUFF_PATHS_CANDIDATES if os.path.exists(os.path.join(wt, p))]
    return paths or None


def step_budget(name, timeout=1800, budget=None):
    """The wall-clock ceiling for one step, in seconds.

    An explicit `budget` wins; then the exact name in STEP_BUDGETS, then a
    matching `*` prefix (so `bun:digichat-tui` takes the `bun:*` budget), then
    STEP_BUDGET. The caller's `timeout` is a ceiling too -
    a tool that already declares it may not take more than N s is not given
    more by this table - so the result is the smaller of the two.
    """
    chosen = budget
    if chosen is None:
        chosen = STEP_BUDGETS.get(name)
        if chosen is None:
            for pattern, secs in STEP_BUDGETS.items():
                if pattern.endswith("*") and name.startswith(pattern[:-1]):
                    chosen = secs
                    break
    if chosen is None:
        chosen = STEP_BUDGET
    return max(1, min(int(chosen), int(timeout)))


def step_failed(fails, name):
    """True when `name` is in the verdict, however the step was recorded.

    An overrun is a sentence (`<step> exceeded <N>s and was killed`) so the
    reader knows why, while a red check keeps its plain name. A caller that
    gates later work on an earlier step has to match both.
    """
    return any(f == name or f.startswith(name + " ") for f in fails)


def _step_duration(out, name, seconds, rc, attempts=1):
    """The one-line duration table the next investigation reads from the log:
    `step=<name> seconds=<n> rc=<n>` for every step, including failures."""
    line = f"step={name} seconds={seconds:.1f} rc={rc}"
    if attempts > 1:
        line += f" attempts={attempts}/{RETRY_CAP}"
    out.write(line + "\n")


def scan_step(name, cmd, timeout=SCAN_TIMEOUT, out=None, fails=None, cwd=None, env=None,
              stall_rcs=(124, 3)):
    """Run one content scanner and record how it answered.

    A scanner that times out did not find anything: it did not finish. Those
    are different verdicts, and a report that cannot tell them apart blames the
    tree for the machine (DIG-5318). So the step is retried once -- a wedged
    daemon often recovers -- and a scanner that still does not answer is
    recorded as a stall: red, because the guard has not cleared the tree, but
    named as the stall it is.

    ``timeout`` is the whole step's budget and the attempts share it (2026-10-26):
    a scanner killed at its ceiling has spent the budget, so it is reported
    instead of being retried into a second stall window.

    ``fails`` collects the verdict: the step name for a finding or the guard's
    own error, ``"<name> exceeded <N>s and was killed"`` for a scanner killed at
    its budget, ``"<name>:stall"`` for one that answered badly without
    overrunning. Returns True when the scanner answered and found nothing.
    """
    if out is None:
        out = sys.stdout
    if fails is None:
        fails = []
    started = time.monotonic()
    deadline = started + max(1, int(timeout))
    rc = None
    attempts = 0
    for attempt in range(1, RETRY_CAP + 1):
        remaining = deadline - time.monotonic()
        if attempt > 1 and remaining < RETRY_MIN_SECS:
            break
        attempts = attempt
        out.write(f"\n===== {name}\n")
        began = time.monotonic()
        rc, _ = sh(cmd, cwd=cwd, timeout=max(1, int(remaining)), out=out, name=name, env=env)
        took = time.monotonic() - began
        if rc == 0:
            _step_duration(out, name, time.monotonic() - started, rc, attempts)
            return True
        if rc not in stall_rcs:
            # rc 1 is a finding; anything else is the guard's own error.
            fails.append(name)
            _step_duration(out, name, time.monotonic() - started, rc, attempts)
            return False
        if rc == 124:
            # Killed at the budget. A second attempt would be another stall
            # window, not another sample.
            out.write(
                f"{name}: did not answer (rc=124, {timeout}s budget, attempt "
                f"{attempt}/{RETRY_CAP}, {took:.1f}s); killed at its budget\n"
            )
            break
        out.write(
            f"{name}: did not answer (rc={rc}, {timeout}s budget, attempt "
            f"{attempt}/{RETRY_CAP}, {took:.1f}s); retrying\n"
        )
    _step_duration(out, name, time.monotonic() - started, rc, attempts)
    if rc == 124:
        why = f"{name} exceeded {timeout}s and was killed"
        fails.append(why)
        out.write(
            f"{name}: STALL -- {why}. The tree was not judged: this is a slow or "
            "wedged host, not a finding.\n"
        )
    else:
        fails.append(f"{name}:stall")
        out.write(
            f"{name}: STALL -- the guard did not answer in {timeout}s twice. The tree "
            "was not judged: this is a slow or wedged host, not a finding.\n"
        )
    return False


def gate_spec(name, cmd, timeout, cwd=None, env=None, stall_rcs=(), budget=None):
    """One pool spec: a step's arguments plus the wall-clock budget it carries.

    The budget is resolved once, here, so a pooled step runs with exactly the
    ceiling the serial `step()` would have given the same name and timeout. An
    explicit `budget` wins over the name table, which is how a tree scanner
    takes SCAN_TIMEOUT instead of the 180 s default (DIG-5724).
    """
    return (name, cmd, timeout, cwd, env, stall_rcs,
            step_budget(name, timeout, budget))


def scan_spec(name, cmd, env=None, stall_rcs=()):
    """One tree-scanner pool spec: SCAN_TIMEOUT is its ceiling and its budget.

    Both scanner waves go through this helper so the two numbers cannot drift
    apart. The scanner names stay out of STEP_BUDGETS on purpose: their runtime
    belongs to the machine, and the one knob that raises it must raise the
    caller ceiling and the step budget together. Passing the budget explicitly
    is what makes LOCAL_CI_SCAN_TIMEOUT reach the step; without it step_budget()
    chose the 180 s default and min(180, 600) left the knob inert (DIG-5724).
    """
    return gate_spec(name, cmd, SCAN_TIMEOUT, None, env, stall_rcs,
                     budget=SCAN_TIMEOUT)


def run_step_pool(specs, out, limit=STEP_POOL):
    """Run independent gate steps concurrently; return (fails, ran) per step name.

    `specs` is a list of (name, cmd, timeout, cwd, env, stall_rcs, budget) in the
    order the log should print them; a spec without the trailing budget gets one
    from its name and timeout. Each step gets its own StringIO, so the log still
    reads as one block per gate in the declared order no matter which one
    finished first, and a step's output is never interleaved with another's.

    Nothing here decides a gate: the same budgeted `run_step` runs, with the
    same cwd, the same environment and the same ``fails`` names, and a blocked
    step is still killed by its own budget (sh() breaks the whole process tree)
    and still recorded by the watchdog. Only the order in which the steps wait
    changed.
    """
    bufs: dict[str, io.StringIO] = {}
    step_fails: dict[str, list] = {}

    def one(spec):
        name, cmd, timeout, cwd, env, stall_rcs, *rest = spec
        budget = rest[0] if rest else None
        buf = io.StringIO()
        bad = []
        # Same refusal as the serial path: a step whose directory is missing
        # fails by name and never runs, so a broken runner state cannot post a
        # dozen plausible-looking failures.
        if not os.path.isdir(cwd or WT):
            buf.write(
                f"\n===== {name}\n{name} FAIL: worktree root {(cwd or WT)!r} is not a directory\n"
            )
            return name, [name], buf
        # One budgeted run, the same one the serial `step()` takes: the ceiling,
        # the process-group kill, the overrun sentence that names the step and
        # the `step=<name> seconds=<n> rc=<n>` line all come from run_step.
        # `cwd or WT`, exactly as the serial `step()` does. Passing the raw
        # `cwd` (None for most specs) let the child inherit the runner's own
        # working directory -- "/" under launchd -- so every check looked
        # for `//scripts/...` and failed for a reason that was not its own.
        run_step(name, cmd, timeout, out=buf, fails=bad, cwd=(cwd or WT), env=env,
                 stall_rcs=stall_rcs, budget=budget)
        return name, bad, buf

    workers = max(1, min(int(limit), len(specs) or 1))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers,
                                               thread_name_prefix="local-ci-step") as pool:
        futures = {pool.submit(one, spec): spec[0] for spec in specs}
        for fut in concurrent.futures.as_completed(futures):
            name = futures[fut]
            try:
                _n, bad, buf = fut.result()
            except Exception as exc:  # a crashed worker is a failed gate, never silence
                bad, buf = [name], io.StringIO(f"\n===== {name}\nstep crashed: {exc}\n")
            bufs[name], step_fails[name] = buf, bad
    fails = []
    for spec in specs:
        name = spec[0]
        out.write(bufs[name].getvalue())
        fails.extend(step_fails.get(name, [name]))
    return fails

def run_step(name, cmd, timeout=1800, out=None, fails=None, cwd=None, env=None,
             stall_rcs=(), budget=None):
    """Run one gate step inside its own wall-clock budget.

    The budget is `step_budget(name, timeout, budget)`. A step that overruns is
    killed by process group (`sh` starts the child in its own session and kills
    the tree), the failure names the step and the seconds it took, and the
    caller carries on with the next step. A check that genuinely fails keeps its
    plain name in the verdict: only an overrun reads as an overrun, so failure
    semantics are unchanged for everything except a hang.
    """
    if out is None:
        out = sys.stdout
    if fails is None:
        fails = []
    cap = step_budget(name, timeout, budget)
    if stall_rcs:
        # A scanner that does not answer is a stall, not a finding.
        return scan_step(name, cmd, timeout=cap, out=out, fails=fails, cwd=cwd, env=env,
                         stall_rcs=stall_rcs)
    out.write(f"\n===== {name}\n")
    started = time.monotonic()
    rc, _ = sh(cmd, cwd=cwd, timeout=cap, out=out, name=name, env=env)
    elapsed = time.monotonic() - started
    _step_duration(out, name, elapsed, rc)
    if rc == 124:
        # sh's timeout path: the process group was killed, so this is a stall
        # and not a check that returned a red verdict.
        why = f"{name} exceeded {cap}s and was killed"
        fails.append(why)
        out.write(why + "\n")
        return False
    if rc != 0:
        fails.append(name)
    return rc == 0


def run_checks(pr, out, summary=None):
    """Run every gate on the PR. Returns the list of failed gates: a plain step
    name, a `<name>:stall`, or the overrun sentence that names the step and its
    budget.

    `summary` is filled with what the receipt needs but the verdict does not
    (today: which bun suites ran, DIG-5203). It is an optional dict rather than
    part of the return value because the post-merge driver calls this function
    in-process and reads a plain list of failures.
    """
    _guard()
    # A gate must never start in a directory that is not there. When the
    # worktree root resolves wrong (empty, "/", a stale path) every check
    # still runs, from the wrong cwd, and reports a real-looking failure for
    # each one -- sixteen at once, none of them true. Refuse the tick instead
    # of producing that verdict: the cause is the runner's own state, and
    # naming it is the only useful thing to say about it.
    if not (os.path.isdir(WT) and wt_is_ours(WT)):
        raise SystemExit(
            f"local-ci: worktree root {WT!r} is not this runner's worktree; "
            "refusing to run gates"
        )
    sha, base, title = pr["headRefOid"], pr["baseRefName"], pr["title"]
    # The R0 allowance gate compares the PR's baseline with the base branch tip.
    # prepare_wt fetched origin/<base>; a caller that knows the exact base commit
    # may pass it as baseCommit (reserved for the post-merge driver, which has
    # no base branch to name). Never guess a ref: an unresolvable one fails the
    # gate closed, so a SHA is used as given.
    base_commit = str(pr.get("baseCommit") or "")
    if re.fullmatch(r"[0-9a-f]{40}", base_commit):
        r0_base = base_commit
    elif re.fullmatch(r"[0-9a-f]{40}", base or ""):
        r0_base = base
    else:
        r0_base = "origin/" + base
    fails = []
    def step(name, cmd, timeout=1800, cwd=None, env=None, stall_rcs=(), budget=None):
        # The missing-directory refusal comes first: a step whose cwd is not
        # there fails by name and never runs (DIG-5318's sibling, 2026-10-26).
        if not os.path.isdir(cwd or WT):
            fails.append(name)
            out.write(f"\n===== {name}\n{name} FAIL: worktree root {(cwd or WT)!r} is not a directory\n")
            return False
        # Every step takes its own wall-clock budget, and the scanner path is
        # inside run_step so a stall spends one budget instead of two windows.
        return run_step(name, cmd, timeout, out=out, fails=fails, cwd=(cwd or WT),
                        env=env, stall_rcs=stall_rcs, budget=budget)
    # PR title
    if not (title == "chore: promote develop to main" or re.match(r"^chore\([^)]*\):\s*release\s|^chore\(release\):\s", title)
            or re.match(rf"^({TYPES})\([^)]+\)!?: .+", title)):
        fails.append("pr-title"); out.write(f"pr-title FAIL: {title!r}\n")
    # PR template (DIG-3842 scope update 15 Oct 2026; DCO gate removed same day,
    # its workflow removal rides on DIG-3845)
    if pr_template is None:
        # A missing checker is a runner defect, not author metadata: the name
        # keeps it out of METADATA_GATES, so the row stays terminal instead of
        # buying a full lane on every title or body edit (DIG-5695 review).
        fails.append("pr-template:checker-missing")
        out.write("pr-template:checker-missing FAIL: checker module missing\n")
    else:
        body = pr_body(pr)
        if summary is not None and body is not None:
            # What this gate judges, so the queue can tell a corrected title or
            # body from the same failed one (DIG-5695).
            summary["metadata_revision"] = metadata_revision(title, body)
        ok, reasons = pr_template.check_template(body or "")
        if not ok:
            fails.append("pr-template")
        for r in reasons:
            out.write(f"pr-template FAIL: {r}\n")
    rep = f"{LOGD}/gitleaks-{sha[:12]}.json"
    opts = gitleaks_log_opts(base, sha, out)
    if opts is None:
        fails.append("gitleaks")
    # One wave for everything that only reads the tree. The npm install is NOT
    # in this wave: it rewrites node_modules while the scanners walk the tree,
    # and a scanner that rglobs a dependency directory then reads a directory
    # being repopulated (check_doc_links measured 58 s pooled against npm ci
    # versus 3 s alone). The install stays with the builds that need it.
    scan_specs = []
    # 2026-10-18 (Board, DIG-4056/DIG-1415): check_vendor_content.py runs with --warn here.
    # Its 28 blocking hits are all in apps/twelvex-runner + the twelvex jobs in apps/digithings-cron;
    # they read as NEW only because the check baselines on merge-base(HEAD, origin/main) (2026-10-13)
    # and that app landed 2026-10-16 (#5852) - and those paths move to the private twelve-x repo in
    # the repo split (DIG-4056). Findings still print in full in this log; only the exit code relaxes.
    # Revert by deleting " --warn" from the entry below once DIG-1415 lands the carve-out rule.
    for s in ["scripts/scan_customer_pii.py --json " + f"{LOGD}/pii-{sha[:12]}.json",
              "scripts/check_frontend_canon.py", "scripts/check_gloomberb_ci_guard.py", "scripts/check_vendor_content.py --warn",
              "scripts/check_plaintext_credentials.py", "scripts/check_example_credentials.py",
              "scripts/check_r0_no_client_literals.py",
              # DIG-5762: the R0 allowance may only shrink, and this is the PR
              # lane that must refuse the growth. The gate lived only in the
              # host runner for months, so #6500 grew the baseline and merged
              # green (totals 1997 -> 2030) until the post-merge run caught it.
              "scripts/check_r0_client_literals_baseline_growth.py --base-ref " + r0_base,
              "scripts/split/manifest.py --check"]:
        if os.path.exists(f"{WT}/{s.split()[0]}"):
            scan_specs.append(scan_spec(s.split()[0], f"python3 {s}", SCAN_ENV, (124, 3)))
    scan_specs.append(gate_spec("actionlint", ["actionlint"], 300, None, None, ()))
    if opts is not None:
        scan_specs.append(gate_spec("gitleaks", ["gitleaks", "detect", "--source", ".", "--config", ".gitleaks.toml",
                                                 "--redact", "--no-banner", "--report-format", "json",
                                                 "--report-path", rep, f"--log-opts={opts}"], 1800, None, None, ()))
    fails.extend(run_step_pool(scan_specs, out))
    step("uv-sync", "uv sync --frozen --all-packages --all-extras", 1800)
    if not step_failed(fails, "uv-sync"):
        U = "uv run --frozen --no-sync "
        rpaths, rnote = ruff_paths_for_tree(WT)
        if rpaths is None:
            rpaths = ruff_paths_fallback(WT)
            if rpaths is None:
                out.write("\n===== ruff\nno ruff path list: ci.yml unavailable (%s) and no candidate path exists in this tree\n" % rnote)
                fails.append("ruff")
                rpaths = []
            else:
                out.write("\nruff-paths: ci.yml unavailable (%s); using the fallback list: %s\n" % (rnote, " ".join(rpaths)))
                log("ruff: path list from ci.yml unavailable (%s); using the fallback list" % rnote)
        else:
            out.write("\nruff-paths: %s: %s\n" % (rnote, " ".join(rpaths)))
        # Second wave: everything that needs the venv uv-sync just prepared.
        uv_specs = []
        if rpaths:
            uv_specs.append(gate_spec("ruff", U + "ruff check " + " ".join(rpaths), 600, None, None, ()))
        uv_specs.append(gate_spec("mypy", U + "mypy digibase/src/digibase/ digikey/src/digikey/ --config-file mypy.ini", 1200, None, None, ()))
        for s in ["check_doc_links.py", "check_adr_numbering.py", "agents_init.py --check", "check_model_name_literals.py",
                  "generate_ci_path_filters.py --check"]:
            if os.path.exists(f"{WT}/scripts/{s.split()[0]}"):
                uv_specs.append(scan_spec(s.split()[0], U + f"python scripts/{s}"))
        fails.extend(run_step_pool(uv_specs, out))
    n_files, hit = worker_gate(pr, WT)
    if hit is None and n_files is None:
        out.write("\n===== worker-build\nchanged-files fetch failed; failing closed\n")
        fails.append("worker-build: changed-files fetch failed")
    elif hit is not None:
        out.write(f"\n===== worker-build\ngate hit: {hit[0]} <- {hit[1]}\n")
        fails.extend(worker_build(WT, step, out=out))
    # Bun suites (DIG-5203): the required check has to prove a clients/** or
    # packages/** change, not report green over a suite nobody ran. The paths
    # come from the same `bun_suites` block the retired lane used, and a hit
    # runs every suite in it (the lane ran the whole matrix for the same reason:
    # these packages import each other, so a surface-config edit is a change to
    # every client that reads it).
    ran_bun = []
    n_bun, bun_hit = bun_gate(pr, WT)
    if n_bun is None:
        out.write("\n===== bun-suites\nchanged-files fetch failed; failing closed\n")
        fails.append("bun-suites: changed-files fetch failed")
    elif bun_hit is not None:
        out.write(f"\n===== bun-suites\ngate hit: {bun_hit[0]} <- {bun_hit[1]}\n")
        ran_bun = run_bun_suites(WT, step, out, fails)
    if summary is not None:
        summary["bun"] = {"hit": bun_hit[0] if bun_hit else None, "ran": ran_bun}
    return fails

def process(pr, dry):
    sha = pr["headRefOid"]; n = pr["number"]
    st0, desc0 = ci_status(sha)
    if st0 == "failure" and (desc0 or "").startswith("local-ci failed: gitleaks"):
        try:
            with open(f"{LOGD}/gitleaks-recheck-{sha}", "w") as f: f.write("1\n")
        except OSError: pass
    logf = f"{LOGD}/pr{n}-{sha[:12]}.log"
    log(f"PR #{n} {sha[:12]} start")
    if not dry:
        # The claim is taken before the `pending` row goes out, so a run that
        # dies leaves a ledger entry naming a holder who is gone. The queue
        # reads it and gives the head its receipt again (DIG-5135).
        write_claim(sha, n)
        status(sha, "pending", "local-ci running on Chris's Mac")
    t0 = time.time()
    summary = {}
    with open(logf, "w") as out:
        ok_wt, why = prepare_wt(n, sha, pr["baseRefName"], out)
        fails = run_checks(pr, out, summary) if ok_wt else [f"worktree checkout ({why})"]
    mins = (time.time() - t0) / 60
    # A failure names the failed gates (`bun:digichat-tui` for a red suite), which
    # is the actionable part; the log names every suite that ran. The success
    # line names the suites so a PR with no bun path says `bun: none` instead of
    # reading like the suites passed (DIG-5203).
    if fails: st, desc = "failure", f"local-ci failed: {', '.join(fails)} ({mins:.0f}m)"
    else: st, desc = "success", success_desc(mins, summary.get("bun"))
    log(f"PR #{n} {sha[:12]} {st}: {desc} log={logf}")
    if not dry:
        if metadata_failure_gates(desc) is not None:
            # Remember what this verdict judged so the same failed metadata is
            # not re-queued tick after tick (DIG-5695). A code failure records
            # nothing: its row is terminal.
            record_judged_metadata(pr, summary.get("metadata_revision"))
        if status(sha, st, desc):
            # The verdict is in, so the claim is spent. When the verdict could
            # not be posted the claim stays: the head is owed a receipt and the
            # queue gives it one instead of waiting for a row that never came.
            clear_claim(sha)
    return st

def skip_reason():
    """Non-None when this tick must not run checks. A skip posts failure, never silence."""
    if os.path.exists(PAUSE):
        return "disk guard pause: worktree creation halted, Mac cannot run checks"
    pct = mem_free_pct()
    avail = mem_available_mb()
    pct_s = f"{pct:.0f}%" if pct is not None else "n/a"
    log(f"mem: avail {avail:.0f}MB free_pct {pct_s} memorystatus_level {sysctl_num('kern.memorystatus_level'):.0f} "
        f"mb_pressure_pct {sysctl_num('kern.ipc.mb_memory_pressure_percentage'):.0f} swap_free {swap_free_mb():.0f}MB")
    if pct is not None:
        if pct < MIN_FREE_PCT:
            return f"memory free {pct:.0f}% < {MIN_FREE_PCT:.0f}%: Mac cannot run checks"
        return None
    if avail < MIN_AVAIL_MB:
        return f"memory available {avail:.0f}MB < {MIN_AVAIL_MB}MB: Mac cannot run checks"
    return None

def claim_path(sha):
    """The ledger file that names the holder of a head's claim.

    The name is the head's sha and nothing else. A name that is not a sha
    would write outside the ledger, so it is refused rather than repaired.
    """
    name = str(sha or "")
    if not re.fullmatch(r"[0-9a-f]{40}", name):
        return None
    return os.path.join(CLAIMS, name)


def pid_alive(pid):
    """True when the pid is still running."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def claim_record(sha):
    """The ledger entry for this head, or None when there is none to read."""
    path = claim_path(sha)
    if not path:
        return None
    try:
        with open(path) as f:
            data = json.loads(f.read() or "{}")
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def claim_state(sha):
    """'live' when a running process holds the claim, 'dead' when the holder is
    gone, 'none' when no claim was ever written for this head."""
    rec = claim_record(sha)
    pid = rec.get("pid") if rec else None
    if not isinstance(pid, int):
        return "none", None
    return ("live" if pid_alive(pid) else "dead"), pid


def claim_age(sha):
    """How long the claim has been held, in seconds, or None when it says
    nothing about that."""
    rec = claim_record(sha)
    started = rec.get("started") if rec else None
    if not isinstance(started, (int, float)):
        return None
    return time.time() - float(started)


def holder_is_the_run(sha, pid):
    """True when the pid that holds the claim is the run that wrote it.

    A pid is reused: a claim left behind by a killed run names a pid the
    kernel may hand to an unrelated process later, and that process is not the
    run that was checking the head. The claim carries the moment it was
    written and the process carries the moment it started, so the two answer
    the question. A process that is a zombie is not running at all: it has
    exited and nobody has reaped it, so it is not the run either. When the
    answer cannot be read the claim is taken at its word: a head is recovered
    when the run is known to be gone, not when the answer is missing.
    """
    rec = claim_record(sha)
    started = rec.get("started") if rec else None
    if not isinstance(started, (int, float)) or not pid:
        return True
    try:
        # /bin/ps and not the one on the PATH: launch_guard.py answers the same
        # question the same way, because a `ps` that somebody put first on the
        # PATH must not decide whose run this is. The state is asked for in the
        # same call, so one read answers both questions.
        out = subprocess.run(["/bin/ps", "-o", "lstart=", "-o", "stat=", "-p", str(pid)],
                             capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return True
    parts = (out or "").strip().split()
    if len(parts) < 6:
        return True
    # `Z` is a zombie: the process is gone and the kernel is holding its slot.
    if parts[5].upper().startswith("Z"):
        return False
    try:
        # `ps` prints the start in local time, so the local zone is what the
        # timestamp is read in.
        started_at = datetime.strptime(" ".join(parts[:5]),
                                       "%a %b %d %H:%M:%S %Y").astimezone().timestamp()
    except ValueError:
        return True
    return started_at <= float(started) + 30


def write_claim(sha, pr_number):
    """Record this process as the holder of the head's claim.

    The claim is taken before the `pending` row goes out. A run that dies
    between the two leaves a ledger entry and no row, which the queue reads as
    a head in flight. A run that dies after the row leaves an entry whose
    holder is gone, and that is what the queue reads to give the head its
    receipt again (DIG-5135).

    The entry is written to a temporary name and moved into place, so a run
    that dies mid-write leaves no half-written claim, and a name that is a
    symlink is replaced rather than followed.
    """
    path = claim_path(sha)
    if not path:
        log(f"claim: {str(sha)[:12]} is not a head sha; no claim is recorded")
        return
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        os.makedirs(CLAIMS, exist_ok=True)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps({"pid": os.getpid(), "pr": pr_number,
                                "started": time.time()}))
        os.replace(tmp, path)
    except OSError as e:
        log(f"claim: could not record the holder of {sha[:12]}: {e}")
        try:
            os.remove(tmp)
        except OSError:
            pass


def clear_claim(sha):
    """Release a claim.

    Only the holder releases its own claim, and a claim nobody holds any more
    is released by whoever notices. A run that was taken over - its head was
    given to a second run - must not delete the claim of the run that replaced
    it: that would let a third run start on a head that is already being
    checked (DIG-5135).
    """
    path = claim_path(sha)
    if not path:
        return
    rec = claim_record(sha) or {}
    pid = rec.get("pid")
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        pid = None
    if pid and pid != os.getpid() and pid_alive(pid):
        log(f"claim: {str(sha)[:12]} is held by the living run {pid}; it keeps it")
        return
    try:
        os.remove(path)
    except OSError:
        pass


def claim_is_lost(sha, created_at):
    """True when the `pending` row on this head belongs to a run that is gone.

    The holder is named in the ledger. A holder that is alive is in flight and
    the head is left alone - an old row does not take a running head away. A
    holder that is gone means the run died, so the receipt is owed again. A
    claim held past the worst case of a gate run is void: the run it names
    cannot still be gating after that. That limit is deliberately longer than
    the life of the tick lock, so a second tick that took over a stale lock
    still leaves the head alone while the first run is alive. A row with no
    ledger entry - posted by a runner that predates the ledger, or by the CI
    container, which keeps its own state directory - is treated the same way
    once it is older than the stale window.
    """
    state, pid = claim_state(sha)
    if state == "live":
        age = claim_age(sha)
        if age is not None and age >= CLAIM_MAX_SECS:
            return True
        return not holder_is_the_run(sha, pid)
    if state == "dead":
        return True
    age = _status_age_secs_or_none(created_at)
    if age is None:
        return False        # an unreadable timestamp is not an old one
    return age >= CLAIM_STALE_SECS


def prune_claims():
    """Drop ledger entries nobody holds any more and that nothing touched for a day.

    Only a claim file is dropped: a name that is not a head sha is somebody
    else's file that happens to sit in the same directory. The temporary name a
    claim is written through is dropped as well, or a run that was killed
    between the write and the move leaves a file for ever.
    """
    try:
        names = os.listdir(CLAIMS)
    except OSError:
        return
    for name in names:
        if re.fullmatch(r"[0-9a-f]{40}\.\d+\.tmp", name):
            path = os.path.join(CLAIMS, name)
            try:
                if time.time() - os.path.getmtime(path) < 3600:
                    continue
                os.remove(path)
            except OSError:
                pass
            continue
        if not re.fullmatch(r"[0-9a-f]{40}", name):
            continue
        path = os.path.join(CLAIMS, name)
        try:
            if time.time() - os.path.getmtime(path) < 86400:
                continue
        except OSError:
            continue
        state, _pid = claim_state(name)
        if state == "live":
            continue
        try:
            os.remove(path)
        except OSError:
            pass


def _touch_refresh_state():
    """Remember that a refresh was attempted, so the next one waits its turn."""
    try:
        os.makedirs(os.path.dirname(REFRESH_STATE), exist_ok=True)
        tmp = f"{REFRESH_STATE}.{os.getpid()}.tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC
                     | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(str(time.time()))
        os.replace(tmp, REFRESH_STATE)
    except OSError:
        pass


def runner_marker():
    """What the operator marked as the runner's own checkout, or None.

    The marker is written by scripts/local-ci/install.sh. It names the checkout
    the runner may keep current and says whether the runner may move it at all.
    A checkout nobody marked is never moved: `MAIN` may point at somebody's
    working tree, and the runner has no business moving a working tree.
    """
    try:
        with open(RUNNER_MARKER) as f:
            data = json.loads(f.read() or "{}")
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _guard_takes_a_runner_path(source):
    """True when the guard source defines `enforce(runner_path, ...)`.

    The check is structural. A comment, a docstring or a dead copy of the old
    signature does not make the guard callable: the runner calls
    `launch_guard.enforce(__file__, ctx)`, so a guard whose `enforce` takes
    something else raises a TypeError on the next tick and stops the only
    producer of the receipt. Reading the text with a regex could be satisfied
    by a line in a comment, so the source is parsed and the function is looked
    up.
    """
    try:
        tree = ast.parse(source or "")
    except (SyntaxError, ValueError):
        return False
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != "enforce":
            continue
        first = list(node.args.posonlyargs) + list(node.args.args)
        if not first:
            return False
        return first[0].arg == "runner_path"
    return False


def _incoming_runner_is_sane():
    """True when the commit FETCH_HEAD names carries a runner that can run.

    The runner is the code that produces the receipt, so the runner switching
    its own code is the one switch on this host that can stop the only
    pre-merge producer. The incoming commit must carry a runner that compiles
    and the guard that decides who may start it: a runner without the guard
    refuses to run at all, and a guard with a different interface would stop
    it the same way.
    """
    rc, out = sh(["git", "-C", MAIN, "show", "FETCH_HEAD:scripts/local-ci/local_ci.py"], timeout=120)
    if rc != 0 or not out:
        log("refresh: the incoming commit carries no runner; the checkout is left alone")
        return False
    try:
        compile(out, "local_ci.py", "exec")
    except (SyntaxError, ValueError) as e:
        log(f"refresh: the incoming runner does not compile ({e}); the checkout is left alone")
        return False
    rc, _out = sh(["git", "-C", MAIN, "cat-file", "-e",
                   "FETCH_HEAD:scripts/local-ci/launch_guard.py"], timeout=60)
    if rc != 0:
        log("refresh: the incoming commit carries no launch guard; the checkout is left alone")
        return False
    rc, guard = sh(["git", "-C", MAIN, "show", "FETCH_HEAD:scripts/local-ci/launch_guard.py"],
                   timeout=120)
    if rc != 0 or not _guard_takes_a_runner_path(guard or ""):
        log("refresh: the incoming launch guard does not take a runner path; "
            "the checkout is left alone")
        return False
    return True


def refresh_checkout():
    """Bring the runner's own checkout to origin/develop, when that is safe.

    The runner is the code that produces the receipt, so a checkout left on an
    old commit produces old receipts: the claim ledger and the fair order only
    reach the daemon once the daemon's checkout carries them (DIG-5135).

    The refresh is deliberately narrow. It moves a checkout only when all of
    these hold:

    - the operator marked that checkout as the runner's own (install.sh writes
      the marker), so the runner never moves somebody's working tree;
    - the checkout is a real clone, never a linked worktree;
    - the checkout is on `develop`;
    - the incoming commit carries a runner that compiles and a launch guard;
    - the checkout fast-forwards cleanly.

    Anything else leaves the checkout exactly as it is, and the runner keeps
    running the commit it was installed on.
    """
    try:
        age = time.time() - os.path.getmtime(REFRESH_STATE)
    except OSError:
        age = REFRESH_MIN_SECS
    if age < REFRESH_MIN_SECS:
        return
    marker = runner_marker() or {}
    named = str(marker.get("main") or "")
    # An empty name is not a checkout: `realpath("")` is the working directory,
    # and a marker without a name would otherwise match the runner's own
    # directory by accident.
    marked = bool(named) and os.path.realpath(named) == os.path.realpath(MAIN)
    if not marked or not marker.get("self_update"):
        log("refresh: this checkout is not marked as the runner's own; the runner keeps "
            "the commit it was installed on")
        _touch_refresh_state()
        return
    if not os.path.isdir(os.path.join(MAIN, ".git")):
        # A linked worktree is not ours to move. The runner keeps running the
        # commit it was installed on until the daemon is installed on a
        # dedicated clone, and that is worth saying out loud.
        log("refresh: the runner checkout is not a clone; it is left alone and the "
            "runner keeps running the commit it was installed on")
        _touch_refresh_state()
        return
    rc, out = sh(["git", "-C", MAIN, "rev-parse", "--abbrev-ref", "HEAD"], timeout=60)
    branch = (out or "").strip()
    if rc != 0 or branch != "develop":
        log(f"refresh: the runner checkout is on '{branch or 'an unknown branch'}', "
            "not develop; it is left alone")
        _touch_refresh_state()
        return
    rc, _out = sh(["git", "-C", MAIN, "fetch", "-q", "origin", "develop"], timeout=600)
    if rc != 0:
        log(f"refresh: fetch failed (rc={rc}); the runner keeps its checkout")
        # The attempt is spent either way. Without this a checkout whose fetch
        # always fails is retried every tick, and every attempt starts a git
        # and an ssh with a 600 s budget of their own.
        _touch_refresh_state()
        return
    if not _incoming_runner_is_sane():
        _touch_refresh_state()
        return
    rc, _out = sh(["git", "-C", MAIN, "merge", "--ff-only", "--quiet", "FETCH_HEAD"], timeout=600)
    if rc != 0:
        log("refresh: the checkout does not fast-forward to origin/develop; it is left alone")
        _touch_refresh_state()
        return
    _touch_refresh_state()
    log("refresh: the runner checkout is at origin/develop")


def ci_status_row(sha):
    """Latest (state, description, created_at) posted under CTX, or (None, None, None)."""
    o = gh("api", f"repos/{REPO}/commits/{sha}/statuses", "--paginate")
    try: rows = json.loads(o or "[]")
    except ValueError: return None, None, None
    rows = [r for r in rows if isinstance(r, dict) and r.get("context") == CTX]
    if not rows: return None, None, None
    rows.sort(key=lambda r: r.get("createdAt", r.get("created_at", "")))
    last = rows[-1]
    return (last.get("state"), last.get("description") or "",
            last.get("createdAt", last.get("created_at", "")) or "")


def ci_status(sha):
    """Latest (state, description) posted under CTX, or (None, None)."""
    st, desc, _created = ci_status_row(sha)
    return st, desc


def metadata_failure_gates(desc):
    """The gates a metadata-only failure names, or None.

    A row names its failed gates after ``local-ci failed: `` and ends with the
    run time in minutes. Only plain gate names count: a stall or an overrun
    reads as a sentence, and one name outside METADATA_GATES makes the whole
    verdict a code failure, whose row stays terminal (DIG-5695).
    """
    prefix = "local-ci failed: "
    text = desc or ""
    if not text.startswith(prefix):
        return None
    names = re.sub(r" \(\d+m\)$", "", text[len(prefix):])
    gates = [g.strip() for g in names.split(",") if g.strip()]
    if not gates or any(g not in METADATA_GATES for g in gates):
        return None
    return gates


def metadata_revision(title, body):
    """A stable digest of the metadata a metadata gate reads: title and body.

    The timestamp is not the revision: GitHub moves `updatedAt` on every
    comment and review, so a time comparison would re-run a full lane for a
    conversation the gates never read.
    """
    h = hashlib.sha256()
    h.update((title or "").encode("utf-8"))
    h.update(b"\0")
    h.update((body or "").encode("utf-8"))
    return h.hexdigest()[:16]


def pr_body(pr):
    """The pull request's body, or None when GitHub could not be read."""
    body = gh("pr", "view", str(pr["number"]), "-R", REPO, "--json", "body", "-q", ".body")
    return None if body is None else body


def judged_metadata_revision(sha):
    """The metadata revision this head's last metadata verdict judged, or None.

    Kept next to the gitleaks re-check sentinel, for the same reason: one
    re-check per change, never one per tick.
    """
    try:
        with open(f"{LOGD}/metadata-recheck-{sha}") as f:
            return f.read().strip() or None
    except OSError:
        return None


def record_judged_metadata(pr, revision=None):
    """Remember the metadata a metadata-only verdict was judged on (DIG-5695).

    `revision` is what the gates read during the run; when a run could not read
    the body, the current body is hashed instead so the same failure cannot
    re-queue for ever. An unreadable body records nothing: a revision nobody
    saw is not a judgement, and the timestamp rule covers that head.
    """
    if revision is None:
        body = pr_body(pr)
        if body is None:
            return
        revision = metadata_revision(pr.get("title"), body)
    try:
        with open(f"{LOGD}/metadata-recheck-{pr['headRefOid']}", "w") as f:
            f.write(revision + "\n")
    except OSError:
        pass


def metadata_recheck_due(pr, desc, created):
    """True when a metadata-only failure is worth one more look on the same head.

    A metadata gate is the one class of failure whose remedy does not touch the
    tree, so the head does not have to be replaced to clear it (DIG-5695, PR
    #6513). The head is re-queued when the metadata it carries now differs from
    the metadata its verdict judged.

    A head with no record - a row from before this rule, or a run that could
    not read the body - falls back to the row's own clock: the pull request
    must have been updated after the row that judged it. Either way a metadata
    failure buys at most one re-check per change.
    """
    if metadata_failure_gates(desc) is None:
        return False
    body = pr_body(pr)
    if body is None:
        return False  # nothing readable to judge: the row stays terminal
    revision = metadata_revision(pr.get("title"), body)
    judged = judged_metadata_revision(pr["headRefOid"])
    if judged is not None:
        return judged != revision
    updated = _status_age_secs_or_none(pr.get("updatedAt"))
    row = _status_age_secs_or_none(created)
    return updated is not None and row is not None and updated < row


def pending(prs, forks, dry=False):
    """Open PRs still needing a check, oldest first.

    The order is the fairness rule (DIG-5135): the pull request that arrived
    first is served first. The queue used to be newest-first, so a PR that
    arrived early sat behind every later arrival and, with the producer
    frozen, could wait for days for a required check. The order is by arrival
    and not by last activity: a pull request that is commented on is not
    pushed back to the end of the queue.

    A head is queued when it carries no `local-ci` row, when its only row is a
    re-checkable skip (DIG-3706), when its row is a gitleaks failure worth one
    more try, when its row says the post itself failed (`error`), when a
    metadata-only failure has been overtaken by a corrected title or body
    (DIG-5695), or when its `pending` row belongs to a run that is gone: the
    claim ledger names the holder, and a holder that is dead means the receipt
    is owed again.

    A head whose claim is held by a living run is left alone: it is not
    queued, not skipped, and its claim is not released. The run that took the
    claim releases it when the verdict is in.

    A preview changes nothing, so a dry run reads the ledger and never writes
    to it (DIG-4490).
    """
    out = []
    for p in prs:
        if bool(p["isCrossRepository"]) == forks:
            sha = p["headRefOid"]
            st, desc, created = ci_status_row(sha)
            state, _pid = claim_state(sha)
            if state == "live" and not claim_is_lost(sha, created):
                # A run is checking this head right now. A claim that is live
                # but lost - held past the life of the lock, or naming a pid
                # the kernel has handed to somebody else - is not in flight.
                continue
            # A gitleaks-only failure is re-queued once. The shallow clone was
            # scanning commits already on the base. A second failure stays put.
            retry = (st == "failure" and (desc or "").startswith("local-ci failed: gitleaks")
                     and not os.path.exists(f"{LOGD}/gitleaks-recheck-{sha}"))
            # A metadata-only failure is the one failure a corrected title or
            # body can clear without touching the tree (DIG-5695).
            meta = st == "failure" and metadata_recheck_due(p, desc, created)
            lost = st == "pending" and claim_is_lost(sha, created)
            if st in ("success", "failure", "error") and not dry:
                # The verdict is in, or the row says the post itself failed:
                # the claim is spent either way. A claim that a living run
                # still holds is that run's to release.
                clear_claim(sha)
            if (st is None or st == "error" or (desc or "").startswith(SKIP_PREFIX)
                    or retry or meta or lost):
                out.append(p)
    out.sort(key=lambda p: (p.get("createdAt") or p.get("updatedAt") or "",
                             p.get("number") or 0))
    return out

def lock_holder_alive():
    """Pid recorded in the lock dir, or None. A dead holder's lock is immediately reusable."""
    try:
        with open(os.path.join(LOCK, "pid")) as f: pid = int(f.read().strip())
    except (OSError, ValueError): return None
    try: os.kill(pid, 0)
    except ProcessLookupError: return None
    except PermissionError: return pid
    return pid

def _lock_is_ours(path, inode):
    """True only while this process still owns the lock directory it created.

    The inode is the identity of the directory this process made: a lock that
    was removed and taken over by another runner is a different directory, and
    a runner must never renew a lock it does not hold.
    """
    try:
        if os.stat(path).st_ino != inode:
            return False
        with open(os.path.join(path, "pid")) as f:
            return f.read().strip() == str(os.getpid())
    except (OSError, ValueError):
        return False


def renew_lock(path, inode):
    """Touch the tick lock so a working tick never looks wedged.

    True when the lock was renewed. A lock this process does not hold is never
    touched: the renewal stops at the first sign that the lock is gone or
    belongs to somebody else.
    """
    if not _lock_is_ours(path, inode):
        return False
    try:
        os.utime(path, None)
    except OSError:
        return False
    return True


def _lock_heartbeat(path, inode, stop, interval):
    """Renew the lock while the tick works, until the tick is over."""
    renewals = 0
    while not stop.wait(interval):
        if not renew_lock(path, inode):
            return  # the lock is gone or somebody else's: stop touching it
        renewals += 1
        if renewals % LOCK_HEARTBEAT_LOG_EVERY == 0:
            log("lock: renewed, this tick still holds the lock")


_lock_heartbeat_stop = None
_lock_heartbeat_thread = None


def _start_lock_heartbeat(path=LOCK, interval=LOCK_HEARTBEAT_SECS):
    """Start renewing the lock this process holds."""
    global _lock_heartbeat_stop, _lock_heartbeat_thread
    try:
        inode = os.stat(path).st_ino
    except OSError:
        return
    stop = threading.Event()
    thread = threading.Thread(target=_lock_heartbeat, args=(path, inode, stop, interval),
                              name="local-ci-lock-heartbeat", daemon=True)
    _lock_heartbeat_stop, _lock_heartbeat_thread = stop, thread
    thread.start()


def _stop_lock_heartbeat():
    """Stop renewing the lock.

    The thread is a daemon, so a tick that is killed without releasing the
    lock leaves no heartbeat behind: the next runner takes the lock over
    because its holder is gone.
    """
    global _lock_heartbeat_stop, _lock_heartbeat_thread
    stop, thread = _lock_heartbeat_stop, _lock_heartbeat_thread
    _lock_heartbeat_stop = _lock_heartbeat_thread = None
    if stop is not None:
        stop.set()
    if thread is not None:
        thread.join(timeout=2)


def acquire_lock():
    """Take the tick lock. A lock whose holder is dead is taken over and logged, never waited on."""
    _guard()
    try:
        os.mkdir(LOCK)
    except FileExistsError:
        pid = lock_holder_alive()
        try: age = time.time() - os.path.getmtime(LOCK)
        except OSError: age = -1
        if pid is not None and age >= 0 and age < LOCK_MAX_AGE:
            log(f"lock busy (pid {pid}, age {age:.0f}s); skip tick")
            return False
        log(f"stale lock removed (pid {pid}, age {age:.0f}s)")
        shutil.rmtree(LOCK, ignore_errors=True)
        try: os.mkdir(LOCK)
        except FileExistsError: return False
    try:
        with open(os.path.join(LOCK, "pid"), "w") as f: f.write(str(os.getpid()))
    except OSError: pass
    # Pass LOCK explicitly: the parameter default was bound at import time, so a
    # caller that moved LOCK (the local suite does) asked for a heartbeat on a
    # path that is nobody's lock, and got none at all.
    _start_lock_heartbeat(LOCK)
    return True

def release_lock():
    """Release only a lock this process holds; never sweep another holder's."""
    _stop_lock_heartbeat()
    try:
        with open(os.path.join(LOCK, "pid")) as f: mine = f.read().strip() == str(os.getpid())
    except (OSError, ValueError): mine = False
    if mine: shutil.rmtree(LOCK, ignore_errors=True)

def list_prs(base):
    o = gh("pr", "list", "-R", REPO, "--base", base, "--state", "open", "--limit", "500",
           "--json", "number,headRefOid,headRefName,baseRefName,title,isCrossRepository,createdAt,updatedAt")
    try: return json.loads(o or "[]")
    except ValueError: return []


def get_pr(number):
    """The pull request with this number, in whatever state it is in.

    `gh pr list --state open` cannot see a closed or a merged pull request, so
    an explicit --pr N run on one iterated an empty list: it evaluated
    nothing, reported nothing, and looked like it had done the work (DIG-4812,
    PR #6087). `gh pr view` resolves a pull request in any state.
    """
    o = gh("pr", "view", str(number), "-R", REPO, "--json",
           "number,state,headRefOid,headRefName,baseRefName,title,"
           "isCrossRepository,updatedAt,mergedAt,closedAt")
    try: pr = json.loads(o or "null")
    except ValueError: return None
    return pr if isinstance(pr, dict) else None


def pr_state(pr):
    """The pull request's state as GitHub reports it: OPEN, CLOSED or MERGED."""
    return (pr.get("state") or "").upper()


# --- review-applied (DIG-3842): required `review-applied` context on develop ---

def applied_status(sha, state, desc):
    """Post under review-applied's context: the exact context develop requires."""
    gh("api", "-X", "POST", f"repos/{REPO}/statuses/{sha}", "-f", f"state={state}",
       "-f", f"context={review_applied.APPLIED_CTX}", "-f", f"description={desc[:139]}")


def applied_ci_status(sha):
    """Latest (state, description, created_at) posted under APPLIED_CTX."""
    o = gh("api", f"repos/{REPO}/commits/{sha}/statuses", "--paginate")
    try: rows = json.loads(o or "[]")
    except ValueError: return None, None, None
    rows = [r for r in rows if isinstance(r, dict)
            and r.get("context") == (review_applied.APPLIED_CTX if review_applied else "review-applied")]
    if not rows: return None, None, None
    rows.sort(key=lambda r: r.get("createdAt", r.get("created_at", "")))
    last = rows[-1]
    return last.get("state"), last.get("description") or "", last.get("createdAt", last.get("created_at", "")) or ""


def pending_applied(prs):
    """Same-repo develop PRs still needing a review-applied verdict: none posted
    yet, a re-checkable skip, or a failure old enough to re-check (replies and
    fix commits may have landed since).

    The order is the same fairness rule the check queue uses (DIG-5135): the
    pull request that arrived first is served first. The newest-first order
    left the old pull requests waiting behind every later arrival, and a
    required context that never reports is a pull request that cannot merge.
    """
    out = []
    for p in prs:
        if bool(p.get("isCrossRepository")):
            continue
        st, desc, ts = applied_ci_status(p["headRefOid"])
        if st == "success":
            continue
        if st in ("pending", "failure") and desc.startswith(SKIP_PREFIX):
            out.append(p)  # gate cleared since the skip; re-check
        elif st is None:
            out.append(p)
        elif st in ("pending", "failure") and _status_age_secs(ts) >= REVIEW_RECHECK_SECS:
            out.append(p)
    out.sort(key=lambda p: (p.get("createdAt") or p.get("updatedAt") or "",
                             p.get("number") or 0))
    return out


def _gh_json(argv):
    o = gh(*argv)
    try: return json.loads(o or "")
    except ValueError: return None


def _rest(path):
    return _gh_json(["api", path, "--paginate"])


def run_applied(pr, out):
    """Evaluate review-applied for one develop PR. Returns (ok, message)."""
    if review_applied is None:
        return False, "review-applied: checker module missing on this Mac (see log)"
    n = pr["number"]
    threads = review_applied.fetch_threads_graphql(
        n, REPO, lambda argv: _gh_json(argv))
    if threads is None:
        out.write("review-applied: thread fetch failed\n")
        return False, "review-applied: could not read review threads (see log)"
    passes = review_applied.fetch_review_passes(n, REPO, lambda argv: _gh_json(argv), _rest)
    # A reviewer bot's thread comments are themselves a review pass: CodeQL posts
    # findings as review threads with an empty REST review body, so the REST-only
    # read above misses it. Any thread comment by a recognised bot counts.
    for t in threads or []:
        if not isinstance(t, dict):
            continue
        for c in (t.get("comments") or []):
            if isinstance(c, dict) and review_applied.is_reviewer_bot(c.get("author")):
                passes.append({"kind": "bot", "author": c.get("author"),
                               "has_comments": True})
                break
    checks = _rest(f"repos/{REPO}/commits/{pr['headRefOid']}/check-runs") or []
    try:
        check_runs = [{"name": r.get("name"), "conclusion": r.get("conclusion")}
                       for r in (checks.get("check_runs", checks) if isinstance(checks, dict) else checks)]
    except AttributeError:
        check_runs = []
    commits = _rest(f"repos/{REPO}/pulls/{n}/commits") or []
    fix_ats = []
    for c in commits:
        try: fix_ats.append((c.get("commit") or {}).get("committer", {}).get("date"))
        except AttributeError: pass
    fix_ats = [t for t in fix_ats if t]
    reviewers = review_applied.reviewer_logins_for(passes)
    # The verdict leg (DIG-4646): a head whose latest review says "changes
    # requested" must never be posted as a review-applied success. The verdicts
    # are read with the shared parser the merge queue uses, so both read the
    # fleet's "Review verdict: ..." lines. An unreadable record is not a
    # clearance, so the check fails closed with that reason.
    verdict_inputs = review_applied.fetch_verdict_inputs(n, REPO, _rest)
    if verdict_inputs is None:
        verdict_blocks, verdict_error = (), "the reviews or comments could not be read"
    else:
        verdict_blocks, verdict_error = review_applied.blocking_verdicts(*verdict_inputs), None
    ok, msg, open_ids = review_applied.evaluate(
        passes, threads, fix_ats, check_runs, reviewers,
        verdict_blocks=verdict_blocks, verdict_error=verdict_error)
    out.write(f"review-applied: passes={len(passes)} threads={len(threads)} "
              f"fix_commits={len(fix_ats)} ok={ok}\n{msg}\n")
    for tid in open_ids:
        out.write(f"  OPEN {tid}\n")
    return ok, msg


def process_applied(pr, dry):
    sha = pr["headRefOid"]; n = pr["number"]
    logf = f"{LOGD}/pr{n}-applied-{sha[:12]}.log"
    log(f"PR #{n} review-applied {sha[:12]} start")
    if not dry: applied_status(sha, "pending", "local-ci: checking review-applied")
    sh(["git", "fetch", "-q", "origin", pr["baseRefName"], f"pull/{n}/head"], cwd=MAIN, timeout=600)
    t0 = time.time()
    with open(logf, "w") as out:
        try:
            ok, msg = run_applied(pr, out)
        except Exception as exc:
            # One broken PR must not kill the whole tick: the tick has no
            # except, and the escape left the head's "review-applied" status
            # stuck at "pending", which the queue then reads as a refusal
            # (DIG-4646).
            ok = False
            msg = "review-applied: the check raised %s (see log)" % type(exc).__name__
            out.write("%s: %s\n" % (type(exc).__name__, exc))
    mins = (time.time() - t0) / 60
    desc = f"{msg} ({mins:.0f}m)"
    log(f"PR #{n} review-applied {sha[:12]} {'success' if ok else 'failure'}: {desc} log={logf}")
    if not dry: applied_status(sha, "success" if ok else "failure", desc)
    return "success" if ok else "failure"


# --- child tracking and the stuck-tick watchdog (DIG-4453) ---------------------
# The lock self-heals only after 7200 s, which is far too long for develop's only
# required context. A step's own timeout normally breaks its tree; the watchdog is
# the backstop for the case where it did not.
CHILD_STATE = os.path.join(HOME, ".config/digithings/state/local-ci.child.json")
WATCHDOG_GRACE_SECS = 120   # slack on top of a step's own budget
KILL_GRACE_SECS = 3.0
# pid -> {"pid", "name", "started", "budget"} for every step running right now.
# Guarded by _CHILD_LOCK: the pool runs steps on worker threads.
_LIVE_CHILDREN: dict[int, dict] = {}
_CHILD_LOCK = threading.Lock()


def _write_child_state(pid, name, budget):
    """Record the running child so the next tick can spot a step that overran its budget.

    Steps now run in a pool (STEP_POOL), so the record has to hold every child
    that is running at once: a single-slot file would forget all but the last
    one and the watchdog could not reap the tick's other half.
    """
    with _CHILD_LOCK:
        _LIVE_CHILDREN[int(pid)] = {"pid": int(pid), "name": str(name)[:120],
                                    "started": time.time(), "budget": int(budget)}
        _flush_child_state()


def _clear_child_state(pid=None):
    """Forget one finished child (pid) or every child (no argument)."""
    with _CHILD_LOCK:
        if pid is None:
            _LIVE_CHILDREN.clear()
        else:
            _LIVE_CHILDREN.pop(int(pid), None)
        _flush_child_state()


def _flush_child_state():
    """Write the live-child list; unlink it when nothing is running. Holds _CHILD_LOCK."""
    tmp = CHILD_STATE + ".tmp"
    try:
        if not _LIVE_CHILDREN:
            try:
                os.unlink(CHILD_STATE)
            except OSError:
                pass
            return
        os.makedirs(os.path.dirname(CHILD_STATE), exist_ok=True)
        with open(tmp, "w") as f:
            json.dump({"children": list(_LIVE_CHILDREN.values())}, f)
        os.replace(tmp, CHILD_STATE)
    except (OSError, ValueError):
        pass


def read_child_state():
    """The recorded children, as {"children": [...]}.

    A state file written before the pool holds one flat child; it is returned in
    the same shape so a watchdog started after an upgrade reads both.
    """
    try:
        with open(CHILD_STATE) as f:
            st = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(st, dict):
        return None
    if isinstance(st.get("children"), list):
        return {"children": [c for c in st["children"] if isinstance(c, dict)]}
    return {"children": [st]}


def _ppid_map():
    out = subprocess.run(["ps", "-Ao", "pid=,ppid="], capture_output=True, text=True).stdout
    m = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2:
            try:
                m[int(parts[0])] = int(parts[1])
            except ValueError:
                pass
    return m


def _tree(pid, ppids):
    """pid plus every descendant, collected before anything is killed."""
    out = [pid]
    for p, pp in ppids.items():
        if pp == pid:
            out.extend(_tree(p, ppids))
    return out


def kill_tree(pid, grace=KILL_GRACE_SECS):
    """TERM a process and its descendants, then KILL what is left."""
    pids = _tree(pid, _ppid_map())
    for p in pids:
        try:
            os.kill(p, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
    time.sleep(grace)
    for p in pids:
        try:
            os.kill(p, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    return pids


def _kill_step_tree(p, grace=KILL_GRACE_SECS):
    """Take down a timed-out step: its process group plus every descendant."""
    pids = _tree(p.pid, _ppid_map())
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(os.getpgid(p.pid), sig)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        for pid_ in pids:
            try:
                os.kill(pid_, sig)
            except (ProcessLookupError, PermissionError):
                pass
        if sig == signal.SIGTERM:
            time.sleep(grace)


GATE_CMD_MARKERS = ("npm exec", "wrangler", "esbuild")
WATCHDOG_PID_REUSE_TOLERANCE = 5   # s between the recorded age and the OS age


def _ps_etime(pid):
    """Elapsed seconds of pid per ps, or None when the pid is not running."""
    try:
        out = subprocess.run(["ps", "-o", "etime=", "-p", str(pid)],
                             capture_output=True, text=True).stdout.strip()
    except OSError:
        return None
    if not out:
        return None
    bits = out.split()
    days = 0
    t = bits[0]
    if "-" in t:
        d, t = t.split("-", 1)
        try:
            days = int(d)
        except ValueError:
            return None
    parts = t.split(":")
    try:
        if len(parts) == 3:
            h, m, sec = (int(x) for x in parts)
        elif len(parts) == 2:
            h, m, sec = 0, int(parts[0]), int(parts[1])
        else:
            h, m, sec = 0, 0, int(parts[0])
    except ValueError:
        return None
    return days * 86400 + h * 3600 + m * 60 + sec


def _group_members(pgid):
    """(pid, command) of every process in the group pgid."""
    try:
        out = subprocess.run(["ps", "-Ao", "pid=,pgid=,command="],
                             capture_output=True, text=True).stdout
    except OSError:
        return []
    rows = []
    for line in out.splitlines():
        bits = line.split(None, 2)
        if len(bits) < 3:
            continue
        try:
            if int(bits[1]) == pgid:
                rows.append((int(bits[0]), bits[2]))
        except ValueError:
            pass
    return rows


def _kill_group(pgid, grace=KILL_GRACE_SECS):
    """Take down a whole process group, leader or not."""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        if sig == signal.SIGTERM:
            time.sleep(grace)


def watchdog():
    """Reap a step that outlived its own budget. Returns True when it acted.

    The age is the OS age of the recorded pid, never the recorded timestamp: a
    state file left behind by a killed run names a pid the kernel may hand to an
    unrelated process later. On 2026-10-19 20:06:35 that happened and the first
    version of this watchdog killed a healthy tick because it trusted the
    recorded start. The recorded age now only proves that the pid is still the
    process we spawned; the kill decision is the OS age.

    Every child in the record is judged, not just one: a tick runs several gates
    at once (STEP_POOL), so a wedged step can be any of them.
    """
    holder = lock_holder_alive()
    if holder is None:
        _clear_child_state()
        return False
    st = read_child_state()
    if not st:
        return False
    acted = False
    keep = []
    for child in st.get("children") or []:
        killed, alive = _judge_child(holder, child)
        acted = killed or acted
        if alive:
            keep.append(child)
    # The record is this tick's input, not its own bookkeeping: a child that was
    # reaped or is already gone is dropped, and one that is still inside its
    # budget stays on the record for the next watchdog.
    _rewrite_child_state(keep)
    return acted


def _rewrite_child_state(children):
    """Replace the record with exactly `children`; unlink it when there are none."""
    tmp = CHILD_STATE + ".tmp"
    try:
        if not children:
            try:
                os.unlink(CHILD_STATE)
            except OSError:
                pass
            return
        os.makedirs(os.path.dirname(CHILD_STATE), exist_ok=True)
        with open(tmp, "w") as f:
            json.dump({"children": children}, f)
        os.replace(tmp, CHILD_STATE)
    except (OSError, ValueError):
        pass


def _judge_child(holder, child):
    """Judge one recorded child: (killed, keep).

    ``keep`` is True only for a child that is still running inside its budget;
    everything else has been dealt with and leaves the record.
    """
    try:
        started = float(child.get("started") or 0)
        budget = float(child.get("budget") or 0)
        pid = int(child.get("pid") or 0)
    except (TypeError, ValueError):
        return False, False
    if pid <= 0:
        return False, False
    age_recorded = time.time() - started
    age_os = _ps_etime(pid)
    if age_os is None:
        # the step leader is gone; only its process group can still leak
        members = [(p, c) for p, c in _group_members(pid)
                   if any(m in c for m in GATE_CMD_MARKERS)]
        if not members:
            return False, False
        if age_recorded <= budget + WATCHDOG_GRACE_SECS:
            return False, False
        log(f"watchdog: tick {holder} group {pid} ({child.get('name')}) age {age_recorded:.0f}s over budget {budget:.0f}s; killing {len(members)} leaked process(es)")
        for p, _c in members:
            kill_tree(p)
        return True, False
    if abs(age_recorded - age_os) > WATCHDOG_PID_REUSE_TOLERANCE:
        # the pid is no longer the process we spawned: stale state, not an overrun
        return False, False
    if age_os <= budget + WATCHDOG_GRACE_SECS:
        return False, True
    log(f"watchdog: tick {holder} child {pid} ({child.get('name')}) age {age_os:.0f}s over budget {budget:.0f}s; killing child tree")
    kill_tree(pid)
    _kill_group(pid)
    return True, False

def wt_is_ours(path):
    """True only for a linked worktree this runner created from MAIN.

    LOCAL_CI_WT is operator-supplied (DIG-4490), so the rebuild path must not delete a
    directory it did not make: a typo such as LOCAL_CI_WT=$HOME/Code would otherwise take
    the whole tree with it. A worktree of ours is a directory whose .git is a *file*
    naming a gitdir under MAIN.
    """
    if os.path.exists(os.path.join(path, ".local-ci-worktree")):
        return True
    if os.environ.get("LOCAL_CI_WT"):
        # Operator-supplied path: only the sentinel we write makes it ours. A worktree of
        # MAIN is still someone's tree, and deleting it in a rebuild would lose work.
        return False
    gitfile = os.path.join(path, ".git")
    if not os.path.exists(gitfile) or os.path.isdir(gitfile):
        return False
    try:
        with open(gitfile, encoding="utf-8", errors="replace") as fh:
            text = fh.read(4096)
    except OSError:
        return False
    if "gitdir:" not in text:
        return False
    target = os.path.realpath(text.split("gitdir:", 1)[1].strip())
    return os.path.realpath(MAIN) in target


def not_open_verdict(pr, dry):
    """The verdict for a pull request that is no longer open.

    A closed or a merged pull request has nothing left to gate, but the run
    must say so out loud: silence is what made the missing verdict on #6087
    invisible until the deploy lane broke again (DIG-4812). The verdict names
    the pull request and its state.

    A head that was gated while the pull request was open keeps the verdict
    it earned. Overwriting that row would make a merged commit look red, and
    the merge queue reads the row. A head that carries only a `pending` row
    (a run that died mid-flight) earned nothing, so it gets a terminal
    verdict here instead of staying pending forever.

    A fork head is not a commit of this repository: no status can be posted
    for it, so the run reports the fact and posts nothing.
    """
    n = pr.get("number"); sha = pr.get("headRefOid") or ""
    st = pr_state(pr) or "UNKNOWN"
    when = pr.get("mergedAt") or pr.get("closedAt") or "no date"
    fork = bool(pr.get("isCrossRepository"))
    st0, desc0 = (None, None)
    if sha and not fork:
        st0, desc0 = ci_status(sha)
    if st0 in ("success", "failure", "error"):
        verdict = f"PR #{n} is {st.lower()}; local-ci verdict on {sha[:12]} kept: {st0} ({desc0})"
    elif fork:
        verdict = f"PR #{n} is {st.lower()}; {FORK_DESC}"
    else:
        desc = f"local-ci skipped: PR #{n} is {st.lower()}; nothing to gate"
        verdict = f"PR #{n} is {st.lower()}; {desc}"
        if not dry and sha:
            status(sha, "failure", desc)
    log(f"PR #{n} {sha[:12]} {st} ({when}): {verdict}")
    print(f"local-ci: {verdict}")
    return st0 if st0 in ("success", "failure", "error") else "failure"


def explicit_run(only, dry):
    """Run the gate for one named pull request, whatever state it is in.

    The pull request is resolved with `gh pr view`, so a closed or a merged
    one is still evaluated and the run still ends with a verdict naming it
    (DIG-4812).
    """
    pr = get_pr(only)
    if not pr:
        log(f"PR #{only} not found in {REPO} (or gh could not resolve it)")
        print(f"local-ci: PR #{only} not found in {REPO} (or gh could not resolve it)")
        return None
    n = pr.get("number", only)
    st = pr_state(pr)
    if st and st != "OPEN":
        return not_open_verdict(pr, dry)
    if pr.get("isCrossRepository"):
        log(f"PR #{n} is a fork pull request: {FORK_DESC}")
        print(f"local-ci: PR #{n} is a fork pull request: {FORK_DESC}")
        return None
    base = pr.get("baseRefName")
    if base == "main":
        if is_promotion_pr(pr):
            return process_review(pr, dry)
        log(f"PR #{n} is not a promotion pull request: out of scope for local-ci")
        print(f"local-ci: PR #{n} is not a promotion pull request: out of scope for local-ci")
        return None
    if base != "develop":
        log(f"PR #{n} has base {base}: out of scope for local-ci")
        print(f"local-ci: PR #{n} has base {base}: out of scope for local-ci")
        return None
    sha = pr.get("headRefOid")
    if sha and not dry:
        # An explicit run is a run like any other: it does not start on a head
        # another run is checking. Two runs on one head post two `local-ci`
        # rows on the required check (DIG-5135).
        state, pid = claim_state(sha)
        if state == "live" and pid != os.getpid() and not claim_is_lost(sha, None):
            log(f"PR #{n} {sha[:12]}: the run {pid} holds this head; "
                "an explicit run does not start a second one")
            print(f"local-ci: PR #{n} is already being checked by the run {pid}")
            return None
    st = process(pr, dry)
    process_applied(pr, dry)
    return st


def check_required_context_producers():
    """DIG-4507: one required context, one producer (recurrence guard).

    A required context with two implementations has no single meaning: the
    verdict then depends on which row a reader happens to look at. The guard
    reads main's protection live and checks that every required context has
    exactly one producer. A failure here is logged and is never fatal to the
    tick: an unreadable protection is reported, not failed.

    The report is logged per repo, because this is the only automated path:
    the guard's own `main()` prints UNREADABLE, but the tick calls `run()`.
    Printing `ok` for a repo whose protection could not be read would be a
    silent pass - a tick that looks healthy while the guard is blind - so
    `ok` is written only for the repos that were actually checked.
    """
    try:
        import importlib.util
        here = os.path.dirname(os.path.abspath(__file__))
        spec = importlib.util.spec_from_file_location(
            "rcp_guard", os.path.join(here, "check_required_context_producers.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        def reader(repo):
            # gh() returns raw stdout, not parsed JSON (see def gh): parse it here.
            out = gh("api", f"repos/{repo}/branches/main/protection")
            if out is None:
                return False, None
            try:
                return True, json.loads(out)
            except ValueError:
                return False, None

        rep = mod.run(host_dir=here, reader=reader)
        readable = [r["repo"] for r in rep["repos"] if r.get("readable")]
        for r in rep["repos"]:
            if not r.get("readable"):
                log("required-context producers: %s protection UNREADABLE (not failed)"
                    % r["repo"])
        if rep["violations"]:
            log("required-context producers: VIOLATION " + json.dumps(rep["violations"]))
        elif readable:
            log("required-context producers: ok " + json.dumps(readable))
        else:
            log("required-context producers: nothing checked: no readable protection")
    except Exception as e:
        log(f"required-context producers: guard error {type(e).__name__}: {e}")


def main():
    # The launch guard runs first, before any side effect: a run that no trusted
    # launcher started (a hand-run from any shell, a seat's shell, a detached
    # script) is refused with exit 78 and never reaches the lock, the watchdog
    # or GitHub (DIG-4796). The guard is asked again at every entry point that
    # does work, because the post-merge launchd job never comes through here.
    _guard()
    dry = "--dry-run" in sys.argv
    if os.environ.get("LOCAL_CI_WT") and os.path.isdir(WT) and not wt_is_ours(WT):
        sys.exit(f"local_ci: LOCAL_CI_WT={WT} exists and is not a worktree of {MAIN}; "
                 "refusing to run rather than rebuild over it")
    if not os.environ.get("LOCAL_CI_MAIN") and not os.path.isdir(os.path.join(MAIN, ".git")):
        sys.exit(f"local_ci: default checkout {MAIN} is not a git repository; "
                 "set LOCAL_CI_MAIN (scripts/local-ci/install.sh writes it)")
    only = int(sys.argv[sys.argv.index("--pr") + 1]) if "--pr" in sys.argv else None
    if dry:
        # A preview changes nothing: taking the tick lock or running the watchdog would
        # perturb the live gate (DIG-4490 review).
        pass
    else:
        watchdog()
        if not acquire_lock(): return
    try:
        if only is not None:
            explicit_run(only, dry)
            return
        if not dry:
            prune_claims()
            refresh_checkout()
        prs = list_prs("develop")
        main_prs = list_prs("main")
        reason = skip_reason()
        if reason is not None:
            log(f"skip: {reason}")
            if not dry:
                for p in pending(prs, False)[:MAX_PER_TICK]:
                    status(p["headRefOid"], "failure", f"local-ci skipped: {reason}")
                for p in pending(prs, True)[:MAX_PER_TICK]:
                    status(p["headRefOid"], "failure", FORK_DESC, app=False)
                for p in pending_applied(prs)[:MAX_PER_TICK]:
                    applied_status(p["headRefOid"], "failure", f"local-ci skipped: {reason}")
            return
        if not dry:
            for p in pending(prs, True)[:MAX_PER_TICK]:
                status(p["headRefOid"], "failure", FORK_DESC, app=False)
        done = 0
        for p in pending(prs, False, dry=dry):
            if done >= MAX_PER_TICK: break
            process(p, dry); done += 1
        applied = 0
        for p in pending_applied(prs):
            if applied >= MAX_PER_TICK: break
            process_applied(p, dry); applied += 1
        reviewed = 0
        for p in pending_reviews(main_prs):
            if reviewed >= REVIEW_MAX_PER_TICK: break
            process_review(p, dry); reviewed += 1
        check_required_context_producers()
    finally:
        release_lock()

if __name__ == "__main__":
    main()
