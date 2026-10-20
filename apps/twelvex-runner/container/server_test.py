"""Unit tests for the container entrypoint. No twelve-x install and no network."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


def load_server():
    path = Path(__file__).with_name("server.py")
    spec = importlib.util.spec_from_file_location("twelvex_server", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


server = load_server()


class CommandTests(unittest.TestCase):
    def test_ingest_argv_matches_the_workflow(self):
        self.assertEqual(
            server.command_for("ingest", "intraday"),
            ["python", "-m", "twelve_x.scripts.ingest_market_context", "intraday"],
        )

    def test_heartbeat_argv_matches_the_workflow(self):
        self.assertEqual(
            server.command_for("heartbeat", None),
            ["python", "-m", "twelve_x.scripts.primemarket_session_heartbeat"],
        )

    def test_unknown_bucket_is_rejected(self):
        with self.assertRaises(ValueError):
            server.command_for("ingest", "hourly")

    def test_session_argv_matches_the_workflow(self):
        self.assertEqual(
            server.command_for("session", None, "asia"),
            ["python", "-m", "twelve_x.graph"],
        )

    def test_unknown_session_is_rejected(self):
        with self.assertRaises(ValueError):
            server.command_for("session", None, "hourly")

    def test_session_runs_the_calendar_first_and_the_graph_fatal(self):
        steps = server.steps_for("session", None, "london")
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0][0], ["python", "-m", "twelve_x.scripts.ingest_calendar"])
        self.assertFalse(steps[0][2])
        self.assertEqual(steps[1][0], ["python", "-m", "twelve_x.graph"])
        self.assertTrue(steps[1][2])
        self.assertEqual(steps[1][1]["FX_SESSION"], "london")
        self.assertEqual(steps[1][1]["TRADE_INTELLIGENCE_MODE"], "alongside")
        # The graph step always carries RUN_DATE, empty for the forward path,
        # and the calendar step never carries one.
        self.assertEqual(steps[1][1]["RUN_DATE"], "")
        self.assertNotIn("RUN_DATE", steps[0][1])

    def test_a_valid_run_date_reaches_the_graph_step_only(self):
        steps = server.steps_for("session", None, "asia", "2026-10-01")
        self.assertNotIn("RUN_DATE", steps[0][1])
        self.assertEqual(steps[1][1]["RUN_DATE"], "2026-10-01")

    def test_an_empty_run_date_is_absent(self):
        self.assertIsNone(server.validate_run_date(None))
        self.assertIsNone(server.validate_run_date(""))
        self.assertIsNone(server.validate_run_date("  "))

    def test_a_valid_run_date_is_kept_as_written(self):
        self.assertEqual(server.validate_run_date("2026-10-01"), "2026-10-01")
        self.assertEqual(server.validate_run_date("2024-02-29"), "2024-02-29")

    def test_a_malformed_run_date_is_rejected(self):
        for value in ["2026-13-01", "2026-02-30", "20261020", "01-10-2026", 7]:
            with self.assertRaises(ValueError):
                server.validate_run_date(value)

    def test_a_failed_calendar_step_does_not_fail_the_run(self):
        steps = [
            ([sys.executable, "-c", "raise SystemExit(3)"], {}, False),
            ([sys.executable, "-c", "print('graph ok')"], {}, True),
        ]
        payload = server.run_steps(steps, timeout=30, dry_run=False)
        self.assertEqual(payload["exit_code"], 0)
        self.assertTrue(payload["ok"])
        self.assertIn("graph ok", payload["log_tail"])

    def test_a_failing_fatal_step_stops_the_run(self):
        steps = [
            ([sys.executable, "-c", "print('first')"], {}, True),
            ([sys.executable, "-c", "print('second')"], {}, True),
        ]
        payload = server.run_steps(
            [
                (steps[0][0], {}, True),
                ([sys.executable, "-c", "raise SystemExit(2)"], {}, True),
            ],
            timeout=30,
            dry_run=False,
        )
        self.assertEqual(payload["exit_code"], 2)
        self.assertFalse(payload["ok"])
        self.assertNotIn("second", payload["log_tail"])

    def test_dry_run_does_not_need_a_process(self):
        payload = server.run_command(
            ["python", "-m", "twelve_x.scripts.ingest_market_context", "daily"],
            timeout=5,
            dry_run=True,
        )
        self.assertEqual(payload["exit_code"], 0)
        self.assertTrue(payload["dry_run"])
        self.assertIn("ingest_market_context", payload["log_tail"])
        self.assertNotIn("SECRET", payload["log_tail"])

    def test_redact_strips_bearer_and_assignments(self):
        raw = (
            "Authorization: Bearer abc.def.ghi token=supersecret "
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.dozjgNryP4J3jVmNHl0w5N"
        )
        cleaned = server.redact(raw)
        self.assertNotIn("abc.def.ghi", cleaned)
        self.assertNotIn("supersecret", cleaned)
        self.assertIn("[redacted]", cleaned)

    def test_env_dry_run_flag(self):
        self.assertTrue(server.dry_run_requested({}, {"DRY_RUN": "1"}))
        self.assertFalse(server.dry_run_requested({}, {"DRY_RUN": "0"}))
        self.assertTrue(server.dry_run_requested({"dry_run": True}, {"DRY_RUN": "0"}))


HEARTBEAT_MODULE = "twelve_x.scripts.primemarket_session_heartbeat"
# The modules of the pinned twelve-x ref that the runner runs. A module path
# anywhere in the app that is not on this list is a typo or a drifted copy.
ALLOWED_MODULES = {
    "twelve_x.graph",
    "twelve_x.scripts.ingest_calendar",
    "twelve_x.scripts.ingest_market_context",
    HEARTBEAT_MODULE,
}
MODULE_PATH = re.compile(r"twelve_x(?:\.[A-Za-z_][A-Za-z0-9_]*)+")
# A copy of an argv in code: "python", "-m", "twelve_x...
# Both quote styles count. A single-quoted copy is the same second source of
# truth as a double-quoted one, so the scan must not only look for one of them.
ARGV_COPY = re.compile(r"['\"]?python['\"]?\s*,\s*['\"]?-m['\"]?\s*,\s*['\"]?twelve_x")
SKIP_DIRS = {"node_modules", ".wrangler", "dist", "build", "__pycache__", ".git"}


class OneCommandSourceTests(unittest.TestCase):
    """The argv lives in container/server.py and nowhere else.

    A second copy of a command would drift from the pinned twelve-x ref
    without any run failing, so the app keeps one source of truth. The scan
    covers the whole app, not only the two folders that hold code today.
    """

    def setUp(self):
        self.app = Path(__file__).resolve().parent.parent
        self.files = [
            path
            for path in self.app.rglob("*")
            if path.is_file()
            and not SKIP_DIRS & set(path.relative_to(self.app).parts)
            and not path.name.endswith((".test.ts", "_test.py"))
            and not path.name.startswith("test_")
        ]

    def test_the_heartbeat_module_path_is_pinned_here(self):
        self.assertIn(f'"{HEARTBEAT_MODULE}"', (self.app / "container" / "server.py").read_text())

    def test_only_the_container_carries_a_command_argv(self):
        holders = [
            str(path.relative_to(self.app))
            for path in self.files
            if ARGV_COPY.search(path.read_text())
        ]
        self.assertEqual(holders, [os.path.join("container", "server.py")])

    def test_every_module_path_in_the_app_is_a_module_of_the_pinned_ref(self):
        for path in self.files:
            for module in MODULE_PATH.findall(path.read_text()):
                self.assertIn(module, ALLOWED_MODULES, f"{path}: {module}")

    def test_no_typo_of_the_heartbeat_module_name(self):
        for path in self.files:
            self.assertNotIn("primarketet_session_heartbeat", path.read_text(), str(path))

    def test_the_routing_module_carries_no_command_mirror(self):
        routes = (self.app / "src" / "routes.ts").read_text()
        self.assertNotIn("twelve_x", routes)
        self.assertNotIn("python", routes)

    def test_the_guard_catches_a_copy_in_either_quote_style(self):
        for copy in (
            'const cmd = ["python", "-m", "twelve_x.graph"];',
            "const cmd = ['python', '-m', 'twelve_x.graph'];",
            'cmd = ["python", "-m", "twelve_x.scripts.ingest_calendar"]',
            "cmd = ['python', '-m', 'twelve_x.scripts.ingest_market_context']",
        ):
            self.assertTrue(ARGV_COPY.search(copy), copy)

    def test_the_guard_does_not_flag_a_mention_of_python(self):
        for text in ("const python = 1;", "twelve_x.graph is the graph module"):
            self.assertFalse(ARGV_COPY.search(text), text)


class RunDateTests(unittest.TestCase):
    """The run_date rules the Worker and the container share."""

    def test_a_calendar_date_is_kept_as_written(self):
        self.assertEqual(server.validate_run_date("2026-10-01"), "2026-10-01")

    def test_an_absent_or_empty_run_date_is_absent(self):
        self.assertIsNone(server.validate_run_date(None))
        self.assertIsNone(server.validate_run_date(""))

    def test_a_malformed_run_date_is_rejected(self):
        for value in ["2026-13-01", "2026-02-30", "20261020", "01-10-2026", "2026-10-01T00:00:00Z", 7]:
            with self.assertRaises(ValueError):
                server.validate_run_date(value)

    def test_a_year_the_graph_cannot_parse_is_rejected(self):
        # Python's date.fromisoformat has no year 0, and so the Worker must
        # not accept one either.
        with self.assertRaises(ValueError):
            server.validate_run_date("0000-01-01")

    def test_the_trim_matches_the_worker(self):
        # The Worker's String.trim() does not remove U+001C.
        with self.assertRaises(ValueError):
            server.validate_run_date("\u001c2026-10-01")
        self.assertEqual(server.validate_run_date("\u00a02026-10-01"), "2026-10-01")

    def test_the_graph_step_always_carries_run_date(self):
        steps = server.steps_for("session", None, "asia")
        self.assertEqual(steps[1][1]["RUN_DATE"], "")
        steps = server.steps_for("session", None, "asia", "2026-10-01")
        self.assertEqual(steps[1][1]["RUN_DATE"], "2026-10-01")

    def test_the_calendar_step_carries_no_run_date(self):
        steps = server.steps_for("session", None, "asia", "2026-10-01")
        self.assertNotIn("RUN_DATE", steps[0][1])

    def test_an_ambient_run_date_never_reaches_a_step(self):
        os.environ["RUN_DATE"] = "2026-01-01"
        try:
            self.assertNotIn("RUN_DATE", server.step_env({}))
            self.assertEqual(server.step_env({"RUN_DATE": ""})["RUN_DATE"], "")
        finally:
            os.environ.pop("RUN_DATE", None)


class HandlerTests(unittest.TestCase):
    """The HTTP handler, not only the pure functions."""

    def post(self, path: str, body: dict) -> tuple[int, dict]:
        raw = json.dumps(body).encode("utf-8")
        handler = server.Handler.__new__(server.Handler)
        handler.path = path
        handler.command = "POST"
        handler.request_version = "HTTP/1.1"
        handler.requestline = f"POST {path} HTTP/1.1"
        handler.headers = {"Content-Length": str(len(raw))}
        handler.rfile = io.BytesIO(raw)
        handler.wfile = io.BytesIO()
        handler.do_POST()
        response = handler.wfile.getvalue().decode("utf-8")
        status = int(response.split(" ", 2)[1])
        return status, json.loads(response.split("\r\n\r\n", 1)[1])

    def test_a_malformed_run_date_is_a_400_and_starts_nothing(self):
        with mock.patch.object(server.subprocess, "run") as run:
            status, payload = self.post("/run/session", {"session": "asia", "run_date": "2026-02-30"})
        self.assertEqual(status, 400)
        self.assertEqual(payload, {"error": "invalid_run_date"})
        run.assert_not_called()

    def test_a_valid_run_date_reaches_the_graph_step(self):
        with mock.patch.object(server.subprocess, "run") as run:
            run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
            status, payload = self.post("/run/session", {"session": "asia", "run_date": "2026-10-01"})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        env = run.call_args_list[-1].kwargs["env"]
        self.assertEqual(env["RUN_DATE"], "2026-10-01")
        self.assertEqual(env["FX_SESSION"], "asia")

    def test_an_unknown_route_is_rejected_before_the_run_date(self):
        with mock.patch.object(server.subprocess, "run") as run:
            status, payload = self.post("/run/bogus", {"run_date": "nope"})
        self.assertEqual(status, 400)
        self.assertEqual(payload, {"error": "unknown route"})
        run.assert_not_called()

    def test_an_invalid_session_wins_over_an_invalid_run_date(self):
        with mock.patch.object(server.subprocess, "run") as run:
            status, payload = self.post("/run/session", {"session": "bogus", "run_date": "nope"})
        self.assertEqual(status, 400)
        self.assertEqual(payload, {"error": "invalid session"})
        run.assert_not_called()
class LogTailTests(unittest.TestCase):
    def test_a_short_log_is_kept_whole(self):
        text = "MARKET_CONTEXT_VERDICT=source: 2 source(s) failed: dmx-overview\n"
        self.assertEqual(server.clip(text), text)

    def test_a_long_log_keeps_the_head_and_the_tail(self):
        text = "HEAD-MARKER\n" + ("x" * 10000) + "\nTAIL-MARKER"
        clipped = server.clip(text)
        self.assertEqual(len(clipped), server.LOG_TAIL)
        self.assertTrue(clipped.startswith("HEAD-MARKER"))
        self.assertTrue(clipped.endswith("TAIL-MARKER"))
        self.assertIn("truncated", clipped)

    def test_a_noisy_run_keeps_the_verdict_line(self):
        # stdout first, then stderr: the verdict line sits at the head, and a
        # tail that kept only the end would drop it.
        code = (
            "import sys; print('MARKET_CONTEXT_VERDICT=source: dmx-overview failed');"
            " sys.stderr.write('noise ' * 5000)"
        )
        steps = [([sys.executable, "-c", code], {}, True)]
        payload = server.run_steps(steps, timeout=30, dry_run=False)
        self.assertLessEqual(len(payload["log_tail"]), server.LOG_TAIL)
        self.assertIn("MARKET_CONTEXT_VERDICT=source: dmx-overview failed", payload["log_tail"])

    def test_the_tail_is_redacted_before_it_is_clipped(self):
        steps = [
            (
                [sys.executable, "-c", "print('token=supersecret')"],
                {},
                True,
            ),
        ]
        payload = server.run_steps(steps, timeout=30, dry_run=False)
        self.assertNotIn("supersecret", payload["log_tail"])
        self.assertIn("[redacted]", payload["log_tail"])



if __name__ == "__main__":
    unittest.main()
