"""The broker's command line.

Nine jobs, and no others:

* `serve` runs the daemon. The launchd job runs this.
* `health` asks the daemon how it is.
* `auth-mode` prints the rollback flag, so a human can see which way it points.
* `github-token` asks the daemon for a token for this run.
* `git-credential` is the git credential helper a seat run points at.
* `identity` prints the bot identity this run commits under.
* `trailers` prints the commit trailers this run writes.
* `revoke` revokes the token this run was given.
* `seat-env` prints the environment a seat run needs.
* `gh` is the `gh` wrapper: it is not a command, it is the whole call.

None of them writes a token to a file, a log or a ticket. The only place a
token appears is stdout of `github-token --print-token`, which a human asks
for on purpose, and the credential helper's stdout, which git reads.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from . import client as broker_client
from .core import (
    APP_MODE,
    DEFAULT_AUTH_MODE_PATH,
    DEFAULT_POLICY_PATH,
    DEFAULT_SOCKET_PATH,
    DEFAULT_STATE_DIR,
    HOST_MODE,
    BrokerError,
    Policy,
    last4,
    read_auth_mode,
)
from .github import GitHubClient
from .server import serve

EXIT_OK = 0
EXIT_USAGE = 64
EXIT_AUTH = 66
EXIT_UNAVAILABLE = 69
EXIT_INTERNAL = 70
EXIT_REFUSED = 76

#: The host git talks to. The credential helper answers for this host and
#: refuses every other one.
GITHUB_HOSTS = ("github.com", "www.github.com")

#: The organization a seat run may push to. The broker narrows every token
#: to one repository inside it.
ORG = "digithings-ai"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _run_jwt(env: dict[str, str]) -> str:
    """The run credential, or a refusal."""
    token = str(env.get("PAPERCLIP_API_KEY") or "").strip()
    if not token:
        raise BrokerError(
            "no run credential is in the environment; a seat run carries one as "
            "PAPERCLIP_API_KEY"
        )
    return token


def _socket(args: argparse.Namespace) -> str:
    return str(args.socket or DEFAULT_SOCKET_PATH)


def _run_tmp(env: dict[str, str]) -> Path:
    """The scratch directory for this run."""
    explicit = env.get("DT_BROKER_RUN_TMP")
    if explicit:
        return Path(explicit).expanduser()
    run_id = str(env.get("PAPERCLIP_RUN_ID") or "no-run")
    return Path(tempfile.gettempdir()) / f"dt-broker-{run_id}"


def _print_json(payload: Any) -> None:
    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")


# ---------------------------------------------------------------------------
# serve
# ---------------------------------------------------------------------------


def cmd_serve(args: argparse.Namespace, env: dict[str, str]) -> int:
    """Run the daemon."""
    policy = Policy.load(Path(args.policy))
    serve(
        args.socket or DEFAULT_SOCKET_PATH,
        policy=policy,
        github=GitHubClient(),
        state_dir=Path(args.state_dir) if args.state_dir else DEFAULT_STATE_DIR,
        log_path=Path(args.log) if args.log else None,
        auth_mode_path=(
            Path(args.auth_mode_path) if args.auth_mode_path else DEFAULT_AUTH_MODE_PATH
        ),
        policy_path=Path(args.policy),
        health_interval=args.health_interval,
    )
    return EXIT_OK


# ---------------------------------------------------------------------------
# health and auth mode
# ---------------------------------------------------------------------------


def cmd_health(args: argparse.Namespace, env: dict[str, str]) -> int:
    """Ask the daemon how it is."""
    try:
        answer = broker_client.health(socket_path=_socket(args))
    except broker_client.BrokerUnavailable as exc:
        _print_json({"ok": False, "error": str(exc)})
        return EXIT_UNAVAILABLE
    _print_json(answer)
    return EXIT_OK if answer.get("ok") else EXIT_INTERNAL


def cmd_auth_mode(args: argparse.Namespace, env: dict[str, str]) -> int:
    """Print the rollback flag."""
    path = Path(args.path) if args.path else DEFAULT_AUTH_MODE_PATH
    mode = read_auth_mode(path, default=args.default)
    if args.json:
        _print_json({"mode": mode, "path": str(path)})
    else:
        sys.stdout.write(f"{mode}\n")
    return EXIT_OK


# ---------------------------------------------------------------------------
# tokens
# ---------------------------------------------------------------------------


def cmd_github_token(args: argparse.Namespace, env: dict[str, str]) -> int:
    """Ask the daemon for a token for this run."""
    try:
        answer = broker_client.github_token(
            _run_jwt(env),
            socket_path=_socket(args),
            repo=args.repo,
            permissions=list(args.permission) if args.permission else None,
            head_sha=args.head_sha,
        )
    except broker_client.BrokerUnavailable as exc:
        sys.stderr.write(f"dt-broker: {exc}\n")
        return EXIT_UNAVAILABLE
    except BrokerError as exc:
        sys.stderr.write(f"dt-broker: {exc}\n")
        return EXIT_AUTH

    if not answer.get("ok"):
        sys.stderr.write(f"dt-broker: refused: {answer.get('error')}\n")
        return EXIT_REFUSED

    token = str(answer.get("token") or "")
    if args.print_token:
        # Asked for on purpose, on stdout, for a caller that needs the value
        # itself. It is still never written to a file or a log.
        sys.stdout.write(f"{token}\n")
        return EXIT_OK

    _print_json(
        {
            "ok": True,
            "app": answer.get("app"),
            "seat_class": answer.get("seat_class"),
            "repositories": answer.get("repositories"),
            "permissions": answer.get("permissions"),
            "expires_at": answer.get("expires_at"),
            "token_last4": last4(token),
            "run_id": answer.get("run_id"),
        }
    )
    return EXIT_OK


def cmd_revoke(args: argparse.Namespace, env: dict[str, str]) -> int:
    """Revoke the token this run was given."""
    try:
        answer = broker_client.revoke(_run_jwt(env), socket_path=_socket(args))
    except broker_client.BrokerUnavailable as exc:
        sys.stderr.write(f"dt-broker: {exc}\n")
        return EXIT_UNAVAILABLE
    except BrokerError as exc:
        sys.stderr.write(f"dt-broker: {exc}\n")
        return EXIT_AUTH
    if not answer.get("ok"):
        sys.stderr.write(f"dt-broker: refused: {answer.get('error')}\n")
        return EXIT_REFUSED
    _print_json(answer)
    return EXIT_OK


# ---------------------------------------------------------------------------
# identity and trailers
# ---------------------------------------------------------------------------


def _identity(args: argparse.Namespace, env: dict[str, str]) -> dict[str, Any]:
    """Ask the daemon who this run commits as."""
    try:
        answer = broker_client.request(
            {"op": "identity", "run_jwt": _run_jwt(env)}, _socket(args)
        )
    except broker_client.BrokerUnavailable as exc:
        raise BrokerError(f"the broker did not answer: {exc}") from exc
    if not answer.get("ok"):
        raise BrokerError(str(answer.get("error") or "the broker refused"))
    return answer


def cmd_identity(args: argparse.Namespace, env: dict[str, str]) -> int:
    """Print the bot identity this run commits under."""
    try:
        answer = _identity(args, env)
    except BrokerError as exc:
        sys.stderr.write(f"dt-broker: {exc}\n")
        return EXIT_UNAVAILABLE
    if args.json:
        _print_json(answer)
    else:
        sys.stdout.write(f"{answer.get('name')} <{answer.get('email')}>\n")
    return EXIT_OK


def cmd_trailers(args: argparse.Namespace, env: dict[str, str]) -> int:
    """Print the commit trailers this run writes.

    The queue reads `Paperclip-Agent-Id` and `Paperclip-Run-Id`. The broker
    ticket also asks for `Paperclip-Seat` and `Paperclip-Run`. All four are
    printed: a commit that carries them is legible to the queue and to a
    human, and the two naming schemes do not fight over the same trailer.
    """
    agent_id = str(env.get("PAPERCLIP_AGENT_ID") or "").strip()
    run_id = str(env.get("PAPERCLIP_RUN_ID") or "").strip()
    seat = str(env.get("PAPERCLIP_SEAT") or "").strip()
    if not seat:
        try:
            seat = str(_identity(args, env).get("app") or "").strip()
        except BrokerError as exc:
            sys.stderr.write(f"dt-broker: {exc}\n")
            return EXIT_UNAVAILABLE
    lines = [
        f"Paperclip-Agent-Id: {agent_id}",
        f"Paperclip-Run-Id: {run_id}",
        f"Paperclip-Seat: {seat}",
        f"Paperclip-Run: {run_id}",
    ]
    sys.stdout.write("\n".join(lines) + "\n")
    return EXIT_OK


# ---------------------------------------------------------------------------
# the git credential helper
# ---------------------------------------------------------------------------


def _read_credential_request(stream: Any) -> dict[str, str]:
    """Read git's credential request from stdin."""
    request: dict[str, str] = {}
    for raw in stream:
        line = raw.rstrip("\n")
        if not line:
            break
        key, _, value = line.partition("=")
        request[key.strip()] = value
    return request


