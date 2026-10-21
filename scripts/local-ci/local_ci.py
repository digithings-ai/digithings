#!/usr/bin/env python3
"""local-ci: runs digithings PR checks on Chris's Mac and posts commit status `local-ci`.
Replaces GitHub Actions PR checks (Actions minutes exhausted, Chris 14 Oct 2026 22:10).
Same-repo PRs into develop only (never forks). Concurrency 1 via lock. Skips when reclaimable
memory is critically low or the disk guard pauses worktrees. Logs: ~/.config/digithings/logs/local-ci/.
Never prints secrets.
A swap/disk-guard skip posts `failure` on the queued PRs, never silence, so merges block
loudly (DIG-3660 must-fix 5). Fork code never executes on this Mac: fork PRs get a `failure`
naming the maintainer re-push path. Static gates only: PR title, PR template,
gitleaks, PII scan, R0 client-literal scan,
guard scripts, actionlint, uv sync, ruff, mypy, doc checks, worker dry-run build (path-gated). NOT gated (DIG-3605 owns the
rest): per-package pytest suites, compose-validate, npm/pip audit, token-canary,
secret-staleness, invite-key rollout, answer-check, cron dispatch, secret sync.
Also posts `Every commit reaching main was reviewed` (main's required context,
same logic ci-review-coverage.yml runs via scripts/check_review_coverage.py) for
same-repo develop->main promotion PRs (DIG-3743). Nothing else posts that name.
Usage: local_ci.py [--pr N] [--dry-run]"""
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
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
HOME = os.path.expanduser("~")
REPO = "digithings-ai/digithings"
MAIN = os.environ.get("LOCAL_CI_MAIN") or f"{HOME}/Code/digithings"
WT = os.environ.get("LOCAL_CI_WT") or f"{HOME}/Code/local-ci/wt"
LOGD = f"{HOME}/.config/digithings/logs/local-ci"
LOCK = f"{HOME}/.config/digithings/state/local-ci.lock"
PAUSE = f"{HOME}/.config/digithings/state/worktree-pause"
CTX = "local-ci"; MAX_PER_TICK = 2; MIN_AVAIL_MB = 2048; MIN_FREE_PCT = 20.0
# Primary memory gate (DIG-3783): skip below this system-wide free percentage,
# the same signal the board driver uses. vm_stat reclaimable MB is the fallback.
# Exact context name required by main's branch protection (ci-review-coverage.yml
# job `review-coverage`). Posted by local-ci for develop->main promotion PRs while
# GitHub Actions minutes are exhausted (DIG-3743). Never rename: protection matches
# this string.
REVIEW_CTX = "Every commit reaching main was reviewed"
# One promotion review per tick: the range is ~1000 commits and takes minutes.
REVIEW_MAX_PER_TICK = 1
# A posted failure is re-checked at most hourly: reviews/approvals/labels may land
# after the verdict, but re-running every 3 min tick would burn the Mac for nothing.
REVIEW_RECHECK_SECS = 3600
SKIP_PREFIX = "local-ci skipped:"
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
               "digitrace-langfuse", "digichat-cloudflare", "digithings-stack-cloudflare",
               # twelvex-runner is in the ci.yml worker-build matrix but was missing
               # here, so the local gate built one Worker less than CI does. It is
               # the build that proves the app's workspace imports bundle (DIG-4753).
               "twelvex-runner")
WORKER_GATE_PATTERNS = tuple(f"apps/{a}/**" for a in WORKER_APPS) + (
    "apps/**/wrangler.toml", "package.json", "package-lock.json",
)
# A dry-run that has not finished in 5 minutes is wedged, not slow (DIG-4453).
WORKER_DRY_RUN_TIMEOUT = 300
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
    return b


ENV = build_env()

def log(m):
    with open(f"{LOGD}/local-ci.log", "a") as f: f.write(time.strftime("%F %T ") + m + "\n")

