"""Two-phase approval tickets for IBKR orders (130-coverage Task 7).

``digifetch_ibkr_preview_order`` mints a ticket (never executes); the caller
hands the returned token to ``digifetch_ibkr_execute_order``, which redeems it
exactly once. The token is an HMAC-SHA256 over the ticket bytes + expiry with a
server-side key from ``GLOOMBERB_APPROVAL_KEY`` (never committed, never logged):
tickets are ticket-hash-bound (any field change breaks the signature), expire
after ``APPROVAL_TTL_SECONDS`` (15 minutes), and are single-use (redeemed
tokens are recorded in-process and rejected on replay).

Until the gate design passes human review the execute path ships DISABLED (the
client returns ``upstream_error`` with zero brokerage traffic); preview,
dry-run, and ticket validation work immediately.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import threading
import time
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "APPROVAL_KEY_ENV",
    "APPROVAL_TTL_SECONDS",
    "ApprovalError",
    "OrderTicket",
    "issue_ticket",
    "redeem_token",
]

#: Env var holding the server-side HMAC key. Never committed, never logged.
APPROVAL_KEY_ENV = "GLOOMBERB_APPROVAL_KEY"

#: Ticket time-to-live: 15 minutes (locked gate rule).
APPROVAL_TTL_SECONDS = 900

_TOKEN_VERSION = "gb1"


class ApprovalError(ValueError):
    """A ticket/token failure: missing key, malformed, bad signature, expired, replayed."""


class OrderTicket(BaseModel):
    """The order a preview minted and the token is bound to.

    ``jti`` makes every issuance unique so two identical orders never share a
    token (a shared token would turn the second redeem into a false replay).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str = Field(min_length=1, max_length=32)
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0)
    order_type: Literal["market", "limit"] = "market"
    limit_price: float | None = Field(default=None, gt=0)
    exchange: str | None = None
    jti: str = Field(default_factory=lambda: uuid.uuid4().hex)


def _server_key(explicit: str | None) -> str:
    if explicit is not None and explicit.strip():
        return explicit
    env_key = os.environ.get(APPROVAL_KEY_ENV, "").strip()
    if env_key:
        return env_key
    raise ApprovalError(
        f"approval key is not configured; set {APPROVAL_KEY_ENV} "
        "(server-side secret, never committed)"
    )


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


def _canonical_ticket(ticket: OrderTicket) -> str:
    return json.dumps(ticket.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


# token -> expiry epoch seconds; guarded by _REDEEMED_LOCK, pruned on redeem.
_REDEEMED: dict[str, float] = {}
_REDEEMED_LOCK = threading.Lock()


def issue_ticket(ticket: OrderTicket, *, key: str | None = None, now: float | None = None) -> str:
    """Mint a single-use token binding *ticket* for 15 minutes. Fails closed without a key."""
    server_key = _server_key(key)
    moment = time.time() if now is None else now
    expiry = int(moment) + APPROVAL_TTL_SECONDS
    ticket_part = _b64url(_canonical_ticket(ticket).encode("utf-8"))
    expiry_part = _b64url(str(expiry).encode("ascii"))
    signature = hmac.new(
        server_key.encode("utf-8"), f"{ticket_part}.{expiry_part}".encode("ascii"), hashlib.sha256
    ).digest()
    return f"{_TOKEN_VERSION}.{ticket_part}.{expiry_part}.{_b64url(signature)}"


def redeem_token(token: str, *, key: str | None = None, now: float | None = None) -> OrderTicket:
    """Validate *token* and return its bound ticket, marking it used.

    Raises :class:`ApprovalError` on malformed structure, bad signature,
    expiry, or replay. Never logs or returns the key.
    """
    server_key = _server_key(key)
    moment = time.time() if now is None else now
    try:
        version, ticket_part, expiry_part, signature_part = token.split(".")
    except ValueError:
        raise ApprovalError("malformed approval token") from None
    if version != _TOKEN_VERSION:
        raise ApprovalError(f"unknown approval token version {version!r}")
    expected = hmac.new(
        server_key.encode("utf-8"), f"{ticket_part}.{expiry_part}".encode("ascii"), hashlib.sha256
    ).digest()
    try:
        presented = _b64url_decode(signature_part)
    except Exception:
        raise ApprovalError("malformed approval token signature") from None
    if not hmac.compare_digest(presented, expected):
        raise ApprovalError("invalid approval token signature")
    try:
        expiry = int(_b64url_decode(expiry_part).decode("ascii"))
    except Exception:
        raise ApprovalError("malformed approval token expiry") from None
    if moment > expiry:
        raise ApprovalError("approval token expired")
    try:
        ticket = OrderTicket.model_validate(json.loads(_b64url_decode(ticket_part).decode("utf-8")))
    except Exception as exc:
        raise ApprovalError(f"malformed approval ticket: {exc}") from None
    with _REDEEMED_LOCK:
        for used, exp in list(_REDEEMED.items()):
            if exp <= moment:
                del _REDEEMED[used]
        if token in _REDEEMED:
            raise ApprovalError("approval token already redeemed (single-use)")
        _REDEEMED[token] = float(expiry)
    return ticket
