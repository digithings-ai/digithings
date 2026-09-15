"""Phase C monitor delivery — webhook/slack fan-out + email (#4065, Task 5).

``validate_delivery`` is the create/update gate (Task 6 HTTP, Task 8 EXA
adapter) with EXA-identical error codes: a non-poll ``DeliveryConfig`` needs at
least one target (``webhook_url_required`` / ``[webhook]: Required``), and
every webhook/slack target URL must be https, carry no userinfo, and resolve —
via ``socket.getaddrinfo`` at validation time — to public addresses only
(``webhook_url_private`` / ``slack_url_private``, EXA's "cannot point to
localhost or private IPs" rule). A hostname that does not resolve is rejected
too: a target that cannot be proven public must not be trusted, and delivery
would resolve it again anyway.

``deliver`` fans one ``MonitorRun`` out to the watch's targets. Webhook/slack
targets receive ``run.model_dump(mode="json")`` as the exact POST body with
``X-digi-signature: sha256=<hmac_sha256(secret, body)>`` (R7h) over httpx, 2
attempts with linear backoff (``_WEBHOOK_ATTEMPTS`` / ``_WEBHOOK_BACKOFF_S``).
Transport errors, 5xx, and 429 are retried; any other 4xx is definitive and
fails fast after one attempt, and the last response's status is recorded. Email
targets receive a text summary over stdlib ``smtplib`` configured from
``DIGISEARCH_SMTP_HOST`` / ``_PORT`` / ``_USER`` / ``_PASS`` / ``_FROM`` (port
defaults to 587; STARTTLS uses ``ssl.create_default_context()`` so the
certificate chain and hostname are verified). Login only happens over
STARTTLS: a relay that does not advertise it gets a ``smtp_tls_unavailable``
receipt whenever credentials are configured, because credentials must never
cross a cleartext connection. A missing or unusable relay config is a failed
receipt, never a raise.

Every target yields exactly one ``DeliveryReceipt``: the per-target boundary
turns any failure — transport exhaustion, SMTP errors, malformed config — into
``ok=False`` instead of an exception, so one bad target cannot abort the
remaining targets or the tick. Receipts are returned to the caller and never
persisted here. Called only for ``status == "ok"`` runs (R13) with a non-poll
mode and a stored per-watch secret; those gates live in the runner. The secret
is never logged and never lands in a receipt: transport error text is redacted
of the secret and of the target URL before it reaches ``DeliveryReceipt.error``
(R8).
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import smtplib
import socket
import ssl
import time
from email.message import EmailMessage
from urllib.parse import urlsplit

import httpx

from digisearch.monitors.models import (
    DeliveryConfig,
    DeliveryReceipt,
    DeliveryTarget,
    MonitorRun,
    Watch,
)

__all__ = ["DeliveryConfigError", "deliver", "validate_delivery"]

logger = logging.getLogger(__name__)

# §4.5: webhook/slack POSTs get 2 attempts with linear backoff.
_WEBHOOK_ATTEMPTS = 2
_WEBHOOK_BACKOFF_S = 0.5

# Sleep seam: tests record backoff without waiting.
_sleep = time.sleep

_DEFAULT_SMTP_PORT = 587

# Stable receipt errors for the email leg (free-form field, but keep them fixed).
_SMTP_NOT_CONFIGURED = "smtp_not_configured"
_EMAIL_RECIPIENTS_MISSING = "email_recipients_missing"
_SMTP_TLS_UNAVAILABLE = "smtp_tls_unavailable"


class DeliveryConfigError(ValueError):
    """A ``DeliveryConfig`` the write path must reject.

    ``code`` is the stable EXA-identical code surfaced in the §4.6 error
    envelope; ``str(exc)`` is the EXA-identical message text.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def validate_delivery(config: DeliveryConfig) -> None:
    """Reject a delivery config that could not be delivered (see module docstring).

    Raises :class:`DeliveryConfigError` with the EXA-identical code and message
    for a missing target list or a non-public target URL; returns ``None`` when
    the config is deliverable. Called on every watch create/update, never only
    at run time.
    """
    if config.mode != "poll" and not config.targets:
        raise DeliveryConfigError("webhook_url_required", "[webhook]: Required")
    for target in config.targets:
        if target.kind == "webhook":
            _validate_target_url(
                target.url,
                required_code="webhook_url_required",
                private_code="webhook_url_private",
                label="webhook",
            )
        elif target.kind == "slack":
            _validate_target_url(
                target.url,
                required_code="slack_url_required",
                private_code="slack_url_private",
                label="slack",
            )


