"""The broker's rules.

Each test here is one rule of the broker: a refusal, or a promise that a token
does not outlive the run that asked for it. The broker is the piece that holds
the GitHub Apps, so the tests are about what it will not do.

Nothing in this file talks to GitHub or to Paperclip. Both are replaced by a
transport that answers from a rule list, the way the rest of the suite replaces
`gh`.
"""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from scripts.dt_broker import core, github, paperclip, server
from scripts.dt_broker.core import Policy

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ID = "38045bd4-eed9-4c4d-bbf5-bdb6b0261407"
OTHER_AGENT_ID = "b14d7a18-0000-4000-8000-000000000000"
RUN_ID = "636b1b0a-b758-438c-add9-bc1a09f1cf73"
ISSUE_ID = "73159183-18bb-42ef-848a-07fc65e40635"
REPO = "digithings-ai/digithings"
#: The token the fake GitHub mints. It is deliberately not shaped like a
#: real one: a credential-shaped string in a test file is a copy of a
#: credential outside its own home, and the secret scanner is right to say so.
MINTED_TOKEN = "minted-token-value"


# ---------------------------------------------------------------------------
# the fakes
# ---------------------------------------------------------------------------


def _b64(payload: Mapping[str, Any]) -> str:
    import base64

    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def run_jwt(
    *,
    agent_id: str = AGENT_ID,
    run_id: str = RUN_ID,
    audience: str = "paperclip-api",
    expires_in: int = 3600,
) -> str:
    """A run credential with the shape the broker expects.

    The signature is not checked by the broker: the authority is the API call
    it makes with the token, and the fake API below answers for one agent only.
    """
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "aud": audience,
        "iss": "paperclip",
        "sub": agent_id,
        "run_id": run_id,
        "iat": now,
        "exp": now + expires_in,
    }
    return f"{_b64(header)}.{_b64(payload)}.signature"


class FakePaperclip:
    """The three Paperclip reads, answered from a rule list."""

    def __init__(
        self,
        *,
        agent_id: str = AGENT_ID,
        run_status: str = "running",
        run_agent_id: str | None = None,
        repo: str | None = REPO,
        issue_id: str = ISSUE_ID,
        run_id: str = RUN_ID,
    ) -> None:
        self.agent_id = agent_id
        self.run_status = run_status
        self.run_agent_id = run_agent_id
        self.repo = repo
        self.issue_id = issue_id
        self.run_id = run_id
        self.calls: list[str] = []

    def transport(self, method: str, url: str, headers: Mapping[str, str], body: bytes | None):
        self.calls.append(url)
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
                        "id": self.run_id,
                        "status": self.run_status,
                        "agentId": self.run_agent_id or self.agent_id,
                        "nativeIssueId": self.issue_id,
                    }
                ).encode("utf-8"),
            )
        if "/api/issues/" in url:
            workspace: dict[str, Any] = {}
            if self.repo:
                workspace["repoUrl"] = f"https://github.com/{self.repo}"
            return paperclip.HttpResponse(
                status=200,
                body=json.dumps(
                    {"id": self.issue_id, "currentExecutionWorkspace": workspace}
                ).encode("utf-8"),
            )
        return paperclip.HttpResponse(status=404, body=b"{}")


