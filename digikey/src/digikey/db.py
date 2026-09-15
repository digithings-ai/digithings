"""Database engine and session."""

from __future__ import annotations

import logging
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from digikey.db_migrate import upgrade_jti_issued_table
from digikey.db_schema import Base

logger = logging.getLogger(__name__)

_engine = None
_session_factory: sessionmaker[Session] | None = None


def _normalize_postgres_driver(url: str) -> str:
    """Route a bare ``postgresql://`` URL to psycopg 3.

    digikey ships ``psycopg[binary]`` (v3) only, while SQLAlchemy's bare
    ``postgresql://`` dialect defaults to psycopg2 — an operator pasting the URL
    their provider hands them (Supabase, libpq) would otherwise hit
    ``No module named 'psycopg2'`` at engine creation (#4080).
    """
    scheme, sep, rest = url.partition("://")
    if sep and scheme.lower() in {"postgres", "postgresql"}:
        return f"postgresql+psycopg://{rest}"
    return url


def database_url() -> str:
    url = (os.environ.get("DIGIKEY_DATABASE_URL") or "").strip()
    if not url:
        raise RuntimeError("DIGIKEY_DATABASE_URL is not set")
    return _normalize_postgres_driver(url)


_TRUTHY = frozenset({"1", "true", "yes", "on"})


def require_durable_store(url: str) -> None:
    """Refuse/flag an ephemeral key store before it silently loses every key.

    SQLite is a single instance-local file: durable on a mounted volume, but a
    Cloudflare Container's ``/data`` is ephemeral, so a deploy that replaces the
    instance wipes issued API keys and JWT revocation state (#4080). Warn by
    default — a deploy must not become an auth outage on the strength of an env
    var — and fail closed when the operator opts in with
    ``DIGIKEY_REQUIRE_DURABLE_DB=1``.
    """
    if not url.startswith("sqlite"):
        return
    message = (
        "DIGIKEY_DATABASE_URL is SQLite: issued API keys and JWT revocation state "
        "live in one instance-local file. That survives a restart on a mounted "
        "volume, but a Cloudflare Container's /data is ephemeral, so replacing the "
        "instance wipes every key and the pipeline 401s. Use a Postgres URL in "
        "production (#4080)."
    )
    flag = (os.environ.get("DIGIKEY_REQUIRE_DURABLE_DB") or "").strip().lower()
    if flag in _TRUTHY:
        raise RuntimeError(message)
    logger.warning(message)


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
    # Checked before the engine exists so a refused store creates no tables.
    require_durable_store(database_url())
    engine = get_engine()
    # Upgrade existing tables *before* ``create_all``. ``create_all`` never
    # alters an existing table, and worse, it would recreate an empty
    # ``digikey_jti_issued`` if an interrupted rebuild left the copied data in
    # the working table. Persistent SQLite volumes from before #3917 still have
    # the old shape, which rehydrate/revoke reference.
    upgrade_jti_issued_table(engine)
    Base.metadata.create_all(bind=engine)
