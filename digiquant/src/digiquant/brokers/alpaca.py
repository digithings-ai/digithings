"""Alpaca paper Trading API adapter (K1).

Implements the K0 ``BrokerAdapter`` protocol against Alpaca **paper** endpoints via
``alpaca-py``. Both API-key and OAuth-token auth are supported (tagged union). Live
construction is refused with ``LiveVenueNotAuthorizedError`` — no env override exists
in this work package.

``alpaca-py`` is an optional extra (``digiquant[brokers-alpaca]``). This module guards
the SDK import so ``import digiquant.brokers`` succeeds without it; constructing an
``AlpacaAdapter`` without the extra raises a clear ``ImportError``.

Fills: v1 derives ``BrokerFill`` rows from closed orders' ``filled_qty`` /
``filled_avg_price`` via REST ``get_orders`` (status=closed, after=since). Account
activities / websockets are out of scope — Alpaca has no fill webhooks, and the SDK
``TradingStream`` does not support OAuth (see Kairos spec §6).
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal, TypeAlias

from pydantic import Field

from digiquant.brokers.contracts import (
    BrokerAccountSnapshot,
    BrokerAuthError,
    BrokerContractModel,
    BrokerError,
    BrokerFill,
    BrokerOrderAck,
    BrokerOrderNotFound,
    BrokerOrderRejected,
    BrokerOrderRequest,
    BrokerOrderStatus,
    BrokerPosition,
    BrokerRateLimited,
    BrokerTransportError,
    LiveVenueNotAuthorizedError,
    OrderSide,
    OrderType,
    TimeInForce,
)

logger = logging.getLogger(__name__)

# Lazy/guarded SDK import — package must load without ``alpaca-py`` installed.
try:
    from alpaca.common.exceptions import APIError as _AlpacaAPIError
    from alpaca.trading.client import TradingClient as _TradingClient
    from alpaca.trading.enums import OrderSide as _AlpacaOrderSide
    from alpaca.trading.enums import OrderStatus as _AlpacaOrderStatus
    from alpaca.trading.enums import QueryOrderStatus as _QueryOrderStatus
    from alpaca.trading.enums import TimeInForce as _AlpacaTimeInForce
    from alpaca.trading.requests import GetOrdersRequest as _GetOrdersRequest
    from alpaca.trading.requests import LimitOrderRequest as _LimitOrderRequest
    from alpaca.trading.requests import MarketOrderRequest as _MarketOrderRequest
except ImportError:  # pragma: no cover - exercised by the no-extra import test
    _AlpacaAPIError = None  # type: ignore[assignment, misc]
    _TradingClient = None  # type: ignore[assignment, misc]
    _AlpacaOrderSide = None  # type: ignore[assignment, misc]
    _AlpacaOrderStatus = None  # type: ignore[assignment, misc]
    _QueryOrderStatus = None  # type: ignore[assignment, misc]
    _AlpacaTimeInForce = None  # type: ignore[assignment, misc]
    _GetOrdersRequest = None  # type: ignore[assignment, misc]
    _LimitOrderRequest = None  # type: ignore[assignment, misc]
    _MarketOrderRequest = None  # type: ignore[assignment, misc]

_ALPACA_EXTRA_HINT = (
    "alpaca-py is required for AlpacaAdapter; install with: pip install 'digiquant[brokers-alpaca]'"
)

_MAX_RATE_LIMIT_TRIES = 3
# Submit attempts (initial + retries). Every retry is gated on a confirmed 404.
_MAX_SUBMIT_TRIES = 3
_FRACTIONAL_EPS = Decimal("0.00000001")

# Alpaca Order.status → BrokerOrderStatus. Unknown values fall through to SUBMITTED + warn.
_STATUS_MAP: dict[str, BrokerOrderStatus] = {
    "new": BrokerOrderStatus.SUBMITTED,
    "pending_new": BrokerOrderStatus.SUBMITTED,
    "accepted": BrokerOrderStatus.ACCEPTED,
    "accepted_for_bidding": BrokerOrderStatus.ACCEPTED,
    "pending_review": BrokerOrderStatus.SUBMITTED,
    "held": BrokerOrderStatus.ACCEPTED,
    "partially_filled": BrokerOrderStatus.PARTIALLY_FILLED,
    "filled": BrokerOrderStatus.FILLED,
    "canceled": BrokerOrderStatus.CANCELED,
    "pending_cancel": BrokerOrderStatus.SUBMITTED,
    "rejected": BrokerOrderStatus.REJECTED,
    "expired": BrokerOrderStatus.EXPIRED,
    "done_for_day": BrokerOrderStatus.EXPIRED,
    "replaced": BrokerOrderStatus.CANCELED,
    "pending_replace": BrokerOrderStatus.SUBMITTED,
    "stopped": BrokerOrderStatus.SUBMITTED,
    "suspended": BrokerOrderStatus.SUBMITTED,
    "calculated": BrokerOrderStatus.SUBMITTED,
}


class ApiKeyAuth(BrokerContractModel):
    """Alpaca Trading API key-pair credentials (dev/house accounts)."""

    kind: Literal["api_key"] = "api_key"
    key_id: str = Field(min_length=1)
    secret: str = Field(min_length=1)


class OAuthAuth(BrokerContractModel):
    """Alpaca OAuth2 access token (product Connect-with-Alpaca flow)."""

    kind: Literal["oauth"] = "oauth"
    access_token: str = Field(min_length=1)


AlpacaAuth: TypeAlias = ApiKeyAuth | OAuthAuth


def _sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _fingerprint(secret: str) -> str:
    """6-char sha256 prefix of a credential — safe to log, never the secret itself."""
    return _sha256_hex(secret.encode("utf-8"))[:6]


def _decimal(value: object) -> Decimal:
    """Parse an Alpaca decimal-string (or number) via ``Decimal(str(...))`` — never float."""
    if value is None:
        raise ValueError("expected a decimal value, got None")
    return Decimal(str(value))


def _is_fractional(quantity: Decimal) -> bool:
    return (quantity % Decimal("1")).copy_abs() > _FRACTIONAL_EPS


def _ensure_sdk() -> None:
    if _TradingClient is None:
        raise ImportError(_ALPACA_EXTRA_HINT)


def _api_error_message(exc: Exception) -> str:
    """Read ``APIError.message`` without leaking ``json.loads`` failures on non-JSON bodies."""
    try:
        return str(exc.message)  # type: ignore[attr-defined]
    except Exception:
        return str(exc)


def _api_error_code(exc: Exception) -> str | None:
    try:
        return str(exc.code)  # type: ignore[attr-defined]
    except Exception:
        return None


def _map_status(raw: object) -> BrokerOrderStatus:
    key = raw.value if hasattr(raw, "value") else str(raw)
    key = key.lower()
    mapped = _STATUS_MAP.get(key)
    if mapped is None:
        logger.warning("unknown Alpaca order status %r; mapping to submitted", key)
        return BrokerOrderStatus.SUBMITTED
    return mapped


def _order_raw_sha256(order: object) -> str:
    if hasattr(order, "model_dump"):
        payload = order.model_dump(mode="json")
    elif isinstance(order, dict):
        payload = order
    else:
        payload = {"repr": repr(order)}
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return _sha256_hex(blob)


def _as_utc(dt: datetime | None) -> datetime:
    if dt is None:
        return datetime.now(tz=UTC)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _request_id_from_error(exc: Exception) -> str | None:
    response = getattr(exc, "response", None)
    if response is None:
        return None
    headers = getattr(response, "headers", None) or {}
    for key in ("X-Request-ID", "x-request-id"):
        if key in headers:
            return str(headers[key])
    return None


def _retry_after_seconds(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    if response is None:
        return None
    headers = getattr(response, "headers", None) or {}
    # Prefer Retry-After; fall back to X-RateLimit-Reset as an absolute epoch when present.
    for key in ("Retry-After", "retry-after"):
        if key in headers:
            try:
                return float(headers[key])
            except (TypeError, ValueError):
                pass
    for key in ("X-RateLimit-Reset", "x-ratelimit-reset"):
        if key in headers:
            try:
                reset_at = float(headers[key])
                return max(0.0, reset_at - time.time())
            except (TypeError, ValueError):
                pass
    return None


class AlpacaAdapter:
    """Paper-only Alpaca Trading API adapter implementing ``BrokerAdapter``."""

    name = "alpaca"

    def __init__(self, auth: AlpacaAuth, env: Literal["paper"] = "paper") -> None:
        if env != "paper":
            raise LiveVenueNotAuthorizedError(
                f"AlpacaAdapter refuses env={env!r}; only paper is authorized in this program"
            )
        _ensure_sdk()
        assert _TradingClient is not None

        if isinstance(auth, ApiKeyAuth):
            self._auth_fingerprint = _fingerprint(auth.secret)
            self._client = _TradingClient(
                api_key=auth.key_id,
                secret_key=auth.secret,
                paper=True,
            )
            logger.info(
                "AlpacaAdapter ready auth=api_key fingerprint=%s paper=True",
                self._auth_fingerprint,
            )
        elif isinstance(auth, OAuthAuth):
            self._auth_fingerprint = _fingerprint(auth.access_token)
            self._client = _TradingClient(
                oauth_token=auth.access_token,
                paper=True,
            )
            logger.info(
                "AlpacaAdapter ready auth=oauth fingerprint=%s paper=True",
                self._auth_fingerprint,
            )
        else:
            raise TypeError(f"unsupported auth type: {type(auth)!r}")

        self._connected = False

    def connect(self) -> None:
        # TradingClient is HTTP-stateless; connect is a no-op readiness latch.
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def get_account(self) -> BrokerAccountSnapshot:
        account = self._call(self._client.get_account)
        return BrokerAccountSnapshot(
            account_id=str(account.id),
            equity=_decimal(account.equity),
            cash=_decimal(account.cash),
            buying_power=_decimal(account.buying_power),
            currency=str(account.currency or "USD"),
            as_of=datetime.now(tz=UTC),
        )

    def get_positions(self) -> list[BrokerPosition]:
        positions = self._call(self._client.get_all_positions)
        out: list[BrokerPosition] = []
        for pos in positions:
            qty = _decimal(pos.qty)
            side = str(getattr(pos, "side", "long") or "long").lower()
            if side == "short":
                qty = -qty
            out.append(
                BrokerPosition(
                    symbol=str(pos.symbol),
                    quantity=qty,
                    avg_entry_price=_decimal(pos.avg_entry_price),
                    market_value=_decimal(pos.market_value),
                    unrealized_pl=_decimal(pos.unrealized_pl),
                )
            )
        return out

    def submit_order(self, req: BrokerOrderRequest) -> BrokerOrderAck:
        """Submit with idempotent retry across transport and rate-limit failures.

        Invariant: a submit is never retried (by any exception path) without first
        consulting ``get_order_by_client_id``. Only a confirmed 404
        (``BrokerOrderNotFound``) authorizes a resubmit; any other lookup failure
        propagates without calling submit again. ``_submit_once`` disables
        ``_call``'s internal 429 loop so every retry decision lives here.
        """
        self._validate_local_tif(req)
        last_retryable: BrokerTransportError | BrokerRateLimited | None = None
        for attempt in range(_MAX_SUBMIT_TRIES):
            try:
                return self._submit_once(req)
            except (BrokerTransportError, BrokerRateLimited) as exc:
                last_retryable = exc
                # Lookup BEFORE any retry (and before giving up after exhaustion).
                recovered = self._recover_by_client_id(req.client_order_id)
                if recovered is not None:
                    logger.info(
                        "submit failure recovered via client_order_id=%s "
                        "fingerprint=%s attempt=%d error=%s",
                        req.client_order_id,
                        self._auth_fingerprint,
                        attempt + 1,
                        type(exc).__name__,
                    )
                    return recovered
                # Confirmed 404 — a resubmit is authorized if attempts remain.
                if attempt + 1 >= _MAX_SUBMIT_TRIES:
                    break
                if isinstance(exc, BrokerRateLimited):
                    delay = exc.retry_after if exc.retry_after is not None else (2**attempt)
                    delay = float(delay) + random.uniform(0, 0.25)
                    logger.warning(
                        "submit 429 after confirmed miss; sleeping %.2fs "
                        "attempt=%d/%d fingerprint=%s client_order_id=%s",
                        delay,
                        attempt + 1,
                        _MAX_SUBMIT_TRIES,
                        self._auth_fingerprint,
                        req.client_order_id,
                    )
                    time.sleep(delay)
                else:
                    logger.warning(
                        "submit transport failure after confirmed miss; retrying "
                        "attempt=%d/%d fingerprint=%s client_order_id=%s",
                        attempt + 1,
                        _MAX_SUBMIT_TRIES,
                        self._auth_fingerprint,
                        req.client_order_id,
                    )
                continue
        assert last_retryable is not None
        raise last_retryable

    def get_order(self, external_order_id: str) -> BrokerOrderAck:
        order = self._call(self._client.get_order_by_id, external_order_id)
        return self._order_to_ack(order)

    def cancel_order(self, external_order_id: str) -> None:
        self._call(self._client.cancel_order_by_id, external_order_id)

    def list_fills(self, since: datetime) -> list[BrokerFill]:
        """List fills since ``since`` from closed orders' filled_qty / filled_avg_price.

        Chosen over account-activities because ``TradingClient`` in alpaca-py 0.x has no
        activities helper, and websockets/OAuth streaming are out of K1 scope (spec §6).
        """
        since_utc = _as_utc(since)
        assert _GetOrdersRequest is not None and _QueryOrderStatus is not None
        filter_req = _GetOrdersRequest(
            status=_QueryOrderStatus.CLOSED,
            after=since_utc,
            direction="asc",
        )
        orders = self._call(self._client.get_orders, filter=filter_req)
        fills: list[BrokerFill] = []
        for order in orders:
            filled_qty = (
                _decimal(order.filled_qty) if order.filled_qty is not None else Decimal("0")
            )
            if filled_qty <= 0:
                continue
            if order.filled_avg_price is None:
                continue
            executed_at = _as_utc(
                order.filled_at or order.updated_at or order.submitted_at or datetime.now(tz=UTC)
            )
            fills.append(
                BrokerFill(
                    external_fill_id=str(order.id),
                    symbol=str(order.symbol),
                    quantity=filled_qty,
                    price=_decimal(order.filled_avg_price),
                    fee=None,
                    executed_at=executed_at,
                )
            )
        return fills

    # --- internals -----------------------------------------------------------------

    def _validate_local_tif(self, req: BrokerOrderRequest) -> None:
        needs_day = req.notional is not None or (
            req.quantity is not None and _is_fractional(req.quantity)
        )
        if needs_day and req.time_in_force is not TimeInForce.DAY:
            raise BrokerOrderRejected(
                "fractional/notional requires day TIF",
                code="local_tif_guard",
            )

    def _build_order_request(self, req: BrokerOrderRequest) -> object:
        assert (
            _MarketOrderRequest is not None
            and _LimitOrderRequest is not None
            and _AlpacaOrderSide is not None
            and _AlpacaTimeInForce is not None
        )
        side = _AlpacaOrderSide.BUY if req.side is OrderSide.BUY else _AlpacaOrderSide.SELL
        tif = _AlpacaTimeInForce(req.time_in_force.value)
        # Pass qty/notional as strings so the SDK boundary does not start from a float literal.
        qty = str(req.quantity) if req.quantity is not None else None
        notional = str(req.notional) if req.notional is not None else None
        common = dict(
            symbol=req.symbol,
            qty=qty,
            notional=notional,
            side=side,
            time_in_force=tif,
            client_order_id=req.client_order_id,
            # extended_hours deliberately omitted — v1 never sends it (spec §6).
        )
        if req.order_type is OrderType.MARKET:
            return _MarketOrderRequest(**common)
        assert req.limit_price is not None
        return _LimitOrderRequest(**common, limit_price=str(req.limit_price))

    def _submit_once(self, req: BrokerOrderRequest) -> BrokerOrderAck:
        # No internal 429 retry — submit_order owns every retry after a client-id lookup.
        order_req = self._build_order_request(req)
        order = self._call(self._client.submit_order, order_req, retry_on_rate_limit=False)
        return self._order_to_ack(order)

    def _recover_by_client_id(self, client_order_id: str) -> BrokerOrderAck | None:
        """Return an ack if the venue already has this client_order_id.

        ``None`` means a confirmed 404 (safe to resubmit). Any other failure —
        auth, rate-limit exhaustion, transport, 5xx — propagates so the caller
        never blindly resubmits.
        """
        try:
            order = self._call(self._client.get_order_by_client_id, client_order_id)
        except BrokerOrderNotFound:
            return None
        return self._order_to_ack(order)

    def _order_to_ack(self, order: object) -> BrokerOrderAck:
        submitted_at = _as_utc(
            getattr(order, "submitted_at", None) or getattr(order, "created_at", None)
        )
        return BrokerOrderAck(
            external_order_id=str(order.id),
            status=_map_status(order.status),
            submitted_at=submitted_at,
            raw_sha256=_order_raw_sha256(order),
        )

    def _call(
        self,
        fn: object,
        *args: object,
        retry_on_rate_limit: bool = True,
        **kwargs: object,
    ) -> object:
        """Invoke an SDK method with optional 429 backoff (max 3 tries + jitter).

        Pass ``retry_on_rate_limit=False`` for submit: the submit path must consult
        ``get_order_by_client_id`` before any retry (see ``submit_order``).
        Idempotent reads (account/positions/lookup) keep the internal 429 loop.
        """
        assert callable(fn)
        last_rate: BrokerRateLimited | None = None
        tries = _MAX_RATE_LIMIT_TRIES if retry_on_rate_limit else 1
        for attempt in range(tries):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                mapped = self._map_exception(exc)
                if (
                    retry_on_rate_limit
                    and isinstance(mapped, BrokerRateLimited)
                    and attempt + 1 < tries
                ):
                    last_rate = mapped
                    delay = mapped.retry_after if mapped.retry_after is not None else (2**attempt)
                    delay = float(delay) + random.uniform(0, 0.25)
                    logger.warning(
                        "Alpaca 429; sleeping %.2fs attempt=%d/%d fingerprint=%s request_id=%s",
                        delay,
                        attempt + 1,
                        tries,
                        self._auth_fingerprint,
                        _request_id_from_error(exc),
                    )
                    time.sleep(delay)
                    continue
                raise mapped from exc
        assert last_rate is not None
        raise last_rate

    def _map_exception(self, exc: Exception) -> BrokerError:
        if _AlpacaAPIError is not None and isinstance(exc, _AlpacaAPIError):
            status = exc.status_code
            request_id = _request_id_from_error(exc)
            logger.info(
                "Alpaca APIError status=%s fingerprint=%s request_id=%s",
                status,
                self._auth_fingerprint,
                request_id,
            )
            if status in (401, 403):
                return BrokerAuthError(_api_error_message(exc))
            if status == 404:
                return BrokerOrderNotFound(_api_error_message(exc))
            if status == 422:
                return BrokerOrderRejected(_api_error_message(exc), code=_api_error_code(exc))
            if status == 429:
                return BrokerRateLimited(retry_after=_retry_after_seconds(exc))
            return BrokerTransportError(str(exc))

        # Network / timeout / unexpected — treat as transport.
        if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
            return BrokerTransportError(str(exc))
        # Already one of ours (e.g. re-raised) — pass through.
        if isinstance(exc, BrokerError):
            return exc
        return BrokerTransportError(str(exc))


__all__ = [
    "AlpacaAdapter",
    "AlpacaAuth",
    "ApiKeyAuth",
    "OAuthAuth",
]
