"""Non-destructive in-place upgrade of a pre-#3917 ``digikey_jti_issued`` table.

digikey has no migration framework: ``init_db()`` is ``create_all`` only, which
creates missing tables but never alters existing ones. A persistent SQLite
volume from a pre-#3917 deployment therefore still has ``api_key_id NOT NULL``
and no ``subject`` / ``revoked_at`` columns. Starting digikey against it must
upgrade the table in place without dropping API keys or issued-jti rows.
"""

from __future__ import annotations

import sqlite3

import pytest

pytestmark = pytest.mark.unit

# Exact shape of ``digikey_jti_issued`` before #3917, plus a revoked API key and
# one live issued jti so we can prove data is preserved and rehydrate works.
_OLD_SCHEMA = """
CREATE TABLE digikey_api_keys (
    id VARCHAR(36) NOT NULL,
    key_hash TEXT NOT NULL,
    key_prefix VARCHAR(64) NOT NULL,
    tenant_slug VARCHAR(256) NOT NULL,
    project_id VARCHAR(512),
    project_config_ref TEXT,
    scopes JSON NOT NULL,
    kind VARCHAR(32) NOT NULL,
    label VARCHAR(256),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    revoked_at DATETIME,
    PRIMARY KEY (id)
);
CREATE UNIQUE INDEX ix_digikey_api_keys_key_prefix ON digikey_api_keys (key_prefix);
CREATE INDEX ix_digikey_api_keys_tenant_slug ON digikey_api_keys (tenant_slug);
CREATE TABLE digikey_jti_issued (
    jti VARCHAR(36) NOT NULL,
    api_key_id VARCHAR(36) NOT NULL,
    exp INTEGER NOT NULL,
    issued_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    PRIMARY KEY (jti),
    FOREIGN KEY(api_key_id) REFERENCES digikey_api_keys (id)
);
CREATE INDEX ix_digikey_jti_issued_key_exp ON digikey_jti_issued (api_key_id, exp);
INSERT INTO digikey_api_keys
    (id, key_hash, key_prefix, tenant_slug, scopes, kind, revoked_at)
    VALUES ('key-1', 'hash', 'dgk_live_prefix', 'acme', '[]', 'standard', CURRENT_TIMESTAMP);
INSERT INTO digikey_jti_issued (jti, api_key_id, exp) VALUES ('jti-old', 'key-1', 9999999999);
"""


def _write_old_db(db_path) -> None:
    con = sqlite3.connect(db_path)
    con.executescript(_OLD_SCHEMA)
    con.commit()
    con.close()


@pytest.fixture()
def old_db(monkeypatch, tmp_path):
    db_path = tmp_path / "digikey.db"
    _write_old_db(db_path)
    monkeypatch.setenv("DIGIKEY_DATABASE_URL", f"sqlite:///{db_path}")
    from digikey import blocklist, db

    db._engine = None
    db._session_factory = None
    blocklist.reset_client_cache()
    return db


def test_init_db_upgrades_old_sqlite_schema_without_data_loss(old_db, fake_blocklist_redis) -> None:
    _fake, blocklist = fake_blocklist_redis
    from sqlalchemy import inspect

    old_db.init_db()

    inspector = inspect(old_db.get_engine())
    cols = {c["name"]: c for c in inspector.get_columns("digikey_jti_issued")}
    assert "subject" in cols, "subject column must be added by the upgrade"
    assert "revoked_at" in cols, "revoked_at column must be added by the upgrade"
    assert cols["api_key_id"]["nullable"] is True, "api_key_id NOT NULL must be dropped"

    indexes = {i["name"] for i in inspector.get_indexes("digikey_jti_issued")}
    assert "ix_digikey_jti_issued_subject_exp" in indexes

    # Pre-existing row and API key survive.
    from digikey.db_schema import ApiKeyRow, JtiIssuedRow

    sf = old_db.session_factory()
    with sf() as session:
        jti_row = session.get(JtiIssuedRow, "jti-old")
        assert jti_row is not None
        assert jti_row.api_key_id == "key-1"
        assert session.get(ApiKeyRow, "key-1") is not None

    # The query that previously raised OperationalError now works end to end.
    from digikey.blocklist_rehydrate import rehydrate_blocklist_from_db

    written = rehydrate_blocklist_from_db(old_db.session_factory)
    assert written == 1
    assert blocklist.is_blocked("jti-old") is True


def test_upgrade_recovers_interrupted_rebuild_without_data_loss(old_db) -> None:
    from sqlalchemy import inspect, text

    # Simulate an interruption after the copy but before the rename: the table
    # only exists under the working name, carrying the original rows.
    engine = old_db.get_engine()
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE digikey_jti_issued RENAME TO digikey_jti_issued__new_3917"))
    assert not inspect(engine).has_table("digikey_jti_issued")

    old_db.init_db()

    inspector = inspect(engine)
    assert inspector.has_table("digikey_jti_issued")
    assert not inspector.has_table("digikey_jti_issued__new_3917")
    cols = {c["name"] for c in inspector.get_columns("digikey_jti_issued")}
    assert {"subject", "revoked_at"} <= cols

    from digikey.db_schema import JtiIssuedRow

    sf = old_db.session_factory()
    with sf() as session:
        assert session.get(JtiIssuedRow, "jti-old") is not None


def test_init_db_upgrade_is_idempotent(old_db) -> None:
    old_db.init_db()
    # Second call must be a no-op rather than re-running the rebuild.
    old_db.init_db()

    from sqlalchemy import inspect

    inspector = inspect(old_db.get_engine())
    cols = {c["name"]: c for c in inspector.get_columns("digikey_jti_issued")}
    assert "subject" in cols and "revoked_at" in cols

    from digikey.db_schema import JtiIssuedRow

    sf = old_db.session_factory()
    with sf() as session:
        assert session.get(JtiIssuedRow, "jti-old") is not None
