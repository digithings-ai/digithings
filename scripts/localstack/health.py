"""The local-stack health gate (plan section 6).

Runs the catalogue from :mod:`scripts.localstack.contracts` and returns one
verdict per check. The gate is deliberately boring about verdicts:

* ``passed`` -- the probe ran and the response was what it demanded;
* ``failed`` -- the probe ran and the response was wrong, or it could not connect;
* ``skipped`` -- the probe **could not run**, because it needs configuration it
  does not have.

``skipped`` is the one that gets people into trouble. A check that could not
run is not a passing check, so it is never reported as one, and
``--require-all`` turns any skip into a failure so CI can demand zero of them.

Nothing here invents an endpoint. Checks that could not be sourced from the
repository arrive with ``url=None`` and skip with a reason.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .contracts import FAILED, PASSED, SKIPPED, Check, resolve

DEFAULT_TIMEOUT = 5.0

#: JSON-RPC request used by the MCP probe.
MCP_TOOLS_LIST: dict[str, Any] = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/list",
    "params": {},
}


@dataclass(frozen=True)
class Result:
    name: str
    status: str
    detail: str
    url: str | None
    elapsed_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "url": self.url,
            "elapsed_ms": self.elapsed_ms,
        }


@dataclass(frozen=True)
class GateReport:
    results: tuple[Result, ...]
    profile: str
    origin: str
    require_all: bool = False

    @property
    def failed(self) -> tuple[Result, ...]:
        return tuple(r for r in self.results if r.status == FAILED)

    @property
    def skipped(self) -> tuple[Result, ...]:
        return tuple(r for r in self.results if r.status == SKIPPED)

    @property
    def passed(self) -> tuple[Result, ...]:
        return tuple(r for r in self.results if r.status == PASSED)

    @property
    def ok(self) -> bool:
        """Gate verdict. Any failure fails it; any skip fails it under ``--require-all``."""
        if self.failed:
            return False
        return not (self.require_all and self.skipped)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "profile": self.profile,
            "origin": self.origin,
            "require_all": self.require_all,
            "counts": {
                "passed": len(self.passed),
                "failed": len(self.failed),
                "skipped": len(self.skipped),
                "total": len(self.results),
            },
            "results": [r.to_dict() for r in self.results],
        }


def new_nonce() -> str:
    return uuid.uuid4().hex[:12]


def _request(
    url: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    content_type: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[int, bytes]:
    """Perform one HTTP request. Raises on transport failure or bad status."""
    headers = {"User-Agent": "dt-health/1"}
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return int(resp.status), resp.read()


def probe_http(
    url: str,
    *,
    method: str = "GET",
    expect_status: tuple[int, ...] = (200,),
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[str, str]:
    """Return ``(status, detail)`` -- never raises."""
    started = time.monotonic()
    try:
        code, payload = _request(url, method=method, timeout=timeout)
    except urllib.error.HTTPError as exc:
        return FAILED, f"HTTP {exc.code}"
    except Exception as exc:
        return FAILED, f"{type(exc).__name__}: {exc}"
    if code not in expect_status:
        return FAILED, f"HTTP {code}, expected {'/'.join(str(s) for s in expect_status)}"
    ms = (time.monotonic() - started) * 1000
    return PASSED, f"HTTP {code}, {len(payload)} bytes, {ms:.0f} ms"


def probe_jsonrpc(url: str, *, timeout: float = DEFAULT_TIMEOUT) -> tuple[str, str]:
    """POST a JSON-RPC ``tools/list`` and require a ``result.tools`` array.

    An MCP error can arrive as HTTP 200 with an ``error`` member, so the status
    code alone is not the verdict -- the body is checked too.
    """
    body = json.dumps(MCP_TOOLS_LIST).encode("utf-8")
    try:
        code, payload = _request(
            url, method="POST", body=body, content_type="application/json", timeout=timeout
        )
    except urllib.error.HTTPError as exc:
        return FAILED, f"HTTP {exc.code}"
    except Exception as exc:
        return FAILED, f"{type(exc).__name__}: {exc}"
    if code != 200:
        return FAILED, f"HTTP {code}, expected 200"
    try:
        parsed = json.loads(payload)
    except ValueError:
        return FAILED, "response was not JSON"
    if not isinstance(parsed, dict):
        return FAILED, "response was not a JSON object"
    if "error" in parsed:
        return FAILED, f"JSON-RPC error: {parsed['error']}"
    tools = (
        parsed.get("result", {}).get("tools") if isinstance(parsed.get("result"), dict) else None
    )
    if not isinstance(tools, list):
        return FAILED, "no result.tools array in the response"
    return PASSED, f"tools/list returned {len(tools)} tools"


def probe_roundtrip(
    url: str,
    nonce: str,
    *,
    read_path: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[str, str]:
    """Write ``nonce`` then read it back.

    A storage binding that answers 200 to a write but returns nothing on the
    read is not healthy, so the read-back is the part that carries the verdict.

    ``url`` is the write endpoint and is written to exactly as configured - no
    trailing slash is appended, because a local binding route is keyed on the
    path it is given. ``read_path`` is origin-relative (it replaces the url's
    path); by default the read-back reads the same path that was written.
    """
    payload = json.dumps({"probe": nonce}).encode("utf-8")
    try:
        _request(url, method="POST", body=payload, content_type="application/json", timeout=timeout)
    except urllib.error.HTTPError as exc:
        return FAILED, f"write failed: HTTP {exc.code}"
    except Exception as exc:
        return FAILED, f"write failed: {type(exc).__name__}: {exc}"

    if read_path:
        split = urllib.parse.urlsplit(url)
        read_url = urllib.parse.urlunsplit((split.scheme, split.netloc, read_path, "", ""))
    else:
        read_url = url
    try:
        code, body = _request(read_url, timeout=timeout)
    except urllib.error.HTTPError as exc:
        return FAILED, f"read-back failed: HTTP {exc.code}"
    except Exception as exc:
        return FAILED, f"read-back failed: {type(exc).__name__}: {exc}"
    if code != 200:
        return FAILED, f"read-back failed: HTTP {code}"
    if nonce not in body.decode("utf-8", "replace"):
        return FAILED, f"read-back did not return the written value (HTTP {code})"
    return PASSED, "write/read-back returned the written value"


PROBES: dict[str, Callable[..., tuple[str, str]]] = {
    "http": probe_http,
    "jsonrpc": probe_jsonrpc,
    "roundtrip": probe_roundtrip,
}


def run_check(
    check: Check,
    *,
    config: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    nonce: str | None = None,
) -> Result:
    """Probe one check and classify the outcome."""
    config = config or {}
    url, reason = resolve(check, config)
    if url is None:
        return Result(check.name, SKIPPED, reason or "no url configured", None, 0)

    probe = PROBES.get(check.kind)
    if probe is None:
        return Result(check.name, SKIPPED, f"unknown probe kind {check.kind!r}", url, 0)

    started = time.monotonic()
    try:
        if check.kind == "roundtrip":
            status, detail = probe(
                url, nonce or new_nonce(), read_path=check.read_path, timeout=timeout
            )
        elif check.kind == "jsonrpc":
            status, detail = probe(url, timeout=timeout)
        else:
            status, detail = probe(
                url, method=check.method, expect_status=check.expect_status, timeout=timeout
            )
    except TypeError as exc:  # a probe called with the wrong signature
        return Result(check.name, FAILED, f"probe mis-wired: {exc}", url, 0)
    except Exception as exc:  # a probe that raises is a broken check, not a green one
        return Result(check.name, FAILED, f"probe raised {type(exc).__name__}: {exc}", url, 0)

    elapsed = int((time.monotonic() - started) * 1000)
    return Result(check.name, status, detail, url, elapsed)


def run_gate(
    checks: tuple[Check, ...],
    *,
    profile: str = "all",
    origin: str = "built-in defaults",
    config: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    require_all: bool = False,
    nonce: str | None = None,
) -> GateReport:
    """Run every check and decide the gate."""
    results = tuple(
        run_check(check, config=config, timeout=timeout, nonce=nonce) for check in checks
    )
    return GateReport(results, profile=profile, origin=origin, require_all=require_all)
