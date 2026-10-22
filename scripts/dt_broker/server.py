"""The broker daemon.

One process, one unix socket, four operations: `github-token`, `revoke`,
`health` and `identity`. The daemon is the only holder of the App private
keys, so it is also the only place a policy decision can be made.

The daemon does not decide anything by itself: `Policy` holds the rules and
`BrokerService` applies them. This module is the transport around that.

Two things the daemon is careful about:

* It runs as `_dtbroker`, so the socket is created with mode 0660 and the
  group `_dtseats`. A seat can talk to it; a process that is not a seat
  cannot.
* It answers a health tick and remembers how many ticks have failed in a
  row. After two failed ticks it writes an alert file, because a daemon that
  has stopped working must not look exactly like a daemon that has stopped
  being asked.
"""

from __future__ import annotations

import json
import os
import socket
import socketserver
import threading
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .core import (
    APP_MODE,
    DEFAULT_AUTH_MODE_PATH,
    DEFAULT_SOCKET_PATH,
    DEFAULT_STATE_DIR,
    AuthError,
    BrokerError,
    Policy,
    RefusedError,
    audit,
    decode_jwt_claims,
    last4,
    owner_from_commit_message,
    read_auth_mode,
)
from .github import GitHubClient, InstallationToken, noreply_address
from .paperclip import PaperclipClient, RunContext, resolve_run_context

#: How many failed health ticks in a row are an alert. Two: one failed tick
#: is a hiccup, two in a row is the broker down.
ALERT_AFTER_FAILURES = 2

#: The mode the socket is created with: the owner and the seat group.
SOCKET_MODE = 0o660
#: The group the seats are in.
SOCKET_GROUP = "_dtseats"