def _repo_from_path(path: str) -> str | None:
    """`owner/repo` from a credential path, when it has one."""
    cleaned = path.strip("/")
    if cleaned.endswith(".git"):
        cleaned = cleaned[: -len(".git")]
    parts = cleaned.split("/")
    if len(parts) >= 2 and parts[0] and parts[1]:
        return f"{parts[0]}/{parts[1]}"
    return None


def cmd_git_credential(args: argparse.Namespace, env: dict[str, str]) -> int:
    """The git credential helper.

    git asks for a credential; the broker hands out a token that is scoped to
    the repository this run is working on. A host or a repository outside the
    organization is refused here, before the broker is even asked, and the
    refusal says why.
    """
    operation = args.operation
    request = _read_credential_request(sys.stdin)

    if operation == "store":
        # Nothing is stored anywhere: the broker holds the token and the
        # run holds the credential in its memory only.
        return EXIT_OK

    if operation == "erase":
        # The credential is gone; so is the token behind it.
        try:
            broker_client.revoke(_run_jwt(env), socket_path=_socket(args))
        except (broker_client.BrokerUnavailable, BrokerError):
            pass
        return EXIT_OK

    protocol = (request.get("protocol") or "https").strip().lower()
    host = (request.get("host") or "").strip().lower()
    if protocol not in ("https", "http"):
        sys.stderr.write(f"dt-broker: refusing: the protocol {protocol} is not supported\n")
        return EXIT_REFUSED
    if host not in GITHUB_HOSTS:
        sys.stderr.write(
            f"dt-broker: refusing: a credential for {host or '(no host)'} is not one this "
            "run may hold\n"
        )
        return EXIT_REFUSED

    repo = _repo_from_path(request.get("path") or "")
    if repo and repo.split("/", 1)[0].lower() != ORG:
        sys.stderr.write(
            f"dt-broker: refusing: {repo} is outside the {ORG} organization, and a seat run "
            "has no credential outside it\n"
        )
        return EXIT_REFUSED

    try:
        answer = broker_client.github_token(
            _run_jwt(env),
            socket_path=_socket(args),
            repo=repo,
        )
    except broker_client.BrokerUnavailable as exc:
        sys.stderr.write(f"dt-broker: {exc}; the push is not made with host credentials\n")
        return EXIT_UNAVAILABLE
    except BrokerError as exc:
        sys.stderr.write(f"dt-broker: {exc}\n")
        return EXIT_AUTH

    if not answer.get("ok"):
        sys.stderr.write(f"dt-broker: refused: {answer.get('error')}\n")
        return EXIT_REFUSED

    token = str(answer.get("token") or "")
    if not token:
        sys.stderr.write("dt-broker: the broker answered without a token\n")
        return EXIT_INTERNAL
    sys.stdout.write("username=x-access-token\n")
    sys.stdout.write(f"password={token}\n")
    return EXIT_OK