def sh(cmd, cwd=None, timeout=1800, out=None, name=None):
    """Run a command under a wall-clock timeout that takes the WHOLE tree down.

    `subprocess.run(timeout=)` kills only the direct child: the wrangler and
    esbuild grandchildren survive, are re-parented to pid 1 and leak (8 leaked
    trees measured 2026-10-19). The child gets its own process group so the
    timeout can break the tree, and its identity is recorded for the watchdog.
    """
    try:
        p = subprocess.Popen(cmd, cwd=cwd, env=ENV, stdout=subprocess.PIPE,
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
        _clear_child_state()
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

def status(sha, state, desc):
    gh("api", "-X", "POST", f"repos/{REPO}/statuses/{sha}", "-f", f"state={state}", "-f", f"context={CTX}", "-f", f"description={desc[:139]}")


def review_status(sha, state, desc):
    """Post under REVIEW_CTX: the exact context main's protection requires."""
    gh("api", "-X", "POST", f"repos/{REPO}/statuses/{sha}", "-f", f"state={state}", "-f", f"context={REVIEW_CTX}", "-f", f"description={desc[:139]}")


def review_ci_status(sha):
    """Latest (state, description, created_at) posted under REVIEW_CTX, or (None, None, None)."""
    o = gh("api", f"repos/{REPO}/commits/{sha}/statuses", "--paginate")
    try: rows = json.loads(o or "[]")
    except ValueError: return None, None, None
    rows = [r for r in rows if isinstance(r, dict) and r.get("context") == REVIEW_CTX]
    if not rows: return None, None, None
    rows.sort(key=lambda r: r.get("createdAt", r.get("created_at", "")))
    last = rows[-1]
    return last.get("state"), last.get("description") or "", last.get("createdAt", last.get("created_at", "")) or ""


def _status_age_secs(created_at):
    try:
        ts = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - ts).total_seconds()
    except (ValueError, TypeError):
        return float("inf")


def is_promotion_pr(pr):
    """Same-repo PRs into main carrying develop (promotion title). Only these get
    the local review-coverage verdict; other main PRs are out of scope."""
    if pr.get("baseRefName") != "main" or bool(pr.get("isCrossRepository")):
        return False
    title = pr.get("title") or ""
    return title == "chore: promote develop to main" or re.match(
        r"^chore\([^)]*\):\s*release\s|^chore\(release\):\s", title) is not None


def pending_reviews(prs):
    """Promotion PRs still needing a review-coverage verdict: none posted yet, or
    the last verdict is old enough to re-check (reviews may have landed since)."""
    out = []
    for p in prs:
        if not is_promotion_pr(p):
            continue
        st, desc, ts = review_ci_status(p["headRefOid"])
        if st == "success":
            continue
        if st in ("pending", "failure") and desc.startswith(SKIP_PREFIX):
            out.append(p)  # gate cleared since the skip; re-check
        elif st is None:
            out.append(p)
        elif st in ("pending", "failure") and _status_age_secs(ts) >= REVIEW_RECHECK_SECS:
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
    if not dry: review_status(sha, "pending", "local-ci: checking review coverage")
    t0 = time.time()
    with open(logf, "w") as out:
        ok_wt, why = prepare_wt(n, sha, pr["baseRefName"], out)
        ok, total, unreviewed = run_review_coverage(pr, out) if ok_wt else (False, -1, -1)
    mins = (time.time() - t0) / 60
    if ok: st, desc = "success", f"review coverage: all {total} commits reviewed ({mins:.0f}m)"
    else: st, desc = "failure", f"review coverage: {unreviewed} unreviewed of {total} (see log) ({mins:.0f}m)"
    log(f"PR #{n} review-coverage {sha[:12]} {st}: {desc} log={logf}")
    if not dry: review_status(sha, st, desc)
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


def parse_workers_patterns(text):
    """Parse the `workers:` path-filter block out of scripts/ci_paths.yaml text.

    Returns the `- <pattern>` entries in order, or [] when the block is absent.
    """
    out = []
    in_block = False
    for line in (text or "").splitlines():
        if not line.startswith((" ", "\t")):
            if line.startswith("workers:"):
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


