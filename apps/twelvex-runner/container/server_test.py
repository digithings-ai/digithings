"""Unit tests for the container entrypoint. No twelve-x install and no network."""

from __future__ import annotations

import importlib.util
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
