"""The gh shim: what it rewrites, what it refuses, and what the guard receives.

The shim sits between a seat run and the host gh guard. It does three things
the guard does not:

* it refuses a pull request against a repository outside the digithings-ai
  organization, under any identity;
* it expands a field value of `@<path>` into the contents of that file, for
  both `-f/--raw-field` and `-F/--field`, so the body that arrives is the
  body that was written;
* in `app` mode it hands the guard a per-run token from the broker, and
  nothing else.

The first two are the DIG-4818 lesson: a review body that was silently
replaced by the path of the file that held it.

The last section of this file runs the shim as a process, against a broker
that is a process, with a guard that records what it was given. That is the
only way to prove the chain: the guard is exec'd, the token comes over the
socket, and the host's own token is not in the room.

Nothing here talks to GitHub or to Paperclip. Both are replaced by a
transport that answers from a rule list, the way the rest of the suite
replaces `gh`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from scripts.dt_broker import ghshim, github, paperclip, server
from scripts.dt_broker.core import Policy

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ID = "38045bd4-eed9-4c4d-bbf5-bdb6b0261407"
RUN_ID = "636b1b0a-b758-438c-add9-bc1a09f1cf73"
ISSUE_ID = "73159183-18bb-42ef-848a-07fc65e40635"
REPO = "digithings-ai/digithings"
BODY = "the review text that was written"


# ---------------------------------------------------------------------------
# the fakes
# ---------------------------------------------------------------------------


def _b64(payload: Mapping[str, Any]) -> str:
    import base64

    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def run_jwt(*, agent_id: str = AGENT_ID, run_id: str = RUN_ID) -> str:
    """A run credential with the shape the broker expects."""
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "aud": "paperclip-api",
        "iss": "paperclip",
        "sub": agent_id,
        "run_id": run_id,
        "iat": now,
        "exp": now + 3600,
    }
    return f"{_b64(header)}.{_b64(payload)}.signature"


class FakePaperclip:
    """The three Paperclip reads, answered from a rule list."""

    def __init__(self, *, agent_id: str = AGENT_ID) -> None:
        self.agent_id = agent_id

    def transport(self, method: str, url: str, headers: Mapping[str, str], body: bytes | None):
        if url.endswith("/api/agents/me"):
            return paperclip.HttpResponse(
                status=200,
                body=json.dumps({"id": self.agent_id, "name": "a seat"}).encode("utf-8"),
            )
        if "/api/heartbeat-runs/" in url:
            return paperclip.HttpResponse(
                status=200,
                body=json.dumps(
                    {
                        "id": RUN_ID,
                        "status": "running",
                        "agentId": self.agent_id,
                        "nativeIssueId": ISSUE_ID,
                    }
                ).encode("utf-8"),
            )
        if "/api/issues/" in url:
            return paperclip.HttpResponse(
                status=200,
                body=json.dumps(
                    {
                        "id": ISSUE_ID,
                        "currentExecutionWorkspace": {
                            "repoUrl": f"https://github.com/{REPO}",
                        },
                    }
                ).encode("utf-8"),
            )
        return paperclip.HttpResponse(status=404, body=b"{}")


class FakeGitHub:
    """The GitHub calls the broker makes."""

    def __init__(self, *, token: str = "minted-token-value") -> None:
        self.token = token
        self.minted: list[dict[str, Any]] = []

    def transport(self, method: str, url: str, headers: Mapping[str, str], body: bytes | None):
        if "/access_tokens" in url:
            payload = json.loads(body.decode("utf-8")) if body else {}
            self.minted.append(payload)
            return github.HttpResponse(
                status=201,
                body=json.dumps(
                    {"token": self.token, "expires_at": "2099-01-01T00:00:00Z"}
                ).encode("utf-8"),
            )
        if method == "DELETE" and url.endswith("/installation/token"):
            return github.HttpResponse(status=204, body=b"")
        if "/users/" in url:
            return github.HttpResponse(
                status=200,
                body=json.dumps({"id": 4242, "login": "digithings-seat[bot]"}).encode("utf-8"),
            )
        return github.HttpResponse(status=404, body=b"{}")


def policy_document(key_path: Path) -> dict[str, Any]:
    """A policy with one seat, bound to the agent under test."""
    return {
        "version": 1,
        "org": "digithings-ai",
        "paperclip_api_url": "http://127.0.0.1:3100",
        "review_app": "digithings-review",
        "apps": {
            "digithings-seat": {
                "app_id": "10001",
                "installation_id": "20001",
                "key_path": str(key_path),
                "bot_login": "digithings-seat[bot]",
            },
        },
        "classes": {
            "seat": {
                "app": "digithings-seat",
                "permissions": {
                    "contents": "write",
                    "metadata": "read",
                    "pull_requests": "write",
                },
            },
        },
        "seats": {AGENT_ID: {"class": "seat"}},
    }


# ---------------------------------------------------------------------------
# the fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def app_key(tmp_path: Path) -> Path:
    """A private key the App JWT is signed with."""
    key = tmp_path / "app.pem"
    subprocess.run(
        ["openssl", "genrsa", "-out", str(key), "2048"],
        check=True,
        capture_output=True,
    )
    return key


@pytest.fixture
def seat_env(tmp_path: Path) -> dict[str, str]:
    """The environment of a seat run."""
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(tmp_path),
        "PAPERCLIP_AGENT_ID": AGENT_ID,
        "PAPERCLIP_RUN_ID": RUN_ID,
        "PAPERCLIP_API_KEY": run_jwt(),
        "DT_BROKER_RUN_TMP": str(tmp_path / "run"),
        "GITHUB_TOKEN": "the-host-token",
    }


@pytest.fixture
def guard(tmp_path: Path) -> Path:
    """A stand-in for the host guard, which only has to exist."""
    path = tmp_path / "gh-guard"
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """The calls the shim handed to the guard."""
    calls: list[dict[str, Any]] = []

    def _exec_guard(guard_path: Path, argv: list[str], env: dict[str, str]) -> int:
        calls.append({"guard": Path(guard_path), "argv": list(argv), "env": dict(env)})
        return 0

    monkeypatch.setattr(ghshim, "exec_guard", _exec_guard)
    return calls


@pytest.fixture
def app_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The rollback flag, pointing at `app`."""
    flag = tmp_path / "github-auth-mode"
    flag.write_text("app\n", encoding="utf-8")
    monkeypatch.setattr(ghshim, "AUTH_MODE_PATH", flag)
    return flag