def worker_gate_hit(files, patterns):
    """First (pattern, path) hit of changed files against gate patterns, else None.

    Pattern-major: the first pattern (in ci_paths.yaml order) matching any file wins.
    """
    rxs = [(p, glob_to_regex(p)) for p in patterns]
    for p, rx in rxs:
        for f in files:
            if rx.match(f):
                return p, f
    return None


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


def worker_build(wt, step):
    """Run the ci.yml worker-build dry-run over all WORKER_APPS. Failures record via step.

    Returns the failed step names (for tests/observability); run_checks discards it.
    """
    failed = []
    outdir = tempfile.mkdtemp(prefix="wrangler-dry-run-")
    try:
        if not step("worker-build:npm-ci", ["npm", "ci", "--no-audit", "--no-fund"], 1800):
            return ["worker-build:npm-ci"]
        for app in WORKER_APPS:
            ok = step(f"worker-build:{app}",
                      ["npm", "exec", "--", "wrangler", "deploy", "--dry-run",
                       "--containers-rollout=none", "--outdir", outdir],
                      WORKER_DRY_RUN_TIMEOUT, os.path.join(wt, "apps", app))
            if not ok:
                failed.append(f"worker-build:{app}")
        return failed
    finally:
        shutil.rmtree(outdir, ignore_errors=True)


def wt_head():
    """HEAD sha of the checks worktree, or None when git cannot read it
    (missing dir, pruned worktree metadata, broken index)."""
    rc, o = sh(["git", "rev-parse", "HEAD"], cwd=WT) if os.path.isdir(WT) else (1, "")
    o = (o or "").strip()
    return o if rc == 0 and re.fullmatch(r"[0-9a-f]{40}", o) else None


def prepare_wt(n, sha, base, out):
    """Put the checks worktree on exactly `sha`. Returns (ok, reason).

    Fails closed (stale-worktree incident, 17 Oct 2026): from 15 Oct to
    17 Oct every `git checkout` here failed silently and all gates ran on
    one frozen tree, so local-ci posted green for code it never checked.
    Now every step's rc is logged, a worktree git cannot read is rebuilt,
    and HEAD must equal the PR head before any gate runs. origin/main is
    fetched too: check_vendor_content.py baselines on merge-base(HEAD, origin/main)."""
    out.write(f"===== worktree {sha[:12]}\n")
    sh(["git", "fetch", "-q", "origin", base, "main", f"pull/{n}/head"], cwd=MAIN, timeout=600, out=out)
    if os.path.isdir(WT) and wt_head() is None:
        if not wt_is_ours(WT):
            return False, (f"{WT} is not a worktree this runner created; refusing to rebuild "
                           "over it (set LOCAL_CI_WT to the runner's own worktree directory)")
        out.write("worktree unreadable by git; rebuilding\n")
        shutil.rmtree(WT, ignore_errors=True)
        sh(["git", "worktree", "prune"], cwd=MAIN, out=out)
    if not os.path.exists(WT):
        sh(["git", "worktree", "add", "--detach", "-f", WT, sha], cwd=MAIN, timeout=900, out=out)
    sh(["git", "checkout", "-q", "--detach", "-f", sha], cwd=WT, timeout=900, out=out)
    sh(["git", "clean", "-fdq", "-e", ".venv", "-e", "node_modules"], cwd=WT, out=out)
    try:
        with open(os.path.join(WT, ".local-ci-worktree"), "w", encoding="utf-8") as fh:
            fh.write(sha + "\n")
    except OSError as exc:  # a read-only worktree still works; it just cannot be rebuilt
        out.write(f"could not mark the worktree as ours: {exc}\n")
    head = wt_head()
    if head != sha:
        out.write(f"worktree FAIL: HEAD {head} != PR head {sha}; no gate ran\n")
        log(f"PR #{n} worktree checkout failed: HEAD {head} != {sha}")
        return False, f"HEAD {(head or 'unreadable')[:12]} != {sha[:12]}"
    return True, ""


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


