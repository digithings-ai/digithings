#!/usr/bin/env python3
"""Unit tests for the digiquant host runner (DIG-2915).

Stdlib only: ``/usr/bin/python3 -m unittest test_digiquant_host_runner -v``.

The suite pins the two things that would break production silently:

* the launchd clock table against ``apps/digithings-cron/src/jobs.ts``, because a
  moved Worker clock that leaves an old Mac clock behind looks exactly like a healthy
  job;
* the step plan against the container's ``exec_job``, because a job that resolves one
  way in the image and another on the Mac is two different jobs wearing one name.

The rest is the plumbing the container got from its platform: the lock that stops two
clocks sharing one job, the env file that is refused when it is not private, the
record every run leaves, and the installer's refusal to load a job by itself.

No test loads, unloads or edits a launchd job and no test writes under
``~/Library/LaunchAgents``.
"""

import fcntl
import importlib.util
import io
import json
import os
import plistlib
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

try:  # the marker puts this file in the CI lane; a plain unittest run does not need it
    import pytest

    pytestmark = pytest.mark.unit
except ImportError:  # pragma: no cover - pytest is not installed in a stdlib-only run
    pass

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[1]
_DIR = _ROOT / "scripts" / "digiquant-host-runner"
_RUN_JOB = _DIR / "run_job.py"
_SCHEDULE = _DIR / "schedule.py"
_INSTALL = _DIR / "install.sh"
_DOC = _ROOT / "docs" / "ops" / "digiquant-host-runner.md"
_JOBS_TS = _ROOT / "apps" / "digithings-cron" / "src" / "jobs.ts"
_EXEC_JOB = _ROOT / "apps" / "digiquant-runner" / "container" / "exec_job.py"
_COMMANDS = _ROOT / "apps" / "digiquant-runner" / "commands.json"

for path, name in ((_DIR, "digiquant_host_runner"), (_DIR, "digiquant_host_schedule")):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

_runner_spec = importlib.util.spec_from_file_location("digiquant_host_runner", _RUN_JOB)
runner = importlib.util.module_from_spec(_runner_spec)
sys.modules["digiquant_host_runner"] = runner
_runner_spec.loader.exec_module(runner)

_schedule_spec = importlib.util.spec_from_file_location("digiquant_host_schedule", _SCHEDULE)
schedule = importlib.util.module_from_spec(_schedule_spec)
sys.modules["digiquant_host_schedule"] = schedule
_schedule_spec.loader.exec_module(schedule)

_exec_spec = importlib.util.spec_from_file_location("digiquant_container_exec_job", _EXEC_JOB)
exec_job = importlib.util.module_from_spec(_exec_spec)
sys.modules["digiquant_container_exec_job"] = exec_job
_exec_spec.loader.exec_module(exec_job)

# cj(id, cron, workflow, command, concurrency, timeout[, {opts}]). The opts object has
# no parentheses in this file; a comment inside a cj call would fail the parse loudly
# rather than match the wrong row.
_CJ = re.compile(
    # The workflow argument is `undefined` once its GHA fallback file is deleted.
    r'cj\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*(?:"[^"]+"|undefined)\s*,\s*"([^"]+)"\s*,'
    r'\s*"[^"]+"\s*,\s*\d+\s*(?:,\s*(\{[^()]*\}))?\s*,?\s*\)',
    re.S,
)


def _jobs_ts_container_rows():
    source = _JOBS_TS.read_text(encoding="utf-8")
    rows = []
    for match in _CJ.finditer(source):
        label, cron, command, opts = match.group(1), match.group(2), match.group(3), match.group(4) or ""
        if "enabled: false" in opts:
            continue
        rows.append((label, cron, command))
    return rows


def _can_signal_children():
    """True when this host lets the runner signal a child process group.

    The seat sandbox denies every signal (EPERM), so the deadline test is skipped
    there instead of pretending the killing path was exercised.
    """
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"], start_new_session=True)
    try:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            return True
        except OSError:
            return False
    finally:
        try:
            proc.kill()
        except OSError:
            pass
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:  # pragma: no cover - defensive
            pass


