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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .core import (
    APP_MODE,
    DEFAULT_AUTH_MODE_PATH,
    DEFAULT_SOCKET_PATH,
    DEFAULT_STATE_DIR,
    INSTALLATION_TOKEN_TTL_SECONDS,
    AuthError,
    BrokerError,
    Policy,
    RefusedError,
    TokenError,
    agent_ids_from_commit_message,
    audit,
    last4,
    read_auth_mode,
)
from .github import GitHubClient, InstallationToken, noreply_address
from .paperclip import (
    PaperclipClient,
    PaperclipError,
    RunContext,
    resolve_run_context,
    verify_run_credential,
)

#: How many failed health ticks in a row are an alert. Two: one failed tick
#: is a hiccup, two in a row is the broker down.
ALERT_AFTER_FAILURES = 2

#: The mode the socket is created with: the owner and the seat group.
SOCKET_MODE = 0o660
#: The group the seats are in.
SOCKET_GROUP = "_dtseats"


def _as_pr_number(value: Any) -> int | None:
    """A pull request number, when the request carries one."""
    if value is None:
        return None
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


@dataclass
class _Issued:
    """One token this daemon minted, and when it minted it.

    The time it was minted is kept because GitHub's answer carries an
    expiry in its own format, and the daemon needs to know whether a token
    is still worth handing out before it hands it out again.
    """

    token: InstallationToken
    issued_at: float
    repositories: tuple[str, ...]
    permissions: dict[str, str]

    def usable_at(self, now: float) -> bool:
        """True while the token is still worth handing to a caller."""
        return now - self.issued_at < INSTALLATION_TOKEN_TTL_SECONDS - 60

    def expired_at(self, now: float) -> bool:
        """True once GitHub will not honour the token any more."""
        return now - self.issued_at >= INSTALLATION_TOKEN_TTL_SECONDS


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
        # a run is short, so this map holds a handful of entries; the tokens
        # are here so that `revoke` can find them at the end of the run.
        # A run may hold more than one: a token is kept per repository and
        # permission set, and every one of them is revoked together.
        self._issued: dict[str, list[_Issued]] = {}
        #: The credential each run presented, kept in memory so the daemon
        #: can ask whether that run is still running and revoke what it
        #: minted for it. It is never written down and never logged.
        self._run_credentials: dict[str, str] = {}
        self._lock = threading.Lock()
        #: Set when the socket could not be given to the seat group. A seat
        #: that cannot connect to a broker that looks healthy is the worst
        #: kind of healthy, so the health tick says so.
        self.socket_group_error: str | None = None

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

        if self.auth_mode() != APP_MODE:
            raise RefusedError(
                "the rollback flag says the host's own credentials are in charge, so the "
                "broker does not mint tokens"
            )

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
                    "the repository asked for is not the repository this run is working on "
                    f"({repo}); a token is scoped to the ticket's own repository"
                )

        permissions = self.policy.select_permissions(
            seat_class, request.get("permissions")
        )

        head_sha = str(request.get("head_sha") or "").strip()
        pr: int | None = None
        if self.policy.is_review_class(seat_class):
            pr, head_sha = self._check_review_independence(
                context,
                app,
                repo,
                _as_pr_number(request.get("pr_number")),
                head_sha,
            )

        now = time.time()
        existing = self._reusable_token(context.run_id, repo, permissions, now)
        if existing is not None:
            token = existing.token
            reused = True
        else:
            token = self.github.mint_installation_token(
                app=app,
                repositories=[repo],
                permissions=permissions,
            )
            with self._lock:
                self._issued.setdefault(context.run_id, []).append(
                    _Issued(
                        token=token,
                        issued_at=now,
                        repositories=(repo,),
                        permissions=dict(permissions),
                    )
                )
            reused = False
        with self._lock:
            self._run_credentials[context.run_id] = run_jwt

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
            reused=reused,
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
        if pr is not None:
            # The token is bound to one pull request, and the head commit is
            # the one GitHub says that pull request has. The caller is told
            # both so it can check that the call it makes is about that
            # pull request.
            answer["pr_number"] = pr
            answer["head_sha"] = head_sha
        return answer

    def _reusable_token(
        self,
        run_id: str,
        repo: str,
        permissions: Mapping[str, str],
        now: float,
    ) -> _Issued | None:
        """A token this run already holds for the same job, if there is one.

        A seat makes many `gh` calls in a run. Minting a fresh installation
        token for each one leaves a token behind for every call but the last,
        and the revocation at the end of the run only knows about the last
        one. One token per run, per repository and permission set, is both
        safer and cheaper.
        """
        with self._lock:
            entries = self._issued.get(run_id, [])
            for entry in entries:
                if (
                    entry.usable_at(now)
                    and entry.repositories == (repo,)
                    and entry.permissions == dict(permissions)
                ):
                    return entry
        return None

    def _prune(self, now: float) -> None:
        """Drop the tokens GitHub will not honour any more."""
        with self._lock:
            for run_id in list(self._issued):
                kept = [
                    entry
                    for entry in self._issued[run_id]
                    if not entry.expired_at(now)
                ]
                if kept:
                    self._issued[run_id] = kept
                else:
                    del self._issued[run_id]

    def _check_review_independence(
        self,
        context: RunContext,
        app: Any,
        repo: str,
        pr_number: int | None,
        head_sha: str,
    ) -> tuple[int, str]:
        """Refuse a seat that would review its own change.

        The change under review is a pull request, and the pull request is
        read from GitHub. The head commit comes from the pull request
        itself, not from the caller: a caller that named the commit would
        be naming the commit it wanted a token for.

        The owner is read from the trailers of that head commit, which is
        where every seat writes the seat and the run that wrote it. Only
        the `Paperclip-Agent-Id` trailer counts: the `Paperclip-Seat`
        trailer names the App, and every seat that uses that App writes the
        same name there.
        """
        if not pr_number:
            raise RefusedError(
                "a review token needs the pull request it is for, so the head commit "
                "can be read from it"
            )
        pull = self.github.pull_request(app, repo, pr_number)
        head = pull.get("head")
        actual = str(head.get("sha") or "") if isinstance(head, Mapping) else ""
        if not actual:
            raise RefusedError(
                f"pull request {pr_number} in {repo} names no head commit, so there is "
                "nothing to review"
            )
        if head_sha and head_sha != actual:
            raise RefusedError(
                f"the commit asked for is not the head of pull request {pr_number}"
            )
        message = self.github.commit_message(app, repo, actual)
        owners = agent_ids_from_commit_message(message)
        requester = context.agent_id.strip().lower()
        if not owners:
            raise RefusedError(
                "the head commit of that pull request names no agent id, so its author "
                "cannot be told apart from the reviewer; a review token needs a commit "
                "with a Paperclip-Agent-Id trailer"
            )
        if any(owner.strip().lower() == requester for owner in owners):
            raise RefusedError(
                f"seat {context.agent_id} wrote the change under review; a seat may not "
                "review its own change"
            )
        return pr_number, actual

    def op_revoke(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """Revoke the tokens this daemon minted for a run.

        The credential is verified against the Paperclip API first, the same
        way a mint is: a run id read out of an unverified credential is not
        a run id, and a revocation that trusted one would let any caller
        kill another run's token.

        A token GitHub will not revoke is still live at GitHub, so it stays
        in the ledger and the next revocation tries again. Dropping it here
        would leave it alive for the rest of its hour with nobody left to
        revoke it.
        """
        run_jwt = str(request.get("run_jwt") or "")
        if not run_jwt:
            raise RefusedError("no run credential was supplied")
        try:
            agent_id, run_id, _ = verify_run_credential(self._paperclip(run_jwt), run_jwt)
        except PaperclipError as exc:
            raise AuthError(f"the run credential was refused: {exc}") from exc
        with self._lock:
            entries = list(self._issued.get(run_id, []))
        if not entries:
            self._log("revoke-noop", run_id=run_id, agent_id=agent_id)
            return {"ok": True, "revoked": False, "run_id": run_id}
        revoked = 0
        failed: list[_Issued] = []
        for entry in entries:
            try:
                self.github.revoke_installation_token(entry.token.token)
            except TokenError:
                failed.append(entry)
                continue
            revoked += 1
            self._log(
                "revoke",
                run_id=run_id,
                agent_id=agent_id,
                repositories=list(entry.repositories),
                expires_at=entry.token.expires_at,
                token_last4=last4(entry.token.token),
            )
        with self._lock:
            remaining = self._issued.get(run_id, [])
            kept = [
                entry for entry in remaining if any(entry is item for item in failed)
            ]
            if kept:
                self._issued[run_id] = kept
            else:
                self._issued.pop(run_id, None)
        return {
            "ok": True,
            "revoked": bool(revoked),
            "run_id": run_id,
            "tokens": revoked,
            "failed": len(failed),
        }

    def sweep_finished_runs(self) -> int:
        """Revoke what was minted for the runs that have ended.

        The daemon promises that it revokes what it minted when the run
        ends, so it has to ask whether the run is still running. The run is
        asked with the credential the run itself presented, which the
        Paperclip API accepts after the run is over -- the same reason a
        revocation is allowed at the end of a run at all.

        A run that cannot be asked about is left alone. A token expires at
        GitHub within the hour anyway, and a sweep that revoked on a failed
        read would take away a live run's token.
        """
        with self._lock:
            runs = {
                run_id: list(entries)
                for run_id, entries in self._issued.items()
                if entries
            }
            credentials = dict(self._run_credentials)
        revoked = 0
        for run_id in runs:
            credential = credentials.get(run_id)
            if not credential:
                continue
            try:
                run = self._paperclip(credential).heartbeat_run(run_id)
            except (PaperclipError, BrokerError):
                continue
            status = str(run.get("status") or "").strip().lower()
            if not status or status == "running":
                continue
            try:
                answer = self.op_revoke({"run_jwt": credential})
            except (AuthError, BrokerError):
                continue
            if answer.get("revoked"):
                revoked += int(answer.get("tokens") or 0)
        return revoked

    def op_health(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """How the daemon is.

        The answer's own `ok` is the health's `ok`: a watchdog that reads the
        exit code must not be told "healthy" while the alert file is on
        disk.
        """
        record = self.health_record()
        return {"ok": bool(record.get("ok")), "health": record}

    def op_identity(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """The bot identity the calling seat commits under."""
        run_jwt = str(request.get("run_jwt") or "")
        if not run_jwt:
            raise RefusedError("no run credential was supplied")
        context = resolve_run_context(self._paperclip(run_jwt), run_jwt)
        binding = self.policy.seat_for(context.agent_id)
        seat_class = self.policy.class_for(binding)
        app = self.policy.app_for(seat_class)
        bot_id = self.github.user_id(app, app.bot_login)
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
        and the socket must still be on disk, with the group the seats are
        in. What the tick buys is the count of consecutive failures, which
        is what the alert is about.
        """
        failures = 0
        detail = ""
        self._prune(time.time())
        try:
            self.sweep_finished_runs()
        except (BrokerError, OSError):  # pragma: no cover - the sweep is best effort
            pass
        if self.policy_path is not None:
            try:
                Policy.load(self.policy_path)
            except BrokerError as exc:
                failures += 1
                detail = str(exc)
        if not detail and self.socket_path is not None and not self.socket_path.exists():
            failures += 1
            detail = f"the socket {self.socket_path} is gone"
        if not detail and self.socket_group_error:
            failures += 1
            detail = self.socket_group_error
        if not detail and self.socket_path is not None and not _socket_group_ok(
            self.socket_path
        ):
            failures += 1
            detail = (
                f"the socket {self.socket_path} is not in the {SOCKET_GROUP} group, so no "
                "seat can connect to it"
            )
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
            try:
                self.state_dir.chmod(0o750)
            except OSError:
                pass
            path = self.state_dir / "health.json"
            handle = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o640)
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(json.dumps(record, indent=2, sort_keys=True) + "\n")
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
        """Start the loop in a thread.

        The first tick happens at once: a daemon that has just started has
        not written a health record yet, and "no health record" must not
        read as "unhealthy" for the first minute of its life.
        """
        if self._thread is not None:
            return
        try:
            self.run_once()
        except Exception:  # pragma: no cover - the first tick must not kill us
            pass

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
        try:
            self.wfile.write(json.dumps(answer, sort_keys=True).encode("utf-8") + b"\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            # The caller gave up before the answer was written -- the token
            # was still minted, and it is still revoked at the end of the run.
            return


class BrokerServer(socketserver.ThreadingUnixStreamServer):
    """The socket server."""

    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, socket_path: Path, service: BrokerService) -> None:
        self.socket_path = Path(socket_path)
        self.service = service
        super().__init__(str(self.socket_path), _Handler)

    def server_bind(self) -> None:
        # The socket is created by `bind`, and it exists with the mode the
        # process's umask allows until the `chmod` below. The umask is set
        # for the moment of the bind, so the socket is never readable by
        # anyone but its owner and the seat group.
        previous = os.umask(0o117)
        try:
            super().server_bind()
        finally:
            os.umask(previous)
        os.chmod(self.socket_path, SOCKET_MODE)
        if not _set_group(self.socket_path, SOCKET_GROUP):
            self.service.socket_group_error = (
                f"the socket {self.socket_path} could not be given to the group "
                f"{SOCKET_GROUP}, so no seat can connect to it"
            )


def _seat_group_gid(group: str) -> int | None:
    """The gid of the seat group, when it exists on this host."""
    try:
        import grp

        return int(grp.getgrnam(group).gr_gid)
    except (ImportError, KeyError, TypeError, ValueError):
        return None


def _socket_group_ok(path: Path) -> bool:
    """True when the socket is in the seat group."""
    gid = _seat_group_gid(SOCKET_GROUP)
    if gid is None:
        # The group does not exist on this host: there is nothing to check
        # against, and the daemon is not going to invent one.
        return True
    try:
        return os.stat(path).st_gid == gid
    except OSError:
        return False


def _set_group(path: Path, group: str) -> bool:
    """Give the socket to the seat group, when the daemon may do so.

    The daemon runs as `_dtbroker`, which is a member of `_dtseats`; a group
    it does not belong to is left alone rather than guessed at, and the
    failure is written down rather than swallowed.
    """
    gid = _seat_group_gid(group)
    if gid is None:
        return False
    try:
        os.chown(path, -1, gid)
    except (OSError, PermissionError):
        return False
    return True


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