class BrokerService:
    """The policy engine behind the socket.

    Every method answers with a dictionary. `ok: true` carries the answer;
    `ok: false` carries `error` and `code`, and never carries a token.
    """

    def __init__(
        self,
        policy: Policy,
        *,
        github: GitHubClient | None = None,
        state_dir: Path | None = None,
        log_path: Path | None = None,
        auth_mode_path: Path | None = None,
        policy_path: Path | None = None,
        socket_path: Path | None = None,
        paperclip_transport: Any = None,
    ) -> None:
        self.policy = policy
        self.github = github or GitHubClient()
        self.state_dir = Path(state_dir) if state_dir else DEFAULT_STATE_DIR
        self.log_path = Path(log_path) if log_path else self.state_dir / "dt-broker.jsonl"
        self.auth_mode_path = (
            Path(auth_mode_path) if auth_mode_path else DEFAULT_AUTH_MODE_PATH
        )
        self.policy_path = Path(policy_path) if policy_path else None
        self.socket_path = Path(socket_path) if socket_path else None
        self._paperclip_transport = paperclip_transport
        # The tokens this daemon minted, by run. The daemon is long-lived and
        # a run is short, so this map holds a handful of entries; the token
        # is here so that `revoke` can find it at the end of the run.
        self._issued: dict[str, InstallationToken] = {}
        self._lock = threading.Lock()

    # -- helpers --------------------------------------------------------

    def _log(self, event: str, **fields: Any) -> None:
        audit(self.log_path, event, **fields)

    def _paperclip(self, run_jwt: str) -> PaperclipClient:
        return PaperclipClient(
            self.policy.paperclip_api_url,
            run_jwt,
            transport=self._paperclip_transport,
        )

    def auth_mode(self) -> str:
        """The rollback flag, as the daemon sees it."""
        return read_auth_mode(self.auth_mode_path)

    # -- operations -----------------------------------------------------

    def handle(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """Answer one request."""
        op = str(request.get("op") or "").strip()
        handler = {
            "github-token": self.op_github_token,
            "revoke": self.op_revoke,
            "health": self.op_health,
            "identity": self.op_identity,
        }.get(op)
        if handler is None:
            return _failure(f"unknown operation: {op or '(none)'}", "unknown_op")
        try:
            return handler(request)
        except RefusedError as exc:
            return _failure(str(exc), "refused")
        except AuthError as exc:
            return _failure(str(exc), "auth")
        except BrokerError as exc:
            return _failure(str(exc), "broker_error")

    def op_github_token(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """Mint a token for the run that asked."""
        run_jwt = str(request.get("run_jwt") or "")
        if not run_jwt:
            raise RefusedError("no run credential was supplied")

        context = resolve_run_context(self._paperclip(run_jwt), run_jwt)
        binding = self.policy.seat_for(context.agent_id)
        seat_class = self.policy.class_for(binding)
        app = self.policy.app_for(seat_class)

        repo = self.policy.check_org(context.repo)
        repo = self.policy.check_repo_allowed(binding, repo)

        asked_for = request.get("repo")
        if asked_for:
            asked = str(asked_for).strip()
            if asked.lower() != repo.lower():
                raise RefusedError(
                    f"{asked} is not the repository this run is working on ({repo}); "
                    "a token is scoped to the ticket's own repository"
                )

        permissions = self.policy.select_permissions(
            seat_class, request.get("permissions")
        )

        head_sha = str(request.get("head_sha") or "").strip()
        if self.policy.is_review_class(seat_class):
            self._check_review_independence(context, seat_class, repo, head_sha)

        token = self.github.mint_installation_token(
            app=app,
            repositories=[repo],
            permissions=permissions,
        )
        with self._lock:
            self._issued[context.run_id] = token

        self._log(
            "github-token",
            run_id=context.run_id,
            agent_id=context.agent_id,
            issue_id=context.issue_id,
            seat_class=seat_class.name,
            **app.to_record(),
            repositories=[repo],
            permissions=dict(permissions),
            expires_at=token.expires_at,
            token_last4=last4(token.token),
        )
        answer: dict[str, Any] = {
            "ok": True,
            "token": token.token,
            "expires_at": token.expires_at,
            "repositories": [repo],
            "permissions": dict(permissions),
            "app": app.name,
            "seat_class": seat_class.name,
            "run_id": context.run_id,
        }
        return answer

    def _check_review_independence(
        self,
        context: RunContext,
        seat_class: Any,
        repo: str,
        head_sha: str,
    ) -> None:
        """Refuse a seat that would review its own change.

        The change owner is read from the trailers of the head commit, which
        is where every seat writes the seat and the run that wrote it.
        """
        if not head_sha:
            raise RefusedError(
                "a review token needs the head commit of the change under review"
            )
        message = self.github.commit_message(repo, head_sha)
        owner = owner_from_commit_message(message)
        if owner and owner.strip().lower() == context.agent_id.strip().lower():
            raise RefusedError(
                f"seat {context.agent_id} wrote the change at {head_sha}; "
                "a seat may not review its own change"
            )

    def op_revoke(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """Revoke the token this daemon minted for a run."""
        run_jwt = str(request.get("run_jwt") or "")
        if not run_jwt:
            raise RefusedError("no run credential was supplied")
        claims = decode_jwt_claims(run_jwt)
        run_id = str(claims.get("run_id") or "")
        with self._lock:
            token = self._issued.pop(run_id, None)
        if token is None:
            self._log("revoke-noop", run_id=run_id)
            return {"ok": True, "revoked": False, "run_id": run_id}
        self.github.revoke_installation_token(token.token)
        self._log(
            "revoke",
            run_id=run_id,
            repositories=list(token.repositories),
            expires_at=token.expires_at,
            token_last4=last4(token.token),
        )
        return {"ok": True, "revoked": True, "run_id": run_id}

    def op_health(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """How the daemon is."""
        return {"ok": True, "health": self.health_record()}

    def op_identity(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """The bot identity the calling seat commits under."""
        run_jwt = str(request.get("run_jwt") or "")
        if not run_jwt:
            raise RefusedError("no run credential was supplied")
        context = resolve_run_context(self._paperclip(run_jwt), run_jwt)
        binding = self.policy.seat_for(context.agent_id)
        seat_class = self.policy.class_for(binding)
        app = self.policy.app_for(seat_class)
        bot_id = self.github.user_id(app.bot_login)
        return {
            "ok": True,
            "name": app.bot_login,
            "email": noreply_address(app.bot_login, bot_id),
            "app": app.name,
            "run_id": context.run_id,
            "agent_id": context.agent_id,
        }

    # -- health ---------------------------------------------------------

    def health_record(self) -> dict[str, Any]:
        """The health file's contents, as a dictionary."""
        path = self.state_dir / "health.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"ok": False, "detail": "no health record has been written yet"}

    def tick(self) -> dict[str, Any]:
        """One health tick.

        The probe is deliberately dull: the policy file must still be there
        and the socket must still be on disk. What the tick buys is the
        count of consecutive failures, which is what the alert is about.
        """
        failures = 0
        detail = ""
        if self.policy_path is not None:
            try:
                Policy.load(self.policy_path)
            except BrokerError as exc:
                failures += 1
                detail = str(exc)
        if not detail and self.socket_path is not None and not self.socket_path.exists():
            failures += 1
            detail = f"the socket {self.socket_path} is gone"
        record = {
            "ok": failures == 0,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "pid": os.getpid(),
            "consecutive_failures": failures,
        }
        if detail:
            record["detail"] = detail
        self._write_health(record)
        return record

    def _write_health(self, record: Mapping[str, Any]) -> None:
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            (self.state_dir / "health.json").write_text(
                json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        except OSError:
            pass


class HealthMonitor:
    """The tick loop and the alert it raises.

    The alert is a file, not a message: the daemon is a local process with
    no board account, and the seat's watchdog reads the file. The board is
    told by the watchdog, not by the daemon pretending it can talk to it.
    """

    def __init__(
        self,
        service: BrokerService,
        *,
        interval: float = 60.0,
        alert_after: int = ALERT_AFTER_FAILURES,
    ) -> None:
        self.service = service
        self.interval = interval
        self.alert_after = alert_after
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def run_once(self) -> dict[str, Any]:
        """One tick, with the alert raised when the failures pile up."""
        previous = self.service.health_record()
        count = int(previous.get("consecutive_failures") or 0) if previous else 0
        record = self.service.tick()
        if record.get("ok"):
            count = 0
        else:
            count += 1
        record["consecutive_failures"] = count
        self.service._write_health(record)
        alert_path = self.service.state_dir / "alert.json"
        if count >= self.alert_after:
            alert = {
                "ok": False,
                "ts": record.get("ts"),
                "detail": record.get("detail", "the broker health check failed"),
                "consecutive_failures": count,
            }
            try:
                self.service.state_dir.mkdir(parents=True, exist_ok=True)
                alert_path.write_text(
                    json.dumps(alert, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                )
            except OSError:
                pass
            self.service._log("alert", **alert)
        elif alert_path.exists():
            try:
                alert_path.unlink()
            except OSError:
                pass
        return record

    def start(self) -> None:
        """Start the loop in a thread."""
        if self._thread is not None:
            return

        def _loop() -> None:
            while not self._stop.wait(self.interval):
                try:
                    self.run_once()
                except Exception:  # pragma: no cover - the loop must not die
                    continue

        self._thread = threading.Thread(target=_loop, name="dt-broker-health", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the loop."""
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=5)
        self._thread = None


class _Handler(socketserver.StreamRequestHandler):
    """One connection: one JSON line in, one JSON line out."""

    def handle(self) -> None:
        service: BrokerService = self.server.service  # type: ignore[attr-defined]
        line = self.rfile.readline(1 << 20)
        if not line.strip():
            return
        try:
            request = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            answer: dict[str, Any] = _failure(f"the request is not JSON: {exc}", "bad_request")
        else:
            if not isinstance(request, dict):
                answer = _failure("the request is not an object", "bad_request")
            else:
                answer = service.handle(request)
        self.wfile.write(json.dumps(answer, sort_keys=True).encode("utf-8") + b"\n")
        self.wfile.flush()


class BrokerServer(socketserver.ThreadingUnixStreamServer):
    """The socket server."""

    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, socket_path: Path, service: BrokerService) -> None:
        self.socket_path = Path(socket_path)
        self.service = service
        super().__init__(str(self.socket_path), _Handler)

    def server_bind(self) -> None:
        super().server_bind()
        os.chmod(self.socket_path, SOCKET_MODE)
        _set_group(self.socket_path, SOCKET_GROUP)


def _set_group(path: Path, group: str) -> None:
    """Give the socket to the seat group, when the daemon may do so.

    The daemon runs as `_dtbroker`, which is a member of `_dtseats`; a group
    it does not belong to is left alone rather than guessed at, and the
    failure is written down.
    """
    try:
        import grp

        gid = grp.getgrnam(group).gr_gid
    except (ImportError, KeyError):
        return
    try:
        os.chown(path, -1, gid)
    except (OSError, PermissionError):
        pass


def _failure(message: str, code: str) -> dict[str, Any]:
    """A refusal, in the shape the client expects."""
    return {"ok": False, "error": message, "code": code}


def serve(
    socket_path: Path | str = DEFAULT_SOCKET_PATH,
    *,
    policy: Policy,
    github: GitHubClient | None = None,
    state_dir: Path | None = None,
    log_path: Path | None = None,
    auth_mode_path: Path | None = None,
    policy_path: Path | None = None,
    health_interval: float = 60.0,
) -> None:
    """Run the daemon until it is stopped."""
    target = Path(socket_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    service = BrokerService(
        policy,
        github=github,
        state_dir=state_dir,
        log_path=log_path,
        auth_mode_path=auth_mode_path,
        policy_path=policy_path,
        socket_path=target,
    )
    server = BrokerServer(target, service)
    monitor = HealthMonitor(service, interval=health_interval)
    monitor.start()
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        monitor.stop()
        server.server_close()
        try:
            target.unlink()
        except OSError:
            pass


def socket_is_live(socket_path: Path | str = DEFAULT_SOCKET_PATH) -> bool:
    """True when something is listening on the socket."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(2)
            client.connect(str(socket_path))
        return True
    except OSError:
        return False


#: Kept for the CLI, which prints the mode it is in before it does anything.
AUTH_MODE_APP = APP_MODE