class CatalogAndScheduleTest(unittest.TestCase):
    def test_every_clock_names_a_real_catalogue_job(self):
        catalog = runner.load_catalog(_COMMANDS)
        for row in schedule.ROWS:
            with self.subTest(label=row.label):
                self.assertIn(row.job, catalog)

    def test_clock_table_matches_the_worker_source_of_truth(self):
        expected = _jobs_ts_container_rows()
        actual = [(row.label, row.cron, row.job) for row in schedule.ROWS]
        self.assertEqual(sorted(expected), sorted(actual), "a container clock moved: update schedule.ROWS")

    def test_parser_found_the_container_rows(self):
        # Guards the guard: a regex that matched nothing would make the test above pass.
        self.assertGreaterEqual(len(_jobs_ts_container_rows()), 10)

    def test_labels_are_unique_and_prefixed(self):
        labels = [schedule.label_for(row) for row in schedule.ROWS]
        self.assertEqual(len(labels), len(set(labels)))
        for label in labels:
            self.assertTrue(label.startswith(schedule.LABEL_PREFIX))

    def test_every_job_shares_the_container_concurrency_key(self):
        catalog = runner.load_catalog(_COMMANDS)
        for row in schedule.ROWS:
            with self.subTest(label=row.label):
                self.assertTrue(catalog[row.job].get("concurrency"))


class CronTest(unittest.TestCase):
    def test_daily_cron_expands_to_one_interval(self):
        self.assertEqual(schedule.parse_cron("0 13 * * *"), [{"Hour": 13, "Minute": 0}])

    def test_weekday_range_and_hour_step(self):
        intervals = schedule.parse_cron("19 */2 * * MON-FRI")
        self.assertEqual(len(intervals), 12 * 5)
        self.assertEqual({item["Weekday"] for item in intervals}, {1, 2, 3, 4, 5})
        self.assertEqual({item["Hour"] for item in intervals}, set(range(0, 24, 2)))

    def test_single_weekday(self):
        self.assertEqual(schedule.parse_cron("19 22 * * SUN"), [{"Hour": 22, "Minute": 19, "Weekday": 0}])

    def test_unsupported_forms_raise_instead_of_moving_a_clock(self):
        for expr in ("0 13 1 * *", "0 13 * 1 *", "0 13 * * MON-SUN", "0 13 * * FUNDAY", "bad"):
            with self.subTest(expr=expr):
                with self.assertRaises(schedule.CronError):
                    schedule.parse_cron(expr)

    def test_local_conversion_follows_the_host_zone(self):
        now = schedule.datetime(2026, 1, 5, 0, 0, tzinfo=schedule.timezone.utc)
        original = os.environ.get("TZ")

        def convert(tz):
            os.environ["TZ"] = tz
            time.tzset()
            try:
                return schedule.local_intervals("0 13 * * *", now)
            finally:
                if original is None:
                    os.environ.pop("TZ", None)
                else:
                    os.environ["TZ"] = original
                time.tzset()

        self.assertEqual(convert("UTC"), [{"Hour": 13, "Minute": 0}])
        self.assertEqual(convert("Asia/Tokyo"), [{"Hour": 22, "Minute": 0}])
        self.assertEqual(convert("America/New_York"), [{"Hour": 8, "Minute": 0}])

    def test_weekday_moves_when_local_time_crosses_midnight(self):
        now = schedule.datetime(2026, 1, 5, 0, 0, tzinfo=schedule.timezone.utc)
        original = os.environ.get("TZ")
        os.environ["TZ"] = "Asia/Tokyo"
        time.tzset()
        try:
            # 22:19 UTC Sunday is 07:19 Monday in Tokyo.
            intervals = schedule.local_intervals("19 22 * * SUN", now)
        finally:
            if original is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = original
            time.tzset()
        self.assertEqual(intervals, [{"Weekday": 1, "Hour": 7, "Minute": 19}])


