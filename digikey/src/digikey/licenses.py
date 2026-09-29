"""Customer license registry (digichat managed-deployment entitlement).

Slice 1 of the customer-license program: owner-run issuance writes rows to
``digikey_licenses``; the heartbeat slice reads them against the four-state
contract (valid / expired / revoked / unknown). No HTTP surface here — mint
and revoke are CLI-only, against the same database the server reads.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from digikey.db_schema import LicenseRow, utcnow
from digikey.jwt_issue import (
    LICENSE_AUDIENCE,
    LICENSE_KIND,
    LICENSE_MAX_TERM_DAYS,
)

__all__ = [
    "LICENSE_AUDIENCE",
    "LICENSE_KIND",
    "LICENSE_MAX_TERM_DAYS",
    "LICENSE_SERVICES_ALLOWLIST",
    "LicenseMintInput",
    "LicenseNotFoundError",
    "get_license_row",
    "insert_license_row",
    "parse_hosts",
    "parse_services",
    "revoke_license",
]

#: Hosted-service scopes a license may carry. Absent ``services`` means
#: entitled to the hosted services of the commercial term — never unentitled.
LICENSE_SERVICES_ALLOWLIST: frozenset[str] = frozenset({"digisearch-corpus", "hosted-web-search"})


class LicenseNotFoundError(LookupError):
    """Raised when a ``license_id`` has no row in ``digikey_licenses``."""


def parse_hosts(raw: str) -> list[str]:
    """Split a comma-separated ``--hosts`` value; at least one entry required."""
    hosts = [h.strip() for h in raw.split(",") if h.strip()]
    if not hosts:
        raise ValueError("--hosts must name at least one hostname")
    return hosts


def parse_services(raw: str | None) -> list[str] | None:
    """Split a comma-separated ``--services`` value; ``None`` when omitted."""
    if raw is None:
        return None
    services = [s.strip() for s in raw.split(",") if s.strip()]
    unknown = sorted({s for s in services} - LICENSE_SERVICES_ALLOWLIST)
    if unknown:
        raise ValueError(f"unknown --services entry: {', '.join(unknown)}")
    if not services:
        raise ValueError("--services must name at least one scope when passed")
    return services


class LicenseMintInput(BaseModel):
    """Validated mint parameters (used by the CLI and tests)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    customer_slug: str = Field(min_length=1, max_length=256)
    hosts: list[str] = Field(min_length=1)
    services: list[str] | None = None
    term_days: int = Field(ge=1, le=LICENSE_MAX_TERM_DAYS)
    label: str = ""

    @field_validator("customer_slug")
    @classmethod
    def _nonblank_customer(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("customer must not be blank")
        return v

    @field_validator("hosts")
    @classmethod
    def _nonblank_hosts(cls, v: list[str]) -> list[str]:
        cleaned = [h.strip() for h in v if h.strip()]
        if not cleaned:
            raise ValueError("hosts must name at least one hostname")
        return cleaned

    @field_validator("services")
    @classmethod
    def _known_services(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        unknown = sorted(set(v) - LICENSE_SERVICES_ALLOWLIST)
        if unknown:
            raise ValueError(f"unknown services entry: {', '.join(unknown)}")
        if not v:
            raise ValueError("services must name at least one scope when passed")
        return list(v)


def get_license_row(session: Session, license_id: str) -> LicenseRow | None:
    """Fetch a license row by id, or ``None`` when unknown."""
    return session.get(LicenseRow, license_id)


def insert_license_row(
    session: Session,
    *,
    license_id: str,
    customer_slug: str,
    hosts: Sequence[str],
    services: Sequence[str] | None,
    expires_at: int,
    label: str | None,
) -> LicenseRow:
    """Insert a live license row. Mint is append-only — never upsert."""
    row = LicenseRow(
        license_id=license_id,
        customer_slug=customer_slug,
        hosts=list(hosts),
        services=list(services) if services is not None else None,
        expires_at=expires_at,
        label=(label or "").strip() or None,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def revoke_license(session: Session, license_id: str) -> bool:
    """Set ``revoked_at`` on a license row.

    Returns ``True`` when the row was already revoked (idempotent).
    Raises ``LicenseNotFoundError`` for unknown ids — distinct from revoked.
    """
    row = session.get(LicenseRow, license_id)
    if row is None:
        raise LicenseNotFoundError(f"license not found: {license_id}")
    if row.revoked_at is not None:
        return True
    row.revoked_at = utcnow()
    session.commit()
    return False
