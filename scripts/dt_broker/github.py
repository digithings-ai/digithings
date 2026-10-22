"""The GitHub calls the broker makes.

Four of them: mint an installation token, revoke it, read the numeric id of a
bot login, and read the message of a commit (which is where the seat that
wrote it is named).

The transport is injected so the tests can answer these calls without a
network and without a key: a test hands the client a fake transport and reads
back exactly what the broker asked GitHub for.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Optional

from .core import APP_JWT_TTL_SECONDS, AppConfig, BrokerError, TokenError, sign_rs256

#: The GitHub REST API. `api.github.com` is the public host; a GitHub
#: Enterprise host would be a policy field, not a guess.
DEFAULT_API_BASE = "https://api.github.com"

#: The user agent every call carries. GitHub asks for one and the broker
#: names itself in it, so a rate-limit notice says who was asking.
USER_AGENT = "dt-broker/1.0 (+https://github.com/digithings-ai/digithings)"

#: How long a GitHub call may take before the broker gives up.
DEFAULT_TIMEOUT = 20


@dataclass(frozen=True)
class HttpResponse:
    """One HTTP answer."""

    status: int
    body: bytes
    headers: Mapping[str, str] | None = None


#: A transport takes a method, a url, headers and a body and answers with an
#: `HttpResponse`. The default one uses urllib; the tests replace it.
#:
#: `Optional` rather than `bytes | None`: this alias is evaluated when the
#: module is imported, and the daemon runs on the interpreter macOS ships
#: (`/usr/bin/python3`, 3.9), where `X | Y` is a `TypeError` at import time.
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
            return HttpResponse(
                status=int(response.status),
                body=response.read(),
                headers={k.lower(): v for k, v in response.headers.items()},
            )
    except urllib.error.HTTPError as exc:
        return HttpResponse(
            status=int(exc.code),
            body=exc.read(),
            headers={k.lower(): v for k, v in (exc.headers or {}).items()},
        )
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise BrokerError(f"GitHub could not be reached: {exc}") from exc


@dataclass(frozen=True)
class InstallationToken:
    """A minted installation token and what it is scoped to."""

    token: str
    expires_at: str
    repositories: tuple[str, ...]
    permissions: Mapping[str, str]

    def to_record(self) -> dict[str, Any]:
        """The part of the token that may be logged: no token, only its tail."""
        return {
            "expires_at": self.expires_at,
            "repositories": list(self.repositories),
            "permissions": dict(self.permissions),
        }


class GitHubClient:
    """The GitHub REST calls the broker makes."""

    def __init__(
        self,
        api_base: str = DEFAULT_API_BASE,
        transport: Transport | None = None,
    ) -> None:
        self.api_base = api_base.rstrip("/")
        self._transport = transport or urllib_transport

    # -- plumbing -------------------------------------------------------

    def _call(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str],
        body: bytes | None = None,
    ) -> tuple[int, bytes]:
        url = f"{self.api_base}{path}"
        merged = {"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT}
        merged.update(headers)
        response = self._transport(method, url, merged, body)
        return response.status, response.body

    def _json(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        body = None
        merged = dict(headers)
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            merged["Content-Type"] = "application/json"
        status, raw = self._call(method, path, headers=merged, body=body)
        text = raw.decode("utf-8", "replace")
        if status >= 400:
            raise TokenError(f"GitHub answered {status}: {_message_of(text)}")
        if not text.strip():
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise TokenError(f"GitHub answered with something that is not JSON: {exc}") from exc
        return parsed if isinstance(parsed, dict) else {"value": parsed}

    # -- the calls ------------------------------------------------------

    def _app_jwt(self, app: AppConfig, now: float | None = None) -> str:
        """A ten-minute App JWT, signed with the App's own private key.

        The App JWT is what authenticates a call that is made *before* a
        token exists: reading a commit to find out who wrote it, and reading
        a login to get its numeric id. An unauthenticated read of a private
        repository is answered with a 404, so those two calls would be dead
        on `twelve-x` and `digiforge` without it.
        """
        issued = int(time.time() if now is None else now)
        return sign_rs256(
            {
                "iat": issued - 60,
                "exp": issued + APP_JWT_TTL_SECONDS,
                "iss": app.app_id,
            },
            app.key_path,
        )

    def mint_installation_token(
        self,
        *,
        app: AppConfig,
        repositories: Sequence[str],
        permissions: Mapping[str, str],
        now: float | None = None,
    ) -> InstallationToken:
        """Mint a one-hour installation token scoped to `repositories`.

        The App JWT is signed with the App's private key and lives ten
        minutes. GitHub's `repositories` field names repositories by their
        bare name, so `digithings-ai/digithings` is sent as `digithings`.
        """
        issued = int(time.time() if now is None else now)
        jwt = sign_rs256(
            {
                "iat": issued - 60,
                "exp": issued + APP_JWT_TTL_SECONDS,
                "iss": app.app_id,
            },
            app.key_path,
        )
        names = [name.split("/", 1)[-1] for name in repositories]
        payload = self._json(
            "POST",
            f"/app/installations/{app.installation_id}/access_tokens",
            headers={"Authorization": f"Bearer {jwt}"},
            payload={"repositories": names, "permissions": dict(permissions)},
        )
        token = str(payload.get("token") or "")
        if not token:
            raise TokenError("GitHub minted no token")
        return InstallationToken(
            token=token,
            expires_at=str(payload.get("expires_at") or ""),
            repositories=tuple(repositories),
            permissions=dict(permissions),
        )

    def revoke_installation_token(self, token: str) -> None:
        """Revoke an installation token.

        The token authenticates its own revocation: GitHub accepts the
        installation token in the `Authorization` header of the delete.
        """
        status, raw = self._call(
            "DELETE",
            "/installation/token",
            headers={"Authorization": f"token {token}"},
        )
        if status >= 400 and status != 404:
            detail = raw.decode("utf-8", "replace")
            raise TokenError(f"GitHub refused to revoke the token: {_message_of(detail)}")

    def user_id(self, app: AppConfig, login: str) -> str:
        """The numeric id of a login, which is what a noreply address needs.

        The call is made with the App's own JWT: an unauthenticated read is
        answered from the anonymous rate limit, and the answer is not
        guaranteed to be the same one.
        """
        payload = self._json(
            "GET",
            f"/users/{login}",
            headers={"Authorization": f"Bearer {self._app_jwt(app)}"},
        )
        value = payload.get("id")
        if value is None:
            raise TokenError(f"GitHub did not answer with an id for {login}")
        return str(value)

    def commit_message(self, app: AppConfig, repo: str, sha: str) -> str:
        """The message of a commit, which is where its trailers are.

        The call is made with the App's own JWT: the repositories this broker
        serves include private ones, and an unauthenticated read of a private
        repository is answered with a 404 -- which would make the review
        check fail on exactly the repositories that need it.
        """
        payload = self._json(
            "GET",
            f"/repos/{repo}/commits/{sha}",
            headers={"Authorization": f"Bearer {self._app_jwt(app)}"},
        )
        commit = payload.get("commit")
        message = ""
        if isinstance(commit, Mapping):
            message = str(commit.get("message") or "")
        if not message:
            message = str(payload.get("message") or "")
        return message


def _message_of(text: str) -> str:
    """GitHub's error body is JSON with a `message`; fall back to the text."""
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text.strip()[:200] or "no detail"
    if isinstance(parsed, Mapping):
        detail = str(parsed.get("message") or "")
        if detail:
            return detail[:200]
    return text.strip()[:200] or "no detail"


def noreply_address(bot_login: str, bot_id: str) -> str:
    """The address a bot commits under.

    GitHub's own rule: `<id>+<login>@users.noreply.github.com` is the
    address of the account with that numeric id and login, so a commit that
    GitHub attributes to the bot is attributed to the right bot even when two
    Apps share a name.
    """
    return f"{bot_id}+{bot_login}@users.noreply.github.com"
