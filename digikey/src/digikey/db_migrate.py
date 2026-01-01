"""Non-destructive schema upgrades for digikey (no migration framework).

``init_db()`` uses SQLAlchemy ``create_all``, which creates missing tables but
never alters existing ones. A deployment with a persistent ``digikey.db`` from
before #3917 therefore still has ``digikey_jti_issued.api_key_id NOT NULL`` and
no ``subject`` / ``revoked_at`` columns. ``rehydrate_blocklist_from_db()``
references ``JtiIssuedRow.revoked_at`` at startup, so leaving that schema alone
would crash-loop digikey — or 503 every BFF exchange.

This module upgrades ``digikey_jti_issued`` in place, preserving every row:

- SQLite cannot ``ALTER COLUMN ... DROP NOT NULL``, so it gets a table rebuild
  (create new, copy, drop old, rename). The original table is only dropped after
  a successful copy, and interrupted rebuilds are recovered on the next start —
  the old table is never silently wiped.
- Other dialects (Postgres) get additive ``ALTER TABLE`` statements.

It also adds the nullable ``digikey_licenses.terms_version`` column (DIG-4290)
when a table predates it. That column has no server default, so it is a plain
``ADD COLUMN`` on both dialects — no rebuild, no data movement.

Both paths are idempotent and safe to run on every startup.
"""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from digikey.db_schema import JtiIssuedRow, LicenseRow

logger = logging.getLogger(__name__)

_TABLE = JtiIssuedRow.__tablename__
#: Working name for the rebuilt SQLite table (migration-scoped, not a real table).
_NEW = f"{_TABLE}__new_3917"
_NEW_COLUMNS = ("jti", "api_key_id", "subject", "exp", "issued_at", "revoked_at")

# Kept in sync with ``JtiIssuedRow``. Frozen at the #3917 shape: it describes the
# upgrade target for databases created before this change.
_NEW_TABLE_DDL = f"""
CREATE TABLE {_NEW} (
    jti VARCHAR(36) NOT NULL,
    api_key_id VARCHAR(36),
    subject VARCHAR(256),
    exp INTEGER NOT NULL,
    issued_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revoked_at DATETIME,
    PRIMARY KEY (jti),
    FOREIGN KEY(api_key_id) REFERENCES digikey_api_keys (id)
)
"""


class SchemaUpgradeError(RuntimeError):
    """Raised when an existing digikey schema cannot be upgraded in place."""


def _columns(inspector, table: str) -> dict[str, dict] | None:
    if not inspector.has_table(table):
        return None
    return {c["name"]: c for c in inspector.get_columns(table)}


def _needs_upgrade(columns: dict[str, dict]) -> bool:
    if "subject" not in columns or "revoked_at" not in columns:
        return True
    return not bool(columns["api_key_id"].get("nullable", False))


def upgrade_jti_issued_table(engine: Engine) -> bool:
    """Upgrade ``digikey_jti_issued`` in place. Returns True when it changed."""
    inspector = inspect(engine)
    has_main = inspector.has_table(_TABLE)
    has_new = inspector.has_table(_NEW)

    # Recover an interrupted SQLite rebuild before inspecting the live schema:
    #  - ``_NEW`` without the main table: the copy finished and the drop/rename
    #    did not; promote the fully-copied table.
    #  - both present: the copy was interrupted pre-drop; the original is
    #    authoritative, so discard the incomplete working table.
    if has_new and not has_main:
        logger.warning("recovering interrupted digikey_jti_issued rebuild")
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {_NEW} RENAME TO {_TABLE}"))
    elif has_new and has_main:
        logger.warning("discarding incomplete digikey_jti_issued rebuild")
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE {_NEW}"))

    # Refresh: a mutation may have changed what ``inspector`` has cached.
    inspector = inspect(engine)
    columns = _columns(inspector, _TABLE)
    if columns is None or not _needs_upgrade(columns):
        return False

    logger.warning(
        "digikey_jti_issued has a pre-#3917 schema; upgrading in place (%s)",
        engine.dialect.name,
    )
    try:
        if engine.dialect.name == "sqlite":
            _rebuild_sqlite(engine, columns)
        else:
            _alter_generic(engine, columns)
    except Exception as e:  # pragma: no cover - defensive, tested via SQLite path
        raise SchemaUpgradeError(
            "failed to upgrade digikey_jti_issued; back up the database and re-run "
            "the upgrade before starting digikey"
        ) from e
    return True


