"""In-place upgrade of a pre-DIG-4290 ``digikey_licenses`` table.

digikey has no migration framework: ``init_db()`` is ``create_all`` only, which
creates missing tables but never alters existing ones. A persistent SQLite
volume from before DIG-4290 therefore still has a ``digikey_licenses`` table
with no ``terms_version`` column, and the first ``license-mint`` after the
deploy would hard-fail with
``table digikey_licenses has no column named terms_version``. Starting digikey
against that database must add the nullable column in place without dropping
already-issued licence rows.
"""

from __future__ import annotations

import sqlite3

import pytest

pytestmark = pytest.mark.unit

# Exact shape of ``digikey_licenses`` before DIG-4290 (no ``terms_version``),
# plus one issued licence so we can prove the row survives and reads NULL.
_OLD_LICENSES_SCHEMA = """
CREATE TABLE digikey_licenses (
    license_id VARCHAR(36) NOT NULL,
    customer_slug VARCHAR(256) NOT NULL,
    hosts JSON NOT NULL,
    services JSON,
    issued_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    expires_at INTEGER NOT NULL,
    revoked_at DATETIME,
    label VARCHAR(256),
    PRIMARY KEY (license_id)
);
CREATE INDEX ix_digikey_licenses_customer_slug ON digikey_licenses (customer_slug);
INSERT INTO digikey_licenses (license_id, customer_slug, hosts, expires_at, label)
    VALUES ('lic-old', 'example-customer', '["a.com"]', 9999999999, 'legacy');
"""


@pytest.fixture()
def old_licenses_db(monkeypatch, tmp_path):
    db_path = tmp_path / "digikey.db"
    con = sqlite3.connect(db_path)
    con.executescript(_OLD_LICENSES_SCHEMA)
    con.commit()
    con.close()
    monkeypatch.setenv("DIGIKEY_DATABASE_URL", f"sqlite:///{db_path}")
    from digikey import db

    db._engine = None
    db._session_factory = None
    yield db
    db._engine = None
    db._session_factory = None


def test_init_db_adds_terms_version_without_data_loss(old_licenses_db) -> None:
    from sqlalchemy import inspect

    old_licenses_db.init_db()

    inspector = inspect(old_licenses_db.get_engine())
    cols = {c["name"]: c for c in inspector.get_columns("digikey_licenses")}
    assert "terms_version" in cols, "terms_version column must be added by the upgrade"
    assert cols["terms_version"]["nullable"] is True, "terms_version must be nullable"

    # The pre-existing row survives and reports an honest NULL — not a version
    # string, and not inferred from anything.
    from digikey.db_schema import LicenseRow

    sf = old_licenses_db.session_factory()
    with sf() as session:
        row = session.get(LicenseRow, "lic-old")
        assert row is not None
        assert row.customer_slug == "example-customer"
        assert row.terms_version is None


def test_upgrade_licenses_table_is_idempotent(old_licenses_db) -> None:
    from sqlalchemy import inspect

    # The second call must be a no-op. A blind re-run would raise
    # ``duplicate column name: terms_version`` on the next restart.
    assert old_licenses_db.init_db() is None
    old_licenses_db.init_db()

    inspector = inspect(old_licenses_db.get_engine())
    cols = {c["name"] for c in inspector.get_columns("digikey_licenses")}
    assert "terms_version" in cols

    from digikey.db_schema import LicenseRow

    sf = old_licenses_db.session_factory()
    with sf() as session:
        assert session.get(LicenseRow, "lic-old") is not None


def test_upgrade_licenses_table_noop_when_table_absent(monkeypatch, tmp_path) -> None:
    """Fresh install: the table does not exist yet, so the upgrade is a no-op
    and ``create_all`` creates it complete."""
    from sqlalchemy import inspect

    from digikey import db

    monkeypatch.setenv("DIGIKEY_DATABASE_URL", f"sqlite:///{tmp_path / 'fresh.db'}")
    db._engine = None
    db._session_factory = None
    try:
        db.init_db()
        inspector = inspect(db.get_engine())
        cols = {c["name"] for c in inspector.get_columns("digikey_licenses")}
        assert "terms_version" in cols
    finally:
        db._engine = None
        db._session_factory = None
