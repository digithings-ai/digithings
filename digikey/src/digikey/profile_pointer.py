"""Minimal per-user profile *pointers* for JWT claims (#308).

This module stores only ``profile_id`` + ``profile_version`` keyed by BFF
subject. It is **not** the investment-profile / asset-preferences body store —
that CRUD surface is #307. Digikey mints these claims on ``bff_session`` token
exchange so Atlas / digigraph can key caches without a second DB lookup.

Contract:
- When a pointer row exists for the subject, minted JWTs include both claims.
- When no pointer exists, both claims are **absent** (not null). Frontends may
  treat absence as "route user to intake."
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from digikey.db_schema import UserProfilePointerRow, utcnow


class ProfilePointer(BaseModel):
    """Identity pointer embedded (optionally) on digikey JWTs."""

    profile_id: str = Field(..., min_length=1, description="Stable profile UUID")
    profile_version: int = Field(
        ...,
        ge=1,
        description="Monotonic revision; bumps on each profile update",
    )
    subject: str = Field(..., min_length=1, description="Bare BFF subject (no bff: prefix)")
    tenant_slug: str = Field(..., min_length=1)


def _row_to_pointer(row: UserProfilePointerRow) -> ProfilePointer:
    return ProfilePointer(
        profile_id=row.id,
        profile_version=row.profile_version,
        subject=row.subject,
        tenant_slug=row.tenant_slug,
    )


def get_profile_pointer(session: Session, subject: str) -> ProfilePointer | None:
    """Return the active pointer for ``subject``, or None if missing/soft-deleted."""
    subj = subject.strip()
    if not subj:
        return None
    row = session.scalar(
        select(UserProfilePointerRow).where(
            UserProfilePointerRow.subject == subj,
            UserProfilePointerRow.deleted_at.is_(None),
        )
    )
    return _row_to_pointer(row) if row is not None else None


def create_profile_pointer(
    session: Session,
    *,
    subject: str,
    tenant_slug: str,
    profile_id: str | None = None,
) -> ProfilePointer:
    """Create a new pointer at ``profile_version=1``.

    Raises ``ValueError`` if an active pointer already exists for ``subject``.
    Full profile payload persistence belongs to #307; this only allocates the
    id/version used on JWTs.
    """
    subj = subject.strip()
    tenant = tenant_slug.strip()
    if not subj or not tenant:
        raise ValueError("subject and tenant_slug are required")
    existing = get_profile_pointer(session, subj)
    if existing is not None:
        raise ValueError(f"profile pointer already exists for subject={subj!r}")
    row = UserProfilePointerRow(
        id=(profile_id or str(uuid.uuid4())).strip(),
        subject=subj,
        tenant_slug=tenant,
        profile_version=1,
    )
    session.add(row)
    session.flush()
    return _row_to_pointer(row)


def bump_profile_version(session: Session, subject: str) -> ProfilePointer:
    """Increment ``profile_version`` for ``subject`` (profile update path).

    Raises ``ValueError`` if no active pointer exists.
    """
    subj = subject.strip()
    row = session.scalar(
        select(UserProfilePointerRow).where(
            UserProfilePointerRow.subject == subj,
            UserProfilePointerRow.deleted_at.is_(None),
        )
    )
    if row is None:
        raise ValueError(f"no profile pointer for subject={subj!r}")
    row.profile_version = int(row.profile_version) + 1
    row.updated_at = utcnow()
    session.flush()
    return _row_to_pointer(row)
