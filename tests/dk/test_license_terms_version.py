"""Terms version recorded on every licence minted (DIG-2198, DIG-2161 §2.1).

The versioned Terms a licence was granted under is evidence, and evidence that
can be absent is different from evidence that is fabricated. Two rules hold the
whole leaf together:

1. **Absent, never null, never mandatory.** ``terms_version`` is nullable with no
   server default. A falsy value omits the claim entirely (the same pairwise-omit
   convention ``services``/``scope`` already uses) rather than emitting a literal
   JSON ``null``, which consumers cannot distinguish from "recorded as none".
   Publication is on hold pending the partita IVA, so no versioned Terms exists to
   point at; a required field would block issuance or invite an invented version.

2. **An existing install must survive the column.** ``create_all`` never alters an
   existing table, so a ``terms_version`` declared on ``LicenseRow`` never
   materialises on a database that already has ``digikey_licenses`` — the next mint
   dies with "no column named terms_version". Fresh CI and new volumes pass anyway,
   which is why ``test_init_db_upgrades_pre_existing_licenses_table`` below is the
   test that carries this leaf, and why a green suite over a fresh database is not
   evidence.

There is no backfill: there is no version to backfill, and writing one would be
exactly the false record this issue exists to prevent. Art. 1341 per-clause
approvals are phase 2 and get their own columns once Counsel signs off the clause
list; they are never packed into ``terms_version`` as a delimited string.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

pytestmark = pytest.mark.unit

ISSUER = "http://test-digikey"

#: Exact pre-DIG-2198 shape of ``digikey_licenses``: the DDL a persistent volume
#: already holds when this code is deployed. No ``terms_version`` column.
_PRE_CHANGE_LICENSES_DDL = """
CREATE TABLE digikey_licenses (
    license_id VARCHAR(36) PRIMARY KEY,
    customer_slug VARCHAR(256) NOT NULL,
    hosts TEXT NOT NULL,
    services TEXT NULL,
    issued_at DATETIME NULL,
    expires_at INTEGER NOT NULL,
    revoked_at DATETIME NULL,
    label VARCHAR(256) NULL
)
"""


@pytest.fixture()
def lic_env(monkeypatch, tmp_path):
    """Fresh sqlite db + generated signing key, singletons reset per test."""
    from digikey.crypto_keys import generate_rsa_private_key, private_key_to_pem

    from digikey import db

    monkeypatch.setenv("DIGIKEY_DATABASE_URL", f"sqlite:///{tmp_path / 'lic.db'}")
    monkeypatch.delenv("DIGIKEY_ALLOW_EPHEMERAL_KEY", raising=False)
    monkeypatch.delenv("DIGIKEY_AUDIENCE", raising=False)
    monkeypatch.setenv("DIGIKEY_ISSUER", ISSUER)
    key = generate_rsa_private_key()
    monkeypatch.setenv("DIGIKEY_PRIVATE_KEY_PEM", private_key_to_pem(key))
    db._engine = None
    db._session_factory = None
    from digikey.db import init_db

    init_db()
    yield key
    db._engine = None
    db._session_factory = None


def _run_cli(monkeypatch, capsys, *argv):
    from digikey.cli import main

    monkeypatch.setattr("sys.argv", ["digikey", *argv])
    main()
    return capsys.readouterr()


def _mint_row(license_id: str):
    from digikey.db import session_factory
    from digikey.db_schema import LicenseRow

    with session_factory()() as session:
        row = session.get(LicenseRow, license_id)
        assert row is not None
        session.expunge(row)
        return row


def _minted_license_id(out) -> str:
    return out.out.strip().splitlines()[0].split("=", 1)[1]


# --- the claim is omitted, never null ---


def test_license_claims_omit_terms_version_when_not_supplied(lic_env) -> None:
    from digikey.jwt_issue import build_license_claims

    claims, _ = build_license_claims(customer_slug="c", hosts=["h"])
    assert "terms_version" not in claims


@pytest.mark.parametrize("falsy", [None, "", "   ", "\t\n"])
def test_build_license_claims_omits_falsy_terms_version(lic_env, falsy) -> None:
    """Blank and whitespace are *not supplied*, matching the services convention.

    A literal JSON ``null`` would be ambiguous to consumers: it reads as
    "recorded, and the value is none" rather than "never recorded".
    """
    from digikey.jwt_issue import build_license_claims

    claims, _ = build_license_claims(customer_slug="c", hosts=["h"], terms_version=falsy)
    assert "terms_version" not in claims


def test_build_license_claims_carries_supplied_terms_version(lic_env) -> None:
    from digikey.jwt_issue import build_license_claims

    claims, _ = build_license_claims(customer_slug="c", hosts=["h"], terms_version="v2026-01-15")
    assert claims["terms_version"] == "v2026-01-15"


def test_issue_license_token_carries_terms_version(lic_env) -> None:
    import jwt
    from digikey.crypto_keys import public_key_to_pem
    from digikey.jwt_issue import issue_license_token

    token, _, _ = issue_license_token(
        lic_env, kid="k1", customer_slug="c", hosts=["h"], terms_version="v2026-01-15"
    )
    claims = jwt.decode(
        token,
        public_key_to_pem(lic_env.public_key()),
        algorithms=["RS256"],
        audience="digichat-license",
        issuer=ISSUER,
    )
    assert claims["terms_version"] == "v2026-01-15"


# --- the claim reaches the registry row ---


def test_cli_mint_without_flag_leaves_column_null(monkeypatch, capsys, lic_env) -> None:
    out = _run_cli(monkeypatch, capsys, "license-mint", "--customer", "datatap", "--hosts", "a.com")
    import jwt
    from digikey.crypto_keys import public_key_to_pem

    token = out.out.strip().splitlines()[3].split("=", 1)[1]
    claims = jwt.decode(
        token,
        public_key_to_pem(lic_env.public_key()),
        algorithms=["RS256"],
        audience="digichat-license",
        issuer=ISSUER,
    )
    assert "terms_version" not in claims
    assert _mint_row(claims["license_id"]).terms_version is None


def test_cli_mint_with_flag_persists_claim_and_column(monkeypatch, capsys, lic_env) -> None:
    out = _run_cli(
        monkeypatch,
        capsys,
        "license-mint",
        "--customer",
        "datatap",
        "--hosts",
        "a.com",
        "--terms-version",
        "v2026-01-15",
    )
    import jwt
    from digikey.crypto_keys import public_key_to_pem

    token = out.out.strip().splitlines()[3].split("=", 1)[1]
    claims = jwt.decode(
        token,
        public_key_to_pem(lic_env.public_key()),
        algorithms=["RS256"],
        audience="digichat-license",
        issuer=ISSUER,
    )
    assert claims["terms_version"] == "v2026-01-15"
    assert _mint_row(claims["license_id"]).terms_version == "v2026-01-15"


@pytest.mark.parametrize("blank", ["", "   ", "\t"])
def test_cli_blank_terms_version_is_not_supplied(monkeypatch, capsys, lic_env, blank) -> None:
    out = _run_cli(
        monkeypatch,
        capsys,
        "license-mint",
        "--customer",
        "datatap",
        "--hosts",
        "a.com",
        "--terms-version",
        blank,
    )
    license_id = _minted_license_id(out)
    assert _mint_row(license_id).terms_version is None


# --- dry run ---


def test_dry_run_includes_terms_version_when_supplied(monkeypatch, capsys, lic_env) -> None:
    out = _run_cli(
        monkeypatch,
        capsys,
        "license-mint",
        "--customer",
        "datatap",
        "--hosts",
        "a.com",
        "--terms-version",
        "v2026-01-15",
        "--dry-run",
    )
    claims = json.loads(out.out)
    assert claims["terms_version"] == "v2026-01-15"


def test_dry_run_omits_terms_version_when_not_supplied(monkeypatch, capsys, lic_env) -> None:
    out = _run_cli(
        monkeypatch,
        capsys,
        "license-mint",
        "--customer",
        "datatap",
        "--hosts",
        "a.com",
        "--dry-run",
    )
    assert "terms_version" not in json.loads(out.out)


# --- the gap: an install that already has the table ---


@pytest.fixture()
def pre_existing_db(monkeypatch, tmp_path):
    """A ``digikey.db`` written before DIG-2198, holding an already-issued licence."""
    db_path = tmp_path / "pre-change.db"
    con = sqlite3.connect(db_path)
    con.executescript(_PRE_CHANGE_LICENSES_DDL)
    con.execute(
        "INSERT INTO digikey_licenses "
        "(license_id, customer_slug, hosts, services, issued_at, expires_at, revoked_at, label) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "lic-issued-before",
            "datatap",
            json.dumps(["datatapstream.com"]),
            None,
            "2026-01-02 03:04:05",
            9999999999,
            None,
            "pilot",
        ),
    )
    con.commit()
    con.close()

    from digikey import blocklist, db

    monkeypatch.setenv("DIGIKEY_DATABASE_URL", f"sqlite:///{db_path}")
    db._engine = None
    db._session_factory = None
    blocklist.reset_client_cache()
    yield db
    db._engine = None
    db._session_factory = None


def test_init_db_upgrades_pre_existing_licenses_table(
    pre_existing_db, fake_blocklist_redis
) -> None:
    """The column must exist on a database that already had ``digikey_licenses``.

    ``create_all`` is create-only, so without an in-place upgrade this install
    keeps the old shape forever and every subsequent mint raises "no column named
    terms_version". The pre-existing licence survives with ``terms_version`` NULL:
    no version was in force when it was granted, and inventing one is the false
    record DIG-2161 exists to prevent.
    """
    from sqlalchemy import inspect

    pre_existing_db.init_db()

    inspector = inspect(pre_existing_db.get_engine())
    cols = {c["name"]: c for c in inspector.get_columns("digikey_licenses")}
    assert "terms_version" in cols, "upgrade must add terms_version to an existing table"
    assert cols["terms_version"]["nullable"] is True

    from digikey.db_schema import LicenseRow

    with pre_existing_db.session_factory()() as session:
        pre_existing = session.get(LicenseRow, "lic-issued-before")
        assert pre_existing is not None
        assert pre_existing.customer_slug == "datatap"
        assert pre_existing.label == "pilot"
        assert pre_existing.terms_version is None, "no backfill: absence must stay absence"


def test_mint_succeeds_after_pre_existing_table_upgrade(
    pre_existing_db, fake_blocklist_redis
) -> None:
    """The upgrade's whole point: the next mint works on the upgraded volume."""
    from digikey.db_schema import LicenseRow
    from digikey.licenses import insert_license_row

    from digikey import db

    db.init_db()
    with db.session_factory()() as session:
        insert_license_row(
            session,
            license_id="lic-minted-after",
            customer_slug="datatap",
            hosts=["datatapstream.com"],
            services=None,
            expires_at=9999999999,
            label="",
            terms_version="v2026-01-15",
        )
        assert session.get(LicenseRow, "lic-minted-after").terms_version == "v2026-01-15"


