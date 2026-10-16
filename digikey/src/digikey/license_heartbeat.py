"""Four-state heartbeat read over the ``digikey_licenses`` allowlist (slice 3).

Normative contract — byte-identical to slice 1 §4.4 and slice 2 §8:

| State   | Row condition                                    | HTTP | Body                                    |
|---------|--------------------------------------------------|------|-----------------------------------------|
| valid   | row, ``revoked_at IS NULL``, ``expires_at`` live | 200  | ``{"license_status": "valid"}``         |
| expired | row, ``revoked_at IS NULL``, ``expires_at`` past | 200  | ``{"license_status": "expired"}``       |
| revoked | row, ``revoked_at IS NOT NULL``                  | 401  | ``{"error": "license_revoked", ...}``   |
| unknown | no row                                           | 401  | ``{"error": "unknown_license", ...}``   |

Binding rules: expiry is 200, never 401; revoked beats expired; only the two
401 bodies above latch (anything else the route emits as 401 is the generic
``unauthorized`` error outcome); malformed telemetry is 400, never a deny;
clock-skew leeway is 300s symmetric. The ``error``-key shape is deliberate —
it is what the sender matches on, not the middleware ``code`` idiom.

DB access is raw SQL (``sqlalchemy.text``) on purpose: the table is written by
slice 1's CLI, so this read side takes no dependency on its ORM model and the
two slices merge without touching each other's files.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from digikey.license_verify import CLOCK_SKEW_LEEWAY_SEC

logger = logging.getLogger(__name__)

LICENSE_TABLE = "digikey_licenses"

LicenseHeartbeatState = Literal["valid", "expired", "revoked", "unknown"]

ERROR_LICENSE_REVOKED = "license_revoked"
ERROR_UNKNOWN_LICENSE = "unknown_license"
ERROR_UNAUTHORIZED = "unauthorized"
ERROR_INVALID_BODY = "invalid_heartbeat_body"
ERROR_STORE_UNAVAILABLE = "license_store_unavailable"

#: Every 401 this route emits carries one of these ``error`` codes — the only
#: two latch codes plus the generic error outcome. Asserted by tests.
HEARTBEAT_401_ERRORS = (ERROR_LICENSE_REVOKED, ERROR_UNKNOWN_LICENSE, ERROR_UNAUTHORIZED)

#: Telemetry keys the sender always transmits (slice 2 §5.3). All required;
#: a missing key is a 400 hygiene error, never a deny. Extra keys tolerated.
HEARTBEAT_REQUIRED_KEYS = (
    "license_id",
    "customer",
    "license_status",
    "version",
    "hosts_configured",
    "started_at",
    "seq",
)

_HEARTBEAT_COUNTER: Any | None = None


def count_heartbeat(result: str) -> None:
    """Increment ``license_heartbeat_total{result}`` (no-op when metrics absent).

    Created lazily so importing this module never requires prometheus_client
    and a duplicate registration across test reloads degrades to reuse.
    """
    global _HEARTBEAT_COUNTER
    try:
        if _HEARTBEAT_COUNTER is None:
            from prometheus_client import REGISTRY, Counter

            existing = getattr(REGISTRY, "_names_to_collectors", {}).get("license_heartbeat_total")
            if existing is not None:
                _HEARTBEAT_COUNTER = existing
            else:
                _HEARTBEAT_COUNTER = Counter(
                    "license_heartbeat_total",
                    "Customer license heartbeat outcomes by result.",
                    ["result"],
                )
        _HEARTBEAT_COUNTER.labels(result=result).inc()
    except Exception:
        logger.debug("license heartbeat counter write failed", exc_info=True)


def resolve_license_state(
    *,
    row_exists: bool,
    revoked: bool,
    expires_at: int | None,
    now: int,
) -> LicenseHeartbeatState:
    """Pure four-state read. Revoked beats expired; expiry honors 300s leeway."""
    if not row_exists:
        return "unknown"
    if revoked:
        return "revoked"
    if expires_at is None:
        # Schema declares NOT NULL; fail open rather than brick on a bad row.
        return "valid"
    if int(expires_at) + CLOCK_SKEW_LEEWAY_SEC <= now:
        return "expired"
    return "valid"


def heartbeat_status_body(state: LicenseHeartbeatState) -> tuple[int, dict[str, str]]:
    """Map a resolved state to its exact (status, body) contract rows."""
    if state == "valid":
        return 200, {"license_status": "valid"}
    if state == "expired":
        return 200, {"license_status": "expired"}
    if state == "revoked":
        return 401, {
            "error": ERROR_LICENSE_REVOKED,
            "message": "This deployment's license has been revoked.",
        }
    return 401, {"error": ERROR_UNKNOWN_LICENSE, "message": "Unknown license."}


def validate_heartbeat_body(raw: Any, *, jwt_license_id: str) -> tuple[dict[str, Any], str | None]:
    """Validate telemetry. Returns ``(cleaned, None)`` or ``({}, error_detail)``."""
    if not isinstance(raw, dict):
        return {}, "body must be a JSON object"
    missing = [k for k in HEARTBEAT_REQUIRED_KEYS if k not in raw]
    if missing:
        return {}, f"missing keys: {', '.join(missing)}"
    if str(raw["license_id"]) != jwt_license_id:
        return {}, "body license_id does not match token license_id"
    seq = raw["seq"]
    if isinstance(seq, bool) or not isinstance(seq, int) or seq < 1:
        return {}, "seq must be a positive int"
    return {k: raw[k] for k in HEARTBEAT_REQUIRED_KEYS}, None


def get_license_row(session: Session, license_id: str) -> dict[str, Any] | None:
    """Read one allowlist row. ``None`` = unknown. Raises on store failure."""
    row = (
        session.execute(
            text(
                "SELECT license_id, customer_slug, expires_at, revoked_at"
                " FROM digikey_licenses WHERE license_id = :lid"
            ),
            {"lid": license_id},
        )
        .mappings()
        .first()
    )
    return dict(row) if row is not None else None