def _validate_target_url(
    url: str | None, *, required_code: str, private_code: str, label: str
) -> None:
    """Enforce the EXA-identical https + public-target rule for one URL."""
    if not url:
        raise DeliveryConfigError(required_code, f"[{label}]: Required")
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise DeliveryConfigError(private_code, _private_message(label)) from exc
    if parsed.scheme != "https" or parsed.username is not None or parsed.password is not None:
        raise DeliveryConfigError(private_code, _private_message(label))
    if not host:
        raise DeliveryConfigError(private_code, _private_message(label))
    try:
        infos = socket.getaddrinfo(host, port or 443, proto=socket.IPPROTO_TCP)
    except (OSError, UnicodeError) as exc:
        raise DeliveryConfigError(private_code, _private_message(label)) from exc
    for info in infos:
        try:
            address = ipaddress.ip_address(info[4][0])
        except ValueError as exc:
            raise DeliveryConfigError(private_code, _private_message(label)) from exc
        if not address.is_global:
            raise DeliveryConfigError(private_code, _private_message(label))


def _private_message(label: str) -> str:
    return f"[{label}.url]: Webhook URL cannot point to localhost or private IPs"


def deliver(
    run: MonitorRun,
    watch: Watch,
    *,
    delivery_secret: str,
    timeout_s: float = 10.0,
) -> list[DeliveryReceipt]:
    """Fan *run* out to *watch*'s targets; exactly one receipt per target.

    Callers gate on ``status == "ok"``, a non-poll delivery mode, and a stored
    secret (R13); this function attempts every target regardless and never
    raises for a target failure — a failed target is an ``ok=False`` receipt.
    """
    payload = json.dumps(run.model_dump(mode="json")).encode("utf-8")
    receipts: list[DeliveryReceipt] = []
    for target in watch.delivery.targets:
        receipt = _attempt_target(
            target,
            run=run,
            watch=watch,
            payload=payload,
            delivery_secret=delivery_secret,
            timeout_s=timeout_s,
        )
        if not receipt.ok:
            # Never the secret and never the target URL (R8): the receipt's
            # error text is already redacted and the URL is not logged.
            logger.warning(
                "monitor delivery failed target_kind=%s status=%s error=%s",
                receipt.target_kind,
                receipt.status_code,
                receipt.error,
            )
        receipts.append(receipt)
    return receipts


def _attempt_target(
    target: DeliveryTarget,
    *,
    run: MonitorRun,
    watch: Watch,
    payload: bytes,
    delivery_secret: str,
    timeout_s: float,
) -> DeliveryReceipt:
    """Deliver to one target; every failure becomes a failed receipt."""
    try:
        if target.kind == "email":
            return _send_email(run, watch, target, timeout_s)
        return _post_json(target, payload, delivery_secret, timeout_s)
    except Exception as exc:
        return DeliveryReceipt(
            target_kind=target.kind,
            ok=False,
            error=_redacted_error(exc, secret=delivery_secret, target_url=target.url),
        )


def _post_json(
    target: DeliveryTarget, payload: bytes, secret: str, timeout_s: float
) -> DeliveryReceipt:
    """POST the signed run body to a webhook/slack target, retried per §4.5."""
    url = target.url or ""
    signature = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "X-digi-signature": f"sha256={signature}",
    }
    last_response: httpx.Response | None = None
    with _client_for(timeout_s) as client:
        for attempt in range(1, _WEBHOOK_ATTEMPTS + 1):
            if attempt > 1:
                _sleep(_WEBHOOK_BACKOFF_S * (attempt - 1))
            try:
                response = client.post(url, content=payload, headers=headers)
            except Exception:
                if attempt == _WEBHOOK_ATTEMPTS:
                    raise
                continue
            if response.is_success:
                return DeliveryReceipt(
                    target_kind=target.kind, ok=True, status_code=response.status_code
                )
            last_response = response
            if not _retryable_status(response.status_code):
                break
    assert last_response is not None
    return DeliveryReceipt(
        target_kind=target.kind,
        ok=False,
        status_code=last_response.status_code,
        error=f"HTTP {last_response.status_code}",
    )


def _retryable_status(status_code: int) -> bool:
    """Server errors and rate limiting are worth a second attempt; 4xx is final."""
    return status_code == 429 or status_code >= 500


