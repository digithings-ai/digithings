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

from scripts.dt_broker import client, ghshim, github, paperclip, server
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
def seat_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """The environment of a seat run."""
    # The scratch directory is named by the shim, not by the caller: a
    # caller that could name it could point it at the host's own `gh`
    # configuration and have it emptied.
    monkeypatch.setattr(ghshim, "RUN_TMP_ROOT", tmp_path / "run-tmp")
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(tmp_path),
        "PAPERCLIP_AGENT_ID": AGENT_ID,
        "PAPERCLIP_RUN_ID": RUN_ID,
        "PAPERCLIP_API_KEY": run_jwt(),
        "GITHUB_TOKEN": "the-host-token",
    }


@pytest.fixture
def guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A stand-in for the host guard, which only has to exist.

    The guard's path is a constant in the shim, not an environment variable:
    a seat that could name its own program as "the guard" would have taken
    the guard out of the chain. The tests change the constant instead.
    """
    path = tmp_path / "gh-guard"
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    monkeypatch.setattr(ghshim, "GUARD_PATH", path)
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


def test_a_pull_request_with_no_repository_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A repository that cannot be identified cannot be cleared either."""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ghshim.Refusal):
        ghshim.check_pull_request_target(["pr", "create"], {})


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
# the rules that were found by the in-session review of 22 October
# ---------------------------------------------------------------------------


def test_the_endpoint_may_sit_behind_a_flag() -> None:
    """`gh api` takes its endpoint after the flags, so every argument is read."""
    with pytest.raises(ghshim.Refusal):
        ghshim.check_pull_request_target(
            ["api", "-X", "POST", "repos/someone-else/their-project/pulls"], {}
        )


def test_the_endpoint_with_a_query_string_is_refused() -> None:
    with pytest.raises(ghshim.Refusal):
        ghshim.check_pull_request_target(
            ["api", "repos/someone-else/their-project/pulls?per_page=1"], {}
        )


def test_a_graphql_mutation_in_an_input_file_is_refused(tmp_path: Path) -> None:
    """`--input` hides the body from the command line."""
    body = tmp_path / "query.json"
    body.write_text(
        json.dumps({"query": "mutation { createPullRequest(input: {}) { clientMutationId } }"}),
        encoding="utf-8",
    )
    with pytest.raises(ghshim.Refusal) as excinfo:
        ghshim.check_pull_request_target(["api", "graphql", "--input", str(body)], {})
    assert "GraphQL" in str(excinfo.value)


def test_the_last_repository_flag_wins() -> None:
    """gh's `--repo` is a plain flag, and the last value set is the one used."""
    with pytest.raises(ghshim.Refusal):
        ghshim.check_pull_request_target(
            [
                "pr",
                "create",
                "--repo",
                "digithings-ai/digithings",
                "--repo",
                "someone-else/their-project",
            ],
            {},
        )


def test_the_attached_repository_flag_is_read() -> None:
    """gh accepts `-Rowner/name`, and a shape the wall cannot read is a hole."""
    # `GH_REPO` is the fallback, so a test that does not set it would pass
    # on the fallback and prove nothing about the flag.
    notes = ghshim.check_pull_request_target(
        ["pr", "create", "-Rdigithings-ai/digithings"], {"GH_REPO": "digithings-ai/other"}
    )
    assert notes == ["pull request against digithings-ai/digithings"]


def test_the_attached_repository_flag_is_checked_against_the_organization() -> None:
    """The short form is not a way around the wall."""
    with pytest.raises(ghshim.Refusal):
        ghshim.check_pull_request_target(
            ["pr", "create", "-Rsomeone-else/their-project"], {}
        )


def test_the_attached_repository_flag_with_an_equal_sign_is_checked() -> None:
    """pflag strips the `=`, so `-R=owner/name` names the same repository."""
    with pytest.raises(ghshim.Refusal):
        ghshim.check_pull_request_target(
            ["pr", "create", "-R=someone-else/their-project"], {}
        )