# ---------------------------------------------------------------------------
# the seat environment
# ---------------------------------------------------------------------------


def _write_gitconfig(path: Path) -> Path:
    """The git configuration a seat run uses."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '[credential "https://github.com"]\n'
        "\thelper = !dt-broker git-credential\n",
        encoding="utf-8",
    )
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def cmd_seat_env(args: argparse.Namespace, env: dict[str, str]) -> int:
    """Print the environment a seat run needs.

    The lines are `export` lines, so a wrapper can do
    `eval "$(dt-broker seat-env)"` and be done with it.
    """
    tmp = _run_tmp(env)
    gitconfig = _write_gitconfig(tmp / "gitconfig")
    gh_dir = tmp / "gh"
    gh_dir.mkdir(parents=True, exist_ok=True)
    try:
        gh_dir.chmod(0o700)
    except OSError:
        pass
    for child in gh_dir.iterdir():
        try:
            if child.is_file():
                child.unlink()
        except OSError:
            continue

    try:
        identity = _identity(args, env)
    except BrokerError as exc:
        sys.stderr.write(f"dt-broker: {exc}\n")
        return EXIT_UNAVAILABLE

    name = str(identity.get("name") or "")
    email = str(identity.get("email") or "")
    lines = [
        f"export GIT_CONFIG_GLOBAL={shquote(str(gitconfig))}",
        f"export GH_CONFIG_DIR={shquote(str(gh_dir))}",
        f"export GIT_AUTHOR_NAME={shquote(name)}",
        f"export GIT_AUTHOR_EMAIL={shquote(email)}",
        f"export GIT_COMMITTER_NAME={shquote(name)}",
        f"export GIT_COMMITTER_EMAIL={shquote(email)}",
    ]
    sys.stdout.write("\n".join(lines) + "\n")
    return EXIT_OK


def shquote(value: str) -> str:
    """Quote a value for a POSIX shell."""
    return "'" + value.replace("'", "'\\''") + "'"


# ---------------------------------------------------------------------------
# the parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """The command line."""
    parser = argparse.ArgumentParser(
        prog="dt-broker",
        description="The per-run GitHub credential broker for digithings seats.",
    )
    parser.add_argument(
        "--socket",
        default=None,
        help=f"the broker's unix socket (default: {DEFAULT_SOCKET_PATH})",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    serve_parser = sub.add_parser("serve", help="run the daemon")
    serve_parser.add_argument("--policy", default=str(DEFAULT_POLICY_PATH))
    serve_parser.add_argument("--state-dir", default=None)
    serve_parser.add_argument("--log", default=None)
    serve_parser.add_argument("--auth-mode-path", default=None)
    serve_parser.add_argument("--health-interval", type=float, default=60.0)
    serve_parser.set_defaults(func=cmd_serve)

    health_parser = sub.add_parser("health", help="ask the daemon how it is")
    health_parser.set_defaults(func=cmd_health)

    mode_parser = sub.add_parser("auth-mode", help="print the rollback flag")
    mode_parser.add_argument("--path", default=None)
    mode_parser.add_argument("--default", default=APP_MODE, choices=(APP_MODE, HOST_MODE))
    mode_parser.add_argument("--json", action="store_true")
    mode_parser.set_defaults(func=cmd_auth_mode)

    token_parser = sub.add_parser("github-token", help="ask for a token for this run")
    token_parser.add_argument("--repo", default=None)
    token_parser.add_argument("--permission", action="append", default=None)
    token_parser.add_argument("--head-sha", default=None)
    token_parser.add_argument(
        "--print-token",
        action="store_true",
        help="print the token itself on stdout instead of its metadata",
    )
    token_parser.set_defaults(func=cmd_github_token)

    revoke_parser = sub.add_parser("revoke", help="revoke this run's token")
    revoke_parser.set_defaults(func=cmd_revoke)

    identity_parser = sub.add_parser("identity", help="print the bot identity")
    identity_parser.add_argument("--json", action="store_true")
    identity_parser.set_defaults(func=cmd_identity)

    trailers_parser = sub.add_parser("trailers", help="print the commit trailers")
    trailers_parser.set_defaults(func=cmd_trailers)

    credential_parser = sub.add_parser(
        "git-credential", help="the git credential helper"
    )
    credential_parser.add_argument("operation", choices=("get", "store", "erase"))
    credential_parser.set_defaults(func=cmd_git_credential)

    env_parser = sub.add_parser("seat-env", help="print the environment for a seat run")
    env_parser.set_defaults(func=cmd_seat_env)

    return parser


def main(argv: list[str] | None = None, env: dict[str, str] | None = None) -> int:
    """Run one command."""
    environment = dict(os.environ if env is None else env)
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "gh":
        # `dt-broker gh ...` is the shim: the arguments are the gh call, and
        # they are handed over untouched.
        from .ghshim import main as gh_main

        return int(gh_main(arguments[1:], environment))
    parser = build_parser()
    args = parser.parse_args(arguments)
    try:
        return int(args.func(args, environment))
    except BrokerError as exc:
        sys.stderr.write(f"dt-broker: {exc}\n")
        return EXIT_INTERNAL
    except BrokenPipeError:  # pragma: no cover - the reader went away
        return EXIT_OK


__all__ = ["build_parser", "main"]