def run_checks(pr, out):
    sha, base, title = pr["headRefOid"], pr["baseRefName"], pr["title"]
    fails = []
    def step(name, cmd, timeout=1800, cwd=None):
        out.write(f"\n===== {name}\n"); rc, _ = sh(cmd, cwd=(cwd or WT), timeout=timeout, out=out, name=name)
        if rc != 0: fails.append(name)
        return rc == 0
    # PR title
    if not (title == "chore: promote develop to main" or re.match(r"^chore\([^)]*\):\s*release\s|^chore\(release\):\s", title)
            or re.match(rf"^({TYPES})\([^)]+\)!?: .+", title)):
        fails.append("pr-title"); out.write(f"pr-title FAIL: {title!r}\n")
    # PR template (DIG-3842 scope update 15 Oct 2026; DCO gate removed same day,
    # its workflow removal rides on DIG-3845)
    if pr_template is None:
        fails.append("pr-template"); out.write("pr-template FAIL: checker module missing\n")
    else:
        body = gh("pr", "view", str(pr["number"]), "-R", REPO, "--json", "body", "-q", ".body")
        ok, reasons = pr_template.check_template(body or "")
        if not ok:
            fails.append("pr-template")
        for r in reasons:
            out.write(f"pr-template FAIL: {r}\n")
    rep = f"{LOGD}/gitleaks-{sha[:12]}.json"
    opts = gitleaks_log_opts(base, sha, out)
    if opts is None:
        fails.append("gitleaks")
    else:
        step("gitleaks", ["gitleaks", "detect", "--source", ".", "--config", ".gitleaks.toml", "--redact", "--no-banner",
                          "--report-format", "json", "--report-path", rep, f"--log-opts={opts}"])
    # 2026-10-18 (Board, DIG-4056/DIG-1415): check_vendor_content.py runs with --warn here.
    # Its 28 blocking hits are all in apps/twelvex-runner + the twelvex jobs in apps/digithings-cron;
    # they read as NEW only because the check baselines on merge-base(HEAD, origin/main) (2026-10-13)
    # and that app landed 2026-10-16 (#5852) - and those paths move to the private twelve-x repo in
    # the repo split (DIG-4056). Findings still print in full in this log; only the exit code relaxes.
    # Revert by deleting " --warn" from the entry below once DIG-1415 lands the carve-out rule.
    for s in ["scripts/scan_customer_pii.py --json " + f"{LOGD}/pii-{sha[:12]}.json",
              "scripts/check_frontend_canon.py", "scripts/check_gloomberb_ci_guard.py", "scripts/check_vendor_content.py --warn",
              "scripts/check_plaintext_credentials.py", "scripts/check_example_credentials.py",
              "scripts/check_r0_no_client_literals.py"]:
        if os.path.exists(f"{WT}/{s.split()[0]}"): step(s.split()[0], f"python3 {s}", 600)
    step("actionlint", ["actionlint"], 300)
    step("uv-sync", "uv sync --frozen --all-packages --all-extras", 1800)
    if "uv-sync" not in fails:
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
        if rpaths:
            step("ruff", U + "ruff check " + " ".join(rpaths), 600)
        step("mypy", U + "mypy digibase/src/digibase/ digikey/src/digikey/ --config-file mypy.ini", 1200)
        for s in ["check_doc_links.py", "check_adr_numbering.py", "agents_init.py --check", "check_model_name_literals.py",
                  "generate_ci_path_filters.py --check"]:
            if os.path.exists(f"{WT}/scripts/{s.split()[0]}"): step(s.split()[0], U + f"python scripts/{s}", 600)
    n_files, hit = worker_gate(pr, WT)
    if hit is None and n_files is None:
        out.write("\n===== worker-build\nchanged-files fetch failed; failing closed\n")
        fails.append("worker-build: changed-files fetch failed")
    elif hit is not None:
        out.write(f"\n===== worker-build\ngate hit: {hit[0]} <- {hit[1]}\n")
        worker_build(WT, step)
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
    if not dry: status(sha, "pending", "local-ci running on Chris's Mac")
    t0 = time.time()
    with open(logf, "w") as out:
        ok_wt, why = prepare_wt(n, sha, pr["baseRefName"], out)
        fails = run_checks(pr, out) if ok_wt else [f"worktree checkout ({why})"]
    mins = (time.time() - t0) / 60
    if fails: st, desc = "failure", f"local-ci failed: {', '.join(fails)} ({mins:.0f}m)"
    else: st, desc = "success", f"{GATED_NOTE} ({mins:.0f}m)"
    log(f"PR #{n} {sha[:12]} {st}: {desc} log={logf}")
    if not dry: status(sha, st, desc)
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