@pytest.fixture
def host_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The rollback flag, pointing at `host`."""
    flag = tmp_path / "github-auth-mode"
    flag.write_text("host\n", encoding="utf-8")
    monkeypatch.setattr(ghshim, "AUTH_MODE_PATH", flag)
    return flag


# ---------------------------------------------------------------------------
# the field rewrite: the body that was written, not the path that was typed
# ---------------------------------------------------------------------------


def test_a_raw_field_carries_the_file_not_the_path(tmp_path: Path) -> None:
    body = tmp_path / "review.md"
    body.write_text(BODY, encoding="utf-8")
    argv, notes = ghshim.rewrite_fields(
        ["api", "repos/digithings-ai/digithings/issues/1/comments", "-f", f"body=@{body}"]
    )
    assert argv == [
        "api",
        "repos/digithings-ai/digithings/issues/1/comments",
        "-f",
        f"body={BODY}",
    ]
    assert notes


def test_a_field_carries_the_file_not_the_path(tmp_path: Path) -> None:
    """`-F/--field` is the flag the DIG-4818 run used, and it is fixed too."""
    body = tmp_path / "review.md"
    body.write_text(BODY, encoding="utf-8")
    argv, _ = ghshim.rewrite_fields(
        ["api", "repos/digithings-ai/digithings/issues/1/comments", "-F", f"body=@{body}"]
    )
    assert argv[-2:] == ["-f", f"body={BODY}"]


def test_a_long_field_carries_the_file_not_the_path(tmp_path: Path) -> None:
    body = tmp_path / "review.md"
    body.write_text(BODY, encoding="utf-8")
    argv, _ = ghshim.rewrite_fields(
        ["api", "repos/digithings-ai/digithings/issues/1/comments", "--field", f"body=@{body}"]
    )
    assert argv[-2:] == ["--raw-field", f"body={BODY}"]


def test_an_attached_field_carries_the_file_not_the_path(tmp_path: Path) -> None:
    body = tmp_path / "review.md"
    body.write_text(BODY, encoding="utf-8")
    argv, _ = ghshim.rewrite_fields(
        ["api", "repos/digithings-ai/digithings/issues/1/comments", f"-fbody=@{body}"]
    )
    assert argv[-1] == f"-fbody={BODY}"


def test_a_long_attached_field_carries_the_file_not_the_path(tmp_path: Path) -> None:
    body = tmp_path / "review.md"
    body.write_text(BODY, encoding="utf-8")
    argv, _ = ghshim.rewrite_fields(
        ["api", "repos/digithings-ai/digithings/issues/1/comments", f"--field=body=@{body}"]
    )
    assert argv[-1] == f"--raw-field=body={BODY}"


def test_a_body_that_is_a_path_is_refused(tmp_path: Path) -> None:
    """A body that is a path is a mistake, and posting it is the damage."""
    body = tmp_path / "review.md"
    body.write_text(BODY, encoding="utf-8")
    with pytest.raises(ghshim.Refusal) as excinfo:
        ghshim.rewrite_fields(
            ["api", "repos/digithings-ai/digithings/issues/1/comments", "-f", f"body={body}"]
        )
    assert "path" in str(excinfo.value)


def test_a_body_that_is_a_path_is_refused_for_a_field_too(tmp_path: Path) -> None:
    body = tmp_path / "review.md"
    body.write_text(BODY, encoding="utf-8")
    with pytest.raises(ghshim.Refusal):
        ghshim.rewrite_fields(
            ["api", "repos/digithings-ai/digithings/issues/1/comments", "-F", f"body={body}"]
        )


def test_a_body_flag_carries_the_file_not_the_path(tmp_path: Path) -> None:
    body = tmp_path / "review.md"
    body.write_text(BODY, encoding="utf-8")
    argv, _ = ghshim.rewrite_body_flags(["pr", "comment", "1", "--body", f"@{body}"])
    assert argv == ["pr", "comment", "1", "--body", BODY]


def test_a_body_flag_that_is_a_path_is_refused(tmp_path: Path) -> None:
    body = tmp_path / "review.md"
    body.write_text(BODY, encoding="utf-8")
    with pytest.raises(ghshim.Refusal):
        ghshim.rewrite_body_flags(["pr", "comment", "1", "--body", str(body)])


def test_a_body_file_flag_is_left_alone(tmp_path: Path) -> None:
    """`--body-file` already reads the file, and is already correct."""
    body = tmp_path / "review.md"
    body.write_text(BODY, encoding="utf-8")
    argv, notes = ghshim.rewrite_body_flags(["pr", "comment", "1", "--body-file", str(body)])
    assert argv == ["pr", "comment", "1", "--body-file", str(body)]
    assert notes == []


def test_a_field_that_is_not_a_body_is_left_alone() -> None:
    argv, notes = ghshim.rewrite_fields(["api", "repos/o/r/issues/1", "-f", "state=closed"])
    assert argv == ["api", "repos/o/r/issues/1", "-f", "state=closed"]
    assert notes == []


# ---------------------------------------------------------------------------
# the organization check
# ---------------------------------------------------------------------------


def test_a_pull_request_outside_the_organization_is_refused() -> None:
    with pytest.raises(ghshim.Refusal) as excinfo:
        ghshim.check_pull_request_target(
            ["pr", "create", "--repo", "someone-else/their-project"], {}
        )
    assert "digithings-ai" in str(excinfo.value)


def test_a_pull_request_inside_the_organization_is_allowed() -> None:
    notes = ghshim.check_pull_request_target(
        ["pr", "create", "--repo", "digithings-ai/digithings"], {}
    )
    assert notes


def test_a_pull_request_with_no_repository_is_refused(tmp_path: Path) -> None:
    """A repository that cannot be identified cannot be cleared either."""
    with pytest.raises(ghshim.Refusal):
        ghshim.check_pull_request_target(
            ["pr", "create"], {"DT_BROKER_CWD": str(tmp_path)}
        )


def test_the_pulls_endpoint_outside_the_organization_is_refused() -> None:
    with pytest.raises(ghshim.Refusal):
        ghshim.check_pull_request_target(["api", "repos/someone-else/their-project/pulls"], {})


def test_the_pulls_endpoint_inside_the_organization_is_allowed() -> None:
    notes = ghshim.check_pull_request_target(
        ["api", f"repos/{REPO}/pulls"], {}
    )
    assert notes


def test_a_graphql_pull_request_is_refused() -> None:
    """The repository is inside a query string, so it cannot be checked."""
    with pytest.raises(ghshim.Refusal) as excinfo:
        ghshim.check_pull_request_target(
            ["api", "graphql", "-f", "query=mutation { createPullRequest(input: {}) { clientMutationId } }"],
            {},
        )
    assert "GraphQL" in str(excinfo.value)


# ---------------------------------------------------------------------------
# the guard, and the modes
# ---------------------------------------------------------------------------


def test_the_shim_never_calls_the_real_gh(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pointing the shim at the real `gh` would turn the guard off."""
    with pytest.raises(ghshim.Refusal) as excinfo:
        ghshim.guard_path({"DT_BROKER_GH_GUARD": "/opt/homebrew/bin/gh"})
    assert "guard" in str(excinfo.value)