class StrictPaperclip(FakePaperclip):
    """A fake API that accepts one credential and refuses every other one.

    The real API checks the signature of the credential it is given. This
    fake checks the string instead, which is the same thing for a test: a
    credential nobody issued is refused, whatever its claims say.
    """

    def __init__(self, accepted: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.accepted = accepted

    def transport(self, method: str, url: str, headers: Mapping[str, str], body: bytes | None):
        bearer = str(headers.get("Authorization") or "")
        if bearer != f"Bearer {self.accepted}":
            return paperclip.HttpResponse(status=401, body=b'{"error":"unauthorized"}')
        return super().transport(method, url, headers, body)


class FakeGitHub:
    """The GitHub calls the broker makes."""

    def __init__(self, *, commit_message: str = "", token: str = MINTED_TOKEN) -> None:
        self.commit_message = commit_message
        self.token = token
        self.calls: list[tuple[str, str]] = []
        self.headers: list[dict[str, str]] = []
        self.minted: list[dict[str, Any]] = []
        self.revoked: list[str] = []

    def transport(self, method: str, url: str, headers: Mapping[str, str], body: bytes | None):
        self.calls.append((method, url))
        self.headers.append(dict(headers))
        if "/access_tokens" in url:
            payload = json.loads(body.decode("utf-8")) if body else {}
            self.minted.append(payload)
            return github.HttpResponse(
                status=201,
                body=json.dumps(
                    {
                        "token": self.token,
                        "expires_at": "2099-01-01T00:00:00Z",
                    }
                ).encode("utf-8"),
            )
        if method == "DELETE" and url.endswith("/installation/token"):
            self.revoked.append(headers.get("Authorization", ""))
            return github.HttpResponse(status=204, body=b"")
        if "/users/" in url:
            return github.HttpResponse(
                status=200, body=json.dumps({"id": 4242, "login": "digithings-seat[bot]"}).encode("utf-8")
            )
        if "/commits/" in url:
            return github.HttpResponse(
                status=200,
                body=json.dumps({"commit": {"message": self.commit_message}}).encode("utf-8"),
            )
        return github.HttpResponse(status=404, body=b"{}")


# ---------------------------------------------------------------------------
# the policy under test
# ---------------------------------------------------------------------------


def policy_document(
    *,
    seat_repos: list[str] | None = None,
    seat_class: str = "seat",
    permissions: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """A policy with one seat, one reviewer and the CI class."""
    return {
        "version": 1,
        "org": "digithings-ai",
        "paperclip_api_url": "http://127.0.0.1:3100",
        "review_app": "digithings-review",
        "apps": {
            "digithings-seat": {
                "app_id": "10001",
                "installation_id": "20001",
                "key_path": "/nonexistent/digithings-seat.pem",
                "bot_login": "digithings-seat[bot]",
            },
            "digithings-review": {
                "app_id": "10002",
                "installation_id": "20002",
                "key_path": "/nonexistent/digithings-review.pem",
                "bot_login": "digithings-review[bot]",
            },
            "digithings-ci": {
                "app_id": "10003",
                "installation_id": "20003",
                "key_path": "/nonexistent/digithings-ci.pem",
                "bot_login": "digithings-ci[bot]",
            },
        },
        "classes": {
            "seat": {
                "app": "digithings-seat",
                "permissions": dict(
                    permissions
                    if permissions is not None
                    else {"contents": "write", "metadata": "read", "pull_requests": "write"}
                ),
            },
            "reviewer": {
                "app": "digithings-review",
                "permissions": {"contents": "read", "metadata": "read", "pull_requests": "write"},
            },
            "ci": {
                "app": "digithings-ci",
                "permissions": {"contents": "write", "metadata": "read", "statuses": "write"},
            },
        },
        "seats": {
            AGENT_ID: {"class": seat_class, **({"repos": seat_repos} if seat_repos else {})},
            OTHER_AGENT_ID: {"class": "reviewer"},
        },
    }


@pytest.fixture
def rsa_key(tmp_path: Path) -> Path:
    """A private key the App JWT is signed with."""
    key = tmp_path / "app.pem"
    subprocess.run(
        ["openssl", "genrsa", "-out", str(key), "2048"],
        check=True,
        capture_output=True,
    )
    return key


@pytest.fixture
def service(tmp_path: Path, rsa_key: Path) -> tuple[server.BrokerService, FakePaperclip, FakeGitHub]:
    """A broker service with both APIs faked."""
    document = policy_document()
    document["apps"]["digithings-seat"]["key_path"] = str(rsa_key)
    policy = Policy.from_dict(document, source="<test>")
    paperclip_fake = FakePaperclip()
    github_fake = FakeGitHub()
    socket_path = tmp_path / "dt-broker.sock"
    socket_path.touch()
    broker = server.BrokerService(
        policy,
        github=github.GitHubClient(transport=github_fake.transport),
        state_dir=tmp_path / "state",
        log_path=tmp_path / "state" / "dt-broker.jsonl",
        socket_path=socket_path,
        paperclip_transport=paperclip_fake.transport,
    )
    return broker, paperclip_fake, github_fake


def ask(broker: server.BrokerService, **request: Any) -> dict[str, Any]:
    """Ask the broker for a token, and answer with its raw answer."""
    payload = {"op": "github-token", "run_jwt": run_jwt()}
    payload.update(request)
    return broker.handle(payload)


# ---------------------------------------------------------------------------
# the refusals
# ---------------------------------------------------------------------------


def test_a_credential_that_is_not_a_jwt_is_refused(service) -> None:
    broker, _, _ = service
    answer = broker.handle({"op": "github-token", "run_jwt": "not-a-jwt"})
    assert answer["ok"] is False
    assert answer["code"] == "auth"
    assert "JWT" in answer["error"]


def test_a_credential_for_another_api_is_refused(service) -> None:
    broker, _, _ = service
    answer = broker.handle(
        {"op": "github-token", "run_jwt": run_jwt(audience="something-else")}
    )
    assert answer["ok"] is False
    assert "Paperclip API" in answer["error"]


def test_an_expired_credential_is_refused(service) -> None:
    broker, _, _ = service
    answer = broker.handle(
        {"op": "github-token", "run_jwt": run_jwt(expires_in=-10)}
    )
    assert answer["ok"] is False
    assert "expired" in answer["error"]


def test_a_run_that_is_not_running_is_refused(tmp_path: Path, rsa_key: Path) -> None:
    document = policy_document()
    document["apps"]["digithings-seat"]["key_path"] = str(rsa_key)
    policy = Policy.from_dict(document, source="<test>")
    paperclip_fake = FakePaperclip(run_status="completed")
    github_fake = FakeGitHub()
    broker = server.BrokerService(
        policy,
        github=github.GitHubClient(transport=github_fake.transport),
        state_dir=tmp_path / "state",
        log_path=tmp_path / "state" / "dt-broker.jsonl",
        socket_path=tmp_path / "dt-broker.sock",
        paperclip_transport=paperclip_fake.transport,
    )
    answer = broker.handle({"op": "github-token", "run_jwt": run_jwt()})
    assert answer["ok"] is False
    assert "not running" in answer["error"]
    assert github_fake.minted == []


def test_a_credential_naming_another_agent_is_refused(tmp_path: Path, rsa_key: Path) -> None:
    document = policy_document()
    document["apps"]["digithings-seat"]["key_path"] = str(rsa_key)
    policy = Policy.from_dict(document, source="<test>")
    paperclip_fake = FakePaperclip(agent_id=OTHER_AGENT_ID)
    github_fake = FakeGitHub()
    broker = server.BrokerService(
        policy,
        github=github.GitHubClient(transport=github_fake.transport),
        state_dir=tmp_path / "state",
        log_path=tmp_path / "state" / "dt-broker.jsonl",
        socket_path=tmp_path / "dt-broker.sock",
        paperclip_transport=paperclip_fake.transport,
    )
    answer = broker.handle({"op": "github-token", "run_jwt": run_jwt()})
    assert answer["ok"] is False
    assert answer["code"] == "auth"


def test_an_agent_with_no_binding_is_refused(tmp_path: Path, rsa_key: Path) -> None:
    document = policy_document()
    document["apps"]["digithings-seat"]["key_path"] = str(rsa_key)
    policy = Policy.from_dict(document, source="<test>")
    unbound = "99999999-0000-4000-8000-000000000000"
    paperclip_fake = FakePaperclip(agent_id=unbound)
    github_fake = FakeGitHub()
    broker = server.BrokerService(
        policy,
        github=github.GitHubClient(transport=github_fake.transport),
        state_dir=tmp_path / "state",
        log_path=tmp_path / "state" / "dt-broker.jsonl",
        socket_path=tmp_path / "dt-broker.sock",
        paperclip_transport=paperclip_fake.transport,
    )
    answer = broker.handle(
        {"op": "github-token", "run_jwt": run_jwt(agent_id=unbound)}
    )
    assert answer["ok"] is False
    assert "not bound to a seat class" in answer["error"]
    assert github_fake.minted == []


def test_a_repository_outside_the_organization_is_refused(service) -> None:
    broker, _, github_fake = service
    answer = ask(broker, repo="somebody-else/digithings")
    assert answer["ok"] is False
    assert "digithings-ai" in answer["error"]
    assert github_fake.minted == []


def test_a_repository_the_seat_is_not_bound_to_is_refused(tmp_path: Path, rsa_key: Path) -> None:
    document = policy_document(seat_repos=["digithings-ai/twelve-x"])
    document["apps"]["digithings-seat"]["key_path"] = str(rsa_key)
    policy = Policy.from_dict(document, source="<test>")
    paperclip_fake = FakePaperclip()
    github_fake = FakeGitHub()
    broker = server.BrokerService(
        policy,
        github=github.GitHubClient(transport=github_fake.transport),
        state_dir=tmp_path / "state",
        log_path=tmp_path / "state" / "dt-broker.jsonl",
        socket_path=tmp_path / "dt-broker.sock",
        paperclip_transport=paperclip_fake.transport,
    )
    answer = broker.handle({"op": "github-token", "run_jwt": run_jwt()})
    assert answer["ok"] is False
    assert "not one of the repositories bound to this seat" in answer["error"]
    assert github_fake.minted == []


def test_a_token_never_covers_a_second_repository(service) -> None:
    broker, _, github_fake = service
    answer = ask(broker, repo="digithings-ai/twelve-x")
    assert answer["ok"] is False
    assert "not the repository this run is working on" in answer["error"]
    assert github_fake.minted == []


def test_a_permission_the_class_does_not_hold_is_refused(service) -> None:
    broker, _, github_fake = service
    answer = ask(broker, permissions=["contents", "workflows"])
    assert answer["ok"] is False
    assert "may not hold" in answer["error"]
    assert github_fake.minted == []


def test_a_class_that_asks_for_secrets_is_refused_by_the_policy() -> None:
    document = policy_document()
    document["classes"]["seat"]["permissions"]["secrets"] = "write"
    with pytest.raises(core.PolicyError) as caught:
        Policy.from_dict(document, source="<test>")
    assert "secrets" in str(caught.value)


def test_a_class_that_asks_for_statuses_is_refused_by_the_policy() -> None:
    document = policy_document()
    document["classes"]["seat"]["permissions"]["statuses"] = "write"
    with pytest.raises(core.PolicyError) as caught:
        Policy.from_dict(document, source="<test>")
    assert "statuses" in str(caught.value)


# ---------------------------------------------------------------------------
# the promise
# ---------------------------------------------------------------------------


def test_a_token_is_minted_for_the_tickets_own_repository(service) -> None:
    broker, _, github_fake = service
    answer = ask(broker)
    assert answer["ok"] is True
    assert answer["repositories"] == [REPO]
    assert answer["app"] == "digithings-seat"
    # GitHub is asked for the bare repository name, scoped to that one.
    assert github_fake.minted[0]["repositories"] == ["digithings"]
    assert github_fake.minted[0]["permissions"] == {
        "contents": "write",
        "metadata": "read",
        "pull_requests": "write",
    }


def test_the_token_is_never_written_down(service, tmp_path: Path) -> None:
    broker, _, _ = service
    answer = ask(broker)
    assert answer["ok"] is True
    log = (tmp_path / "state" / "dt-broker.jsonl").read_text(encoding="utf-8")
    assert MINTED_TOKEN not in log
    assert "token_last4" in log
    assert MINTED_TOKEN[-4:] in log


def test_the_token_is_never_in_a_refusal(service, tmp_path: Path) -> None:
    broker, _, _ = service
    assert ask(broker)["ok"] is True
    broker.handle({"op": "github-token", "run_jwt": run_jwt(audience="wrong")})
    log = (tmp_path / "state" / "dt-broker.jsonl").read_text(encoding="utf-8")
    assert MINTED_TOKEN not in log


def test_the_run_is_revoked_at_the_end(service) -> None:
    broker, _, github_fake = service
    assert ask(broker)["ok"] is True
    answer = broker.handle({"op": "revoke", "run_jwt": run_jwt()})
    assert answer["ok"] is True
    assert answer["revoked"] is True
    assert github_fake.revoked == [f"token {MINTED_TOKEN}"]


def test_a_revoke_for_a_run_that_never_asked_is_a_no_op(service) -> None:
    broker, _, github_fake = service
    answer = broker.handle({"op": "revoke", "run_jwt": run_jwt()})
    assert answer["ok"] is True
    assert answer["revoked"] is False
    assert github_fake.revoked == []


# ---------------------------------------------------------------------------
# the review path
# ---------------------------------------------------------------------------


def review_broker(
    tmp_path: Path,
    rsa_key: Path,
    *,
    commit_message: str,
) -> server.BrokerService:
    """A broker whose seat is a reviewer."""
    document = policy_document(seat_class="reviewer")
    document["apps"]["digithings-review"]["key_path"] = str(rsa_key)
    policy = Policy.from_dict(document, source="<test>")
    paperclip_fake = FakePaperclip()
    github_fake = FakeGitHub(commit_message=commit_message)
    return server.BrokerService(
        policy,
        github=github.GitHubClient(transport=github_fake.transport),
        state_dir=tmp_path / "state",
        log_path=tmp_path / "state" / "dt-broker.jsonl",
        socket_path=tmp_path / "dt-broker.sock",
        paperclip_transport=paperclip_fake.transport,
    )


def test_a_reviewer_may_not_review_its_own_change(tmp_path: Path, rsa_key: Path) -> None:
    broker = review_broker(
        tmp_path,
        rsa_key,
        commit_message=f"a change\n\nPaperclip-Agent-Id: {AGENT_ID}\n",
    )
    answer = broker.handle(
        {
            "op": "github-token",
            "run_jwt": run_jwt(),
            "head_sha": "abc123",
        }
    )
    assert answer["ok"] is False
    assert "may not review its own change" in answer["error"]


def test_a_reviewer_may_review_somebody_elses_change(tmp_path: Path, rsa_key: Path) -> None:
    broker = review_broker(
        tmp_path,
        rsa_key,
        commit_message=f"a change\n\nPaperclip-Agent-Id: {OTHER_AGENT_ID}\n",
    )
    answer = broker.handle(
        {
            "op": "github-token",
            "run_jwt": run_jwt(),
            "head_sha": "abc123",
        }
    )
    assert answer["ok"] is True
    assert answer["app"] == "digithings-review"


def test_a_review_without_the_head_commit_is_refused(tmp_path: Path, rsa_key: Path) -> None:
    broker = review_broker(tmp_path, rsa_key, commit_message="a change")
    answer = broker.handle({"op": "github-token", "run_jwt": run_jwt()})
    assert answer["ok"] is False
    assert "head commit" in answer["error"]


# ---------------------------------------------------------------------------
# the flag and the health
# ---------------------------------------------------------------------------


def test_a_missing_flag_reads_as_app(tmp_path: Path) -> None:
    assert core.read_auth_mode(tmp_path / "nothing", default=core.APP_MODE) == core.APP_MODE


def test_a_damaged_flag_reads_as_the_default(tmp_path: Path) -> None:
    flag = tmp_path / "github-auth-mode"
    flag.write_text("APP\n", encoding="utf-8")
    assert core.read_auth_mode(flag, default=core.APP_MODE) == core.APP_MODE
    flag.write_text("host\n", encoding="utf-8")
    assert core.read_auth_mode(flag, default=core.APP_MODE) == core.HOST_MODE


def test_the_health_tick_counts_consecutive_failures(service, tmp_path: Path) -> None:
    broker, _, _ = service
    record = broker.tick()
    assert record["ok"] is True
    assert record["consecutive_failures"] == 0
    (tmp_path / "state" / "health.json").unlink()
    broker.policy_path = tmp_path / "no-such-policy.json"
    broker.socket_path = tmp_path / "no-such-socket.sock"
    record = broker.tick()
    assert record["ok"] is False
    assert record["consecutive_failures"] >= 1


def test_the_alert_lands_after_two_failed_ticks(service, tmp_path: Path) -> None:
    broker, _, _ = service
    monitor = server.HealthMonitor(broker, interval=60, alert_after=2)
    broker.policy_path = tmp_path / "no-such-policy.json"
    broker.socket_path = tmp_path / "no-such-socket.sock"
    monitor.run_once()
    assert not (tmp_path / "state" / "alert.json").exists()
    monitor.run_once()
    alert = json.loads((tmp_path / "state" / "alert.json").read_text(encoding="utf-8"))
    assert alert["consecutive_failures"] >= 2


# ---------------------------------------------------------------------------
# the rules that were found by the in-session review of 22 October
# ---------------------------------------------------------------------------


def test_the_daemon_refuses_to_mint_in_host_mode(service, tmp_path: Path) -> None:
    """The rollback flag turns the broker off, not only the shim."""
    broker, _, github_fake = service
    flag = tmp_path / "github-auth-mode"
    flag.write_text("host\n", encoding="utf-8")
    broker.auth_mode_path = flag
    answer = ask(broker)
    assert answer["ok"] is False
    assert "host" in answer["error"]
    assert github_fake.minted == []


def test_a_revocation_needs_a_credential_the_api_accepts(
    tmp_path: Path, rsa_key: Path
) -> None:
    """A forged credential must not be able to kill another run's token."""
    document = policy_document()
    document["apps"]["digithings-seat"]["key_path"] = str(rsa_key)
    policy = Policy.from_dict(document, source="<test>")
    github_fake = FakeGitHub()
    broker = server.BrokerService(
        policy,
        github=github.GitHubClient(transport=github_fake.transport),
        state_dir=tmp_path / "state",
        log_path=tmp_path / "state" / "dt-broker.jsonl",
        socket_path=tmp_path / "dt-broker.sock",
        paperclip_transport=FakePaperclip().transport,
    )
    assert broker.handle({"op": "github-token", "run_jwt": run_jwt()})["ok"] is True

    forged = run_jwt(agent_id=OTHER_AGENT_ID)
    answer = broker.handle({"op": "revoke", "run_jwt": forged})
    assert answer["ok"] is False
    assert github_fake.revoked == []


def test_one_token_serves_the_run_and_every_one_of_them_is_revoked(service) -> None:
    """A run that makes three calls must not leave three live tokens."""
    broker, _, github_fake = service
    for _ in range(3):
        assert ask(broker)["ok"] is True
    assert len(github_fake.minted) == 1
    answer = broker.handle({"op": "revoke", "run_jwt": run_jwt()})
    assert answer["revoked"] is True
    assert answer["tokens"] == 1
    assert github_fake.revoked == [f"token {MINTED_TOKEN}"]


def test_a_review_of_a_commit_with_no_agent_id_is_refused(
    tmp_path: Path, rsa_key: Path
) -> None:
    """An author whose id cannot be read cannot be told from the reviewer."""
    broker = review_broker(tmp_path, rsa_key, commit_message="a change with no trailer")
    answer = broker.handle(
        {"op": "github-token", "run_jwt": run_jwt(), "head_sha": "abc123"}
    )
    assert answer["ok"] is False
    assert "names no agent id" in answer["error"]


def test_a_review_with_a_decoy_trailer_is_refused(tmp_path: Path, rsa_key: Path) -> None:
    """The author writes the commit message, so every trailer is read."""
    broker = review_broker(
        tmp_path,
        rsa_key,
        commit_message=(
            f"a change\n\nPaperclip-Agent-Id: {OTHER_AGENT_ID}\n"
            f"Paperclip-Agent-Id: {AGENT_ID}\n"
        ),
    )
    answer = broker.handle(
        {"op": "github-token", "run_jwt": run_jwt(), "head_sha": "abc123"}
    )
    assert answer["ok"] is False
    assert "may not review its own change" in answer["error"]


def test_the_commit_is_read_with_the_apps_own_jwt(tmp_path: Path, rsa_key: Path) -> None:
    """A private repository answers 404 to an anonymous read."""
    github_fake = FakeGitHub(
        commit_message=f"x\n\nPaperclip-Agent-Id: {OTHER_AGENT_ID}\n"
    )
    document = policy_document(seat_class="reviewer")
    document["apps"]["digithings-review"]["key_path"] = str(rsa_key)
    policy = Policy.from_dict(document, source="<test>")
    broker = server.BrokerService(
        policy,
        github=github.GitHubClient(transport=github_fake.transport),
        state_dir=tmp_path / "state",
        log_path=tmp_path / "state" / "dt-broker.jsonl",
        socket_path=tmp_path / "dt-broker.sock",
        paperclip_transport=FakePaperclip().transport,
    )
    assert broker.handle(
        {"op": "github-token", "run_jwt": run_jwt(), "head_sha": "abc123"}
    )["ok"] is True
    commit_calls = [
        headers
        for (method, url), headers in zip(github_fake.calls, github_fake.headers)
        if "/commits/" in url
    ]
    assert commit_calls
    assert commit_calls[0].get("Authorization", "").startswith("Bearer ")


def test_the_health_answer_is_not_ok_while_the_broker_is_not(service, tmp_path: Path) -> None:
    """A watchdog that reads the exit code must not be told 'healthy'."""
    broker, _, _ = service
    broker.policy_path = tmp_path / "no-such-policy.json"
    broker.tick()
    answer = broker.handle({"op": "health"})
    assert answer["ok"] is False
    assert answer["health"]["consecutive_failures"] >= 1


# ---------------------------------------------------------------------------
# the command line, the git credential helper and the launchd copy of record
# ---------------------------------------------------------------------------


def test_the_gitconfig_resets_the_host_credential_helper(tmp_path: Path) -> None:
    """The host's `osxkeychain` helper wins unless the list is reset."""
    from scripts.dt_broker import cli

    path = cli._write_gitconfig(tmp_path / "gitconfig")
    text = path.read_text(encoding="utf-8")
    assert "helper =\n" in text
    assert "git-credential" in text
    assert "!dt-broker" not in text
    assert str(path.parent.parent) not in text


def test_the_credential_helper_refuses_in_host_mode(
    tmp_path: Path, monkeypatch
) -> None:
    from scripts.dt_broker import cli

    flag = tmp_path / "github-auth-mode"
    flag.write_text("host\n", encoding="utf-8")
    monkeypatch.setattr(cli, "DEFAULT_AUTH_MODE_PATH", flag)
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO("protocol=https\nhost=github.com\npath=digithings-ai/digithings.git\n\n"),
    )
    args = argparse.Namespace(operation="get", socket=None)
    env = {"PAPERCLIP_API_KEY": run_jwt()}
    assert cli.cmd_git_credential(args, env) == cli.EXIT_REFUSED


def test_a_refusal_has_its_own_exit_code(monkeypatch) -> None:
    """A refusal is not an outage, and a caller can tell them apart."""
    from scripts.dt_broker import cli

    def _refused(payload, socket_path):
        return {"ok": False, "error": "the run is not running", "code": "auth"}

    monkeypatch.setattr(cli.broker_client, "request", _refused)
    args = argparse.Namespace(json=True, socket=None)
    env = {"PAPERCLIP_API_KEY": run_jwt()}
    assert cli.cmd_identity(args, env) == cli.EXIT_REFUSED


def test_the_launchd_arguments_are_arguments_the_command_understands() -> None:
    """A launchd job that dies on its own command line never listens."""
    from scripts.dt_broker import cli

    plist = REPO_ROOT / "infra" / "self-host" / "dt-broker" / "com.digithings.dt-broker.plist"
    # `plutil` is what launchd itself reads the file with.
    proc = subprocess.run(
        ["plutil", "-convert", "json", "-o", "-", str(plist)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    tree = json.loads(proc.stdout)
    arguments = list(tree["ProgramArguments"])
    parser = cli.build_parser()
    parsed = parser.parse_args(arguments[2:])
    assert parsed.command == "serve"
    assert parsed.socket == "/Users/_dtbroker/run/dt-broker.sock"
    assert parsed.policy == "/Users/_dtbroker/policy.json"


def test_the_daemon_imports_on_the_interpreter_the_launchd_job_names() -> None:
    """The plist names `/usr/bin/python3`, which is Python 3.9 on macOS."""
    interpreter = Path("/usr/bin/python3")
    if not interpreter.exists():  # pragma: no cover - host dependent
        pytest.skip("this host has no /usr/bin/python3")
    proc = subprocess.run(
        [str(interpreter), "-c", "import scripts.dt_broker.cli, scripts.dt_broker.server"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
