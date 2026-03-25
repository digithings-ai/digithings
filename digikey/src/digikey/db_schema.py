"""SQLAlchemy models for API keys."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.sqlite import JSON as SQLITE_JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _json_type():
    return JSONB().with_variant(SQLITE_JSON(), "sqlite")


class ApiKeyRow(Base):
    __tablename__ = "digikey_api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    tenant_slug: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    project_config_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    scopes: Mapped[list[Any]] = mapped_column(_json_type(), nullable=False, default=list)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="standard")
    label: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
