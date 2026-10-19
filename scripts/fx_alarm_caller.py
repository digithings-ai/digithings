#!/usr/bin/env python3
"""Caller for the pinned twelve-x FX alarm reader (DIG-2707).

The reader itself is vendored byte-for-byte under ``scripts/vendor/twelve_x/``
and must never be edited in this repo. This module owns everything the reader
deliberately leaves out:

* loading the vendored reader from an explicit path (so the file that runs is
  the pinned one, not whatever ``sys.path`` happens to resolve);
* converting the persisted watermark document back to the ``dict[int, str]``
  the reader expects (JSON keys are strings; a quoted watermark never equals
  the next tick's ``str(cursor)``);
* filing the board issue / comment and only then persisting the watermark, so a
  crash between the two re-reports once (a duplicate alarm is a nuisance a human
  closes; a silent alarm is a dead channel);
* ``--check-vendor``: an offline assertion that the vendored blob is the pinned
  one.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import (  # score:allow untyped any — board API JSON + vendored reader shapes
    Any,
    Callable,
    Iterable,
    Optional,
)
from urllib.parse import quote

REPO_ROOT = Path(__file__).resolve().parent.parent
VENDOR_PATH = REPO_ROOT / "scripts" / "vendor" / "twelve_x" / "fx_alarm_watch.py"
VENDOR_BLOB_SHA1 = "0bbd3527e8359c2192f4cdc4837b38a202d132ae"

STATE_DOCUMENT_KEY = "fx_alarm_watermarks"
STATE_ISSUE_IDENTIFIER = "DIG-2594"
GITHUB_REPO = "digithings-ai/twelve-x"


def _load_vendor() -> Any:
    """Load the pinned reader from its explicit path.

    ``spec_from_file_location`` alone leaves ``sys.modules`` untouched, which
    breaks dataclasses and any module that inspects its own ``__module__``; we
    register the module before executing it for the same reason.
    """
    spec = importlib.util.spec_from_file_location("fx_alarm_watch", VENDOR_PATH)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError(f"could not load vendored reader at {VENDOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_VENDOR = _load_vendor()

# Re-exported so callers (and tests) reach the pinned reader through this
# module rather than importing the vendored path directly.
ALARM_LABELS = _VENDOR.ALARM_LABELS
new_alarms = _VENDOR.new_alarms


def blob_sha1(data: bytes) -> str:
    """Git's blob-object sha1: ``sha1(b"blob <len>\\0" + data)``.

    This is not ``shasum -a 1`` on the plain bytes; the header and the length
    are part of the hash.
    """
    header = b"blob %d\0" % len(data)
    return hashlib.sha1(header + data).hexdigest()


def check_vendor() -> int:
    """Assert the vendored reader is the pinned blob. Offline.

    Returns 0 on a match, 1 on drift, 2 when the file cannot be read.
    """
    try:
        data = VENDOR_PATH.read_bytes()
    except OSError as exc:
        print(f"vendor check: cannot read {VENDOR_PATH}: {exc}", file=sys.stderr)
        return 2
    actual = blob_sha1(data)
    if actual != VENDOR_BLOB_SHA1:
        print(
            f"vendor check: DRIFT in {VENDOR_PATH}\n"
            f"  expected blob {VENDOR_BLOB_SHA1}\n"
            f"  actual   blob {actual}",
            file=sys.stderr,
        )
        return 1
    print(f"vendor check: {VENDOR_PATH.name} is the pinned blob {VENDOR_BLOB_SHA1}")
    return 0


# ---------------------------------------------------------------------------
# watermark document
# ---------------------------------------------------------------------------


def load_watermarks(raw: Any) -> dict[int, str]:
    """Convert the raw parsed JSON document to the reader's ``{int: str}``.

    JSON object keys are always strings; the reader compares each stored
    watermark against ``str(cursor)`` per issue, so the keys must be ints or
    every issue reads as new on every tick.
    """
    return {int(k): v for k, v in raw.items()}


def dump_watermarks(watermarks: dict[int, str]) -> str:
    """Serialise watermarks with str keys in int order, for a stable document."""
    ordered = {str(k): watermarks[k] for k in sorted(watermarks)}
    return json.dumps(ordered, indent=2) + "\n"


def save_watermarks(store: Callable[[str], None], watermarks: dict[int, str]) -> None:
    """Hand the serialised document to ``store`` (an injectable writer)."""
    store(dump_watermarks(watermarks))


def parse_state_document(body: str) -> Any:
    """Extract the fenced JSON block from the state document body."""
    marker = "```json"
    start = body.find(marker)
    if start == -1:
        raise ValueError("state document has no ```json block")
    start += len(marker)
    end = body.find("```", start)
    if end == -1:
        raise ValueError("state document json block is unterminated")
    return json.loads(body[start:end])


def render_state_document(payload: str) -> str:
    """Wrap the serialised watermarks in a markdown envelope."""
    return (
        "# FX alarm watermarks\n\n"
        "Watermark state for the twelve-x FX alarm caller (DIG-2707). "
        "Single writer; edited only by `scripts/fx_alarm_caller.py`.\n\n"
        "```json\n" + payload + "```\n"
    )


# ---------------------------------------------------------------------------
# board API
# ---------------------------------------------------------------------------


def board_config(*, required: bool = True) -> Optional[dict[str, str]]:
    """Read the board credentials from the environment.

    Returns ``None`` when the trio is incomplete and ``required`` is false, so
    ``--dry-run`` needs no credentials.
    """
    base = os.environ.get("PAPERCLIP_API_URL", "").rstrip("/")
    key = os.environ.get("PAPERCLIP_API_KEY", "")
    company = os.environ.get("PAPERCLIP_COMPANY_ID", "")
    if not base or not key or not company:
        if required:
            raise RuntimeError(
                "board credentials incomplete: set PAPERCLIP_API_URL, "
                "PAPERCLIP_API_KEY and PAPERCLIP_COMPANY_ID"
            )
        return None
    if not base.endswith("/api"):
        base = base + "/api"
    cfg = {"base": base, "key": key, "company": company}
    run_id = os.environ.get("PAPERCLIP_RUN_ID", "")
    if run_id:
        cfg["run_id"] = run_id
    return cfg


def _request(
    cfg: dict[str, str], method: str, path: str, payload: Optional[dict[str, Any]] = None
) -> Any:
    url = cfg["base"] + path
    data = None
    headers = {
        "Authorization": f"Bearer {cfg['key']}",
        "Accept": "application/json",
    }
    if cfg.get("run_id"):
        headers["X-Paperclip-Run-Id"] = cfg["run_id"]
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        exc.close()
        raise RuntimeError(f"{method} {path} -> HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        # network-level failure (connection refused, DNS, read timeout); HTTPError
        # is a subclass of URLError and is normalised above with the status code.
        raise RuntimeError(f"{method} {path} -> {exc.reason}") from exc
    if not body.strip():
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{method} {path} -> 2xx body is not JSON: {exc}") from exc


def board_marker(number: int) -> str:
    return f"github_issue_number: {number}"


def board_issue_title(number: int, title: str) -> str:
    return f"[FX Alarm] {title} (#{number})"


def board_issue_description(number: int, title: str, url: str) -> str:
    # the find-or-create key is (source_repo, github_issue_number) per DIG-728:
    # the ``source_repo:`` line makes the lookup reject a description from any
    # other vendored repo that happens to carry the same number marker.
    return (
        f"FX alarm filed by the twelve-x alarm caller (DIG-2707).\n\n"
        f"source_repo: twelve-x\n"
        f"{board_marker(number)}\n\n"
        f"- upstream issue: {title}\n"
        f"- upstream url: {url}\n"
    )


def _as_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        rows = payload.get("issues")
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def _list_issues(cfg: dict[str, str], query: str) -> list[dict[str, Any]]:
    # encode the query: a literal like "FX Alarm" contains a space, which
    # urllib refuses client-side (http.client.InvalidURL) before any bytes
    # hit the wire.
    path = f"/companies/{cfg['company']}/issues?q={quote(query)}&limit=500"
    return _as_rows(_request(cfg, "GET", path))


def _find_board_issue(cfg: dict[str, str], number: int) -> Optional[dict[str, Any]]:
    """Find the board issue for ``number`` by marker, matched client-side.

    ``?q=`` is a loose relevance match, so the exact marker is verified here
    rather than trusted from the query. The key is ``(source_repo, number)``
    (DIG-728): both lines must be present. Human-closed board issues (status
    ``done``) are skipped when an open one with the same key exists, so the
    caller comments on the open row instead of filing a duplicate.
    """
    marker = board_marker(number)
    repo_line = "source_repo: twelve-x"

    def keyed(row: dict[str, Any]) -> bool:
        description = row.get("description") or ""
        return marker in description and repo_line in description

    matches = [row for row in _list_issues(cfg, "FX Alarm") if keyed(row)]
    for row in matches:
        if row.get("status") != "done":
            return row
    return matches[0] if matches else None


def build_board_deliver(
    cfg: dict[str, str], index: dict[int, dict[str, Any]]
) -> Callable[[int], None]:
    """Build the ``deliver(number)`` callable that files the board report."""

    def deliver(number: int) -> None:
        issue = index[number]
        title = issue.get("title") or f"issue {number}"
        url = issue.get("html_url") or ""
        existing = _find_board_issue(cfg, number)
        if existing is not None and existing.get("status") != "done":
            _request(
                cfg,
                "POST",
                f"/issues/{existing['id']}/comments",
                {"body": f"FX alarm re-raised: {title}\n\n{url}\n"},
            )
            return
        _request(
            cfg,
            "POST",
            f"/companies/{cfg['company']}/issues",
            {
                "title": board_issue_title(number, title),
                "description": board_issue_description(number, title, url),
                "priority": "high",
                "labels": ["fx-alarm", "twelve-x", "needs-triage"],
                "status": "todo",
            },
        )

    return deliver


# ---------------------------------------------------------------------------
# state document storage
# ---------------------------------------------------------------------------


def resolve_state_issue(cfg: dict[str, str]) -> str:
    """Resolve the DIG-2594 issue id from the live board."""
    matches = [
        row["id"]
        for row in _list_issues(cfg, STATE_ISSUE_IDENTIFIER)
        if row.get("identifier") == STATE_ISSUE_IDENTIFIER
    ]
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one {STATE_ISSUE_IDENTIFIER}, found {len(matches)}")
    return matches[0]


def read_state(cfg: dict[str, str], issue_id: str) -> dict[int, str]:
    """Read and parse the watermark document, empty when it does not exist."""
    path = f"/issues/{issue_id}/documents"
    rows = _as_rows(_request(cfg, "GET", path))
    document = None
    for row in rows:
        if row.get("key") == STATE_DOCUMENT_KEY:
            document = row
            break
    if document is None:
        return {}
    body = document.get("body")
    if body is None:
        fetched = _request(cfg, "GET", f"{path}/{STATE_DOCUMENT_KEY}")
        body = (fetched or {}).get("body", "")
    return load_watermarks(parse_state_document(body))


def build_document_store(cfg: dict[str, str], issue_id: str) -> Callable[[str], None]:
    """Build the ``store(payload)`` callable that PUTs the state document."""

    def store(payload: str) -> None:
        path = f"/issues/{issue_id}/documents"
        latest = ""
        rows = _as_rows(_request(cfg, "GET", path))
        for row in rows:
            if row.get("key") == STATE_DOCUMENT_KEY:
                latest = row.get("latestRevisionId") or ""
                break
        body = {
            "title": "FX alarm watermarks",
            "format": "markdown",
            "body": render_state_document(payload),
        }
        if latest:
            body["baseRevisionId"] = latest
        _request(cfg, "PUT", f"{path}/{STATE_DOCUMENT_KEY}", body)

    return store


# ---------------------------------------------------------------------------
# tick
# ---------------------------------------------------------------------------


def run_tick(
    issues: list[dict[str, Any]],
    watermarks: dict[int, str],
    *,
    deliver: Callable[[int], None],
    save: Callable[[dict[int, str]], None],
) -> list[int]:
    """File new alarms, then persist the watermark of what was filed.

    ``save`` runs only when something was reported, and only after ``deliver``
    returned for that number. A number whose ``deliver`` raised is not
    recorded, so it re-reports on the next tick. A ``save`` failure must not
    mask a board failure: the board error is the primary one and is chained
    from.
    """
    reported, nxt = new_alarms(issues, watermarks)
    if not reported:
        return []
    delivered: list[int] = []
    failure: Optional[Exception] = None
    for number in reported:
        try:
            deliver(number)
        except Exception as exc:
            failure = exc
            break
        delivered.append(number)
    if delivered:
        updated = dict(watermarks)
        for number in delivered:
            updated[number] = nxt[number]
        try:
            save(updated)
        except Exception as save_error:
            if failure is not None:
                raise failure from save_error
            raise
    if failure is not None:
        raise failure
    return reported


# ---------------------------------------------------------------------------
# issue fetching (online)
# ---------------------------------------------------------------------------


def _gh_json(args: list[str]) -> Any:
    proc = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout) if proc.stdout.strip() else None


def _flatten(payload: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, list):
                rows.extend(row for row in item if isinstance(row, dict))
            elif isinstance(item, dict):
                rows.append(item)
    return rows


def _normalise_labels(raw_labels: Any) -> list[str]:
    names: list[str] = []
    for label in raw_labels or []:
        if isinstance(label, dict):
            names.append(label.get("name", ""))
        else:
            names.append(str(label))
    return names


def fetch_issues() -> list[dict[str, Any]]:
    """Fetch open issues carrying any alarm label, de-duplicated by number."""
    index: dict[int, dict[str, Any]] = {}
    for label in sorted(ALARM_LABELS):
        payload = _gh_json(
            [
                "api",
                "--paginate",
                "--slurp",
                f"repos/{GITHUB_REPO}/issues?state=open&labels={label}",
            ]
        )
        for row in _flatten(payload):
            if row.get("pull_request"):
                continue
            number = row.get("number")
            if number is None:
                continue
            row["labels"] = _normalise_labels(row.get("labels"))
            index[int(number)] = row
    # one comment lookup per unique number: a row carrying two alarm labels
    # appears twice above, and the second pass keeps the newest-comment query
    # from running once per duplicate occurrence.
    for key, row in index.items():
        row["newest_comment_id"] = _newest_comment_id(key)
    return [index[key] for key in sorted(index)]


def _newest_comment_id(number: int) -> Optional[int]:
    payload = _gh_json(
        [
            "api",
            "--paginate",
            "--slurp",
            f"repos/{GITHUB_REPO}/issues/{number}/comments?per_page=1&sort=created&direction=desc",
        ]
    )
    rows = _flatten(payload)
    if not rows:
        return None
    newest = max(rows, key=lambda row: row.get("id", 0))
    return newest.get("id")


# ---------------------------------------------------------------------------
# entrypoint
# ---------------------------------------------------------------------------


def _load_issues_file(path: str) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise RuntimeError("--issues-file must hold a JSON list of issues")
    for row in payload:
        row["labels"] = _normalise_labels(row.get("labels"))
    return payload


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-vendor", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the alarms without writing to the board",
    )
    parser.add_argument(
        "--issues-file",
        help="offline JSON list of issues to evaluate instead of fetching",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.check_vendor and not (args.run or args.dry_run or args.issues_file):
        return check_vendor()
    if args.check_vendor and check_vendor() != 0:
        # a combined invocation still asserts the pin first: running the caller
        # against drifted vendored bytes is exactly what must never happen.
        return 1

    if args.issues_file:
        issues = _load_issues_file(args.issues_file)
    elif args.run or args.dry_run:
        issues = fetch_issues()
    else:
        parser.error("specify --check-vendor, --issues-file or --run")
        return 2  # pragma: no cover - argparse exits

    if args.dry_run or not args.run:
        cfg = board_config(required=False)
        watermarks = read_state(cfg, resolve_state_issue(cfg)) if cfg else {}
        reported, _ = new_alarms(issues, watermarks)
        for number in reported:
            print(f"would report #{number}")
        return 0

    cfg = board_config(required=True)
    index = {int(row["number"]): row for row in issues}
    issue_id = resolve_state_issue(cfg)
    watermarks = read_state(cfg, issue_id)
    deliver = build_board_deliver(cfg, index)
    store = build_document_store(cfg, issue_id)

    def save(updated: dict[int, str]) -> None:
        save_watermarks(store, updated)

    reported = run_tick(issues, watermarks, deliver=deliver, save=save)
    for number in reported:
        print(f"reported #{number}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