def test_upgrade_licenses_table_is_a_no_op_on_re_run(pre_existing_db, fake_blocklist_redis) -> None:
    """A blind re-run on the next restart raises "duplicate column name"."""
    from digikey.db_migrate import upgrade_licenses_table

    assert upgrade_licenses_table(pre_existing_db.get_engine()) is True
    assert upgrade_licenses_table(pre_existing_db.get_engine()) is False
    pre_existing_db.init_db()
    assert upgrade_licenses_table(pre_existing_db.get_engine()) is False


def test_upgrade_licenses_table_is_a_no_op_on_a_fresh_install(lic_env) -> None:
    """Table absent is a no-op: ``create_all`` builds it with the column."""
    from digikey.db_migrate import upgrade_licenses_table

    assert upgrade_licenses_table(lic_env.get_engine()) is False


# --- unchanged by this leaf ---


def test_180_day_cap_still_rejects_a_longer_term(monkeypatch, capsys, lic_env) -> None:
    from digikey.cli import main

    monkeypatch.setattr(
        "sys.argv",
        ["digikey", "license-mint", "--customer", "c", "--hosts", "a.com", "--term-days", "181"],
    )
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 2


def test_license_mint_has_no_dev_global_bypass_kind(monkeypatch, capsys, lic_env) -> None:
    """``license-mint`` takes no wildcard-scope bypass kind (AGENTS.md:46)."""
    from digikey.cli import main

    monkeypatch.setattr(
        "sys.argv",
        ["digikey", "license-mint", "--customer", "c", "--hosts", "a.com", "--kind", "dev_global"],
    )
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 2
