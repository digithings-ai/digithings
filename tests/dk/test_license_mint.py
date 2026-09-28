"""Slice 1: license-mint CLI + digikey_licenses registry (unit, no stack)."""

from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.unit

ISSUER = "http://test-digikey"


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


def _decode(token: str, key, audience: str = "digichat-license") -> dict:
    import jwt
    from digikey.crypto_keys import public_key_to_pem

    pub = public_key_to_pem(key.public_key())
    return jwt.decode(token, pub, algorithms=["RS256"], audience=audience, issuer=ISSUER)


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


# --- claims table ---


def test_claims_golden_defaults(lic_env):
    from digikey.jwt_issue import _issuer, issue_access_token, issue_license_token

    token, license_id, exp = issue_license_token(
        lic_env, kid="k1", customer_slug="datatap", hosts=["a.com", "www.a.com"]
    )
    claims = _decode(token, lic_env)
    assert claims["iss"] == _issuer()
    assert claims["aud"] == "digichat-license"
    assert claims["sub"] == "datatap"
    assert claims["tenant_slug"] == "datatap"
    assert claims["jti"] == license_id
    assert claims["license_id"] == license_id
    assert claims["hosts"] == ["a.com", "www.a.com"]
    assert claims["kind"] == "digichat-license"
    assert claims["exp"] - claims["iat"] == 90 * 86400 == 7776000
    assert claims["exp"] == exp
    assert "services" not in claims
    assert "scope" not in claims
    for absent in ("scopes", "key_pub", "principal_kind", "project_id", "tenant_id"):
        assert absent not in claims
    # iss equals the access-token issuer: aud discriminates, not iss.
    access_token, _ = issue_access_token(
        lic_env, kid="k1", sub="key:x", tenant_slug="acme", scopes=["digigraph:chat"]
    )
    import jwt
    from digikey.crypto_keys import public_key_to_pem

    access_claims = jwt.decode(
        access_token,
        public_key_to_pem(lic_env.public_key()),
        algorithms=["RS256"],
        audience="digi-ecosystem",
        issuer=ISSUER,
    )
    assert access_claims["iss"] == claims["iss"]


def test_claims_with_services_mirror_scope(lic_env):
    from digikey.jwt_issue import issue_license_token

    token, _, _ = issue_license_token(
        lic_env,
        kid="k1",
        customer_slug="datatap",
        hosts=["a.com"],
        services=["digisearch-corpus", "hosted-web-search"],
    )
    claims = _decode(token, lic_env)
    assert claims["services"] == ["digisearch-corpus", "hosted-web-search"]
    assert claims["scope"] == "digisearch-corpus hosted-web-search"


def test_claims_empty_services_omitted(lic_env):
    from digikey.jwt_issue import build_license_claims

    claims, _ = build_license_claims(customer_slug="c", hosts=["h"], services=[])
    assert "services" not in claims
    assert "scope" not in claims


def test_audience_discrimination(lic_env):
    import jwt
    from digikey.crypto_keys import public_key_to_pem
    from digikey.jwt_issue import issue_access_token, issue_license_token

    pub = public_key_to_pem(lic_env.public_key())
    lic_token, _, _ = issue_license_token(
        lic_env, kid="k1", customer_slug="datatap", hosts=["a.com"]
    )
    with pytest.raises(jwt.InvalidAudienceError):
        jwt.decode(
            lic_token,
            pub,
            algorithms=["RS256"],
            audience="digi-ecosystem",
            issuer=ISSUER,
        )
    access_token, _ = issue_access_token(
        lic_env, kid="k1", sub="key:x", tenant_slug="acme", scopes=["a:b"]
    )
    with pytest.raises(jwt.InvalidAudienceError):
        jwt.decode(
            access_token,
            pub,
            algorithms=["RS256"],
            audience="digichat-license",
            issuer=ISSUER,
        )


def test_kid_header_present_and_stable(lic_env):
    import jwt
    from digikey.crypto_keys import generate_rsa_private_key
    from digikey.jwt_issue import issue_license_token

    t1, _, _ = issue_license_token(lic_env, kid="key-A", customer_slug="c", hosts=["h"])
    t2, _, _ = issue_license_token(lic_env, kid="key-A", customer_slug="c", hosts=["h"])
    assert jwt.get_unverified_header(t1)["kid"] == "key-A"
    assert jwt.get_unverified_header(t2)["kid"] == "key-A"
    # Mint under key A verifies against public key A.
    assert _decode(t1, lic_env)["sub"] == "c"
    # ... and not against an unrelated key.
    other = generate_rsa_private_key()
    with pytest.raises(jwt.InvalidSignatureError):
        _decode(t1, other)


