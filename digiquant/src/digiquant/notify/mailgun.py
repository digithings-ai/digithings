"""Thin Mailgun HTTP client for K5 email dispatch (fail-soft callers only).

API key and domain come from env — never logged. Suppression is checked before send.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

MAILGUN_API_KEY_ENV = "MAILGUN_API_KEY"
MAILGUN_DOMAIN_ENV = "MAILGUN_DOMAIN"
NOTIFY_FROM_ENV = "NOTIFY_FROM"
NOTIFY_UNSUBSCRIBE_BASE_ENV = "NOTIFY_UNSUBSCRIBE_BASE"

DEFAULT_UNSUBSCRIBE_BASE = "https://digiquant.io/olympus/settings/notifications"


class MailgunTransportError(Exception):
    """Raised when Mailgun HTTP fails — dispatch catches and fail-softs."""


class MailgunClientProtocol(Protocol):
    def is_suppressed(self, email: str) -> bool: ...

    def send_message(
        self,
        to: str,
        subject: str,
        text_body: str,
        html_body: str,
    ) -> None: ...


@dataclass(frozen=True)
class MailgunConfig:
    api_key: str
    domain: str
    from_address: str
    unsubscribe_base: str

    @classmethod
    def from_env(cls) -> MailgunConfig | None:
        api_key = (os.environ.get(MAILGUN_API_KEY_ENV) or "").strip()
        domain = (os.environ.get(MAILGUN_DOMAIN_ENV) or "").strip()
        from_address = (os.environ.get(NOTIFY_FROM_ENV) or "").strip()
        if not api_key or not domain or not from_address:
            return None
        base = (os.environ.get(NOTIFY_UNSUBSCRIBE_BASE_ENV) or DEFAULT_UNSUBSCRIBE_BASE).strip()
        return cls(
            api_key=api_key,
            domain=domain,
            from_address=from_address,
            unsubscribe_base=base.rstrip("/"),
        )


def unsubscribe_url(workspace_id: str, config: MailgunConfig) -> str:
    """Placeholder toggle URL for notification_prefs (T3 settings ships the real page)."""
    return f"{config.unsubscribe_base}?workspace={workspace_id}"


class UrllibMailgunClient:
    """Stdlib urllib POST wrapper — no extra deps beyond the repo baseline."""

    def __init__(self, config: MailgunConfig) -> None:
        self._config = config

    def is_suppressed(self, email: str) -> bool:
        encoded = quote(email, safe="")
        url = f"https://api.mailgun.net/v3/{self._config.domain}/bounces/{encoded}"
        try:
            req = Request(url, method="GET")
            req.add_header("Authorization", f"Basic {self._basic_auth()}")
            with urlopen(req, timeout=15) as resp:
                return 200 <= resp.status < 300
        except HTTPError as exc:
            if exc.code == 404:
                return False
            raise MailgunTransportError(str(exc)) from exc
        except URLError as exc:
            raise MailgunTransportError(str(exc)) from exc

    def send_message(
        self,
        to: str,
        subject: str,
        text_body: str,
        html_body: str,
    ) -> None:
        url = f"https://api.mailgun.net/v3/{self._config.domain}/messages"
        payload = (
            f"from={self._config.from_address}&to={quote(to)}"
            f"&subject={quote(subject)}"
            f"&text={quote(text_body)}"
            f"&html={quote(html_body)}"
        ).encode()
        try:
            req = Request(url, data=payload, method="POST")
            req.add_header("Authorization", f"Basic {self._basic_auth()}")
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
            with urlopen(req, timeout=30) as resp:
                if resp.status < 200 or resp.status >= 300:
                    raise MailgunTransportError(f"unexpected status {resp.status}")
        except (HTTPError, URLError) as exc:
            raise MailgunTransportError(str(exc)) from exc

    def _basic_auth(self) -> str:
        # Mailgun uses api:key as Basic user:password — key must not be logged.
        import base64

        token = base64.b64encode(f"api:{self._config.api_key}".encode()).decode("ascii")
        return token


def build_mailgun_client() -> MailgunClientProtocol | None:
    config = MailgunConfig.from_env()
    if config is None:
        return None
    return UrllibMailgunClient(config)


__all__ = [
    "DEFAULT_UNSUBSCRIBE_BASE",
    "MAILGUN_API_KEY_ENV",
    "MAILGUN_DOMAIN_ENV",
    "MailgunClientProtocol",
    "MailgunConfig",
    "MailgunTransportError",
    "NOTIFY_FROM_ENV",
    "NOTIFY_UNSUBSCRIBE_BASE_ENV",
    "UrllibMailgunClient",
    "build_mailgun_client",
    "unsubscribe_url",
]
