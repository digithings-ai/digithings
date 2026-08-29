"""IBKR Client Portal Web API adapter — read-first, orders feature-flagged off (K2).

Implements the K0 `BrokerAdapter` surface against IBKR's CPAPI. The portfolio read path
(`get_account` / `get_positions`) rides the SSO/live-session layer and **never** opens a
brokerage session (`/iserver/auth/ssodh/init`). Order submission is implemented but locked
behind `DIGIQUANT_IBKR_ORDERS=1` (default off).

Auth signing is out of scope for this work package: construct `IbkrAdapter` with an injected
pre-authenticated `IbkrTransport`. Production OAuth 1.0a vendor wiring lands with vendor
onboarding — see `digiquant/docs/brokers/IBKR-NOTES.md`.

No threads: `keepalive()` is a single `POST /tickle`; the caller owns any tickle loop.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol, runtime_checkable

from digiquant.brokers.contracts import (
    BrokerAccountSnapshot,
    BrokerFill,
    BrokerOrderAck,
    BrokerOrderRequest,
    BrokerOrderStatus,
    BrokerPosition,
    OrderSide,
    OrderType,
    TimeInForce,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exception family — local until K1's shared contracts.py family merges
# TODO(K-merge): unify with contracts.py exception family when K1 lands
# ---------------------------------------------------------------------------


class BrokerAuthError(Exception):
    """Authentication or live-session failure after the one transparent re-auth attempt."""


class BrokerTransportError(Exception):
    """Non-auth HTTP / transport failure talking to IBKR."""


class BrokerRateLimited(Exception):
    """A paced endpoint was called sooner than the required spacing."""


class BrokerOrderRejected(Exception):
    """Venue refused the order, or a reply question was off the suppressible allowlist."""

    def __init__(self, message: str, *, question_text: str | None = None) -> None:
        super().__init__(message)
        self.question_text = question_text if question_text is not None else message


class IbkrOrdersDisabledError(Exception):
    """Raised when `submit_order` is called without `DIGIQUANT_IBKR_ORDERS=1`."""


class SessionCompetingError(Exception):
    """Brokerage session init reported a competing session (`compete=false` path)."""


ORDERS_ENV = "DIGIQUANT_IBKR_ORDERS"

# Per-endpoint pacing: ≥5s between calls (spec §7). Violation → raise BrokerRateLimited.
PACED_PATH_MARKERS: tuple[str, ...] = (
    "/portfolio/accounts",
    "/iserver/orders",
    "/iserver/trades",
)
PACE_SECONDS = 5.0

# Hard-coded suppressible reply message ids (IBKR Campus suppressible-id list).
# Re-applied via POST /iserver/questions/suppress after every brokerage session init.
# Anything off this list aborts with BrokerOrderRejected(question_text) — never auto-confirm.
SUPPRESSIBLE_MESSAGE_IDS: frozenset[str] = frozenset(
    {
        "o162",  # size / percentage of NAV caution
        "o163",  # price percentage constraint
        "o354",  # submitting without market data
        "o382",  # order will be submitted as a market order after hours
        "o383",  # order will be submitted as a limit order after hours
        "o403",  # order value vs available funds
        "o451",  # cross-side / wash caution family
        "o452",
        "o2136",  # equity stop-order precaution
        "o2137",
    }
)

_AUTH_STATUS_PATH = "/iserver/auth/status"
_TICKLE_PATH = "/tickle"
_SSODH_INIT_PATH = "/iserver/auth/ssodh/init"
_SUPPRESS_PATH = "/iserver/questions/suppress"
_SECDEF_SEARCH_PATH = "/iserver/secdef/search"
_PORTFOLIO_ACCOUNTS_PATH = "/portfolio/accounts"


@runtime_checkable
class IbkrTransport(Protocol):
    """Pre-authenticated HTTP transport injected into `IbkrAdapter`.

    Implementations must already carry whatever live-session / OAuth material IBKR
    requires. This adapter never signs requests.
    """

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Mapping[str, Any] | Sequence[Any] | None = None,
        params: Mapping[str, str] | None = None,
    ) -> IbkrHttpResponse:
        """Perform one HTTP call. `path` is CPAPI-relative (e.g. `/tickle`)."""
        ...


class IbkrHttpResponse:
    """Parsed transport response with raw bytes for fingerprinting."""

    __slots__ = ("status_code", "body", "raw_bytes")

    def __init__(self, status_code: int, body: Any, raw_bytes: bytes) -> None:
        self.status_code = status_code
        self.body = body
        self.raw_bytes = raw_bytes

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.raw_bytes).hexdigest()


def orders_enabled() -> bool:
    """Return True only when `DIGIQUANT_IBKR_ORDERS=1`."""
    return os.environ.get(ORDERS_ENV, "") == "1"


def _as_decimal(value: object, *, field: str) -> Decimal:
    """Parse a venue numeric as Decimal; never via float."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool) or value is None:
        raise BrokerTransportError(f"IBKR field {field!r} missing or invalid: {value!r}")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        # Venue JSON may decode numbers as float; re-stringify to avoid binary float noise.
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            return Decimal(value.strip())
        except InvalidOperation as exc:
            raise BrokerTransportError(f"IBKR field {field!r} not a decimal: {value!r}") from exc
    raise BrokerTransportError(f"IBKR field {field!r} unsupported type: {type(value)!r}")


