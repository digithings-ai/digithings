"""JWT issue/decode roundtrip (RS256)."""

import pytest

pytestmark = pytest.mark.unit

jwt = pytest.importorskip("jwt")


@pytest.fixture()
def key_setup(monkeypatch):
    from cryptography.hazmat.primitives.asymmetric import rsa

    from digikey.crypto_keys import private_key_to_pem, public_key_to_pem

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = private_key_to_pem(key)
    pub_pem = public_key_to_pem(key.public_key())
    monkeypatch.setenv("DIGIKEY_ISSUER", "http://test-digikey")
    monkeypatch.setenv("DIGIKEY_AUDIENCE", "digi-ecosystem")
    return priv_pem, pub_pem


def test_issue_and_decode(key_setup, monkeypatch):
    from digikey.jwt_issue import issue_access_token
    from digikey.jwt_verify import decode_token

    priv_pem, pub_pem = key_setup
    monkeypatch.setenv("DIGIKEY_PUBLIC_KEY_PEM", pub_pem)
    from cryptography.hazmat.primitives import serialization

    priv = serialization.load_pem_private_key(priv_pem.encode(), password=None)

    token, jti = issue_access_token(
        priv,
        kid="t1",
        sub="key:x",
        tenant_slug="acme",
        scopes=["digigraph:chat"],
        key_pub="dgk_prefix",
    )
    assert jti
    claims = decode_token(token)
    assert claims.tenant_slug == "acme"
    assert "digigraph:chat" in claims.scopes
    assert claims.key_pub == "dgk_prefix"
