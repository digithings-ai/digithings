"""The key-store URL is required; nothing may invent a SQLite default (#4080).

The stack used to default ``DIGIKEY_DATABASE_URL`` to SQLite on the Cloudflare
Container's ephemeral ``/data``, so a deploy that replaced the instance wiped
every issued API key. The daily digiquant book run then failed with a 401 that
looked like a bad key rather than lost storage. The URL is now required — the
service refuses to start without it — and a bare provider URL is routed to
psycopg 3, the only driver digikey ships.
"""

from __future__ import annotations

from pathlib import Path

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


def test_an_unset_url_is_refused(monkeypatch) -> None:
    monkeypatch.delenv("DIGIKEY_DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="not set"):
        db_mod.database_url()


def test_a_blank_url_is_refused(monkeypatch) -> None:
    monkeypatch.setenv("DIGIKEY_DATABASE_URL", "   ")

    with pytest.raises(RuntimeError, match="not set"):
        db_mod.database_url()


def test_init_db_creates_no_engine_when_the_url_is_unset(monkeypatch) -> None:
    monkeypatch.delenv("DIGIKEY_DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="not set"):
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

    engine = create_engine(db_mod.database_url())

    assert engine.dialect.driver == "psycopg"


def test_sqlite_is_still_usable_when_asked_for_explicitly(monkeypatch, tmp_path) -> None:
    """Dev/local deployments keep working — they just have to say so."""
    from sqlalchemy import inspect

    monkeypatch.setenv("DIGIKEY_DATABASE_URL", f"sqlite:///{tmp_path / 'digikey.db'}")

    db_mod.init_db()

    created = set(inspect(db_mod._engine).get_table_names())
    assert {"digikey_api_keys", "digikey_jti_issued"} <= created


def test_the_stack_does_not_synthesize_a_sqlite_url() -> None:
    """Recurrence guard: refusing an unset URL is worthless if the stack sets one.

    ``database_url()`` raises when the variable is empty, so the only way back to
    #4080 is a substituted default. The Cloudflare stack carried exactly that on
    two lines; pin that no SQLite URL returns to either — matching any path or
    ``:memory:`` form, not just the one that was there.
    """
    root = Path(__file__).resolve().parents[2]
    for rel in (
        "apps/digithings-stack-cloudflare/src/index.ts",
        "apps/digithings-stack-cloudflare/container/entrypoint.sh",
    ):
        text = (root / rel).read_text(encoding="utf-8")
        assert "sqlite://" not in text, f"{rel} invents an ephemeral store"