def _fingerprint_log(path: str, response: IbkrHttpResponse) -> None:
    logger.info(
        "ibkr response path=%s status=%s sha256=%s",
        path,
        response.status_code,
        response.fingerprint,
    )


def _pace_key(path: str) -> str | None:
    """Return the pacing bucket for a path, or None if unpaced.

    Spec §7 names `/portfolio/accounts`, `/iserver/orders`, `/iserver/trades`. IBKR's
    concrete order/trade URLs nest under `/iserver/account/.../orders|trades`, so we
    match those families rather than an exact suffix alone.
    """
    if "/portfolio/accounts" in path:
        return "/portfolio/accounts"
    if "/iserver/" in path and "/orders" in path:
        return "/iserver/orders"
    if "/iserver/" in path and "/trades" in path:
        return "/iserver/trades"
    return None


def _map_order_status(raw: object) -> BrokerOrderStatus:
    text = str(raw or "").strip().lower()
    mapping = {
        "pendingSubmit": BrokerOrderStatus.SUBMITTED,
        "pendingsubmit": BrokerOrderStatus.SUBMITTED,
        "preSubmitted": BrokerOrderStatus.SUBMITTED,
        "presubmitted": BrokerOrderStatus.SUBMITTED,
        "submitted": BrokerOrderStatus.SUBMITTED,
        "filled": BrokerOrderStatus.FILLED,
        "cancelled": BrokerOrderStatus.CANCELED,
        "canceled": BrokerOrderStatus.CANCELED,
        "inactive": BrokerOrderStatus.REJECTED,
        "rejected": BrokerOrderStatus.REJECTED,
        "apicancelled": BrokerOrderStatus.CANCELED,
        "pendingcancel": BrokerOrderStatus.CANCELED,
        "partiallyfilled": BrokerOrderStatus.PARTIALLY_FILLED,
        "partially_filled": BrokerOrderStatus.PARTIALLY_FILLED,
        "expired": BrokerOrderStatus.EXPIRED,
        "accepted": BrokerOrderStatus.ACCEPTED,
    }
    return mapping.get(text, BrokerOrderStatus.SUBMITTED)


def _tif_to_ibkr(tif: TimeInForce) -> str:
    return {
        TimeInForce.DAY: "DAY",
        TimeInForce.GTC: "GTC",
        TimeInForce.OPG: "OPG",
        TimeInForce.IOC: "IOC",
    }[tif]


