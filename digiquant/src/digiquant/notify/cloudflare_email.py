"""Thin Cloudflare Email Sending client for K5 email dispatch.

Sends over the account-scoped REST endpoint (`/accounts/<id>/email/sending/send`)
with stdlib urllib — no SDK dependency, matching the rest of the notify package.

The API token is a dedicated **Email Sending: Edit** token
(``CLOUDFLARE_EMAIL_API_TOKEN``), deliberately *not* the broad deploy token: a
rotation of one must not break the other. ``CLOUDFLARE_ACCOUNT_ID`` is not a
credential and reuses the existing repo secret. Values are never logged.

Suppression is enforced by the service, which blocks the send and does not charge
it against quota, so :meth:`CloudflareEmailClient.is_suppressed` is a no-op kept for
the client protocol — unlike the old provider there is nothing to pre-check.

Cron / post-run callers may fail-soft via :func:`build_email_client` returning
``None``. Probes and CLI entrypoints use :func:`missing_notify_env_names` /
:func:`format_notify_not_configured` to **fail loudly** with named env keys
(``NOTIFY_NOT_CONFIGURED``) so missing vendor secrets are never silent green.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

CLOUDFLARE_EMAIL_API_TOKEN_ENV = "CLOUDFLARE_EMAIL_API_TOKEN"
CLOUDFLARE_ACCOUNT_ID_ENV = "CLOUDFLARE_ACCOUNT_ID"
NOTIFY_FROM_ENV = "NOTIFY_FROM"
NOTIFY_UNSUBSCRIBE_BASE_ENV = "NOTIFY_UNSUBSCRIBE_BASE"
NOTIFY_NOT_CONFIGURED = "NOTIFY_NOT_CONFIGURED"

# Ordered for HUMAN-UNBLOCK / staging inventory — never log values.
NOTIFY_REQUIRED_ENV: tuple[str, ...] = (
    CLOUDFLARE_EMAIL_API_TOKEN_ENV,
    CLOUDFLARE_ACCOUNT_ID_ENV,
    NOTIFY_FROM_ENV,
)

DEFAULT_UNSUBSCRIBE_BASE = "https://digiquant.io/dashboard/settings/notifications"
SEND_URL_TEMPLATE = "https://api.cloudflare.com/client/v4/accounts/{account_id}/email/sending/send"


class EmailTransportError(Exception):
    """Raised when a send fails — dispatch catches and fail-softs."""


class NotifyNotConfiguredError(RuntimeError):
    """Named misconfig — missing notify env (values never included)."""

    code = NOTIFY_NOT_CONFIGURED

    def __init__(self, missing: list[str]) -> None:
        self.missing = list(missing)
        super().__init__(format_notify_not_configured(self.missing))


class EmailClientProtocol(Protocol):
    def is_suppressed(self, email: str) -> bool: ...

    def send_message(
        self,
        to: str,
        subject: str,
        text_body: str,
        html_body: str,
    ) -> None: ...


def _nonempty(value: str | None) -> bool:
    if value is None:
        return False
    stripped = value.strip()
    if not stripped:
        return False
    return stripped.upper() not in {"EMPTY", "NULL", "NONE", "UNDEFINED", "***"}


def missing_notify_env_names(environ: Mapping[str, str] | None = None) -> list[str]:
    """Return required notify env *names* that are missing/empty."""
    env = os.environ if environ is None else environ
    return [name for name in NOTIFY_REQUIRED_ENV if not _nonempty(env.get(name))]


def format_notify_not_configured(missing: list[str]) -> str:
    """Single-line failure for CLI / pytest (names only; never values)."""
    joined = ", ".join(missing)
    return (
        f"{NOTIFY_NOT_CONFIGURED}: missing {joined}. "
        "Set the Cloudflare Email Sending token (Email Sending: Edit) + "
        "CLOUDFLARE_ACCOUNT_ID + NOTIFY_FROM; see docs/ops/SECRETS_INVENTORY.md."
    )


def split_from_address(value: str) -> tuple[str, str | None]:
    """``Name <addr@domain>`` → ``(addr, name)``; a bare address → ``(addr, None)``."""
    text = value.strip()
    if text.endswith(">") and "<" in text:
        name, _, rest = text.partition("<")
        return rest[:-1].strip(), name.strip() or None
    return text, None


def _from_field(from_address: str, from_name: str | None) -> str | dict[str, str]:
    if from_name is None:
        return from_address
    return {"address": from_address, "name": from_name}


@dataclass(frozen=True)
class CloudflareEmailConfig:
    api_token: str
    account_id: str
    from_address: str
    unsubscribe_base: str
    from_name: str | None = None

    @classmethod
    def from_env(cls) -> CloudflareEmailConfig | None:
        if missing_notify_env_names():
            return None
        api_token = (os.environ.get(CLOUDFLARE_EMAIL_API_TOKEN_ENV) or "").strip()
        account_id = (os.environ.get(CLOUDFLARE_ACCOUNT_ID_ENV) or "").strip()
        from_address, from_name = split_from_address(os.environ.get(NOTIFY_FROM_ENV) or "")
        base = (os.environ.get(NOTIFY_UNSUBSCRIBE_BASE_ENV) or DEFAULT_UNSUBSCRIBE_BASE).strip()
        return cls(
            api_token=api_token,
            account_id=account_id,
            from_address=from_address,
            from_name=from_name,
            unsubscribe_base=base.rstrip("/"),
        )

    @classmethod
    def require_from_env(cls) -> CloudflareEmailConfig:
        """Loud-fail constructor for probes/CLI — raises :class:`NotifyNotConfiguredError`."""
        missing = missing_notify_env_names()
        if missing:
            raise NotifyNotConfiguredError(missing)
        cfg = cls.from_env()
        if cfg is None:  # pragma: no cover — defensive; missing list should have caught this
            raise NotifyNotConfiguredError(list(NOTIFY_REQUIRED_ENV))
        return cfg

    @property
    def send_url(self) -> str:
        return SEND_URL_TEMPLATE.format(account_id=self.account_id)


def unsubscribe_url(workspace_id: str, config: CloudflareEmailConfig) -> str:
    """Placeholder toggle URL for notification_prefs (T3 settings ships the real page)."""
    return f"{config.unsubscribe_base}?workspace={workspace_id}"


class CloudflareEmailClient:
    """Stdlib urllib POST wrapper — no extra deps beyond the repo baseline."""

    def __init__(self, config: CloudflareEmailConfig) -> None:
        self._config = config

    def is_suppressed(self, email: str) -> bool:
        """No pre-check: Cloudflare enforces suppression at send time.

        A suppressed recipient is blocked by the service and is not billed against
        the monthly quota, so there is nothing to query here. Kept so callers keep
        one client protocol.
        """
        return False

    def send_message(
        self,
        to: str,
        subject: str,
        text_body: str,
        html_body: str,
    ) -> None:
        payload = {
            "to": to,
            "from": _from_field(self._config.from_address, self._config.from_name),
            "subject": subject,
            "text": text_body,
            "html": html_body,
        }
        try:
            req = Request(
                self._config.send_url,
                data=json.dumps(payload).encode("utf-8"),
                method="POST",
            )
            req.add_header("Authorization", f"Bearer {self._config.api_token}")
            req.add_header("Content-Type", "application/json")
            with urlopen(req, timeout=30) as resp:
                body = resp.read()
                if resp.status < 200 or resp.status >= 300:
                    raise EmailTransportError(f"unexpected status {resp.status}")
        except HTTPError as exc:
            raise EmailTransportError(_http_error_detail(exc)) from exc
        except URLError as exc:
            raise EmailTransportError(str(exc)) from exc
        detail = _api_error_detail(body)
        if detail is not None:
            raise EmailTransportError(f"cloudflare email rejected the send: {detail}")


def _http_error_detail(exc: HTTPError) -> str:
    try:
        body = exc.read()
    except Exception:  # pragma: no cover — defensive; unreadable body
        return f"HTTP {exc.code}"
    detail = _api_error_detail(body)
    return f"HTTP {exc.code}: {detail}" if detail else f"HTTP {exc.code}"


def _api_error_detail(body: bytes) -> str | None:
    """``{"success": false, "errors": [{"code", "message"}]}`` → ``"10102 forbidden"``."""
    if not body:
        return None
    try:
        parsed: Any = json.loads(body)
    except (ValueError, TypeError):
        return None
    if not isinstance(parsed, dict) or parsed.get("success", True):
        return None
    errors = parsed.get("errors")
    if not isinstance(errors, list) or not errors:
        return "success=false"
    first = errors[0] if isinstance(errors[0], dict) else {}
    code = first.get("code")
    message = first.get("message")
    return f"{code} {message}".strip() if (code or message) else "success=false"


def build_email_client() -> EmailClientProtocol | None:
    config = CloudflareEmailConfig.from_env()
    if config is None:
        return None
    return CloudflareEmailClient(config)


__all__ = [
    "CLOUDFLARE_ACCOUNT_ID_ENV",
    "CLOUDFLARE_EMAIL_API_TOKEN_ENV",
    "CloudflareEmailClient",
    "CloudflareEmailConfig",
    "DEFAULT_UNSUBSCRIBE_BASE",
    "EmailClientProtocol",
    "EmailTransportError",
    "NOTIFY_FROM_ENV",
    "NOTIFY_NOT_CONFIGURED",
    "NOTIFY_REQUIRED_ENV",
    "NOTIFY_UNSUBSCRIBE_BASE_ENV",
    "NotifyNotConfiguredError",
    "build_email_client",
    "format_notify_not_configured",
    "missing_notify_env_names",
    "split_from_address",
    "unsubscribe_url",
]
