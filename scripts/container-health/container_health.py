#!/usr/bin/env python3
"""Daily container health check for the digithings stack, run from Chris's Mac.

Why this exists (DIG-2910, parent DIG-2904 "Cloudflare cost minimum")

The cron job ``smoke-stack`` probes the worker-only ``/_stack/status`` endpoints on
graph, key and search (DIG-2908, PR #5413). Those endpoints are answered by the
stack Worker itself, so the probe never boots the paid 6 GiB container. That is the
right trade for a cost epic, but it also means the cron cannot see whether the
container is healthy: it only ever sees the worker.

This check is the other half. It reads ``/healthz`` on the same three hosts from
Chris's Mac, once a day, under launchd. It is free, because of the wake hygiene in
``apps/digithings-stack-cloudflare/src/wake-hygiene.ts``:

* ``/healthz`` never wakes a sleeping container. The Worker answers
  ``200 {"status":"ok","service":"digithings-stack","container":"sleeping",...}``.
* When the container is already awake, the Worker proxies the request to it, so the
  answer is the container's own liveness payload ``200 {"ok": true}``.

So one probe answers two different questions, and the body says which one:

============================  ==================  ===============================
body                          meaning             cost
============================  ==================  ===============================
``{"ok": true}``              container awake and the service answered   free
``{"container": "sleeping"}`` worker up, container asleep                free
anything else / non-200       failure              free
============================  ==================  ===============================

A failure is one of three things: the edge is not answering, the Worker is not
answering, or the container is awake and the service inside it is broken. The last
one is the class the worker-only cron probe cannot see.

What this script does

1. Probes the three hosts and classifies each answer.
2. Writes a JSON line to ``~/.config/digithings/logs/container-health.log`` and the
   run summary to ``~/.config/digithings/state/container-health.json``.
3. On a failure it files ONE ticket ``[run-watch] container-health: <symptom>``
   through ``kit/bin/dt-create-issue`` (never a bare POST), and every later
   recurrence is a comment on that same ticket, never a second ticket.

Stdlib only. Run it by hand with ``--dry-run`` to see the report without writing
anything.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

# --- what we probe ------------------------------------------------------------

DEFAULT_HOSTS: tuple[str, ...] = ("graph", "key", "search")
DEFAULT_DOMAIN = "digithings.ai"
HEALTH_PATH = "/healthz"
DEFAULT_TIMEOUT = 20.0
USER_AGENT = "digithings-container-health/1.0 (launchd, read-only)"

# --- how we read an answer ----------------------------------------------------

STATE_OK = "container_ok"      # the container was awake and answered
STATE_SLEEPING = "sleeping"    # the worker is up, the container is asleep
STATE_UNEXPECTED = "unexpected"  # 200, but not a shape we know
STATE_HTTP = "http_error"      # a status code that is not 200
STATE_UNREACHABLE = "unreachable"  # no answer at all: DNS, TLS, timeout

#: A state that is not a failure. Sleeping is not a failure: the container is
#: asleep on purpose, and waking it would cost the boot plus the sleepAfter tail.
HEALTHY_STATES = frozenset({STATE_OK, STATE_SLEEPING})

#: The overall verdict of a run.
OVERALL_HEALTHY = "healthy"
OVERALL_DEGRADED = "degraded"    # a body we do not recognise
OVERALL_FAILED = "failed"        # no answer, or a status code that is not 200

# --- where things live on the host ---------------------------------------------

CONFIG_DIR = Path.home() / ".config" / "digithings"
STATE_PATH = CONFIG_DIR / "state" / "container-health.json"
LOG_PATH = CONFIG_DIR / "logs" / "container-health.log"

CREATE_ISSUE = os.environ.get(
    "DT_CREATE_ISSUE", str(Path.home() / "paperclip-workspace" / "kit" / "bin" / "dt-create-issue")
)
API_BASE = os.environ.get("PAPERCLIP_API_URL", "http://localhost:3100/api")

# --- how a filed ticket is routed ----------------------------------------------

#: The run-watch ticket follows the epic that owns the container it watches, so it
#: is never a free-floating issue, and the goal of DIG-2910 keeps it on the same
#: line of work.
TICKET_PROJECT = "digithings"
TICKET_PARENT = "DIG-2904"
TICKET_GOAL = "657cd9ec-cba3-467e-9afb-e2b4df7f8c44"
TICKET_ASSIGNEE = "c838b4b0-424b-4b58-a2c6-c140c97a0f87"  # DevOps Lead
TICKET_PRIORITY = "high"
TICKET_STATUS = "todo"

#: A recurrence comment on the ticket is a note, not a new signal: one per day is
#: enough, unless the symptom changed.
RECURRENCE_COMMENT_HOURS = 24.0


def utcnow() -> str:
    """The current UTC time as an ISO-8601 string with a Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def excerpt(text: str, limit: int = 160) -> str:
    """One short, single-line excerpt of a body, for a log line or a ticket."""
    flat = " ".join((text or "").split())
    if len(flat) <= limit:
        return flat
    return flat[: limit - 1] + "…"