def test_a_repository_flag_that_names_nothing_is_refused() -> None:
    """A flag with no value is not a call without a repository.

    An ignored flag is a flag the call did not make, and the fallback to
    `GH_REPO` or to the checkout's own remote would then answer for it.
    """
    for call in (
        ["pr", "create", "-R"],
        ["pr", "create", "-R="],
        ["pr", "create", "--repo="],
    ):
        with pytest.raises(ghshim.Refusal):
            ghshim.check_pull_request_target(call, {})


# ---------------------------------------------------------------------------
# the rules the review of DIG-5413 found (DIG-5415)
# ---------------------------------------------------------------------------


def test_a_flag_value_that_parses_as_a_repository_is_not_the_repository() -> None:
    """The title is a title; the call is about the repository gh will use.

    Before DIG-5415 the shim read the title as the repository flag, cleared
    the wall, and gh opened the pull request against `GH_REPO`.
    """
    with pytest.raises(ghshim.Refusal):
        ghshim.check_pull_request_target(
            ["pr", "create", "--title", "-Rdigithings-ai/digithings"],
            {"GH_REPO": "someone-else/their-project"},
        )


def test_a_flag_value_that_parses_as_a_repository_does_not_answer_for_the_call() -> None:
    """The value is skipped, so the fallback answers -- and it is the org one."""
    notes = ghshim.check_pull_request_target(
        ["pr", "create", "--title", "-Rdigithings-ai/digithings"],
        {"GH_REPO": REPO},
    )
    assert notes == [f"pull request against {REPO}"]


def test_a_short_value_flag_with_a_bare_equals_does_not_eat_the_repository_flag() -> None:
    """`-t=` is the title `=`, not "the title is the next argument".

    pflag strips the `=` only when a value follows it, so `-t=` consumes no
    argument and the `--repo` after it is a flag gh reads. A scan that ate
    the next argument read the call as `GH_REPO` and cleared the wall.
    """
    for call in (
        ["pr", "create", "-t=", "--repo", "someone-else/their-project"],
        ["pr", "create", "-fF=", "--repo", "someone-else/their-project"],
        ["pr", "create", "-fF=", "-Rsomeone-else/their-project"],
    ):
        with pytest.raises(ghshim.Refusal):
            ghshim.check_pull_request_target(call, {"GH_REPO": REPO})


def test_a_short_value_flag_with_an_attached_value_is_a_value() -> None:
    """`-tRsomeone-else/x` is a title whose first two letters are `-R`."""
    notes = ghshim.check_pull_request_target(
        ["pr", "create", "-tRsomeone-else/their-project"], {"GH_REPO": REPO}
    )
    assert notes == [f"pull request against {REPO}"]
    with pytest.raises(ghshim.Refusal):
        ghshim.check_pull_request_target(
            ["pr", "create", "-tRsomeone-else/their-project"],
            {"GH_REPO": "someone-else/their-project"},
        )


def test_every_value_flag_skips_its_value() -> None:
    """A value is not a flag position, for every flag that takes one."""
    value = "-Rdigithings-ai/digithings"
    for flag in (
        "--assignee",
        "-a",
        "--attach",
        "--base",
        "-B",
        "--body",
        "-b",
        "--body-file",
        "-F",
        "--head",
        "-H",
        "--label",
        "-l",
        "--milestone",
        "-m",
        "--project",
        "-p",
        "--recover",
        "--reviewer",
        "-r",
        "--template",
        "-T",
        "--title",
        "-t",
    ):
        with pytest.raises(ghshim.Refusal):
            ghshim.check_pull_request_target(
                ["pr", "create", flag, value],
                {"GH_REPO": "someone-else/their-project"},
            )


def test_the_empty_separate_repository_value_is_refused() -> None:
    """`--repo ""` names nothing, so the fallback must not answer for it."""
    for call in (
        ["pr", "create", "--repo", ""],
        ["pr", "create", "-R", ""],
    ):
        with pytest.raises(ghshim.Refusal):
            ghshim.check_pull_request_target(call, {"GH_REPO": REPO})


