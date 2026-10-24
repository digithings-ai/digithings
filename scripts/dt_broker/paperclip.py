"""The Paperclip calls that turn a run credential into a run context.

A seat proves who it is with its run JWT. The broker does not trust the JWT
on its own -- it hands the token to the Paperclip API and lets the API answer
for itself. Three facts come back and the broker needs all three:

* who the agent is (`GET /api/agents/me`),
* whether the run is still running (`GET /api/heartbeat-runs/{run_id}`),
* which repository the ticket is bound to (`GET /api/issues/{issue_id}`).

The third is the one that scopes the token. It is read from the ticket's
execution workspace, so the repository follows the ticket rather than
whatever the seat says it wants to push to.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Optional

from .core import AuthError, BrokerError, decode_jwt_claims

#: How long a Paperclip call may take before the broker gives up.
DEFAULT_TIMEOUT = 15


class PaperclipError(BrokerError):
    """The Paperclip API could not answer, or answered that no."""


@dataclass(frozen=True)
class HttpResponse:
    """One HTTP answer."""

    status: int
    body: bytes


#: A transport takes a method, a url, headers and a body and answers with an
#: `HttpResponse`. The default one uses urllib; the tests replace it.
#:
#: `Optional` rather than `bytes | None`: the alias is evaluated at import
#: time, and the daemon runs on the interpreter macOS ships.
Transport = Callable[[str, str, Mapping[str, str], Optional[bytes]], HttpResponse]


def urllib_transport(
    method: str, url: str, headers: Mapping[str, str], body: bytes | None
) -> HttpResponse:
    """The default transport: `urllib`, with the error body kept."""
    request = urllib.request.Request(url, data=body, method=method)
    for key, value in headers.items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as response:
            return HttpResponse(status=int(response.status), body=response.read())
    except urllib.error.HTTPError as exc:
        return HttpResponse(status=int(exc.code), body=exc.read())
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise BrokerError(f"Paperclip could not be reached: {exc}") from exc


@dataclass(frozen=True)
class RunContext:
    """Everything the broker learned about one run."""

    agent_id: str
    run_id: str
    issue_id: str
    repo: str

    def to_record(self) -> dict[str, Any]:
        """The part of a run context that may be logged."""
        return {
            "agent_id": self.agent_id,
            "run_id": self.run_id,
            "issue_id": self.issue_id,
            "repo": self.repo,
        }


class PaperclipClient:
    """The three Paperclip reads the broker needs."""

    def __init__(
        self,
        base_url: str,
        token: str,
        transport: Transport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._token = token
        self._transport = transport or urllib_transport

    def _get(self, path: str) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
        }
        response = self._transport("GET", url, headers, None)
        text = response.body.decode("utf-8", "replace")
        if response.status == 404:
            raise PaperclipError(f"Paperclip has no {path}")
        if response.status >= 400:
            raise PaperclipError(f"Paperclip answered {response.status} on {path}")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise PaperclipError(f"Paperclip answered with something that is not JSON: {exc}") from exc
        return parsed if isinstance(parsed, dict) else {}

    def agents_me(self) -> dict[str, Any]:
        """Who the run credential is. The API is the authority on this."""
        return self._get("/api/agents/me")

    def heartbeat_run(self, run_id: str) -> dict[str, Any]:
        """The run itself, including whether it is still running."""
        return self._get(f"/api/heartbeat-runs/{run_id}")

    def issue(self, issue_id: str) -> dict[str, Any]:
        """The ticket, including the repository its workspace is bound to."""
        return self._get(f"/api/issues/{issue_id}")


def repo_from_issue(issue: Mapping[str, Any]) -> str:
    """The repository a ticket is bound to, as `owner/name`.

    The workspace is the answer: an issue provisioned into a workspace names
    the repository there. When there is no workspace, the ticket has no
    repository and the broker refuses rather than guessing one.
    """
    workspace = issue.get("currentExecutionWorkspace")
    if not isinstance(workspace, Mapping):
        raise Refused("the ticket has no execution workspace, so it names no repository")
    raw = workspace.get("repoUrl") or ""
    url = str(raw).strip()
    if not url:
        raise Refused("the ticket's execution workspace names no repository")
    tail = url.rstrip("/").rsplit("/", 2)
    if len(tail) < 2 or not tail[-1] or not tail[-2]:
        raise Refused(f"the ticket's repository url is not readable: {url}")
    return f"{tail[-2]}/{tail[-1]}"


def issue_id_from_run(run: Mapping[str, Any]) -> str:
    """The ticket a run is working on.

    Two places carry it: the run's own `nativeIssueId`, and the recovery
    admission block in the runner profile, which is where a run that was
    resumed from a ticket keeps the link.
    """
    for key in ("nativeIssueId", "issueId", "taskId"):
        value = run.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    profile = run.get("runnerProfileJson")
    if isinstance(profile, Mapping):
        admission = profile.get("chatControlRecoveryAdmission")
        if isinstance(admission, Mapping):
            value = admission.get("issueId")
            if isinstance(value, str) and value.strip():
                return value.strip()
    raise PaperclipError("the run names no ticket")


class Refused(AuthError):
    """The run is real but the ticket does not give the broker a repository."""


def verify_run_credential(client: PaperclipClient, run_jwt: str) -> tuple[str, str, dict[str, Any]]:
    """The agent and run a credential really names, or a refusal.

    The API is the authority: the credential is presented to
    `GET /api/agents/me`, and the answer -- not the credential's own claims
    -- decides who the caller is. The run is then asked whether it belongs
    to that agent.

    The run's *status* is not checked here. A revocation happens at the end
    of a run, when the run is over, and a check that refused a finished run
    would make the revocation impossible exactly when it is needed.
    """
    claims = decode_jwt_claims(run_jwt)
    run_id = str(claims.get("run_id") or "")

    agent = client.agents_me()
    agent_id = str(agent.get("id") or "")
    if not agent_id:
        raise AuthError("the run credential names no agent")
    subject = str(claims.get("sub") or "")
    if subject and subject != agent_id:
        raise AuthError("the run credential names a different agent than the API answers for")

    run = client.heartbeat_run(run_id)
    run_agent = str(run.get("agentId") or "")
    if run_agent and run_agent != agent_id:
        raise AuthError(f"run {run_id} belongs to another agent")
    return agent_id, run_id, run


def resolve_run_context(client: PaperclipClient, run_jwt: str) -> RunContext:
    """Turn a run credential into a run context, or refuse.

    The order matters. The credential is read for shape, then the API is
    asked who it belongs to, then the run is asked whether it is still
    running. A run that has ended is refused before the repository is even
    looked at: a token for a finished run is a token for nobody.
    """
    agent_id, run_id, run = verify_run_credential(client, run_jwt)

    status = str(run.get("status") or "").lower()
    if status != "running":
        raise AuthError(f"run {run_id} is {status or 'unknown'}, not running")

    issue_id = issue_id_from_run(run)
    issue = client.issue(issue_id)
    repo = repo_from_issue(issue)
    return RunContext(agent_id=agent_id, run_id=run_id, issue_id=issue_id, repo=repo)
