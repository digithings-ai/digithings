"""The broker's rules.

Each test here is one rule of the broker: a refusal, or a promise that a token
does not outlive the run that asked for it. The broker is the piece that holds
the GitHub Apps, so the tests are about what it will not do.

Nothing in this file talks to GitHub or to Paperclip. Both are replaced by a
transport that answers from a rule list, the way the rest of the suite replaces
`gh`.
"""

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from scripts.dt_broker import core, github, paperclip, server
from scripts.dt_broker.core import Policy

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


class FakeGitHub:
    """The GitHub calls the broker makes."""

    def __init__(self, *, commit_message: str = "", token: str = MINTED_TOKEN) -> None:
        self.commit_message = commit_message
        self.token = token
        self.calls: list[tuple[str, str]] = []
        self.minted: list[dict[str, Any]] = []
        self.revoked: list[str] = []

    def transport(self, method: str, url: str, headers: Mapping[str, str], body: bytes | None):
        self.calls.append((method, url))
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