# --- probing ------------------------------------------------------------------


def classify(status: int, body: str) -> tuple[str, str]:
    """Classify one answer from a host.

    Returns ``(state, detail)``. The two shapes we know are the container's own
    liveness payload and the worker's sleeping answer; everything else is a
    failure, because a body we do not recognise means the contract moved and
    nobody is watching it.
    """
    if status != 200:
        return STATE_HTTP, f"HTTP {status}"
    try:
        payload = json.loads(body)
    except (TypeError, ValueError):
        return STATE_UNEXPECTED, "body is not JSON: " + excerpt(body, 80)
    if not isinstance(payload, dict):
        return STATE_UNEXPECTED, "body is not a JSON object: " + excerpt(body, 80)
    if payload.get("ok") is True:
        return STATE_OK, "container answered"
    if payload.get("container") == "sleeping":
        return STATE_SLEEPING, "worker up, container asleep"
    return STATE_UNEXPECTED, "unexpected body: " + excerpt(json.dumps(payload), 120)


def probe(
    host: str,
    domain: str = DEFAULT_DOMAIN,
    timeout: float = DEFAULT_TIMEOUT,
    opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Probe one host and return the result as a plain dict.

    ``opener`` is injectable so the tests can answer without a network.
    """
    url = f"https://{host}.{domain}{HEALTH_PATH}"
    open_it = opener or urllib.request.urlopen
    # The User-Agent is not decoration. The edge answers Python-urllib with 403
    # (measured 2026-10-22), so a probe that does not name itself sees a
    # firewall, not the stack.
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    started = time.monotonic()
    raw = b""
    status: int | None = None
    error: str | None = None
    try:
        with open_it(request, timeout=timeout) as response:
            status = getattr(response, "status", None) or response.getcode()
            raw = response.read(8192)
    except urllib.error.HTTPError as err:  # a status code that is not 200
        status = err.code
        error = f"HTTP {err.code}"
        try:
            raw = err.read(8192)
        except Exception:  # pragma: no cover - the body is best effort
            raw = b""
    except Exception as err:  # DNS, TLS, timeout, refused connection
        error = f"{type(err).__name__}: {err}"
    elapsed_ms = int((time.monotonic() - started) * 1000)
    body = raw.decode("utf-8", "replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
    if error is not None and status is None:
        return {
            "host": host,
            "url": url,
            "state": STATE_UNREACHABLE,
            "http_status": None,
            "elapsed_ms": elapsed_ms,
            "detail": excerpt(error, 160),
            "body": "",
        }
    state, detail = classify(int(status or 0), body)
    return {
        "host": host,
        "url": url,
        "state": state,
        "http_status": int(status or 0),
        "elapsed_ms": elapsed_ms,
        "detail": detail,
        "body": excerpt(body, 240),
    }


def run_probes(
    hosts: Sequence[str] = DEFAULT_HOSTS,
    domain: str = DEFAULT_DOMAIN,
    timeout: float = DEFAULT_TIMEOUT,
    opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Probe every host and summarise the run."""
    results = [probe(host, domain=domain, timeout=timeout, opener=opener) for host in hosts]
    states = {r["state"] for r in results}
    if states & {STATE_HTTP, STATE_UNREACHABLE}:
        overall = OVERALL_FAILED
    elif states & {STATE_UNEXPECTED}:
        overall = OVERALL_DEGRADED
    else:
        overall = OVERALL_HEALTHY
    return {
        "ts": utcnow(),
        "overall": overall,
        "hosts": list(hosts),
        "results": results,
        "symptom": symptom(results),
    }


def symptom(results: Iterable[dict[str, Any]]) -> str:
    """One short phrase naming what is wrong, for a ticket title."""
    bad = [r for r in results if r["state"] not in HEALTHY_STATES]
    if not bad:
        return ""
    first = bad[0]
    if first["state"] == STATE_UNREACHABLE:
        what = "unreachable"
    elif first["state"] == STATE_HTTP:
        what = f"HTTP {first['http_status']}"
    else:
        what = "unexpected body"
    return f"{first['host']} {HEALTH_PATH} {what}"


def symptom_signature(results: Iterable[dict[str, Any]]) -> str:
    """A stable name for the class of failure, used to spot a changed symptom."""
    parts = []
    for r in results:
        if r["state"] not in HEALTHY_STATES:
            parts.append(f"{r['host']}:{r['state']}:{r['http_status']}")
    return ",".join(parts)


# --- the report ---------------------------------------------------------------


def report_text(report: dict[str, Any]) -> str:
    """The report as a human reads it in a log or on a ticket."""
    lines = [f"container health {report['ts']}: {report['overall']}"]
    for r in report["results"]:
        code = r["http_status"] if r["http_status"] is not None else "-"
        lines.append(
            f"  {r['host']:<8} {r['state']:<12} http={code:<4} {r['elapsed_ms']:>5}ms  {r['detail']}"
        )
    if report.get("symptom"):
        lines.append(f"  symptom: {report['symptom']}")
    return "\n".join(lines)


# --- state --------------------------------------------------------------------


def load_state(path: Path = STATE_PATH) -> dict[str, Any]:
    """Read the state file. A missing or broken file is an empty state."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"version": 1}
    if not isinstance(data, dict):
        return {"version": 1}
    data.setdefault("version", 1)
    return data


def save_state(state: dict[str, Any], path: Path = STATE_PATH) -> None:
    """Write the state file, atomically enough for a daily job."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def append_log(report: dict[str, Any], path: Path = LOG_PATH) -> None:
    """Append the run to the host log as one JSON line."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(
        {
            "ts": report["ts"],
            "overall": report["overall"],
            "symptom": report.get("symptom", ""),
            "results": [
                {
                    "host": r["host"],
                    "state": r["state"],
                    "http_status": r["http_status"],
                    "elapsed_ms": r["elapsed_ms"],
                    "detail": r["detail"],
                }
                for r in report["results"]
            ],
        },
        sort_keys=True,
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


# --- the ticket ---------------------------------------------------------------


def file_issue(
    title: str,
    description: str,
    project: str = TICKET_PROJECT,
    parent: str = TICKET_PARENT,
    goal: str = TICKET_GOAL,
    assignee: str = TICKET_ASSIGNEE,
    priority: str = TICKET_PRIORITY,
    status: str = TICKET_STATUS,
    create_script: str = CREATE_ISSUE,
    runner: Callable[..., Any] = subprocess.run,
) -> str | None:
    """File the run-watch ticket through ``dt-create-issue``.

    DIG-2040 / DIG-1635: a bare ``POST /api/issues`` writes no workspace fields and
    the issue lands on somebody else's worktree, so creation always goes through
    the script, which sets ``executionWorkspacePreference: isolated_workspace`` and
    reads the issue back. A non-zero exit means the issue was NOT filed: this
    returns None and never falls back to a raw POST.
    """
    cmd = [
        sys.executable or "/usr/bin/python3",
        create_script,
        "--title",
        title,
        "--description",
        description,
        "--project",
        project,
        "--parent",
        parent,
        "--goal",
        goal,
        "--assignee",
        assignee,
        "--status",
        status,
        "--priority",
        priority,
    ]
    try:
        proc = runner(cmd, capture_output=True, text=True)
    except Exception as err:  # the script could not even be run
        print(f"container-health: dt-create-issue could not run: {err}", file=sys.stderr)
        return None
    if proc.returncode != 0:
        print(
            "container-health: dt-create-issue refused (exit "
            f"{proc.returncode}); the ticket was NOT filed: {excerpt(proc.stdout + proc.stderr, 300)}",
            file=sys.stderr,
        )
        return None
    parts = (proc.stdout or "").split()
    if not parts:
        print("container-health: dt-create-issue printed no identifier; the ticket was NOT filed", file=sys.stderr)
        return None
    return parts[0]


def comment(
    identifier: str,
    body: str,
    api_base: str = API_BASE,
    api_key: str | None = None,
    opener: Callable[..., Any] | None = None,
    timeout: float = 60.0,
) -> bool:
    """Add a comment to an existing ticket.

    The write carries the bearer header: without it the server files the comment
    as Chris (local-board), which is not who ran the check.
    """
    key = api_key if api_key is not None else os.environ.get("PAPERCLIP_API_KEY")
    if not key:
        print(
            "container-health: no PAPERCLIP_API_KEY in the environment; the comment was NOT posted",
            file=sys.stderr,
        )
        return False
    open_it = opener or urllib.request.urlopen
    request = urllib.request.Request(
        f"{api_base.rstrip('/')}/issues/{identifier}/comments",
        data=json.dumps({"body": body}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    try:
        with open_it(request, timeout=timeout) as response:
            status = getattr(response, "status", None) or response.getcode()
            return 200 <= int(status) < 300
    except Exception as err:
        print(f"container-health: the comment on {identifier} failed: {err}", file=sys.stderr)
        return False


def ticket_title(report: dict[str, Any]) -> str:
    """The title of the run-watch ticket. One ticket per job, symptom first."""
    symptom_text = report.get("symptom") or "unknown symptom"
    return f"[run-watch] container-health: {symptom_text}"


def ticket_description(report: dict[str, Any]) -> str:
    """The body of the run-watch ticket: what, when, the evidence, the next step."""
    lines = [
        "The daily container health check (DIG-2910) failed from Chris's Mac.",
        "",
        f"Symptom: {report.get('symptom') or 'unknown symptom'}",
        f"Run: {report['ts']}",
        "",
        "Hosts:",
    ]
    for r in report["results"]:
        code = r["http_status"] if r["http_status"] is not None else "-"
        lines.append(f"  {r['host']} {r['state']} http={code} {r['elapsed_ms']}ms {r['detail']}")
        if r.get("body"):
            lines.append(f"    body: {excerpt(r['body'], 120)}")
    lines += [
        "",
        "Evidence: ~/.config/digithings/logs/container-health.log and",
        "~/.config/digithings/state/container-health.json hold the full report.",
        "",
        "/healthz never wakes the container (wake hygiene), so this is the edge or the",
        "worker not answering, or the container awake with the service broken inside",
        "it. The worker-only cron probe (/_stack/status) cannot see this class.",
        "",
        "Next: reproduce with curl -sS -w '\\n%{http_code}\\n' "
        "https://graph.digithings.ai/healthz and look at the stack container.",
        "A repeat of this symptom is commented here, not filed again.",
    ]
    text = "\n".join(lines)
    return text[:1150]


def handle_failure(state: dict[str, Any], report: dict[str, Any]) -> str:
    """File the ticket on the first failure, comment on it on every later one.

    Returns what happened: ``filed``, ``commented``, ``skipped`` or ``not-filed``.
    """
    ticket = state.get("ticket")
    signature = symptom_signature(report["results"])
    if not ticket:
        identifier = file_issue(ticket_title(report), ticket_description(report))
        if not identifier:
            return "not-filed"
        state["ticket"] = {
            "identifier": identifier,
            "symptom": report.get("symptom", ""),
            "signature": signature,
            "created_at": report["ts"],
            "last_comment_at": report["ts"],
            "comments": 1,
        }
        return "filed"
    body = (
        f"The daily container health check (DIG-2910) failed again.\n\n"
        f"Run: {report['ts']}\n"
        f"Symptom now: {report.get('symptom') or 'unknown symptom'}\n"
        f"Symptom when filed: {ticket.get('symptom') or 'unknown symptom'}\n\n"
        + report_text(report)
        + "\n\nThe full report is in ~/.config/digithings/logs/container-health.log."
    )
    posted = comment(ticket["identifier"], body)
    if posted:
        ticket["last_comment_at"] = report["ts"]
        ticket["comments"] = int(ticket.get("comments", 0)) + 1
        if ticket.get("signature") != signature:
            ticket["signature"] = signature
            ticket["symptom"] = report.get("symptom", "")
        return "commented"
    return "skipped"


def handle_recovery(state: dict[str, Any], report: dict[str, Any]) -> str:
    """Say once on the ticket that the check is green again."""
    ticket = state.get("ticket")
    if not ticket or ticket.get("recovered_at"):
        return "skipped"
    body = (
        f"The daily container health check (DIG-2910) is green again.\n\n"
        f"Run: {report['ts']}\n\n"
        + report_text(report)
        + "\n\nThe ticket stays open: a recurrence is commented here, not filed again."
    )
    if not comment(ticket["identifier"], body):
        return "skipped"
    ticket["recovered_at"] = report["ts"]
    return "commented"


# --- the command line ---------------------------------------------------------


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="container_health.py",
        description="Daily /healthz check of the digithings stack containers, from Chris's Mac.",
    )
    parser.add_argument("--hosts", default=",".join(DEFAULT_HOSTS), help="comma separated host names")
    parser.add_argument("--domain", default=DEFAULT_DOMAIN, help="the domain the hosts live under")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="per host timeout in seconds")
    parser.add_argument("--state-path", default=str(STATE_PATH), help="where the run state is kept")
    parser.add_argument("--log-path", default=str(LOG_PATH), help="where the run log is kept")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    parser.add_argument("--dry-run", action="store_true", help="probe and print, write nothing and file nothing")
    parser.add_argument("--status", action="store_true", help="print the last run from the state file and exit")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None, opener: Callable[..., Any] | None = None) -> int:
    """Run the check. ``opener`` is injectable so the tests never touch the network."""
    args = parse_args(argv)
    state_path = Path(args.state_path)
    log_path = Path(args.log_path)
    if args.status:
        state = load_state(state_path)
        last = state.get("last_run", {})
        ticket = state.get("ticket", {})
        print(json.dumps({"last_run": last, "ticket": ticket}, indent=2, sort_keys=True))
        return 0
    hosts = [h.strip() for h in args.hosts.split(",") if h.strip()]
    report = run_probes(hosts, domain=args.domain, timeout=args.timeout, opener=opener)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(report_text(report))
    if args.dry_run:
        return 0 if report["overall"] == OVERALL_HEALTHY else 1
    append_log(report, log_path)
    state = load_state(state_path)
    if report["overall"] == OVERALL_HEALTHY:
        action = handle_recovery(state, report)
    else:
        action = handle_failure(state, report)
    state["last_run"] = {
        "ts": report["ts"],
        "overall": report["overall"],
        "symptom": report.get("symptom", ""),
        "results": [
            {"host": r["host"], "state": r["state"], "http_status": r["http_status"]}
            for r in report["results"]
        ],
    }
    state["last_action"] = action
    save_state(state, state_path)
    print(f"container-health: {action}")
    return 0 if report["overall"] == OVERALL_HEALTHY else 1


if __name__ == "__main__":
    sys.exit(main())