class IbkrAdapter:
    """IBKR Web API adapter implementing the K0 `BrokerAdapter` protocol."""

    name = "ibkr"

    def __init__(
        self,
        transport: IbkrTransport,
        *,
        account_id: str | None = None,
        clock: Any | None = None,
        sleep: Any | None = None,
    ) -> None:
        self._transport = transport
        self._account_id = account_id
        self._connected = False
        self._brokerage_session = False
        self._session_competing = False
        self._conid_cache: dict[str, int] = {}
        self._last_paced: dict[str, float] = {}
        # Injectable for deterministic pacing tests; defaults to time.monotonic / time.sleep.
        self._clock = clock if clock is not None else time.monotonic
        self._sleep = sleep if sleep is not None else time.sleep
        self._reauth_hook: Any | None = None  # set by tests / future auth layer

    @property
    def session_competing(self) -> bool:
        """True when last brokerage init reported a competing session (compete=false)."""
        return self._session_competing

    @property
    def brokerage_session_active(self) -> bool:
        return self._brokerage_session

    def connect(self) -> None:
        """Auth-status check + live-session establishment. Does **not** open brokerage."""
        response = self._call("GET", _AUTH_STATUS_PATH, pace=False, allow_reauth=True)
        body = response.body if isinstance(response.body, Mapping) else {}
        authenticated = bool(body.get("authenticated", body.get("connected", False)))
        if not authenticated and response.status_code >= 400:
            raise BrokerAuthError("IBKR auth status rejected the live session")
        if response.status_code >= 400:
            raise BrokerAuthError(f"IBKR auth status HTTP {response.status_code}")
        # Some gateways report authenticated under nested keys; treat 2xx without an
        # explicit false as connected (injected transport already carries the session).
        if body.get("authenticated") is False:
            raise BrokerAuthError("IBKR reports authenticated=false")
        self._connected = True
        self._brokerage_session = False

    def disconnect(self) -> None:
        self._connected = False
        self._brokerage_session = False
        self._session_competing = False

    def keepalive(self) -> Mapping[str, Any]:
        """Single `POST /tickle`. Caller owns any periodic loop — no threads here."""
        self._require_connected()
        response = self._call("POST", _TICKLE_PATH, pace=False, allow_reauth=True)
        body = response.body if isinstance(response.body, Mapping) else {}
        return dict(body)

    def get_account(self) -> BrokerAccountSnapshot:
        """Portfolio summary/ledger via SSO session — never calls ssodh/init."""
        self._require_connected()
        account_id = self._resolve_account_id()
        summary = self._call(
            "GET",
            f"/portfolio/{account_id}/summary",
            pace=False,
            allow_reauth=True,
        )
        ledger = self._call(
            "GET",
            f"/portfolio/{account_id}/ledger",
            pace=False,
            allow_reauth=True,
        )
        return self._parse_account_snapshot(account_id, summary, ledger)

    def get_positions(self) -> list[BrokerPosition]:
        """Paginated portfolio positions — never calls ssodh/init."""
        self._require_connected()
        account_id = self._resolve_account_id()
        positions: list[BrokerPosition] = []
        page = 0
        while True:
            response = self._call(
                "GET",
                f"/portfolio/{account_id}/positions/{page}",
                pace=False,
                allow_reauth=True,
            )
            rows = response.body
            if not isinstance(rows, list) or not rows:
                break
            for row in rows:
                if isinstance(row, Mapping):
                    positions.append(self._parse_position(row))
            # IBKR pages until an empty list; stop if a short page arrives.
            if len(rows) < 1:
                break
            page += 1
            # Safety: if the venue returns the same non-empty page forever, stop after
            # a large page count (tests use tiny fixtures).
            if page > 10_000:
                raise BrokerTransportError("IBKR positions pagination exceeded safety limit")
        return positions

    def submit_order(self, req: BrokerOrderRequest) -> BrokerOrderAck:
        if not orders_enabled():
            raise IbkrOrdersDisabledError(
                f"IBKR order path disabled; set {ORDERS_ENV}=1 to enable "
                "(default off — read-first adapter)"
            )
        self._require_connected()
        self._ensure_brokerage_session()
        account_id = self._resolve_account_id()
        conid = self._resolve_conid(req.symbol)
        order_body = self._build_order_payload(req, account_id=account_id, conid=conid)
        response = self._call(
            "POST",
            f"/iserver/account/{account_id}/orders",
            json_body=order_body,
            pace=True,
            allow_reauth=True,
        )
        return self._resolve_order_reply_chain(response)

    def get_order(self, external_order_id: str) -> BrokerOrderAck:
        self._require_connected()
        self._ensure_brokerage_session()
        response = self._call(
            "GET",
            f"/iserver/account/order/status/{external_order_id}",
            pace=False,
            allow_reauth=True,
        )
        body = response.body if isinstance(response.body, Mapping) else {}
        status = _map_order_status(body.get("order_status") or body.get("status"))
        submitted_raw = body.get("last_execution_time_r") or body.get("submitted_at")
        submitted_at = self._parse_ts(submitted_raw)
        return BrokerOrderAck(
            external_order_id=str(body.get("order_id") or external_order_id),
            status=status,
            submitted_at=submitted_at,
            raw_sha256=response.fingerprint,
        )

    def cancel_order(self, external_order_id: str) -> None:
        self._require_connected()
        self._ensure_brokerage_session()
        account_id = self._resolve_account_id()
        self._call(
            "DELETE",
            f"/iserver/account/{account_id}/order/{external_order_id}",
            pace=False,
            allow_reauth=True,
        )

    def list_fills(self, since: datetime) -> list[BrokerFill]:
        self._require_connected()
        self._ensure_brokerage_session()
        if since.tzinfo is None or since.utcoffset() != timedelta(0):
            raise ValueError("list_fills(since) requires a UTC-aware datetime")
        response = self._call(
            "GET",
            "/iserver/account/trades",
            pace=True,
            allow_reauth=True,
        )
        rows = response.body if isinstance(response.body, list) else []
        fills: list[BrokerFill] = []
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            executed_at = self._parse_ts(row.get("trade_time_r") or row.get("executed_at"))
            if executed_at < since:
                continue
            fills.append(
                BrokerFill(
                    external_fill_id=str(row.get("execution_id") or row.get("fill_id") or ""),
                    symbol=str(row.get("symbol") or row.get("ticker") or ""),
                    quantity=_as_decimal(row.get("size") or row.get("quantity"), field="quantity"),
                    price=_as_decimal(row.get("price"), field="price"),
                    fee=(
                        _as_decimal(row["commission"], field="fee")
                        if row.get("commission") is not None
                        else None
                    ),
                    executed_at=executed_at,
                )
            )
        return fills

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _require_connected(self) -> None:
        if not self._connected:
            raise BrokerAuthError("IbkrAdapter.connect() has not been called")

    def _call(
        self,
        method: str,
        path: str,
        *,
        json_body: Mapping[str, Any] | Sequence[Any] | None = None,
        params: Mapping[str, str] | None = None,
        pace: bool,
        allow_reauth: bool,
        _reauth_attempted: bool = False,
    ) -> IbkrHttpResponse:
        if pace:
            self._enforce_pacing(path)
        try:
            response = self._transport.request(method, path, json_body=json_body, params=params)
        except BrokerAuthError:
            raise
        except BrokerTransportError:
            raise
        except Exception as exc:
            raise BrokerTransportError(f"IBKR transport error on {method} {path}") from exc

        _fingerprint_log(path, response)

        if response.status_code == 429:
            raise BrokerRateLimited(f"IBKR HTTP 429 on {path}")

        if response.status_code in {401, 403} or self._looks_like_session_expiry(response):
            if allow_reauth and not _reauth_attempted:
                self._transparent_reauth()
                return self._call(
                    method,
                    path,
                    json_body=json_body,
                    params=params,
                    pace=pace,
                    allow_reauth=False,
                    _reauth_attempted=True,
                )
            raise BrokerAuthError(f"IBKR session expired on {method} {path}")

        if response.status_code >= 400:
            raise BrokerTransportError(f"IBKR HTTP {response.status_code} on {method} {path}")
        return response

    def _looks_like_session_expiry(self, response: IbkrHttpResponse) -> bool:
        body = response.body
        if isinstance(body, Mapping):
            error = str(body.get("error") or body.get("message") or "").lower()
            if "not authenticated" in error or "session" in error and "expire" in error:
                return True
            if body.get("authenticated") is False:
                return True
        return False

    def _transparent_reauth(self) -> None:
        """One transparent re-auth attempt (hook or re-connect); failures → BrokerAuthError."""
        if self._reauth_hook is not None:
            try:
                self._reauth_hook()
            except BrokerAuthError:
                raise
            except Exception as exc:
                raise BrokerAuthError("IBKR re-auth hook failed") from exc
            return
        # Default: re-run auth status. If still failing, caller sees BrokerAuthError.
        response = self._transport.request("GET", _AUTH_STATUS_PATH)
        _fingerprint_log(_AUTH_STATUS_PATH, response)
        body = response.body if isinstance(response.body, Mapping) else {}
        if response.status_code >= 400 or body.get("authenticated") is False:
            raise BrokerAuthError("IBKR re-auth failed after session expiry")
        self._connected = True

    def _enforce_pacing(self, path: str) -> None:
        """Raise BrokerRateLimited when a paced endpoint is hit within PACE_SECONDS.

        Chosen over silent wait so callers (K4 sync) see deterministic failures and
        schedule their own ≥5s spacing; tests pin this raise behavior.
        """
        key = _pace_key(path)
        if key is None:
            return
        now = float(self._clock())
        last = self._last_paced.get(key)
        if last is not None and (now - last) < PACE_SECONDS:
            raise BrokerRateLimited(
                f"IBKR pacing: {key} requires ≥{PACE_SECONDS:.0f}s between calls "
                f"(elapsed {now - last:.3f}s)"
            )
        self._last_paced[key] = now

    def _resolve_account_id(self) -> str:
        if self._account_id:
            return self._account_id
        response = self._call(
            "GET",
            _PORTFOLIO_ACCOUNTS_PATH,
            pace=True,
            allow_reauth=True,
        )
        rows = response.body
        if not isinstance(rows, list) or not rows:
            raise BrokerTransportError("IBKR /portfolio/accounts returned no accounts")
        first = rows[0]
        if not isinstance(first, Mapping):
            raise BrokerTransportError("IBKR /portfolio/accounts row is not an object")
        account_id = str(first.get("id") or first.get("accountId") or "")
        if not account_id:
            raise BrokerTransportError("IBKR account id missing from /portfolio/accounts")
        self._account_id = account_id
        return account_id

    def _ensure_brokerage_session(self) -> None:
        if self._brokerage_session:
            return
        # compete=false — never kick the user's own TWS/mobile session.
        response = self._call(
            "POST",
            _SSODH_INIT_PATH,
            json_body={"publish": True, "compete": False},
            pace=False,
            allow_reauth=True,
        )
        body = response.body if isinstance(response.body, Mapping) else {}
        competing = bool(body.get("competing") or body.get("competingSession"))
        self._session_competing = competing
        if competing:
            # Surface as status; do not treat as a successful brokerage session for orders.
            raise SessionCompetingError(
                "IBKR brokerage session competing with an existing login "
                "(compete=false — user session was not kicked)"
            )
        authenticated = body.get("authenticated", True)
        if authenticated is False:
            raise BrokerAuthError("IBKR brokerage session init failed (authenticated=false)")
        self._brokerage_session = True
        self._apply_question_suppression()

    def _apply_question_suppression(self) -> None:
        """Re-apply the suppressible-message allowlist after every session init."""
        self._call(
            "POST",
            _SUPPRESS_PATH,
            json_body={"messageIds": sorted(SUPPRESSIBLE_MESSAGE_IDS)},
            pace=False,
            allow_reauth=False,
        )

    def _resolve_conid(self, symbol: str) -> int:
        cached = self._conid_cache.get(symbol)
        if cached is not None:
            return cached
        response = self._call(
            "GET",
            _SECDEF_SEARCH_PATH,
            params={"symbol": symbol, "name": "true"},
            pace=False,
            allow_reauth=True,
        )
        rows = response.body
        if not isinstance(rows, list) or not rows:
            raise BrokerOrderRejected(f"IBKR secdef search returned no contract for {symbol}")
        first = rows[0]
        if not isinstance(first, Mapping) or first.get("conid") is None:
            raise BrokerOrderRejected(f"IBKR secdef search missing conid for {symbol}")
        conid = int(first["conid"])
        self._conid_cache[symbol] = conid
        return conid

    def _build_order_payload(
        self, req: BrokerOrderRequest, *, account_id: str, conid: int
    ) -> dict[str, Any]:
        order: dict[str, Any] = {
            "acctId": account_id,
            "conid": conid,
            "side": "BUY" if req.side is OrderSide.BUY else "SELL",
            "orderType": "LMT" if req.order_type is OrderType.LIMIT else "MKT",
            "tif": _tif_to_ibkr(req.time_in_force),
            "cOID": req.client_order_id,
        }
        if req.quantity is not None:
            order["quantity"] = float(req.quantity)  # IBKR JSON wire; value from Decimal
        if req.notional is not None:
            order["cashQty"] = float(req.notional)
        if req.limit_price is not None:
            order["price"] = float(req.limit_price)
        return {"orders": [order]}

    def _resolve_order_reply_chain(self, response: IbkrHttpResponse) -> BrokerOrderAck:
        """Walk reply/confirmation prompts; only allowlisted messageIds may be confirmed."""
        current = response
        # Bound the chain so a runaway venue cannot loop forever.
        for _ in range(20):
            body = current.body
            # Direct ack shapes: list of order objects with order_id
            if isinstance(body, list) and body:
                first = body[0]
                if isinstance(first, Mapping) and (
                    "order_id" in first or "orderId" in first or "id" in first
                ):
                    # Reply prompt objects carry "message" + "messageIds" and an "id" reply id.
                    if "message" in first and "messageIds" in first:
                        current = self._handle_reply_prompt(first)
                        continue
                    return self._ack_from_order_body(first, current.fingerprint)
            if isinstance(body, Mapping):
                if "message" in body and "messageIds" in body:
                    current = self._handle_reply_prompt(body)
                    continue
                if "order_id" in body or "orderId" in body:
                    return self._ack_from_order_body(body, current.fingerprint)
            break
        raise BrokerOrderRejected("IBKR order reply chain ended without an acknowledgement")

    def _handle_reply_prompt(self, prompt: Mapping[str, Any]) -> IbkrHttpResponse:
        message_ids = prompt.get("messageIds") or prompt.get("message_ids") or []
        if not isinstance(message_ids, list):
            message_ids = [message_ids]
        ids = [str(m) for m in message_ids]
        question_text = ""
        raw_message = prompt.get("message")
        if isinstance(raw_message, list):
            question_text = " ".join(str(part) for part in raw_message)
        else:
            question_text = str(raw_message or "")
        off_allowlist = [mid for mid in ids if mid not in SUPPRESSIBLE_MESSAGE_IDS]
        if off_allowlist or (not ids and question_text):
            # Any question off the allowlist aborts — never confirm unknown prompts.
            raise BrokerOrderRejected(
                question_text or f"IBKR reply off allowlist: {off_allowlist}",
                question_text=question_text or f"off-allowlist ids={off_allowlist}",
            )
        reply_id = str(prompt.get("id") or "")
        if not reply_id:
            raise BrokerOrderRejected(
                "IBKR reply prompt missing id",
                question_text=question_text,
            )
        return self._call(
            "POST",
            f"/iserver/reply/{reply_id}",
            json_body={"confirmed": True},
            pace=False,
            allow_reauth=False,
        )

    def _ack_from_order_body(self, body: Mapping[str, Any], fingerprint: str) -> BrokerOrderAck:
        external_id = str(body.get("order_id") or body.get("orderId") or body.get("id") or "")
        if not external_id:
            raise BrokerOrderRejected("IBKR order acknowledgement missing order id")
        status = _map_order_status(body.get("order_status") or body.get("status") or "submitted")
        return BrokerOrderAck(
            external_order_id=external_id,
            status=status,
            submitted_at=datetime.now(tz=UTC),
            raw_sha256=fingerprint,
        )

    def _parse_account_snapshot(
        self,
        account_id: str,
        summary: IbkrHttpResponse,
        ledger: IbkrHttpResponse,
    ) -> BrokerAccountSnapshot:
        summary_body = summary.body if isinstance(summary.body, Mapping) else {}
        ledger_body = ledger.body if isinstance(ledger.body, Mapping) else {}

        def _summary_amount(key: str) -> Decimal | None:
            node = summary_body.get(key)
            if isinstance(node, Mapping) and "amount" in node:
                return _as_decimal(node["amount"], field=key)
            if node is not None and not isinstance(node, Mapping):
                return _as_decimal(node, field=key)
            return None

        # Prefer summary; fall back to BASE ledger currency bucket.
        base_ledger = ledger_body.get("BASE")
        if not isinstance(base_ledger, Mapping):
            # Sometimes ledger is keyed by currency code directly at top level.
            base_ledger = next(
                (v for v in ledger_body.values() if isinstance(v, Mapping)),
                {},
            )

        equity = _summary_amount("netliquidation") or _summary_amount("equitywithloanvalue")
        if equity is None and base_ledger:
            equity = _as_decimal(
                base_ledger.get("netliquidationvalue")
                or base_ledger.get("equitywithloanvalue")
                or 0,
                field="equity",
            )
        cash = _summary_amount("totalcashvalue")
        if cash is None and base_ledger:
            cash = _as_decimal(base_ledger.get("cashbalance") or 0, field="cash")
        buying_power = _summary_amount("buyingpower")
        if buying_power is None:
            buying_power = Decimal("0")
        currency = "USD"
        if isinstance(base_ledger, Mapping) and base_ledger.get("currency"):
            currency = str(base_ledger["currency"]).strip().upper()
        if equity is None or cash is None:
            raise BrokerTransportError("IBKR account summary/ledger missing equity or cash")
        return BrokerAccountSnapshot(
            account_id=account_id,
            equity=equity,
            cash=cash,
            buying_power=buying_power if buying_power >= 0 else Decimal("0"),
            currency=currency,
            as_of=datetime.now(tz=UTC),
        )

    def _parse_position(self, row: Mapping[str, Any]) -> BrokerPosition:
        symbol = str(row.get("ticker") or row.get("symbol") or row.get("contractDesc") or "")
        qty = _as_decimal(row.get("position") or row.get("quantity") or 0, field="quantity")
        avg = _as_decimal(row.get("avgCost") or row.get("avg_entry_price") or 0, field="avg")
        mkt = _as_decimal(row.get("mktValue") or row.get("market_value") or 0, field="mkt")
        upl = _as_decimal(row.get("unrealizedPnl") or row.get("unrealized_pl") or 0, field="upl")
        return BrokerPosition(
            symbol=symbol,
            quantity=qty,
            avg_entry_price=avg if avg >= 0 else Decimal("0"),
            market_value=mkt,
            unrealized_pl=upl,
        )

    def _parse_ts(self, raw: object) -> datetime:
        if isinstance(raw, datetime):
            if raw.tzinfo is None:
                return raw.replace(tzinfo=UTC)
            return raw.astimezone(UTC)
        if isinstance(raw, (int, float)):
            # IBKR trade_time_r is often ms since epoch.
            seconds = float(raw) / 1000.0 if float(raw) > 1e12 else float(raw)
            return datetime.fromtimestamp(seconds, tz=UTC)
        if isinstance(raw, str) and raw.strip():
            text = raw.strip().replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(text)
            except ValueError:
                return datetime.now(tz=UTC)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        return datetime.now(tz=UTC)


def encode_json_bytes(payload: Any) -> bytes:
    """Helper for mock transports / fingerprint tests."""
    return json.dumps(payload, separators=(",", ":"), default=str).encode()


__all__ = [
    "BrokerAuthError",
    "BrokerOrderRejected",
    "BrokerRateLimited",
    "BrokerTransportError",
    "IbkrAdapter",
    "IbkrHttpResponse",
    "IbkrOrdersDisabledError",
    "IbkrTransport",
    "ORDERS_ENV",
    "PACE_SECONDS",
    "PACED_PATH_MARKERS",
    "SUPPRESSIBLE_MESSAGE_IDS",
    "SessionCompetingError",
    "encode_json_bytes",
    "orders_enabled",
]