def test_a_repository_flag_inside_a_short_flag_cluster_is_read() -> None:
    """`-f` is `--fill` on `pr create`, so `-fR owner/name` names the repo."""
    notes = ghshim.check_pull_request_target(
        ["pr", "create", "-fRdigithings-ai/digithings"],
        {"GH_REPO": "digithings-ai/other"},
    )
    assert notes == ["pull request against digithings-ai/digithings"]
    with pytest.raises(ghshim.Refusal):
        ghshim.check_pull_request_target(
            ["pr", "create", "-fRsomeone-else/their-project"], {"GH_REPO": REPO}
        )


def test_an_api_field_value_that_parses_as_a_repository_is_not_the_repository() -> None:
    """`-f` takes a value on `gh api`; it is not the repository flag there."""
    with pytest.raises(ghshim.Refusal):
        ghshim.check_pull_request_target(
            ["api", "repos/{owner}/{repo}/pulls", "-f", "-Rdigithings-ai/digithings"],
            {"GH_REPO": "someone-else/their-project"},
        )


def test_a_flag_the_shim_does_not_know_is_refused() -> None:
    """A flag the shim cannot place could be the repository."""
    with pytest.raises(ghshim.Refusal):
        ghshim.check_pull_request_target(
            ["pr", "create", "--a-flag-we-do-not-know", "x"], {"GH_REPO": REPO}
        )


def test_a_repository_flag_after_the_terminator_is_not_read() -> None:
    """After `--` gh takes positionals; the wall does not read a repo there."""
    notes = ghshim.check_pull_request_target(
        ["pr", "create", "--", "-Rsomeone-else/their-project"], {"GH_REPO": REPO}
    )
    assert notes == [f"pull request against {REPO}"]


# ---------------------------------------------------------------------------
# the rules the review of DIG-5420 found (DIG-5415 was read only there)
# ---------------------------------------------------------------------------


def test_a_repository_flag_in_front_of_the_subcommand_is_read() -> None:
    """Cobra skips a flag and its value while it looks for the subcommand.

    `gh pr --repo someone-else/their-project create` runs `create`, so a
    check that read argv[1] for the subcommand never saw the call at all.
    """
    with pytest.raises(ghshim.Refusal):
        ghshim.check_pull_request_target(
            ["pr", "--repo", "someone-else/their-project", "create", "--title", "x"], {}
        )


def test_a_short_repository_flag_in_front_of_the_subcommand_is_read() -> None:
    """`-R owner/name` and `-Rowner/name` are hoisted shapes gh runs as well."""
    with pytest.raises(ghshim.Refusal):
        ghshim.check_pull_request_target(
            ["pr", "-R", "someone-else/their-project", "create"], {}
        )
    with pytest.raises(ghshim.Refusal):
        ghshim.check_pull_request_target(
            ["pr", "-Rsomeone-else/their-project", "create"], {}
        )


def test_an_attached_repository_flag_in_front_of_the_subcommand_is_read() -> None:
    """`--repo=owner/name` carries its value inside the argument."""
    with pytest.raises(ghshim.Refusal):
        ghshim.check_pull_request_target(
            ["pr", "--repo=someone-else/their-project", "create"], {}
        )


def test_a_value_that_parses_as_a_repository_flag_in_front_of_the_subcommand() -> None:
    """`--repo` takes the next argument whatever it looks like.

    gh reads the whole argument as the repository and refuses it; so does
    the wall, rather than decide that the subcommand was hiding behind the
    value.
    """
    with pytest.raises(ghshim.Refusal):
        ghshim.check_pull_request_target(
            ["pr", "--repo", "-Rdigithings-ai/digithings", "create", "--title", "x"],
            {"GH_REPO": REPO},
        )


def test_the_repository_in_front_of_the_subcommand_is_the_call_its_own() -> None:
    """A hoisted repository flag is the repository gh will use."""
    notes = ghshim.check_pull_request_target(
        ["pr", "--repo", "digithings-ai/digithings", "create", "--title", "x"],
        {"GH_REPO": "someone-else/their-project"},
    )
    assert notes == [f"pull request against {REPO}"]