def test_a_guard_that_is_the_real_gh_is_refused(
    seat_env: dict[str, str], captured: list[dict[str, Any]]
) -> None:
    seat_env["DT_BROKER_GH_GUARD"] = "/opt/homebrew/bin/gh"
    assert ghshim.main(["pr", "list"], seat_env) == ghshim.EXIT_REFUSED
    assert captured == []


def test_app_mode_gives_the_guard_a_per_run_token(
    seat_env: dict[str, str],
    guard: Path,
    app_mode: Path,
    captured: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seat_env["DT_BROKER_GH_GUARD"] = str(guard)
    monkeypatch.setattr(ghshim, "request_token", lambda env: "the-minted-token")
    assert ghshim.main(["pr", "list"], seat_env) == ghshim.EXIT_OK
    assert len(captured) == 1
    call = captured[0]
    assert call["guard"] == guard
    assert call["argv"] == ["pr", "list"]
    assert call["env"]["GH_TOKEN"] == "the-minted-token"
    assert call["env"]["GH_CONFIG_DIR"].endswith("gh")


def test_app_mode_keeps_the_host_tokens_out(
    seat_env: dict[str, str],
    guard: Path,
    app_mode: Path,
    captured: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The only credential in the room is the one the broker minted."""
    seat_env["DT_BROKER_GH_GUARD"] = str(guard)
    monkeypatch.setattr(ghshim, "request_token", lambda env: "the-minted-token")
    assert ghshim.main(["pr", "list"], seat_env) == ghshim.EXIT_OK
    child = captured[0]["env"]
    assert "GITHUB_TOKEN" not in child
    assert "GH_ENTERPRISE_TOKEN" not in child
    assert "GITHUB_ENTERPRISE_TOKEN" not in child


def test_app_mode_sends_the_rewritten_call_to_the_guard(
    seat_env: dict[str, str],
    guard: Path,
    app_mode: Path,
    captured: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    seat_env["DT_BROKER_GH_GUARD"] = str(guard)
    monkeypatch.setattr(ghshim, "request_token", lambda env: "the-minted-token")
    body = tmp_path / "review.md"
    body.write_text(BODY, encoding="utf-8")
    ghshim.main(
        ["api", f"repos/{REPO}/issues/1/comments", "-f", f"body=@{body}"], seat_env
    )
    assert captured[0]["argv"] == [
        "api",
        f"repos/{REPO}/issues/1/comments",
        "-f",
        f"body={BODY}",
    ]


def test_a_missing_flag_reads_as_app(
    seat_env: dict[str, str],
    guard: Path,
    captured: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A flag that cannot be read must not turn the broker off."""
    monkeypatch.setattr(ghshim, "AUTH_MODE_PATH", tmp_path / "not-there")
    seat_env["DT_BROKER_GH_GUARD"] = str(guard)
    monkeypatch.setattr(ghshim, "request_token", lambda env: "the-minted-token")
    assert ghshim.main(["pr", "list"], seat_env) == ghshim.EXIT_OK
    assert captured[0]["env"]["GH_TOKEN"] == "the-minted-token"


def test_host_mode_passes_the_call_through_unchanged(
    seat_env: dict[str, str],
    guard: Path,
    host_mode: Path,
    captured: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`host` restores today's behaviour: the broker is not even asked."""
    seat_env["DT_BROKER_GH_GUARD"] = str(guard)

    def _not_asked(env: dict[str, str]) -> str:
        raise AssertionError("the broker must not be asked in host mode")

    monkeypatch.setattr(ghshim, "request_token", _not_asked)
    assert ghshim.main(["pr", "list"], seat_env) == ghshim.EXIT_OK
    assert captured[0]["argv"] == ["pr", "list"]
    assert "GH_TOKEN" not in captured[0]["env"]


def test_host_mode_still_refuses_a_pull_request_outside_the_organization(
    seat_env: dict[str, str],
    guard: Path,
    host_mode: Path,
    captured: list[dict[str, Any]],
) -> None:
    """The rollback flag turns the broker off, not the organization rule."""
    seat_env["DT_BROKER_GH_GUARD"] = str(guard)
    code = ghshim.main(["pr", "create", "--repo", "someone-else/their-project"], seat_env)
    assert code == ghshim.EXIT_REFUSED
    assert captured == []


def test_host_mode_still_expands_a_field(
    seat_env: dict[str, str],
    guard: Path,
    host_mode: Path,
    captured: list[dict[str, Any]],
    tmp_path: Path,
) -> None:
    seat_env["DT_BROKER_GH_GUARD"] = str(guard)
    body = tmp_path / "review.md"
    body.write_text(BODY, encoding="utf-8")
    ghshim.main(["api", f"repos/{REPO}/issues/1/comments", "-f", f"body=@{body}"], seat_env)
    assert captured[0]["argv"][-1] == f"body={BODY}"


def test_a_missing_broker_stops_the_call(
    seat_env: dict[str, str],
    guard: Path,
    app_mode: Path,
    captured: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No broker is not a reason to fall back to the host's credentials."""
    seat_env["DT_BROKER_GH_GUARD"] = str(guard)

    def _unavailable(env: dict[str, str]) -> str:
        raise ghshim.BrokerUnavailable("the broker did not answer")

    monkeypatch.setattr(ghshim, "request_token", _unavailable)
    assert ghshim.main(["pr", "list"], seat_env) == ghshim.EXIT_UNAVAILABLE
    assert captured == []


def test_a_refusal_costs_nothing(
    seat_env: dict[str, str],
    guard: Path,
    app_mode: Path,
    captured: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A refusal happens before the broker is asked for anything."""
    seat_env["DT_BROKER_GH_GUARD"] = str(guard)

    def _not_asked(env: dict[str, str]) -> str:
        raise AssertionError("the broker must not be asked for a refused call")

    monkeypatch.setattr(ghshim, "request_token", _not_asked)
    code = ghshim.main(["pr", "create", "--repo", "someone-else/their-project"], seat_env)
    assert code == ghshim.EXIT_REFUSED
    assert captured == []


def test_a_shim_that_is_already_in_the_chain_refuses(
    seat_env: dict[str, str],
    guard: Path,
    app_mode: Path,
    captured: list[dict[str, Any]],
) -> None:
    """A shim that called itself would loop for ever."""
    seat_env["DT_BROKER_GH_GUARD"] = str(guard)
    seat_env[ghshim.SHIM_MARKER] = "1"
    assert ghshim.main(["pr", "list"], seat_env) == ghshim.EXIT_REFUSED
    assert captured == []


def test_a_process_that_is_not_a_seat_is_left_to_the_guard(
    tmp_path: Path,
    guard: Path,
    app_mode: Path,
    captured: list[dict[str, Any]],
) -> None:
    """The guard decides who is a seat, and so does the shim."""
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "DT_BROKER_GH_GUARD": str(guard)}
    assert ghshim.main(["pr", "list"], env) == ghshim.EXIT_OK
    assert captured[0]["argv"] == ["pr", "list"]
    assert "GH_TOKEN" not in captured[0]["env"]


# ---------------------------------------------------------------------------
# end to end: the shim as a process, the broker as a process, the guard exec'd
# ---------------------------------------------------------------------------


def _short_socket_dir() -> Path:
    """A directory whose path is short enough for an AF_UNIX socket.

    An AF_UNIX path is 104 bytes on macOS. This run's scratch directory is
    already 100 bytes long, so the socket gets a directory one level up:
    the same temp root, without the name of this run in it.
    """
    base = Path(tempfile.gettempdir()).parent
    return Path(tempfile.mkdtemp(prefix="dtb", dir=str(base)))


@pytest.fixture
def running_broker(app_key: Path) -> Any:
    """A broker listening on a socket, with both APIs faked."""
    directory = _short_socket_dir()
    socket_path = directory / "s"
    if len(str(socket_path).encode("utf-8")) > 100:  # pragma: no cover - host dependent
        shutil.rmtree(directory, ignore_errors=True)
        pytest.skip("this host has no room for an AF_UNIX socket path")

    policy = Policy.from_dict(policy_document(app_key), source="<test>")
    github_fake = FakeGitHub()
    service = server.BrokerService(
        policy,
        github=github.GitHubClient(transport=github_fake.transport),
        state_dir=directory / "state",
        log_path=directory / "state" / "dt-broker.jsonl",
        socket_path=socket_path,
        paperclip_transport=FakePaperclip().transport,
    )
    broker = server.BrokerServer(socket_path, service)
    thread = threading.Thread(target=broker.serve_forever, kwargs={"poll_interval": 0.05})
    thread.daemon = True
    thread.start()
    try:
        yield socket_path, github_fake
    finally:
        broker.shutdown()
        broker.server_close()
        thread.join(timeout=5)
        shutil.rmtree(directory, ignore_errors=True)


def _recording_guard(tmp_path: Path) -> Path:
    """A guard that records the call it was given, and the room it was in."""
    record = tmp_path / "guard-record.json"
    path = tmp_path / "gh-guard"
    path.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        f"record = {str(record)!r}\n"
        "keys = ('GH_TOKEN', 'GH_CONFIG_DIR', 'GITHUB_TOKEN', 'GH_ENTERPRISE_TOKEN')\n"
        "with open(record, 'w', encoding='utf-8') as fh:\n"
        "    json.dump({'argv': sys.argv[1:],"
        " 'env': {key: os.environ.get(key) for key in keys}}, fh)\n",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def _run_shim(env: dict[str, str], *arguments: str) -> subprocess.CompletedProcess[str]:
    """Run the shim as a process, the way a seat run would."""
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "dt-broker"), "gh", *arguments],
        env=env,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=60,
    )


def test_the_guard_is_exec_ed_with_the_rewritten_call(
    running_broker: Any, tmp_path: Path, app_mode: Path
) -> None:
    """The whole chain, in one process each: shim, broker, guard."""
    socket_path, github_fake = running_broker
    guard = _recording_guard(tmp_path)
    body = tmp_path / "review.md"
    body.write_text(BODY, encoding="utf-8")

    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(tmp_path),
        "PAPERCLIP_AGENT_ID": AGENT_ID,
        "PAPERCLIP_RUN_ID": RUN_ID,
        "PAPERCLIP_API_KEY": run_jwt(),
        "DT_BROKER_SOCKET": str(socket_path),
        "DT_BROKER_GH_GUARD": str(guard),
        "DT_BROKER_RUN_TMP": str(tmp_path / "run"),
        "GITHUB_TOKEN": "the-host-token",
    }
    proc = _run_shim(
        env, "api", f"repos/{REPO}/issues/1/comments", "-f", f"body=@{body}"
    )
    assert proc.returncode == 0, proc.stderr

    record = json.loads((tmp_path / "guard-record.json").read_text(encoding="utf-8"))
    assert record["argv"] == [
        "api",
        f"repos/{REPO}/issues/1/comments",
        "-f",
        f"body={BODY}",
    ]
    # The token came from the broker, over the socket.
    assert record["env"]["GH_TOKEN"] == "minted-token-value"
    # The host's own token is not in the room.
    assert record["env"]["GITHUB_TOKEN"] is None
    # And the broker minted it for this run's repository, and nothing else.
    assert github_fake.minted == [
        {
            "repositories": ["digithings"],
            "permissions": {
                "contents": "write",
                "metadata": "read",
                "pull_requests": "write",
            },
        }
    ]


def test_the_shim_refuses_a_pull_request_outside_the_organization(
    running_broker: Any, tmp_path: Path, app_mode: Path
) -> None:
    socket_path, github_fake = running_broker
    guard = _recording_guard(tmp_path)
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(tmp_path),
        "PAPERCLIP_AGENT_ID": AGENT_ID,
        "PAPERCLIP_RUN_ID": RUN_ID,
        "PAPERCLIP_API_KEY": run_jwt(),
        "DT_BROKER_SOCKET": str(socket_path),
        "DT_BROKER_GH_GUARD": str(guard),
        "DT_BROKER_RUN_TMP": str(tmp_path / "run"),
    }
    proc = _run_shim(env, "pr", "create", "--repo", "someone-else/their-project")
    assert proc.returncode == ghshim.EXIT_REFUSED
    assert "digithings-ai" in proc.stderr
    assert not (tmp_path / "guard-record.json").exists()
    assert github_fake.minted == []