_LICENSES_TABLE = LicenseRow.__tablename__
#: Added by DIG-4290. Nullable with no server default, so both SQLite and
#: Postgres take it as a plain ``ADD COLUMN`` — no table rebuild, no data move.
_TERMS_VERSION_COLUMN = "terms_version"


def upgrade_licenses_table(engine: Engine) -> bool:
    """Add ``terms_version`` to ``digikey_licenses`` in place. Returns True when it changed.

    ``create_all`` never alters an existing table, so a persistent ``digikey.db``
    whose ``digikey_licenses`` predates DIG-4290 has no ``terms_version`` column,
    and the first ``license-mint`` after the deploy would fail with
    ``table digikey_licenses has no column named terms_version``. Inspect first:
    a blind re-run on the next restart raises ``duplicate column name``.
    """
    inspector = inspect(engine)
    columns = _columns(inspector, _LICENSES_TABLE)
    if columns is None or _TERMS_VERSION_COLUMN in columns:
        return False

    logger.warning(
        "digikey_licenses is missing %s; upgrading in place (%s)",
        _TERMS_VERSION_COLUMN,
        engine.dialect.name,
    )
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    f"ALTER TABLE {_LICENSES_TABLE} ADD COLUMN {_TERMS_VERSION_COLUMN} VARCHAR(64)"
                )
            )
    except Exception as e:  # pragma: no cover - defensive
        raise SchemaUpgradeError(
            "failed to add digikey_licenses.terms_version; back up the database and "
            "re-run the upgrade before starting digikey"
        ) from e
    return True


def _alter_generic(engine: Engine, columns: dict[str, dict]) -> None:
    """Additive ALTERs for dialects that can drop NOT NULL in place."""
    with engine.begin() as conn:
        if "subject" not in columns:
            conn.execute(text(f"ALTER TABLE {_TABLE} ADD COLUMN subject VARCHAR(256)"))
        if "revoked_at" not in columns:
            conn.execute(text(f"ALTER TABLE {_TABLE} ADD COLUMN revoked_at TIMESTAMPTZ"))
        if not columns["api_key_id"].get("nullable", False):
            conn.execute(text(f"ALTER TABLE {_TABLE} ALTER COLUMN api_key_id DROP NOT NULL"))
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_digikey_jti_issued_subject_exp "
                f"ON {_TABLE} (subject, exp)"
            )
        )


def _rebuild_sqlite(engine: Engine, columns: dict[str, dict]) -> None:
    """Transactional-style rebuild for SQLite (no DROP NOT NULL in place)."""
    select_cols = ", ".join(
        f"{name} AS {name}" if name in columns else f"NULL AS {name}" for name in _NEW_COLUMNS
    )
    insert_cols = ", ".join(_NEW_COLUMNS)
    with engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {_NEW}"))
        conn.execute(text(_NEW_TABLE_DDL))
        conn.execute(text(f"INSERT INTO {_NEW} ({insert_cols}) SELECT {select_cols} FROM {_TABLE}"))
        conn.execute(text(f"DROP TABLE {_TABLE}"))
        conn.execute(text(f"ALTER TABLE {_NEW} RENAME TO {_TABLE}"))
        conn.execute(
            text(f"CREATE INDEX ix_digikey_jti_issued_key_exp ON {_TABLE} (api_key_id, exp)")
        )
        conn.execute(
            text(f"CREATE INDEX ix_digikey_jti_issued_subject_exp ON {_TABLE} (subject, exp)")
        )
