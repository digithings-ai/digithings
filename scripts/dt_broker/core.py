"""Policy, identity, JWT signing and the audit log for the dt-broker.

Everything the broker decides is decided from a policy file that Chris owns.
The seat cannot edit it, cannot widen it and cannot read the private keys it
points at. This module holds that policy model, the RS256 signing of the GitHub
App JWT (done with `openssl`, because the repository has no crypto dependency
and a broker that needs a wheel to start is a broker that does not start), the
reading of the rollback flag, and the audit log that records what the broker
did without ever recording what it minted.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: The two authentication modes. `host` is today's behaviour: the seat uses
#: whatever `gh` auth the host already has. `app` is the broker: every call
#: goes through a per-run, per-repository GitHub App token.
APP_MODE = "app"
HOST_MODE = "host"
AUTH_MODES: tuple[str, ...] = (APP_MODE, HOST_MODE)

#: The rollback flag. It lives in the home of the account that owns the
#: broker, and every seat on this machine runs as Chris, so a flag in
#: Chris's own home would be a flag a seat could rewrite. Here it is a file
#: the broker owns and the seats can only read. Chris writes it; nobody else
#: does, and `host` restores today's behaviour.
DEFAULT_AUTH_MODE_PATH = Path("/Users/_dtbroker/.config/digithings/github-auth-mode")

#: Where the daemon listens. A unix socket, not a TCP port: nothing outside
#: the machine can reach it, and the socket's group decides who can.
#:
#: The ticket's example was `/var/run/dt-broker.sock`. `/var/run` is owned by
#: root and is not writable by a daemon running as `_dtbroker`, so a socket
#: there needs a sudo-created parent directory that a cleanup can remove
#: under the daemon's feet. The socket lives in the broker account's own run
#: directory instead: the daemon creates it itself, so it survives a reboot
#: and a cleanup. The mode (0660) and the group (`_dtseats`) are as the
#: ticket says.
DEFAULT_SOCKET_PATH = Path("/Users/_dtbroker/run/dt-broker.sock")

#: The paths Chris owns. The daemon reads the policy and the keys; it never
#: writes to the policy.
DEFAULT_POLICY_PATH = Path("/Users/_dtbroker/policy.json")
DEFAULT_STATE_DIR = Path("/Users/_dtbroker/state")

#: Permissions no seat may ever hold, whatever the policy file says.
#: `secrets` writes the credential store, which is the one thing a token must
#: never be able to reach.
DENIED_PERMISSIONS_ALWAYS: frozenset[str] = frozenset({"secrets"})

#: Permissions denied to the seat classes. The broker hands a seat a token
#: that can read and write code and pull requests, and nothing that can post a
#: commit status (that is the CI's own receipt) and nothing that can drive a
#: workflow (that is a way to run code the seat cannot see).
DENIED_PERMISSIONS_BY_CLASS: Mapping[str, frozenset[str]] = {
    "seat": frozenset({"statuses", "workflows"}),
    "reviewer": frozenset({"statuses", "workflows"}),
}

#: The permissions every GitHub App token needs, whatever the policy says.
#: Without `metadata` the token cannot read the repository at all.
BASE_PERMISSIONS: frozenset[str] = frozenset({"metadata"})

#: How long the App JWT lives. Ten minutes: long enough to mint a token with,
#: short enough that a leaked JWT is not a standing key.
APP_JWT_TTL_SECONDS = 600

#: A GitHub App installation token lives an hour. The broker never asks for
#: more, and it revokes at the end of the run.
INSTALLATION_TOKEN_TTL_SECONDS = 3600

#: The permissions a request may ask for, checked against the class. A
#: request that names a permission its class does not hold is an escalation
#: attempt and is refused, not silently trimmed.
PERMISSION_NAMES: tuple[str, ...] = (
    "actions",
    "administration",
    "checks",
    "contents",
    "deployments",
    "discussions",
    "issues",
    "members",
    "metadata",
    "packages",
    "pages",
    "pull_requests",
    "repository_hooks",
    "secret_scanning_alerts",
    "secrets",
    "security_events",
    "statuses",
    "workflows",
)

#: The identity a bot commits under, and the trailers that name the seat and
#: the run that wrote the commit. Both spellings of the trailers are emitted:
#: the queue reads `Paperclip-Agent-Id` / `Paperclip-Run-Id`, the ticket asks
#: for `Paperclip-Seat` / `Paperclip-Run`.
SEAT_TRAILER = "Paperclip-Seat"
RUN_TRAILER = "Paperclip-Run"
AGENT_TRAILER = "Paperclip-Agent-Id"
AGENT_ID_TRAILER = "Paperclip-Run-Id"

#: The trailers the broker reads to find out who wrote a commit.
OWNER_TRAILER_RE = re.compile(
    r"^(?:Paperclip-Agent-Id|Paperclip-Seat)\s*:\s*(?P<owner>[0-9A-Za-z][0-9A-Za-z._-]*)\s*$",
    re.MULTILINE,
)

#: The agent-id trailer on its own. The review check reads this one and not
#: the other: `Paperclip-Seat` names the App, which is the same for every
#: seat that uses it, so it cannot tell the author of a change from the
#: reviewer of it.
AGENT_ID_OWNER_RE = re.compile(
    r"^Paperclip-Agent-Id\s*:\s*(?P<owner>[0-9A-Za-z][0-9A-Za-z._-]*)\s*$",
    re.MULTILINE,
)

#: A UUID, the shape every Paperclip agent id and run id has.
UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-"
    r"[0-9a-fA-F]{12}$"
)

#: A GitHub token. Any value that looks like one is redacted before it can
#: reach the audit log, whatever the caller asked to record.
_GITHUB_TOKEN_RE = re.compile(r"^gh[pousr]_[A-Za-z0-9]{16,}$")
#: A JSON web token. The App JWT is one of these, and it must not land in a log.
_JWT_RE = re.compile(r"^ey[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*$")

#: Keys whose value is never written, whatever it looks like.
FORBIDDEN_LOG_KEYS: frozenset[str] = frozenset(
    {"token", "password", "secret", "authorization", "private_key", "key", "run_jwt"}
)


class BrokerError(RuntimeError):
    """The broker refused, or could not answer.

    The message is the whole answer: it goes back to the caller over the
    socket and it is written to the audit log. It never carries a credential.
    """


class PolicyError(BrokerError):
    """The policy file is missing, malformed, or says something impossible."""


class AuthError(BrokerError):
    """The caller is not who it claims to be, or its run is over."""


class TokenError(BrokerError):
    """GitHub refused to mint, or to revoke, a token."""


class RefusedError(BrokerError):
    """The request was well-formed but the policy does not allow it."""


def _b64url(raw: bytes) -> str:
    """Base64url without padding, the way a JWT wants it."""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(text: str) -> bytes:
    """Inverse of `_b64url`, tolerant of missing padding."""
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def last4(token: str) -> str:
    """The last four characters of a token. The only part that is ever logged."""
    return token[-4:] if token else ""


def looks_secret(value: str) -> bool:
    """True when a string has the shape of a credential.

    The audit log redacts on this, so the redaction does not depend on the
    caller remembering which field carries the token.
    """
    if not value:
        return False
    return bool(_GITHUB_TOKEN_RE.match(value) or _JWT_RE.match(value))


def scrub(fields: Mapping[str, Any]) -> dict[str, Any]:
    """Redact anything that looks like a credential out of a log record."""
    clean: dict[str, Any] = {}
    for key, value in fields.items():
        if key.lower() in FORBIDDEN_LOG_KEYS:
            clean[key] = "[redacted]"
        elif isinstance(value, str) and looks_secret(value):
            clean[key] = "[redacted]"
        elif isinstance(value, Mapping):
            clean[key] = scrub(value)
        else:
            clean[key] = value
    return clean


def read_auth_mode(path: Path | None = None, *, default: str = APP_MODE) -> str:
    """Read the rollback flag.

    `app` means the broker is in charge. `host` restores today's behaviour.
    A flag that is absent, unreadable, or that says something else entirely
    reads as `default`, which is `app` for the seat shim: a switch that is
    misspelled must never turn the broker off, and the safe reading is the
    one where the broker keeps deciding.

    The merge queue reads the same file itself, in
    `scripts/merge_queue.py`, because there the flag may only ever *lower* a
    gate: `host` puts the provenance check back into shadow. A damaged flag
    there leaves the gate exactly as it was.
    """
    target = path if path is not None else DEFAULT_AUTH_MODE_PATH
    try:
        raw = target.read_text(encoding="utf-8").strip().lower()
    except (OSError, UnicodeDecodeError):
        return default
    return raw if raw in AUTH_MODES else default


def find_openssl() -> str:
    """The `openssl` binary. The daemon runs with a minimal PATH, so the
    absolute system path is the fallback rather than the exception."""
    found = shutil.which("openssl")
    if found:
        return found
    for candidate in ("/usr/bin/openssl", "/opt/homebrew/bin/openssl"):
        if os.path.exists(candidate):
            return candidate
    raise BrokerError("openssl is not available; the broker cannot sign an App JWT")


def sign_rs256(payload: Mapping[str, Any], key_path: Path) -> str:
    """Sign a payload as an RS256 JWT with `openssl`.

    The repository has no crypto dependency and the broker must not add one:
    a broker that needs a wheel installed before it starts is a broker that
    fails open at the worst moment. `openssl dgst -sha256 -sign` is the
    primitive, and it is on every machine that has a key.
    """
    header = {"alg": "RS256", "typ": "JWT"}
    signing_input = ".".join(
        (
            _b64url(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")),
            _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")),
        )
    ).encode("ascii")
    if not key_path.exists():
        raise BrokerError(f"the App private key is not readable at {key_path}")
    try:
        proc = subprocess.run(
            [find_openssl(), "dgst", "-sha256", "-sign", str(key_path), "-binary"],
            input=signing_input,
            capture_output=True,
            check=False,
        )
    except OSError as exc:  # pragma: no cover - depends on the host
        raise BrokerError(f"openssl could not be run: {exc}") from exc
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        tail = detail[-1] if detail else "unknown error"
        raise BrokerError(f"openssl refused to sign the App JWT: {tail}")
    return f"{signing_input.decode('ascii')}.{_b64url(proc.stdout)}"


def decode_jwt_claims(token: str) -> dict[str, Any]:
    """Read the claims of a JWT without verifying its signature.

    This is a shape check, not an authentication: it says the token is a JWT,
    that it has not expired, that it was minted for this API and that it
    names a run. The authority check is the API call itself -- the broker
    presents the token to `GET /api/agents/me` and the API answers for
    nobody else.
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise AuthError("the run credential is not a JWT")
    try:
        header = json.loads(_b64url_decode(parts[0]))
        payload = json.loads(_b64url_decode(parts[1]))
    except (ValueError, json.JSONDecodeError) as exc:
        raise AuthError(f"the run credential is not a readable JWT: {exc}") from exc
    if not isinstance(header, dict) or not isinstance(payload, dict):
        raise AuthError("the run credential is not a readable JWT")
    audience = payload.get("aud")
    audiences = audience if isinstance(audience, list) else [audience]
    if "paperclip-api" not in audiences:
        raise AuthError("the run credential was not minted for the Paperclip API")
    expiry = payload.get("exp")
    if not isinstance(expiry, (int, float)):
        raise AuthError("the run credential carries no expiry")
    if expiry <= time.time():
        raise AuthError("the run credential has expired")
    if not payload.get("run_id"):
        raise AuthError("the run credential names no run")
    return payload


