"""
Heartbeat runner: read HEARTBEAT.md checklist, ping digigraph/digiquant health, log to audit.
Run every 30–60 min via cron or Docker. Phase 3.
"""

from __future__ import annotations

import json
import os
import urllib.parse
from pathlib import Path

import httpx
from digibase.http_client import sync_client

from digiclaw.audit import audit_log
from digiclaw.digikey_auth import digikey_bearer_token

HEARTBEAT_MD = "HEARTBEAT.md"
DIGIGRAPH_URL = os.environ.get("DIGIGRAPH_URL", "http://127.0.0.1:8000")
DIGIQUANT_URL = os.environ.get("DIGIQUANT_URL", "http://127.0.0.1:8001")


def _heartbeat_checklist_path() -> Path | None:
    """Resolve HEARTBEAT.md for Docker (repo mounted at /workspace) and local dev."""
    workspace = Path(os.environ.get("DIGI_WORKSPACE", "."))
    for candidate in (
        workspace / HEARTBEAT_MD,
        workspace / "digiclaw" / "docs" / HEARTBEAT_MD,
        Path(__file__).resolve().parents[2] / "docs" / HEARTBEAT_MD,
    ):
        if candidate.is_file():
            return candidate
    return None


def _request(
    url: str, *, method: str = "GET", data: bytes | None = None, auth: bool = False
) -> tuple[bool, str]:
    headers: dict[str, str] = {}
    if auth:
        token = digikey_bearer_token()
        if not token:
            return False, "digikey_token_unavailable"
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        headers["Content-Type"] = "application/json"
    try:
        with sync_client(timeout=60 if method == "POST" else 5) as client:
            response = client.request(method, url, content=data, headers=headers)
            return response.status_code == 200, str(response.status_code)
    except httpx.HTTPError as e:
        return False, str(e)


def _ping(url: str, path: str = "/health") -> tuple[bool, str]:
    return _request(f"{url.rstrip('/')}{path}")


def run_heartbeat() -> dict[str, bool]:
    """
    Run one heartbeat cycle: ping health endpoints, log results to audit.
    Returns dict of service -> healthy (bool).
    """
    results: dict[str, bool] = {}
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
    """If ADDM reports drift, trigger re-optimize via digiquant (SIMP-025).

    Drift stays colocated with heartbeat until Phase 3; each failure path writes an
    explicit ``audit_log`` event (no silent skip). ``main()`` exits 0/1 from health pings.
    """
    strategy_id = os.environ.get("REOPTIMIZE_STRATEGY", "mean_reversion_tech")
    drift_url = (
        f"{DIGIQUANT_URL.rstrip('/')}/check_drift?strategy_id={urllib.parse.quote(strategy_id)}"
    )
    token = digikey_bearer_token()
    if not token:
        audit_log(
            "drift_check_skipped",
            agent_id="heartbeat_runner",
            payload={"reason": "no_digikey_bearer"},
        )
        return
    try:
        with sync_client(timeout=5) as client:
            data = client.get(
                drift_url,
                headers={"Authorization": f"Bearer {token}"},
            ).json()
    except (httpx.HTTPError, json.JSONDecodeError, ValueError, KeyError, OSError) as e:
        audit_log(
            "drift_check_failed",
            agent_id="heartbeat_runner",
            payload={"strategy_id": strategy_id, "error": str(e)},
        )
        return
    if not data.get("drift_detected"):
        return
    audit_log(
        "reoptimize_triggered",
        agent_id="heartbeat_runner",
        payload={"strategy_id": strategy_id, "reason": "addm_drift"},
    )
    data_dir = os.environ.get("DIGIQUANT_DATA_DIR")
    if not data_dir:
        audit_log(
            "reoptimize_skipped",
            agent_id="heartbeat_runner",
            payload={"error": "DIGIQUANT_DATA_DIR required for run_optimize"},
        )
        return
    try:
        body = json.dumps(
            {
                "strategy_name": strategy_id,
                "symbols": ["AAPL", "MSFT", "GOOGL"],
                "data_dir": data_dir,
            }
        ).encode()
        with sync_client(timeout=60) as client:
            result = client.post(
                f"{DIGIQUANT_URL.rstrip('/')}/run_optimize",
                content=body,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            ).json()
        audit_log(
            "reoptimize_completed",
            agent_id="heartbeat_runner",
            payload={"run_id": result.get("run_id", "")},
        )
    except (httpx.HTTPError, json.JSONDecodeError, ValueError, KeyError, OSError) as e:
        audit_log("reoptimize_failed", agent_id="heartbeat_runner", payload={"error": str(e)})


def main() -> int:
    """Entrypoint for cron or Docker. Exit 0 if all healthy, 1 otherwise."""
    results = run_heartbeat()
    _check_drift_and_reoptimize()
    checklist = _heartbeat_checklist_path()
    if checklist is not None:
        audit_log(
            "heartbeat_checklist_seen",
            agent_id="heartbeat_runner",
            payload={"path": str(checklist)},
        )
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