def test_the_last_repository_flag_wins_across_the_subcommand() -> None:
    """gh's `--repo` is a plain string flag, wherever it sits in the call."""
    with pytest.raises(ghshim.Refusal):
        ghshim.check_pull_request_target(
            [
                "pr",
                "-R",
                "digithings-ai/digithings",
                "create",
                "--repo",
                "someone-else/their-project",
            ],
            {},
        )


def test_a_boolean_flag_in_front_of_the_subcommand_leaves_the_next_argument_in_place() -> None:
    """A boolean takes no value, so `create` is still the first bare argument.

    gh 2.102.0 refuses this shape itself, but the wall reads the same way
    whatever gh answers, and the subcommand is still where the walk says it
    is.
    """
    notes = ghshim.check_pull_request_target(
        ["pr", "--draft", "create", "--repo", "digithings-ai/digithings"], {}
    )
    assert notes == [f"pull request against {REPO}"]


def test_a_flag_the_shim_does_not_know_in_front_of_the_subcommand_is_refused() -> None:
    """A flag the walk cannot place could be carrying the subcommand."""
    with pytest.raises(ghshim.Refusal) as excinfo:
        ghshim.check_pull_request_target(
            ["pr", "--frobnicate", "x", "create"], {"GH_REPO": REPO}
        )
    assert "frobnicate" in str(excinfo.value)


def test_a_subcommand_is_not_found_after_the_terminator() -> None:
    """After `--` the arguments are positionals; nothing back there runs a subcommand."""
    assert ghshim.check_pull_request_target(
        ["pr", "--repo", "someone-else/their-project", "--", "create"], {}
    ) == []


def test_a_call_without_a_subcommand_is_left_alone() -> None:
    """`gh pr --repo owner/name` reaches the help text, not a pull request."""
    notes = ghshim.check_pull_request_target(
        ["pr", "--repo", "someone-else/their-project"], {}
    )
    assert notes == []


def test_the_pull_request_is_read_out_of_a_call_with_a_hoisted_flag() -> None:
    """The review token also needs to know which pull request it is for."""
    assert ghshim.pr_number(["pr", "-R", "o/r", "review", "42"]) == 42
    assert ghshim.pr_number(["pr", "--repo", "o/r", "view", "42"]) == 42
    assert ghshim.pr_number(["pr", "--repo", "o/r", "view", "--json", "title", "42"]) == 42


def test_the_new_alias_of_create_is_read() -> None:
    """`gh pr new` is `gh pr create`.

    The walker hands back a name and the wall decides: `new` is the alias
    of `create`, and a hoisted repository flag answers for it the same way.
    The match is exact, so a name gh itself would refuse is a shape the
    wall does not have to answer for.
    """
    with pytest.raises(ghshim.Refusal):
        ghshim.check_pull_request_target(
            ["pr", "--repo", "someone-else/their-project", "new", "--title", "x"], {}
        )


def test_host_mode_still_refuses_a_hoisted_repository_flag(
    seat_env: dict[str, str],
    guard: Path,
    host_mode: Path,
    captured: list[dict[str, Any]],
) -> None:
    """In host mode the wall is the only control, and it holds."""
    code = ghshim.main(
        ["pr", "--repo", "someone-else/their-project", "create", "--title", "x"],
        seat_env,
    )
    assert code == ghshim.EXIT_REFUSED
    assert captured == []


def test_a_relative_body_path_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The path is relative, but the mistake is the same one."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "review.md").write_text(BODY, encoding="utf-8")
    with pytest.raises(ghshim.Refusal) as excinfo:
        ghshim.rewrite_fields(
            ["api", f"repos/{REPO}/issues/1/comments", "-f", "body=review.md"]
        )
    assert "path" in str(excinfo.value)


def test_a_field_keeps_the_flag_it_was_written_with() -> None:
    """`-F` types its value and `-f` does not; the shim does not change that."""
    argv, _ = ghshim.rewrite_fields(["api", "repos/o/r/issues/1", "-F", "state=closed"])
    assert argv[-2:] == ["-F", "state=closed"]
    argv, _ = ghshim.rewrite_fields(["api", "repos/o/r/issues/1", "--field", "state=closed"])
    assert argv[-2:] == ["--field", "state=closed"]


