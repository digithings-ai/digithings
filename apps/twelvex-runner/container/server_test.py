"""Unit tests for the container entrypoint. No twelve-x install and no network."""

from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path


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
        self.assertNotIn("RUN_DATE", steps[1][1])

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


class OneCommandSourceTests(unittest.TestCase):
    """The argv lives here and nowhere else.

    A second copy of a command would drift from the pinned twelve-x ref
    without any run failing, so the app keeps one source of truth.
    """

    def setUp(self):
        self.app = Path(__file__).resolve().parent.parent
        self.runtime_files = [
            path
            for path in list((self.app / "src").rglob("*"))
            + list((self.app / "container").rglob("*"))
            if path.is_file()
            and path.suffix in {".ts", ".py"}
            and not path.name.endswith((".test.ts", "_test.py"))
        ]
        self.doc_files = [self.app / "README.md", self.app / "wrangler.toml"]

    def test_the_heartbeat_module_path_is_pinned_here(self):
        self.assertIn(f'"{HEARTBEAT_MODULE}"', (self.app / "container" / "server.py").read_text())

    def test_no_other_runtime_module_carries_the_heartbeat_module_path(self):
        holders = [
            str(path.relative_to(self.app))
            for path in self.runtime_files
            if HEARTBEAT_MODULE in path.read_text()
        ]
        self.assertEqual(holders, [os.path.join("container", "server.py")])

    def test_no_typo_of_the_heartbeat_module_name(self):
        for path in self.runtime_files + self.doc_files:
            self.assertNotIn("primarketet", path.read_text(), str(path))

    def test_the_routing_module_carries_no_command_mirror(self):
        routes = (self.app / "src" / "routes.ts").read_text()
        self.assertNotIn("twelve_x", routes)
        self.assertNotIn("python", routes)


if __name__ == "__main__":
    unittest.main()