def ci_status(sha):
    """Latest (state, description) posted under CTX, or (None, None)."""
    o = gh("api", f"repos/{REPO}/commits/{sha}/statuses", "--paginate")
    try: rows = json.loads(o or "[]")
    except ValueError: return None, None
    rows = [r for r in rows if isinstance(r, dict) and r.get("context") == CTX]
    if not rows: return None, None
    rows.sort(key=lambda r: r.get("createdAt", r.get("created_at", "")))
    return rows[-1].get("state"), rows[-1].get("description") or ""

def pending(prs, forks):
    """Open PRs still needing a check, newest first: no `local-ci` status yet, or only a
    re-checkable skip (DIG-3706: a `local-ci skipped:` failure re-queues once the gate clears)."""
    out = []
    for p in prs:
        if bool(p["isCrossRepository"]) == forks:
            st, desc = ci_status(p["headRefOid"])
            # A gitleaks-only failure is re-queued once. The shallow clone was
            # scanning commits already on the base. A second failure stays put.
            retry = (st == "failure" and (desc or "").startswith("local-ci failed: gitleaks")
                     and not os.path.exists(f"{LOGD}/gitleaks-recheck-{p['headRefOid']}"))
            if st is None or (desc or "").startswith(SKIP_PREFIX) or retry:
                out.append(p)
    out.sort(key=lambda p: p["updatedAt"], reverse=True)
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

def acquire_lock():
    """Take the tick lock. A lock whose holder is dead is taken over and logged, never waited on."""
    try:
        os.mkdir(LOCK)
    except FileExistsError:
        pid = lock_holder_alive()
        try: age = time.time() - os.path.getmtime(LOCK)
        except OSError: age = -1
        if pid is not None and age >= 0 and age < 7200:
            log(f"lock busy (pid {pid}, age {age:.0f}s); skip tick")
            return False
        log(f"stale lock removed (pid {pid}, age {age:.0f}s)")
        shutil.rmtree(LOCK, ignore_errors=True)
        try: os.mkdir(LOCK)
        except FileExistsError: return False
    try:
        with open(os.path.join(LOCK, "pid"), "w") as f: f.write(str(os.getpid()))
    except OSError: pass
    return True

def release_lock():
    """Release only a lock this process holds; never sweep another holder's."""
    try:
        with open(os.path.join(LOCK, "pid")) as f: mine = f.read().strip() == str(os.getpid())
    except (OSError, ValueError): mine = False
    if mine: shutil.rmtree(LOCK, ignore_errors=True)