def test_the_upstream_remote_is_the_one_that_is_checked(tmp_path: Path) -> None:
    """gh opens a pull request against `upstream`; so does the shim."""
    checkout = tmp_path / "fork"
    checkout.mkdir()
    subprocess.run(["git", "init", "-q", str(checkout)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(checkout), "remote", "add", "origin",
         "git@github.com:digithings-ai/digithings.git"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(checkout), "remote", "add", "upstream",
         "git@github.com:someone-else/their-project.git"],
        check=True,
        capture_output=True,
    )
    assert ghshim._git_remote_repo(checkout) == "someone-else/their-project"


def test_the_rules_hold_for_a_process_that_is_not_a_seat(
    captured: list[dict[str, Any]], guard: Path
) -> None:
    """The organization rule is not a seat rule: it is ours."""
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    assert ghshim.main(["pr", "create", "--repo", "someone-else/their-project"], env) == (
        ghshim.EXIT_REFUSED
    )
    assert captured == []


# ---------------------------------------------------------------------------
# the guard, and the modes
# ---------------------------------------------------------------------------


def test_the_shim_never_calls_the_real_gh(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pointing the shim at the real `gh` would turn the guard off."""
    monkeypatch.setattr(ghshim, "GUARD_PATH", Path("/opt/homebrew/bin/gh"))
    with pytest.raises(ghshim.Refusal) as excinfo:
        ghshim.guard_path({})
    assert "guard" in str(excinfo.value)


def test_the_guard_path_is_not_an_environment_variable(
    seat_env: dict[str, str], captured: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A seat that could name its own program as the guard would turn it off."""
    monkeypatch.setattr(ghshim, "GUARD_PATH", Path("/opt/homebrew/bin/gh"))
    seat_env["DT_BROKER_GH_GUARD"] = "/tmp/a-program-of-my-own"
    assert ghshim.main(["pr", "list"], seat_env) == ghshim.EXIT_REFUSED
    assert captured == []


def test_a_guard_that_is_the_real_gh_is_refused(
    seat_env: dict[str, str], captured: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ghshim, "GUARD_PATH", Path("/opt/homebrew/bin/gh"))
    assert ghshim.main(["pr", "list"], seat_env) == ghshim.EXIT_REFUSED
    assert captured == []


def test_app_mode_gives_the_guard_a_per_run_token(
    seat_env: dict[str, str],
    guard: Path,
    app_mode: Path,
    captured: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ghshim, "request_token", lambda env, pr=None: ("the-minted-token", {}))
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
    monkeypatch.setattr(ghshim, "request_token", lambda env, pr=None: ("the-minted-token", {}))
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
    monkeypatch.setattr(ghshim, "request_token", lambda env, pr=None: ("the-minted-token", {}))
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
    monkeypatch.setattr(ghshim, "request_token", lambda env, pr=None: ("the-minted-token", {}))
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

    def _not_asked(env: dict[str, str], pr: int | None = None) -> tuple[str, dict[str, Any]]:
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

    def _unavailable(env: dict[str, str], pr: int | None = None) -> tuple[str, dict[str, Any]]:
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

    def _not_asked(env: dict[str, str], pr: int | None = None) -> tuple[str, dict[str, Any]]:
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
    seat_env[ghshim.SHIM_MARKER] = "1"
    assert ghshim.main(["pr", "list"], seat_env) == ghshim.EXIT_REFUSED
    assert captured == []


def test_a_process_with_no_run_credential_is_refused(
    tmp_path: Path,
    guard: Path,
    app_mode: Path,
    captured: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The host's own credential is never the fallback.

    The guard decides who is a seat, and the shim does not decide that with
    three environment variables a caller controls: the broker decides it,
    from the run credential, against the Paperclip API. A caller that
    shows no credential gets no token -- and no host credential either.
    """
    monkeypatch.setattr(ghshim, "RUN_TMP_ROOT", tmp_path / "run-tmp")
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(tmp_path),
        "GITHUB_TOKEN": "the-host-token",
    }
    assert ghshim.main(["pr", "list"], env) == ghshim.EXIT_AUTH
    assert captured == []


def test_a_process_with_no_run_credential_keeps_the_host_token_out(
    tmp_path: Path,
    guard: Path,
    app_mode: Path,
    captured: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even a caller that unsets the seat markers does not get the host token."""
    monkeypatch.setattr(ghshim, "RUN_TMP_ROOT", tmp_path / "run-tmp")
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(tmp_path),
        "PAPERCLIP_AGENT_ID": AGENT_ID,
        "PAPERCLIP_RUN_ID": RUN_ID,
        "GITHUB_TOKEN": "the-host-token",
    }
    assert ghshim.main(["pr", "list"], env) == ghshim.EXIT_AUTH
    assert captured == []


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


def _run_shim(
    env: dict[str, str],
    guard: Path,
    socket: Path | None = None,
    run_tmp: Path | None = None,
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    """Run the shim as a process, the way a seat run would.

    The guard's path and the broker's socket are constants in the shim, and
    the test changes them the way a caller of the module would: in the
    process that runs the shim. There is no environment variable that names
    either of them, because a seat that could name them would have taken
    the guard or the broker out of the chain.
    """
    code = (
        "import os, sys\n"
        "from pathlib import Path\n"
        "from scripts.dt_broker import ghshim\n"
        f"ghshim.GUARD_PATH = {str(guard)!r}\n"
        + (f"ghshim.BROKER_SOCKET = {str(socket)!r}\n" if socket is not None else "")
        + (f"ghshim.RUN_TMP_ROOT = Path({str(run_tmp)!r})\n" if run_tmp is not None else "")
        + "sys.exit(ghshim.main(sys.argv[1:], dict(os.environ)))\n"
    )
    return subprocess.run(
        [sys.executable, "-c", code, *arguments],
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
        "GITHUB_TOKEN": "the-host-token",
    }
    proc = _run_shim(
        env,
        guard,
        socket_path,
        tmp_path / "run-tmp",
        "api",
        f"repos/{REPO}/issues/1/comments",
        "-f",
        f"body=@{body}",
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
    }
    proc = _run_shim(
        env,
        guard,
        socket_path,
        tmp_path / "run-tmp",
        "pr",
        "create",
        "--repo",
        "someone-else/their-project",
    )
    assert proc.returncode == ghshim.EXIT_REFUSED
    assert "digithings-ai" in proc.stderr
    assert not (tmp_path / "guard-record.json").exists()
    assert github_fake.minted == []


# ---------------------------------------------------------------------------
# the rules the review of 22 October found
# ---------------------------------------------------------------------------


def test_the_broker_socket_is_not_an_environment_variable(
    seat_env: dict[str, str], captured: list[dict[str, Any]]
) -> None:
    """A seat that named the socket would be talking to a broker of its own."""
    seat_env["DT_BROKER_SOCKET"] = "/tmp/a-socket-of-my-own.sock"
    assert ghshim.socket_path(seat_env) == ghshim.BROKER_SOCKET
    assert captured == []


def test_the_scratch_directory_is_not_named_by_the_caller(
    seat_env: dict[str, str],
) -> None:
    """A caller that named the directory could have the host's own emptied."""
    seat_env["DT_BROKER_RUN_TMP"] = str(Path.home())
    path = ghshim.run_tmp(seat_env)
    assert Path(ghshim.RUN_TMP_ROOT) in path.parents


def test_a_scratch_directory_that_is_a_symlink_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A symlink is not followed: the shim empties only what it made."""
    real = tmp_path / "real"
    real.mkdir()
    monkeypatch.setattr(ghshim, "RUN_TMP_ROOT", tmp_path / "run")
    env = {"PAPERCLIP_RUN_ID": RUN_ID}
    base = ghshim.run_tmp(env)
    base.parent.mkdir(parents=True, exist_ok=True)
    base.symlink_to(real)
    with pytest.raises(ghshim.Refusal):
        ghshim.empty_gh_config_dir(env)
    assert list(real.iterdir()) == []


def test_a_configuration_directory_that_is_a_symlink_is_not_followed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The host's own `gh` configuration is not unlinked by a seat."""
    host = tmp_path / "host-gh"
    host.mkdir()
    (host / "hosts.yml").write_text("the host's own credential", encoding="utf-8")
    monkeypatch.setattr(ghshim, "RUN_TMP_ROOT", tmp_path / "run")
    env = {"PAPERCLIP_RUN_ID": RUN_ID}
    base = ghshim.run_tmp(env)
    base.mkdir(parents=True, exist_ok=True)
    (base / "gh").symlink_to(host)
    target = ghshim.empty_gh_config_dir(env)
    assert target.is_dir()
    assert not target.is_symlink()
    assert (host / "hosts.yml").read_text(encoding="utf-8") == "the host's own credential"


def test_the_run_credential_decides_and_not_the_markers(
    seat_env: dict[str, str],
    app_mode: Path,
    captured: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The broker decides who is a seat, from the credential it checks."""
    monkeypatch.setattr(ghshim, "request_token", lambda env, pr=None: ("the-minted-token", {}))
    for name in ("PAPERCLIP_AGENT_ID", "PAPERCLIP_RUN_ID", "PAPERCLIP_TASK_ID"):
        seat_env.pop(name, None)
    assert ghshim.main(["pr", "list"], seat_env) == ghshim.EXIT_OK
    assert captured[0]["env"]["GH_TOKEN"] == "the-minted-token"


def test_app_mode_removes_the_host_variable_too(
    seat_env: dict[str, str],
    app_mode: Path,
    captured: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`GH_HOST` chooses the host, and the token goes to the host."""
    monkeypatch.setattr(ghshim, "request_token", lambda env, pr=None: ("the-minted-token", {}))
    seat_env["GH_HOST"] = "github.example.com"
    assert ghshim.main(["pr", "list"], seat_env) == ghshim.EXIT_OK
    assert "GH_HOST" not in captured[0]["env"]


def test_a_call_that_names_another_host_is_refused(
    seat_env: dict[str, str], captured: list[dict[str, Any]]
) -> None:
    """The token is a credential for one host."""
    code = ghshim.main(["api", "--hostname", "github.example.com", "user"], seat_env)
    assert code == ghshim.EXIT_REFUSED
    assert captured == []


def test_printing_the_token_is_refused(
    seat_env: dict[str, str],
    app_mode: Path,
    captured: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A token in a file is a token out of the chain."""
    monkeypatch.setattr(ghshim, "request_token", lambda env, pr=None: ("the-minted-token", {}))
    assert ghshim.main(["auth", "token"], seat_env) == ghshim.EXIT_REFUSED
    assert captured == []


def test_the_organization_rule_does_not_care_about_case(
    seat_env: dict[str, str], captured: list[dict[str, Any]]
) -> None:
    """`REPOS/evilorg/evil/pulls` is the same endpoint as the lower case."""
    code = ghshim.main(["api", "-X", "POST", "REPOS/evilorg/evil/pulls"], seat_env)
    assert code == ghshim.EXIT_REFUSED
    assert captured == []


def test_the_organization_rule_resolves_a_path_that_walks_out(
    seat_env: dict[str, str], captured: list[dict[str, Any]]
) -> None:
    """`repos/digithings-ai/../evilorg/evil/pulls` names the repository it reaches."""
    code = ghshim.main(
        ["api", "-X", "POST", "repos/digithings-ai/../evilorg/evil/pulls"], seat_env
    )
    assert code == ghshim.EXIT_REFUSED
    assert captured == []


def test_a_nul_byte_in_a_field_is_refused(
    seat_env: dict[str, str], captured: list[dict[str, Any]]
) -> None:
    """A NUL byte cannot be passed to a program, and the shim says so."""
    code = ghshim.main(["api", "repos/o/r/issues/1", "-f", "body=with\x00nul"], seat_env)
    assert code == ghshim.EXIT_REFUSED
    assert captured == []


def test_the_answer_must_be_about_this_run(
    seat_env: dict[str, str],
    app_mode: Path,
    captured: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An answer about another run is not this run's token."""
    monkeypatch.setattr(
        client,
        "github_token",
        lambda run_jwt, **kwargs: {
            "ok": True,
            "token": "the-minted-token",
            "run_id": "a-different-run",
        },
    )
    assert ghshim.main(["pr", "list"], seat_env) == ghshim.EXIT_REFUSED
    assert captured == []


def test_a_token_for_one_pull_request_is_not_used_for_another(
    seat_env: dict[str, str],
    app_mode: Path,
    captured: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A review token is bound to one pull request."""
    monkeypatch.setattr(
        ghshim,
        "request_token",
        lambda env, pr=None: ("the-minted-token", {"run_id": RUN_ID, "pr_number": 42}),
    )
    assert ghshim.main(["pr", "review", "99"], seat_env) == ghshim.EXIT_REFUSED
    assert captured == []


def test_a_token_for_a_pull_request_needs_a_call_about_one(
    seat_env: dict[str, str],
    app_mode: Path,
    captured: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A token that is bound to a pull request is not used on anything else."""
    monkeypatch.setattr(
        ghshim,
        "request_token",
        lambda env, pr=None: ("the-minted-token", {"run_id": RUN_ID, "pr_number": 42}),
    )
    assert ghshim.main(["pr", "list"], seat_env) == ghshim.EXIT_REFUSED
    assert captured == []


def test_a_refusal_does_not_echo_a_credential(
    seat_env: dict[str, str], captured: list[dict[str, Any]], capsys: pytest.CaptureFixture
) -> None:
    """A caller that sent a token by mistake does not have it written down."""
    secret = "ghp_" + "A" * 20
    code = ghshim.main(["api", "repos/o/r/issues/1", "-f", secret], seat_env)
    assert code == ghshim.EXIT_REFUSED
    assert secret not in capsys.readouterr().err


def test_a_refusal_does_not_echo_a_credential_from_the_repository(
    seat_env: dict[str, str], captured: list[dict[str, Any]], capsys: pytest.CaptureFixture
) -> None:
    """The refusal quotes the repository the caller named, so it is redacted."""
    secret = "ghp_" + "B" * 20
    code = ghshim.main(["pr", "create", "-R", f"{secret}/their-project"], seat_env)
    assert code == ghshim.EXIT_REFUSED
    assert secret not in capsys.readouterr().err


def test_a_note_does_not_echo_a_credential_from_the_repository() -> None:
    """The note about the repository goes into the run log, so it is redacted."""
    secret = "ghp_" + "C" * 20
    notes = ghshim.check_pull_request_target(
        ["pr", "create", "-R", f"digithings-ai/{secret}"], {}
    )
    assert secret not in " ".join(notes)


def test_the_pull_request_is_read_out_of_the_call(
    seat_env: dict[str, str], app_mode: Path, captured: list[dict[str, Any]]
) -> None:
    """The shim says which pull request the call is about."""
    assert ghshim.pr_number(["pr", "review", "42"]) == 42
    assert ghshim.pr_number(["pr", "review", "--repo", "o/r", "42"]) == 42
    assert ghshim.pr_number(["api", "repos/o/r/pulls/42/reviews"]) == 42
    assert ghshim.pr_number(["pr", "list"]) is None


def test_the_value_of_a_flag_is_not_the_pull_request() -> None:
    """`gh pr view --json title 42` is about pull request 42."""
    assert ghshim.pr_number(["pr", "view", "--json", "title", "6263"]) == 6263
    assert ghshim.pr_number(["pr", "view", "--json", "title", "title", "6263"]) == 6263


def test_a_branch_name_is_not_the_pull_request() -> None:
    """A bare argument that is not a number is not the number."""
    assert ghshim.pr_number(["pr", "view", "my-branch"]) is None
    assert ghshim.pr_number(["pr", "view", "my-branch", "42"]) == 42
