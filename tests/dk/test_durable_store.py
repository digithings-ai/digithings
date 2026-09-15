"""An ephemeral digikey key store must be loud, not silent (#4080).

The stack's ``DIGIKEY_DATABASE_URL`` defaulted to SQLite on the Cloudflare
Container's ephemeral ``/data``, so a deploy that replaced the instance wiped
every issued API key. The daily digiquant book run then failed with a 401 that
looked like a bad key rather than lost storage.
"""

from __future__ import annotations

import logging

import pytest

from digikey import db as db_mod

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _reset_engine():
    db_mod._engine = None
    db_mod._session_factory = None
    yield
    db_mod._engine = None
    db_mod._session_factory = None


def test_sqlite_store_warns(caplog: pytest.LogCaptureFixture, monkeypatch) -> None:
    monkeypatch.delenv("DIGIKEY_REQUIRE_DURABLE_DB", raising=False)

    with caplog.at_level(logging.WARNING, logger="digikey.db"):
        db_mod.require_durable_store("sqlite:////data/digikey.db")

    assert any("ephemeral" in record.getMessage() for record in caplog.records)


def test_sqlite_store_fails_closed_when_required(monkeypatch) -> None:
    monkeypatch.setenv("DIGIKEY_REQUIRE_DURABLE_DB", "1")

    with pytest.raises(RuntimeError, match="ephemeral"):
        db_mod.require_durable_store("sqlite:////data/digikey.db")


def test_postgres_store_is_silent(caplog: pytest.LogCaptureFixture, monkeypatch) -> None:
    monkeypatch.setenv("DIGIKEY_REQUIRE_DURABLE_DB", "1")

    with caplog.at_level(logging.WARNING, logger="digikey.db"):
        db_mod.require_durable_store("postgresql://digikey:pw@db.example:5432/digikey")

    assert caplog.records == []


def test_init_db_refuses_an_ephemeral_store(monkeypatch, tmp_path) -> None:
    """The guard runs on the startup path, not just as a callable."""
    monkeypatch.setenv("DIGIKEY_DATABASE_URL", f"sqlite:///{tmp_path / 'digikey.db'}")
    monkeypatch.setenv("DIGIKEY_REQUIRE_DURABLE_DB", "1")

    with pytest.raises(RuntimeError, match="ephemeral"):
        db_mod.init_db()

    assert db_mod._engine is None


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        (
            "postgresql://dk:pw@db.example:5432/digikey",
            "postgresql+psycopg://dk:pw@db.example:5432/digikey",
        ),
        (
            "postgres://dk:pw@db.example:5432/digikey",
            "postgresql+psycopg://dk:pw@db.example:5432/digikey",
        ),
        (
            "postgresql+psycopg://dk:pw@db.example:5432/digikey",
            "postgresql+psycopg://dk:pw@db.example:5432/digikey",
        ),
        ("sqlite:////data/digikey.db", "sqlite:////data/digikey.db"),
    ],
)
def test_database_url_normalizes_the_postgres_driver(monkeypatch, given, expected) -> None:
    """A bare provider URL must not reach SQLAlchemy's psycopg2 default."""
    monkeypatch.setenv("DIGIKEY_DATABASE_URL", f"  {given}  ")

    assert db_mod.database_url() == expected


def test_a_bare_postgres_url_builds_a_psycopg_engine(monkeypatch) -> None:
    """The URL an operator actually pastes must not need psycopg2 installed."""
    from sqlalchemy import create_engine

    monkeypatch.setenv("DIGIKEY_DATABASE_URL", "postgresql://dk:pw@127.0.0.1:5/digikey")
    monkeypatch.setenv("DIGIKEY_REQUIRE_DURABLE_DB", "1")

    engine = create_engine(db_mod.database_url())

    assert engine.dialect.driver == "psycopg"
    db_mod.require_durable_store(db_mod.database_url())


@pytest.mark.parametrize("flag", ["1", "true", "YES", " on "])
def test_strict_mode_accepts_common_truthy_spellings(monkeypatch, flag) -> None:
    monkeypatch.setenv("DIGIKEY_REQUIRE_DURABLE_DB", flag)

    with pytest.raises(RuntimeError, match="ephemeral"):
        db_mod.require_durable_store("sqlite:////data/digikey.db")