def list_prs(base):
    o = gh("pr", "list", "-R", REPO, "--base", base, "--state", "open", "--limit", "200",
           "--json", "number,headRefOid,headRefName,baseRefName,title,isCrossRepository,updatedAt")
    try: return json.loads(o or "[]")
    except ValueError: return []


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
    fix commits may have landed since)."""
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
    out.sort(key=lambda p: p["updatedAt"], reverse=True)
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
    ok, msg, open_ids = review_applied.evaluate(passes, threads, fix_ats, check_runs, reviewers)
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
        ok, msg = run_applied(pr, out)
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


def _write_child_state(pid, name, budget):
    """Record the running child so the next tick can spot a step that overran its budget."""
    tmp = CHILD_STATE + ".tmp"
    try:
        os.makedirs(os.path.dirname(CHILD_STATE), exist_ok=True)
        with open(tmp, "w") as f:
            json.dump({"pid": int(pid), "name": str(name)[:120], "started": time.time(),
                       "budget": int(budget)}, f)
        os.replace(tmp, CHILD_STATE)
    except (OSError, ValueError):
        pass


def _clear_child_state():
    try:
        os.unlink(CHILD_STATE)
    except OSError:
        pass


def read_child_state():
    try:
        with open(CHILD_STATE) as f:
            st = json.load(f)
        return st if isinstance(st, dict) else None
    except (OSError, ValueError):
        return None


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
    """
    holder = lock_holder_alive()
    if holder is None:
        _clear_child_state()
        return False
    st = read_child_state()
    if not st:
        return False
    try:
        started = float(st.get("started") or 0)
        budget = float(st.get("budget") or 0)
        child = int(st.get("pid") or 0)
    except (TypeError, ValueError):
        _clear_child_state()
        return False
    if child <= 0:
        _clear_child_state()
        return False
    age_recorded = time.time() - started
    age_os = _ps_etime(child)
    if age_os is None:
        # the step leader is gone; only its process group can still leak
        members = [(p, c) for p, c in _group_members(child)
                   if any(m in c for m in GATE_CMD_MARKERS)]
        if not members:
            _clear_child_state()
            return False
        if age_recorded <= budget + WATCHDOG_GRACE_SECS:
            return False
        log(f"watchdog: tick {holder} group {child} ({st.get('name')}) age {age_recorded:.0f}s over budget {budget:.0f}s; killing {len(members)} leaked process(es)")
        for p, _c in members:
            kill_tree(p)
        _clear_child_state()
        return True
    if abs(age_recorded - age_os) > WATCHDOG_PID_REUSE_TOLERANCE:
        # the pid is no longer the process we spawned: stale state, not an overrun
        _clear_child_state()
        return False
    if age_os <= budget + WATCHDOG_GRACE_SECS:
        return False
    log(f"watchdog: tick {holder} child {child} ({st.get('name')}) age {age_os:.0f}s over budget {budget:.0f}s; killing child tree")
    kill_tree(child)
    _kill_group(child)
    _clear_child_state()
    return True

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


def main():
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
        prs = list_prs("develop")
        main_prs = list_prs("main")
        if only is not None:
            for p in [p for p in prs if not p["isCrossRepository"] and p["number"] == only]:
                process(p, dry)
                process_applied(p, dry)
            for p in [p for p in main_prs if not p["isCrossRepository"] and p["number"] == only]:
                if is_promotion_pr(p):
                    process_review(p, dry)
            return
        reason = skip_reason()
        if reason is not None:
            log(f"skip: {reason}")
            if not dry:
                for p in pending(prs, False)[:MAX_PER_TICK]:
                    status(p["headRefOid"], "failure", f"local-ci skipped: {reason}")
                for p in pending(prs, True)[:MAX_PER_TICK]:
                    status(p["headRefOid"], "failure", FORK_DESC)
                for p in pending_applied(prs)[:MAX_PER_TICK]:
                    applied_status(p["headRefOid"], "failure", f"local-ci skipped: {reason}")
                for p in pending_reviews(main_prs)[:REVIEW_MAX_PER_TICK]:
                    review_status(p["headRefOid"], "failure", f"local-ci skipped: {reason}")
            return
        if not dry:
            for p in pending(prs, True)[:MAX_PER_TICK]:
                status(p["headRefOid"], "failure", FORK_DESC)
        done = 0
        for p in pending(prs, False):
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
    finally:
        release_lock()

if __name__ == "__main__":
    main()