class RenderTest(unittest.TestCase):
    def setUp(self):
        self.now = schedule.datetime(2026, 3, 2, 0, 0, tzinfo=schedule.timezone.utc)
        self.row = schedule.Row("prices-at-open-13", "prices-at-open", "40 13 * * MON-FRI")

    def render(self, **kwargs):
        return schedule.render_plist(
            self.row,
            checkout=Path("/tmp/checkout"),
            env_file="~/.config/digithings/digiquant-host-runner.env",
            now=self.now,
            **kwargs,
        )

    def test_rendered_plist_parses_and_carries_the_clock(self):
        payload = plistlib.loads(self.render().encode("utf-8"))
        self.assertEqual(payload["Label"], "com.digithings.digiquant.prices-at-open-13")
        self.assertEqual(payload["RunAtLoad"], False)
        self.assertFalse(payload["StartCalendarInterval"] == [])
        argv = payload["ProgramArguments"]
        self.assertEqual(argv[0], schedule.UV)
        self.assertIn("/scripts/digiquant-host-runner/run_job.py", argv[6])
        self.assertEqual(argv[7], "prices-at-open")
        self.assertEqual(argv[8], "--env-file")
        self.assertEqual(argv[9], os.path.expanduser("~/.config/digithings/digiquant-host-runner.env"))
        self.assertEqual(argv[10], "--json")

    def test_plist_holds_no_secret_and_no_placeholder(self):
        text = self.render()
        self.assertNotIn("__", text)
        payload = plistlib.loads(text.encode("utf-8"))
        self.assertIn("/opt/homebrew/bin", payload["EnvironmentVariables"]["PATH"])
        for key in payload["EnvironmentVariables"]:
            self.assertIn(key, {"PATH", "HOME", "LANG", "DIGIQUANT_HOST_RUNNER"})

    def test_render_is_stable_so_status_can_spot_a_stale_clock(self):
        self.assertEqual(self.render(), self.render())

    def test_unknown_job_in_catalogue_is_not_a_render_error(self):
        # The installer renders every clock; a catalogue gap is caught by the tests
        # above, not at install time on Chris's Mac.
        catalog = runner.load_catalog(_COMMANDS)
        self.assertTrue(all(row.job in catalog for row in schedule.ROWS))


class PlanTest(unittest.TestCase):
    def test_image_paths_are_rewritten_to_the_checkout(self):
        argv = ["uv", "run", "python", "/opt/runner/wake_stack.py", "--x"]
        out = runner.rewrite_argv(argv)
        self.assertEqual(out[:3], argv[:3])
        self.assertTrue(out[3].endswith("/apps/digiquant-runner/container/wake_stack.py"))
        self.assertTrue(os.path.isabs(out[3]))
        self.assertEqual(out[4], "--x")

    def test_host_plan_matches_the_container_plan_except_image_paths(self):
        catalog = runner.load_catalog(_COMMANDS)
        container = exec_job.plans_for("house-run", {}, catalog, workdir=_ROOT)
        host = runner.host_plans(exec_job, "house-run", {}, catalog=catalog)
        self.assertEqual(len(container), len(host))
        for before, after in zip(container, host):
            self.assertEqual(after.continue_on_error, before.continue_on_error)
            self.assertEqual(after.always, before.always)
            self.assertEqual(after.step_timeout_seconds, before.step_timeout_seconds)
            self.assertEqual(
                [part for part in after.argv if not part.startswith(str(runner.CONTAINER_DIR))],
                [part for part in before.argv if not part.startswith("/opt/runner/")],
            )

    def test_gated_steps_still_gate(self):
        catalog = runner.load_catalog(_COMMANDS)
        without = runner.host_plans(exec_job, "prices-eod-macro", {}, catalog=catalog)
        with_writers = runner.host_plans(exec_job, "prices-eod-macro", {"run_writers": "true"}, catalog=catalog)
        self.assertEqual(len(without), 1)
        self.assertEqual(len(with_writers), 2)

    def test_unknown_job_is_a_config_error(self):
        with self.assertRaises(runner.ConfigError):
            runner.host_plans(exec_job, "no-such-job", {}, catalog=runner.load_catalog(_COMMANDS))


class EnvFileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.path = self.tmp / "runner.env"

    def test_parses_comments_quotes_and_export(self):
        self.path.write_text(
            "# comment\nCORE_SUPABASE_URL=https://x\n"
            "export R2_BUCKET='bucket'\n\nDIGI_OTEL_HEADERS=\"a=b\"\n",
            encoding="utf-8",
        )
        environ = runner.parse_env_file(self.path)
        self.assertEqual(environ["CORE_SUPABASE_URL"], "https://x")
        self.assertEqual(environ["R2_BUCKET"], "bucket")
        self.assertEqual(environ["DIGI_OTEL_HEADERS"], "a=b")

    def test_a_typo_is_refused_not_dropped(self):
        self.path.write_text("CORE_SUPABASE_URL https://x\n", encoding="utf-8")
        with self.assertRaises(runner.ConfigError):
            runner.parse_env_file(self.path)

    def test_mode_with_group_or_other_bits_is_refused(self):
        self.path.write_text("A=1\n", encoding="utf-8")
        self.path.chmod(0o644)
        with self.assertRaises(runner.ConfigError):
            runner.check_env_file(self.path)
        self.path.chmod(0o600)
        self.assertEqual(runner.check_env_file(self.path), {"A": "1"})

    def test_missing_file_is_named(self):
        with self.assertRaises(runner.ConfigError):
            runner.check_env_file(self.tmp / "absent.env")

    def test_no_value_is_printed_by_dry_run(self):
        result = subprocess.run(
            [sys.executable, str(_RUN_JOB), "house-run", "--dry-run"],
            cwd=str(_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("env names:", result.stdout)
        # A name is printed, a value never is.
        self.assertNotIn("=", result.stdout.split("env names:")[1].splitlines()[0])


class ExecuteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.catalog = {
            "demo": {
                "timeout_seconds": 60,
                "concurrency": "demo-lock",
                "env": [],
                "steps": [[sys.executable, "-c", "print('hello')"]],
            }
        }

    def run_job(self, job="demo", **kwargs):
        return runner.execute(
            job,
            kwargs.pop("args", {}),
            environ={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(Path.home())},
            state_dir=self.tmp / "state",
            log_dir=self.tmp / "logs",
            out=io.StringIO(),
            catalog=self.catalog,
            exec_job=exec_job,
            run_id="20260101120000",
            **kwargs,
        )

    def test_success_writes_a_record_and_a_log(self):
        record = self.run_job()
        self.assertEqual(record["status"], "succeeded")
        self.assertEqual(record["exit_code"], 0)
        self.assertEqual(len(record["steps"]), 1)
        stored = json.loads((self.tmp / "state" / "demo.json").read_text(encoding="utf-8"))
        self.assertEqual(stored["status"], "succeeded")
        log = Path(record["log"]).read_text(encoding="utf-8")
        self.assertIn("hello", log)
        self.assertTrue((self.tmp / "state" / "history.jsonl").is_file())

    def test_non_zero_step_fails_the_run_with_its_code(self):
        self.catalog["demo"]["steps"] = [[sys.executable, "-c", "raise SystemExit(3)"]]
        record = self.run_job()
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["exit_code"], 3)

    def test_continue_on_error_does_not_fail_the_run(self):
        self.catalog["demo"]["steps"] = [
            {"argv": [sys.executable, "-c", "raise SystemExit(4)"], "continue_on_error": True},
            [sys.executable, "-c", "print('after')"],
        ]
        record = self.run_job()
        self.assertEqual(record["status"], "succeeded")
        self.assertEqual(record["steps"][0]["exit_code"], 4)
        self.assertEqual(len(record["steps"]), 2)

    def test_always_step_runs_after_a_hard_failure(self):
        self.catalog["demo"]["steps"] = [
            [sys.executable, "-c", "raise SystemExit(5)"],
            {"argv": [sys.executable, "-c", "print('always')"], "always": True},
        ]
        record = self.run_job()
        self.assertEqual(record["status"], "failed")
        self.assertEqual(len(record["steps"]), 2)
        self.assertIn("always", Path(record["log"]).read_text(encoding="utf-8"))

    def test_a_held_lock_skips_instead_of_racing(self):
        lock_path = self.tmp / "state" / "locks" / "demo-lock.lock"
        lock_path.parent.mkdir(parents=True)
        handle = lock_path.open("a+")
        self.addCleanup(handle.close)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        record = self.run_job()
        self.assertEqual(record["status"], "skipped")
        self.assertEqual(record["reason"], "already_running")
        self.assertEqual(record["exit_code"], 0)
        self.assertEqual(record["steps"], [])

    def test_missing_env_is_recorded_not_fatal(self):
        self.catalog["demo"]["env"] = ["NOT_SET_ANYWHERE"]
        record = self.run_job()
        self.assertEqual(record["status"], "succeeded")
        self.assertIn("NOT_SET_ANYWHERE", record["missing_env"])

    def test_require_env_fails_before_any_step(self):
        with self.assertRaises(runner.ConfigError):
            self.run_job(require_env=("NOT_SET_ANYWHERE",))
        self.assertFalse((self.tmp / "logs").exists() and any((self.tmp / "logs").iterdir()))

    def test_publish_is_skipped_by_default_and_says_so(self):
        self.catalog["demo"]["publish"] = ["/tmp/never.json"]
        record = self.run_job()
        self.assertEqual(record["status"], "succeeded")
        self.assertIn("skipped", record["publish"])

    def test_a_step_over_its_limit_is_stopped_and_timed_out(self):
        if not _can_signal_children():
            self.skipTest("this host refuses to signal a child process group (seat sandbox)")
        self.catalog["demo"]["steps"] = [
            {"argv": [sys.executable, "-c", "import time; time.sleep(30)"], "step_timeout_seconds": 1}
        ]
        started = time.monotonic()
        record = self.run_job()
        self.assertLess(time.monotonic() - started, 20)
        self.assertEqual(record["status"], "timed_out")
        self.assertEqual(record["exit_code"], 124)


class InstallerTest(unittest.TestCase):
    """The installer is macOS-only: launchd, plutil and /opt/homebrew/bin/uv."""

    def test_list_needs_no_env_file_and_names_every_clock(self):
        result = subprocess.run(
            ["/bin/sh", str(_INSTALL), "--list"],
            cwd=str(_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout.strip().splitlines()), len(schedule.ROWS))

    @unittest.skipUnless(shutil.which("plutil"), "install.sh needs plutil (macOS)")
    def test_dry_run_renders_lintable_plists_without_touching_launchd(self):
        with tempfile.TemporaryDirectory() as home:
            env = dict(os.environ, HOME=home)
            result = subprocess.run(
                ["/bin/sh", str(_INSTALL), "--dry-run"],
                cwd=str(_ROOT),
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            for label in (schedule.label_for(row) for row in schedule.ROWS):
                self.assertIn(f"### {label}", result.stdout)
            self.assertFalse((Path(home) / "Library" / "LaunchAgents").exists())

    @unittest.skipUnless(shutil.which("plutil"), "install.sh needs plutil (macOS)")
    def test_no_flag_changes_nothing(self):
        result = subprocess.run(
            ["/bin/sh", str(_INSTALL)],
            cwd=str(_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("nothing changed", result.stderr)

    @unittest.skipUnless(shutil.which("plutil"), "install.sh needs plutil (macOS)")
    def test_install_refuses_without_an_env_file(self):
        with tempfile.TemporaryDirectory() as home:
            env = dict(os.environ, HOME=home)
            result = subprocess.run(
                ["/bin/sh", str(_INSTALL), "--install", "--allow-worktree", "--allow-branch", str(_ROOT)],
                cwd=str(_ROOT),
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("no env file", result.stderr)
            self.assertFalse((Path(home) / "Library" / "LaunchAgents").exists())

    @unittest.skipUnless(shutil.which("plutil"), "install.sh needs plutil (macOS)")
    def test_install_refuses_a_checkout_without_the_image_environment(self):
        # The plans call `uv run --frozen --no-sync`, so a checkout whose .venv was
        # never built, or was built with a plain `uv sync`, fails every job at its
        # first step. The installer must refuse instead of writing 13 broken clocks.
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as checkout:
            git = ["git", "-C", checkout]
            subprocess.run([*git, "init", "-q", "-b", "develop"], check=True)
            subprocess.run(
                [*git, "-c", "user.email=t@example.com", "-c", "user.name=t",
                 "commit", "-q", "--allow-empty", "-m", "checkout"],
                check=True,
            )
            script = Path(checkout, "scripts", "digiquant-host-runner", "run_job.py")
            script.parent.mkdir(parents=True)
            script.write_text("# placeholder\n", encoding="utf-8")
            env_file = Path(home) / "runner.env"
            env_file.write_text("A=1\n", encoding="utf-8")
            env_file.chmod(0o600)
            result = subprocess.run(
                ["/bin/sh", str(_INSTALL), "--install", checkout],
                cwd=str(_ROOT),
                capture_output=True,
                text=True,
                check=False,
                env=dict(os.environ, HOME=home, DIGIQUANT_HOST_RUNNER_ENV=str(env_file)),
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn(".venv is missing or incomplete", result.stderr)
            self.assertFalse((Path(home) / "Library" / "LaunchAgents").exists())

    @unittest.skipUnless(shutil.which("plutil"), "install.sh needs plutil (macOS)")
    def test_install_refuses_a_linked_worktree(self):
        # A checkout whose `.git` is a file is a linked worktree, and the clocks must
        # not run from one: the branch it names is deleted eventually. The guard is
        # checked before the checkout is read, so an empty tree is enough to prove it.
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as checkout:
            Path(checkout, ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
            env_file = Path(home) / "runner.env"
            env_file.write_text("A=1\n", encoding="utf-8")
            env_file.chmod(0o600)
            result = subprocess.run(
                ["/bin/sh", str(_INSTALL), "--install", checkout],
                cwd=str(_ROOT),
                capture_output=True,
                text=True,
                check=False,
                env=dict(os.environ, HOME=home, DIGIQUANT_HOST_RUNNER_ENV=str(env_file)),
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("worktree", result.stderr)
            self.assertFalse((Path(home) / "Library" / "LaunchAgents").exists())


class DocsTest(unittest.TestCase):
    def test_the_doc_names_the_files_it_describes(self):
        text = _DOC.read_text(encoding="utf-8")
        for name in ("run_job.py", "schedule.py", "install.sh", "digiquant-host-runner.env"):
            self.assertIn(name, text)

    def test_the_doc_does_not_claim_the_container_is_gone(self):
        text = _DOC.read_text(encoding="utf-8")
        self.assertIn("Not true yet", text)
        self.assertIn("still dispatches to the container", text)

    def test_the_doc_gives_the_environment_the_clocks_actually_need(self):
        # A plain `uv sync --frozen` leaves the root workspace's .venv empty, and the
        # plans run with --no-sync. The doc must name the sync the image uses and say
        # that nothing installs at run time.
        text = _DOC.read_text(encoding="utf-8")
        self.assertIn("--no-sync", text)
        self.assertIn("--package digiquant --extra prices --extra research --extra nautilus", text)
        self.assertIn("--package digigraph --extra checkpoint-postgres", text)


if __name__ == "__main__":
    unittest.main()
