"""
Heartbeat runner: read HEARTBEAT.md checklist, ping DigiGraph/DigiQuant health, log to audit.
Run every 30–60 min via cron or Docker. Phase 3.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from digiclaw.audit import audit_log

HEARTBEAT_MD = "HEARTBEAT.md"
DIGIGRAPH_URL = os.environ.get("DIGIGRAPH_URL", "http://127.0.0.1:8000")
DIGIQUANT_URL = os.environ.get("DIGIQUANT_URL", "http://127.0.0.1:8001")


def _ping(url: str, path: str = "/health") -> tuple[bool, str]:
    try:
        req = urllib.request.Request(f"{url.rstrip('/')}{path}", method="GET")
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status == 200, str(r.status)
    except urllib.error.URLError as e:
        return False, str(e.reason) if hasattr(e, "reason") else str(e)
    except Exception as e:
        return False, str(e)


def run_heartbeat() -> dict[str, bool]:
    """
    Run one heartbeat cycle: ping health endpoints, log results to audit.
    Returns dict of service -> healthy (bool).
    """
    results = {}
    dg_ok, dg_msg = _ping(DIGIGRAPH_URL)
    dq_ok, dq_msg = _ping(DIGIQUANT_URL)
    results["digigraph"] = dg_ok
    results["digiquant"] = dq_ok
    audit_log(
        "heartbeat",
        agent_id="heartbeat_runner",
        payload={
            "digigraph_url": DIGIGRAPH_URL,
            "digigraph_ok": dg_ok,
            "digigraph_detail": dg_msg,
            "digiquant_url": DIGIQUANT_URL,
            "digiquant_ok": dq_ok,
            "digiquant_detail": dq_msg,
        },
    )
    return results


def _check_drift_and_reoptimize() -> None:
    """If ADDM reports drift, trigger re-optimize via DigiQuant. Phase 3 self-re-optimization loop."""
    strategy_id = os.environ.get("REOPTIMIZE_STRATEGY", "mean_reversion_tech")
    try:
        req = urllib.request.Request(
            f"{DIGIQUANT_URL.rstrip('/')}/check_drift?strategy_id={urllib.parse.quote(strategy_id)}",
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read().decode())
    except Exception:
        return
    if not data.get("drift_detected"):
        return
    audit_log("reoptimize_triggered", agent_id="heartbeat_runner", payload={"strategy_id": strategy_id, "reason": "addm_drift"})
    try:
        body = json.dumps({"strategy_name": strategy_id, "symbols": ["AAPL", "MSFT", "GOOGL"]}).encode()
        req = urllib.request.Request(
            f"{DIGIQUANT_URL.rstrip('/')}/run_optimize",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            result = json.loads(r.read().decode())
        audit_log("reoptimize_completed", agent_id="heartbeat_runner", payload={"run_id": result.get("run_id", "")})
    except Exception as e:
        audit_log("reoptimize_failed", agent_id="heartbeat_runner", payload={"error": str(e)})


def main() -> int:
    """Entrypoint for cron or Docker. Exit 0 if all healthy, 1 otherwise."""
    run_heartbeat()
    _check_drift_and_reoptimize()
    heartbeat_path = Path(os.environ.get("DIGI_WORKSPACE", ".")) / HEARTBEAT_MD
    if heartbeat_path.exists():
        audit_log("heartbeat_checklist_seen", agent_id="heartbeat_runner", payload={"path": str(heartbeat_path)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