def test_custom_term(lic_env):
    from digikey.jwt_issue import issue_license_token

    token, _, _ = issue_license_token(
        lic_env, kid="k1", customer_slug="c", hosts=["h"], term_days=30
    )
    assert _decode(token, lic_env)["exp"] - _decode(token, lic_env)["iat"] == 30 * 86400


@pytest.mark.parametrize("term", [0, -1, 181, 1000])
def test_term_bounds_rejected(lic_env, term):
    from digikey.jwt_issue import issue_license_token

    with pytest.raises(ValueError, match="term_days"):
        issue_license_token(lic_env, kid="k", customer_slug="c", hosts=["h"], term_days=term)


def test_blank_customer_or_hosts_rejected(lic_env):
    from digikey.jwt_issue import issue_license_token

    with pytest.raises(ValueError, match="customer_slug"):
        issue_license_token(lic_env, kid="k", customer_slug="   ", hosts=["h"])
    with pytest.raises(ValueError, match="hosts"):
        issue_license_token(lic_env, kid="k", customer_slug="c", hosts=["  ", " "])


def test_parse_services(lic_env):
    from digikey.licenses import parse_services

    assert parse_services(None) is None
    assert parse_services("digisearch-corpus,hosted-web-search") == [
        "digisearch-corpus",
        "hosted-web-search",
    ]
    with pytest.raises(ValueError, match="unknown"):
        parse_services("digisearch-corpus,nope")
    with pytest.raises(ValueError, match="--services"):
        parse_services("  , ")


# --- CLI mint ---


def test_cli_mint_inserts_live_row(monkeypatch, capsys, lic_env):
    out = _run_cli(
        monkeypatch,
        capsys,
        "license-mint",
        "--customer",
        "datatap",
        "--hosts",
        "datatapstream.com,www.datatapstream.com",
    )
    lines = out.out.strip().splitlines()
    assert len(lines) == 4
    assert lines[0].startswith("license_id=")
    assert lines[1] == "customer=datatap"
    assert lines[2].startswith("exp=")
    assert lines[3].startswith("license_jwt=")
    license_id = lines[0].split("=", 1)[1]
    token = lines[3].split("=", 1)[1]
    claims = _decode(token, lic_env)
    assert claims["license_id"] == license_id
    row = _mint_row(license_id)
    assert row.customer_slug == "datatap"
    assert row.hosts == ["datatapstream.com", "www.datatapstream.com"]
    assert row.services is None
    assert row.expires_at == claims["exp"]
    assert row.revoked_at is None
    assert row.label is None


def test_cli_mint_with_services_and_label(monkeypatch, capsys, lic_env):
    out = _run_cli(
        monkeypatch,
        capsys,
        "license-mint",
        "--customer",
        "datatap",
        "--hosts",
        "a.com",
        "--services",
        "digisearch-corpus",
        "--label",
        "pilot",
        "--term-days",
        "30",
    )
    license_id = out.out.strip().splitlines()[0].split("=", 1)[1]
    row = _mint_row(license_id)
    assert row.services == ["digisearch-corpus"]
    assert row.label == "pilot"


def test_cli_remint_same_customer_new_id(monkeypatch, capsys, lic_env):
    args = ("license-mint", "--customer", "datatap", "--hosts", "a.com")
    id1 = _run_cli(monkeypatch, capsys, *args).out.strip().splitlines()[0]
    id2 = _run_cli(monkeypatch, capsys, *args).out.strip().splitlines()[0]
    assert id1 != id2
    _mint_row(id1.split("=", 1)[1])
    _mint_row(id2.split("=", 1)[1])


