"""Unit tests for the container entrypoint. No twelve-x install and no network."""

from __future__ import annotations

import importlib.util
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


if __name__ == "__main__":
    unittest.main()