@dataclass(frozen=True)
class AppConfig:
    """One GitHub App: its id, its installation, its key and its bot login."""

    name: str
    app_id: str
    installation_id: str
    key_path: Path
    bot_login: str

    def to_record(self) -> dict[str, Any]:
        """The part of the App that may be logged."""
        return {
            "app": self.name,
            "app_id": self.app_id,
            "installation_id": self.installation_id,
            "bot_login": self.bot_login,
        }


@dataclass(frozen=True)
class SeatClass:
    """A class of seat: the App it uses and the permissions it may ask for."""

    name: str
    app: str
    permissions: Mapping[str, str]

    def denied(self) -> frozenset[str]:
        """The permissions this class may never hold."""
        return DENIED_PERMISSIONS_ALWAYS | DENIED_PERMISSIONS_BY_CLASS.get(self.name, frozenset())


@dataclass(frozen=True)
class SeatBinding:
    """What the policy says about one agent."""

    agent_id: str
    seat_class: str
    repos: tuple[str, ...] | None = None


@dataclass(frozen=True)
class Policy:
    """The broker's policy: who may have what, from which App, where."""

    version: int
    org: str
    apps: Mapping[str, AppConfig]
    classes: Mapping[str, SeatClass]
    seats: Mapping[str, SeatBinding]
    paperclip_api_url: str = "http://127.0.0.1:3100"
    review_app: str = "digithings-review"

    # -- construction ---------------------------------------------------

    @staticmethod
    def from_dict(raw: Mapping[str, Any], source: str = "<policy>") -> Policy:
        """Build a policy from a parsed JSON document.

        Every failure names the file and the field. A policy that half loads
        is worse than a policy that does not load: the daemon would serve a
        narrower world than the file describes and nothing would say so.
        """
        if not isinstance(raw, Mapping):
            raise PolicyError(f"{source}: the policy is not a JSON object")

        version = raw.get("version")
        if not isinstance(version, int):
            raise PolicyError(f"{source}: `version` must be an integer")

        org = str(raw.get("org") or "").strip()
        if not org:
            raise PolicyError(f"{source}: `org` must name the GitHub organization")

        apps: dict[str, AppConfig] = {}
        for name, block in (raw.get("apps") or {}).items():
            if not isinstance(block, Mapping):
                raise PolicyError(f"{source}: apps.{name} must be an object")
            app_id = str(block.get("app_id") or "").strip()
            installation_id = str(block.get("installation_id") or "").strip()
            key_path = str(block.get("key_path") or "").strip()
            if not app_id or not installation_id or not key_path:
                raise PolicyError(
                    f"{source}: apps.{name} needs `app_id`, `installation_id` and `key_path`"
                )
            apps[str(name)] = AppConfig(
                name=str(name),
                app_id=app_id,
                installation_id=installation_id,
                key_path=Path(key_path),
                bot_login=str(block.get("bot_login") or f"{name}[bot]"),
            )

        classes: dict[str, SeatClass] = {}
        for name, block in (raw.get("classes") or {}).items():
            if not isinstance(block, Mapping):
                raise PolicyError(f"{source}: classes.{name} must be an object")
            app = str(block.get("app") or "").strip()
            if app not in apps:
                raise PolicyError(f"{source}: classes.{name} names an unknown App: {app!r}")
            perms = block.get("permissions") or {}
            if not isinstance(perms, Mapping):
                raise PolicyError(f"{source}: classes.{name}.permissions must be an object")
            permissions: dict[str, str] = {}
            for permission, level in perms.items():
                if str(permission) in DENIED_PERMISSIONS_ALWAYS:
                    raise PolicyError(
                        f"{source}: classes.{name} asks for a permission no seat may hold: "
                        f"{permission}"
                    )
                if str(permission) in DENIED_PERMISSIONS_BY_CLASS.get(str(name), frozenset()):
                    raise PolicyError(
                        f"{source}: classes.{name} asks for a permission this class may never "
                        f"hold: {permission}"
                    )
                permissions[str(permission)] = str(level)
            classes[str(name)] = SeatClass(
                name=str(name), app=app, permissions=permissions
            )

        seats: dict[str, SeatBinding] = {}
        for agent_id, block in (raw.get("seats") or {}).items():
            if not isinstance(block, Mapping):
                raise PolicyError(f"{source}: seats.{agent_id} must be an object")
            seat_class = str(block.get("class") or "").strip()
            if seat_class not in classes:
                raise PolicyError(
                    f"{source}: seats.{agent_id} names an unknown class: {seat_class!r}"
                )
            repos_raw = block.get("repos")
            repos: tuple[str, ...] | None = None
            if repos_raw is not None:
                if not isinstance(repos_raw, list):
                    raise PolicyError(f"{source}: seats.{agent_id}.repos must be a list")
                repos = tuple(str(item) for item in repos_raw)
            seats[str(agent_id)] = SeatBinding(
                agent_id=str(agent_id), seat_class=seat_class, repos=repos
            )

        return Policy(
            version=version,
            org=org,
            apps=apps,
            classes=classes,
            seats=seats,
            paperclip_api_url=str(raw.get("paperclip_api_url") or "http://127.0.0.1:3100"),
            review_app=str(raw.get("review_app") or "digithings-review"),
        )

    @staticmethod
    def load(path: Path) -> Policy:
        """Read a policy file from disk."""
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise PolicyError(f"the policy file {path} does not exist") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise PolicyError(f"the policy file {path} could not be read: {exc}") from exc
        return Policy.from_dict(raw, source=str(path))

    # -- decisions ------------------------------------------------------

    def seat_for(self, agent_id: str) -> SeatBinding:
        """The binding for an agent, or a refusal."""
        binding = self.seats.get(agent_id)
        if binding is None:
            raise RefusedError(f"agent {agent_id} is not bound to a seat class")
        return binding

    def class_for(self, binding: SeatBinding) -> SeatClass:
        """The class of a binding, or a refusal."""
        seat_class = self.classes.get(binding.seat_class)
        if seat_class is None:
            raise RefusedError(f"seat class {binding.seat_class!r} is not in the policy")
        return seat_class

    def app_for(self, seat_class: SeatClass) -> AppConfig:
        """The App a class uses, or a refusal."""
        app = self.apps.get(seat_class.app)
        if app is None:
            raise RefusedError(f"App {seat_class.app!r} is not in the policy")
        return app

    def check_org(self, repo: str) -> str:
        """Refuse a repository that is not in our organization.

        The organization is the outer wall. Every repository in it is allowed;
        every repository outside it is refused, whatever else the policy says.
        """
        name = str(repo or "").strip()
        if "/" not in name:
            raise RefusedError(f"{name!r} is not a repository name")
        owner, _, repo_name = name.partition("/")
        if owner.lower() != self.org.lower():
            raise RefusedError(
                f"{name} is outside the {self.org} organization; the broker does not mint "
                "tokens for other organizations"
            )
        if not repo_name:
            raise RefusedError(f"{name!r} is not a repository name")
        return name

    def check_repo_allowed(self, binding: SeatBinding, repo: str) -> str:
        """Refuse a repository the seat's own binding does not name."""
        name = self.check_org(repo)
        if binding.repos is None:
            return name
        allowed = {item.lower() for item in binding.repos}
        if name.lower() not in allowed:
            raise RefusedError(
                f"{name} is not one of the repositories bound to this seat"
            )
        return name

    def select_permissions(
        self, seat_class: SeatClass, requested: Iterable[str] | None
    ) -> dict[str, str]:
        """The permissions a token carries.

        Without a request the token carries the class's permissions. With one,
        every named permission must be one the class holds: a request for a
        permission the class does not hold is an escalation and is refused
        rather than quietly trimmed, because a quietly trimmed request is a
        request nobody sees the answer to.
        """
        held = dict(seat_class.permissions)
        if requested is None:
            selected = held
        else:
            selected = {}
            for name in requested:
                key = str(name)
                if key not in held:
                    raise RefusedError(
                        f"seat class {seat_class.name!r} may not hold {key!r}; "
                        "the request asked for a permission it does not have"
                    )
                selected[key] = held[key]
        denied = seat_class.denied()
        for key in denied:
            selected.pop(key, None)
        if not selected:
            raise RefusedError("the request would mint a token with no permissions at all")
        return selected

    def is_review_class(self, seat_class: SeatClass) -> bool:
        """True when this class uses the review App."""
        return seat_class.app == self.review_app


