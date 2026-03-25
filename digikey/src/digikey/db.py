"""Database engine and session."""

from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from digikey.db_schema import Base

_engine = None
_session_factory: sessionmaker[Session] | None = None


def database_url() -> str:
    url = (os.environ.get("DIGIKEY_DATABASE_URL") or "").strip()
    if not url:
        raise RuntimeError("DIGIKEY_DATABASE_URL is not set")
    if url.startswith("sqlite"):
        return url
    return url


def get_engine():
    global _engine
    if _engine is None:
        url = database_url()
        connect_args = {}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        _engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
    return _engine


def session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), expire_on_commit=False, autoflush=False)
    return _session_factory


def init_db() -> None:
    Base.metadata.create_all(bind=get_engine())
