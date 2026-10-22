"""The socket client.

The broker answers on a unix socket with one JSON object per line in and one
JSON object per line out. There is no other protocol: no HTTP, no TCP port,
nothing a process on another machine can reach.

The answers are deliberately small. A token comes back over the socket and
goes straight into the caller's environment; it is never written to a file, a
log or a comment.
"""

from __future__ import annotations

import json
import socket
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .core import DEFAULT_SOCKET_PATH, BrokerError


class BrokerUnavailable(BrokerError):
    """The broker is not listening, or did not answer in time."""


def request(
    payload: Mapping[str, Any],
    socket_path: Path | str | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Send one request to the broker and return its answer.

    The answer is the raw JSON object; the caller decides what `ok: false`
    means for it. A socket that cannot be reached is `BrokerUnavailable`,
    which is a different thing from a refusal and is reported as such.
    """
    target = Path(socket_path) if socket_path is not None else DEFAULT_SOCKET_PATH
    line = json.dumps(payload, sort_keys=True).encode("utf-8") + b"\n"
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(timeout)
            client.connect(str(target))
            client.sendall(line)
            chunks: list[bytes] = []
            while True:
                chunk = client.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
                if b"\n" in chunk:
                    break
    except (OSError, socket.timeout) as exc:
        raise BrokerUnavailable(
            f"the broker did not answer on {target}: {exc}"
        ) from exc
    raw = b"".join(chunks).split(b"\n", 1)[0]
    if not raw.strip():
        raise BrokerUnavailable(f"the broker closed the connection on {target} without answering")
    try:
        answer = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BrokerUnavailable(f"the broker answered something that is not JSON: {exc}") from exc
    if not isinstance(answer, dict):
        raise BrokerUnavailable("the broker answered something that is not an object")
    return answer


def github_token(
    run_jwt: str,
    *,
    socket_path: Path | str | None = None,
    repo: str | None = None,
    permissions: list[str] | None = None,
    head_sha: str | None = None,
) -> dict[str, Any]:
    """Ask the broker for a token for this run."""
    payload: dict[str, Any] = {"op": "github-token", "run_jwt": run_jwt}
    if repo:
        payload["repo"] = repo
    if permissions is not None:
        payload["permissions"] = list(permissions)
    if head_sha:
        payload["head_sha"] = head_sha
    return request(payload, socket_path)


def revoke(
    run_jwt: str,
    *,
    socket_path: Path | str | None = None,
) -> dict[str, Any]:
    """Ask the broker to revoke the token it minted for this run."""
    return request({"op": "revoke", "run_jwt": run_jwt}, socket_path)


def health(*, socket_path: Path | str | None = None) -> dict[str, Any]:
    """Ask the broker how it is."""
    return request({"op": "health"}, socket_path)