def owners_from_commit_message(message: str) -> list[str]:
    """Every seat id a commit's trailers name.

    The broker needs this for the review path: a seat may not review its own
    change. Both trailer spellings are read -- `Paperclip-Agent-Id` for the
    queue's own convention and `Paperclip-Seat` for the ticket's -- and *all*
    of them are returned, not just the first: the author of a commit writes
    its message, so an author that puts a decoy trailer first would otherwise
    be read as somebody else.
    """
    found: list[str] = []
    for match in OWNER_TRAILER_RE.finditer(message or ""):
        owner = match.group("owner").strip()
        if owner and owner not in found:
            found.append(owner)
    return found


def agent_ids_from_commit_message(message: str) -> list[str]:
    """Every agent id a commit's trailers name.

    Only the `Paperclip-Agent-Id` trailer counts here: it is the one that
    names a seat rather than an App. A commit that names no agent id has an
    author the broker cannot name, and the caller is told so rather than
    being let through.
    """
    found: list[str] = []
    for match in AGENT_ID_OWNER_RE.finditer(message or ""):
        owner = match.group("owner").strip()
        if owner and owner not in found:
            found.append(owner)
    return found


def owner_from_commit_message(message: str) -> str | None:
    """The first seat a commit's trailers name, or None."""
    owners = owners_from_commit_message(message)
    return owners[0] if owners else None


def audit(path: Path, event: str, **fields: Any) -> dict[str, Any]:
    """Write one line to the audit log.

    The log is the evidence that the broker did what it says it did, and that
    no token ever landed in it. Every value is scrubbed on the way in, so a
    caller that passes a token by mistake still cannot write one.
    """
    record: dict[str, Any] = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event": event,
    }
    record.update(scrub(fields))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.parent.chmod(0o750)
        except OSError:
            pass
        # The log holds agent ids, run ids, repository names and permission
        # lists. It holds no credential, but it is still the broker's record
        # of what it did, so it is not world-readable.
        try:
            handle = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o640)
        except OSError:
            handle = -1
        if handle < 0:
            raise OSError(f"the log {path} could not be opened")
        with os.fdopen(handle, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
    except OSError as exc:
        # A log that cannot be written must not stop the broker from
        # answering, but it must be visible: the caller gets the fact and
        # the daemon's own error log says so.
        record["_log_error"] = True
        print(f"dt-broker: the audit log {path} could not be written: {exc}", file=sys.stderr)
    return record