@pytest.mark.parametrize(
    "argv",
    [
        ("license-mint", "--customer", "   ", "--hosts", "a.com"),
        ("license-mint", "--customer", "c", "--hosts", "   "),
        ("license-mint", "--customer", "c", "--hosts", "a.com", "--term-days", "0"),
        ("license-mint", "--customer", "c", "--hosts", "a.com", "--term-days", "-5"),
        ("license-mint", "--customer", "c", "--hosts", "a.com", "--term-days", "181"),
        ("license-mint", "--customer", "c", "--hosts", "a.com", "--services", "bogus-scope"),
    ],
)
def test_cli_validation_exits_2(monkeypatch, capsys, lic_env, argv):
    from digikey.cli import main

    monkeypatch.setattr("sys.argv", ["digikey", *argv])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 2


def test_cli_mint_missing_db_url(monkeypatch, capsys, lic_env):
    from digikey.cli import main

    monkeypatch.delenv("DIGIKEY_DATABASE_URL", raising=False)
    monkeypatch.setattr("sys.argv", ["digikey", "license-mint", "--customer", "c", "--hosts", "h"])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1
    assert "DIGIKEY_DATABASE_URL" in capsys.readouterr().err


def test_cli_mint_refuses_ephemeral_key(monkeypatch, capsys, tmp_path):
    """Minting under an ephemeral key can never verify — always a bug."""
    from digikey.cli import main

    from digikey import db

    monkeypatch.setenv("DIGIKEY_DATABASE_URL", f"sqlite:///{tmp_path / 'e.db'}")
    monkeypatch.delenv("DIGIKEY_PRIVATE_KEY_PEM", raising=False)
    monkeypatch.setenv("DIGIKEY_ALLOW_EPHEMERAL_KEY", "1")
    db._engine = None
    db._session_factory = None
    monkeypatch.setattr("sys.argv", ["digikey", "license-mint", "--customer", "c", "--hosts", "h"])
    try:
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code != 0
        assert "DIGIKEY_PRIVATE_KEY_PEM" in capsys.readouterr().err
    finally:
        db._engine = None
        db._session_factory = None


def test_cli_dry_run_writes_nothing(monkeypatch, capsys, lic_env):
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
    claims = json.loads(out.out)
    assert claims["aud"] == "digichat-license"
    assert claims["sub"] == "datatap"
    from digikey.db import session_factory
    from digikey.db_schema import LicenseRow
    from sqlalchemy import func, select

    with session_factory()() as session:
        count = session.scalar(select(func.count()).select_from(LicenseRow))
    assert count == 0


# --- revoke ---


def test_cli_revoke_idempotent_and_unknown(monkeypatch, capsys, lic_env):
    mint_out = _run_cli(monkeypatch, capsys, "license-mint", "--customer", "c", "--hosts", "h")
    license_id = mint_out.out.strip().splitlines()[0].split("=", 1)[1]

    out = _run_cli(monkeypatch, capsys, "license-revoke", "--license-id", license_id)
    assert out.out.strip().splitlines() == [
        f"license_id={license_id}",
        "revoked=true",
        "already_revoked=false",
    ]
    assert _mint_row(license_id).revoked_at is not None

    out2 = _run_cli(monkeypatch, capsys, "license-revoke", "--license-id", license_id)
    assert out2.out.strip().splitlines()[-1] == "already_revoked=true"

    from digikey.cli import main

    monkeypatch.setattr("sys.argv", ["digikey", "license-revoke", "--license-id", "no-such-id"])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code != 0
    assert "license not found" in capsys.readouterr().err


def test_revoke_missing_db_url(monkeypatch, capsys, lic_env):
    from digikey.cli import main

    monkeypatch.delenv("DIGIKEY_DATABASE_URL", raising=False)
    monkeypatch.setattr("sys.argv", ["digikey", "license-revoke", "--license-id", "x"])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


# --- registry ---


def test_create_all_picks_up_licenses_table(lic_env):
    from digikey.db import get_engine
    from sqlalchemy import inspect

    assert inspect(get_engine()).has_table("digikey_licenses")


def test_mint_input_model_rejects_bad_services():
    from digikey.licenses import LicenseMintInput
    from pydantic import ValidationError

    ok = LicenseMintInput(customer_slug="c", hosts=["h"], term_days=90)
    assert ok.services is None
    with pytest.raises(ValidationError):
        LicenseMintInput(customer_slug="c", hosts=["h"], services=["nope"])
    with pytest.raises(ValidationError):
        LicenseMintInput(customer_slug="   ", hosts=["h"])