def _client_for(timeout_s: float) -> httpx.Client:
    """httpx client factory (test seam): bounded timeout, no redirects.

    Redirects are never followed so a public target cannot 30x the delivery to
    an internal address after validation approved it.
    """
    return httpx.Client(timeout=timeout_s, follow_redirects=False)


def _send_email(
    run: MonitorRun, watch: Watch, target: DeliveryTarget, timeout_s: float
) -> DeliveryReceipt:
    """Send the run summary to one email target over the configured SMTP relay."""
    recipients = [address for address in (target.email_to or []) if address]
    if not recipients:
        return DeliveryReceipt(target_kind="email", ok=False, error=_EMAIL_RECIPIENTS_MISSING)
    settings = _smtp_settings()
    if settings is None:
        return DeliveryReceipt(target_kind="email", ok=False, error=_SMTP_NOT_CONFIGURED)
    host, port, user, password, from_addr = settings
    message = _email_message(run, watch, recipients, from_addr)
    client = _smtp_client(host, port, timeout_s)
    try:
        client.ehlo()
        if client.has_extn("starttls"):
            client.starttls(context=ssl.create_default_context())
            client.ehlo()
        elif user:
            # Fail closed: credentials must never cross a cleartext connection.
            return DeliveryReceipt(target_kind="email", ok=False, error=_SMTP_TLS_UNAVAILABLE)
        if user:
            client.login(user, password)
        client.sendmail(from_addr, recipients, message.as_string())
    finally:
        with contextlib.suppress(Exception):
            client.quit()
    return DeliveryReceipt(target_kind="email", ok=True)


def _smtp_settings() -> tuple[str, int, str, str, str] | None:
    """Read ``DIGISEARCH_SMTP_*``; ``None`` when the relay config is unusable.

    ``_HOST`` is required, ``_FROM`` falls back to ``_USER`` (one of the two
    must be set), ``_PORT`` defaults to 587 and must be numeric, and
    ``_USER``/``_PASS`` are optional (a relay without auth is valid).
    """
    host = os.environ.get("DIGISEARCH_SMTP_HOST", "").strip()
    user = os.environ.get("DIGISEARCH_SMTP_USER", "").strip()
    from_addr = os.environ.get("DIGISEARCH_SMTP_FROM", "").strip() or user
    if not host or not from_addr:
        return None
    try:
        port = int(os.environ.get("DIGISEARCH_SMTP_PORT", str(_DEFAULT_SMTP_PORT)))
    except ValueError:
        return None
    return host, port, user, os.environ.get("DIGISEARCH_SMTP_PASS", ""), from_addr


def _smtp_client(host: str, port: int, timeout_s: float) -> smtplib.SMTP:
    """smtplib factory (test seam); connects to the relay."""
    return smtplib.SMTP(host, port, timeout=timeout_s)


def _email_message(
    run: MonitorRun, watch: Watch, recipients: list[str], from_addr: str
) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = f"[digisearch] {watch.name}: {len(run.results_new)} new result(s)"
    message["From"] = from_addr
    message["To"] = ", ".join(recipients)
    message.set_content(_email_body(run, watch))
    return message


def _email_body(run: MonitorRun, watch: Watch) -> str:
    lines = [
        f"Watch: {watch.name}",
        f"Query: {watch.query}",
        f"Run: {run.run_id}",
        f"New results: {len(run.results_new)} of {len(run.results_all)}",
        "",
    ]
    for index, result in enumerate(run.results_new, start=1):
        title = str(result.get("title") or result.get("url") or "(untitled)")
        lines.append(f"{index}. {title}")
        url = result.get("url")
        if url:
            lines.append(f"   {url}")
    return "\n".join(lines) + "\n"


def _redacted_error(exc: BaseException, *, secret: str, target_url: str | None) -> str:
    """Exception text safe for receipts and logs (R8).

    httpx transport errors may embed the request URL (whose path can carry a
    webhook token), so both the target URL and the per-watch secret are
    stripped before the text leaves this module.
    """
    text = f"{type(exc).__name__}: {exc}"
    if secret:
        text = text.replace(secret, "<redacted>")
    if target_url:
        # Errors can echo the URL either raw or with its trailing slash trimmed.
        for needle in {target_url, target_url.rstrip("/")}:
            if needle:
                text = text.replace(needle, "<target>")
    return text
