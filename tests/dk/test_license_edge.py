"""Slice 3: edge license scope checks (unit, no stack).

Pins the §7 normative scope map: corpus/vault headers require
``digisearch-corpus``, the web-search opt-in requires ``hosted-web-search``,
plain inference never touches license code, ``services``-absent means entitled,
and refusals name the missing scope with 403 ``insufficient_license_scope``.
"""

from __future__ import annotations

import time
import uuid

import jwt
import pytest

pytestmark = pytest.mark.unit

ISSUER = "http://test-digikey"


@pytest.fixture()
def keys():
    from cryptography.hazmat.primitives.asymmetric import rsa
    from digikey.crypto_keys import private_key_to_pem, public_key_to_pem

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key_to_pem(key), public_key_to_pem(key.public_key())


def _mint(
    priv_pem: str,
    license_id: str,
    *,
    services: list[str] | None = "absent",  # type: ignore[assignment]
    exp: int | None = None,
    sub: str = "datatap",
) -> str:
    now = int(time.time())
    claims: dict = {
        "sub": sub,
        "iss": ISSUER,
        "aud": "digichat-license",
        "iat": now,
        "exp": exp if exp is not None else now + 90 * 86400,
        "jti": license_id,
        "license_id": license_id,
        "tenant_slug": sub,
        "hosts": ["datatapstream.com"],
        "kind": "digichat-license",
    }
    if services != "absent" and services is not None:
        claims["services"] = list(services)
    return str(jwt.encode(claims, priv_pem, algorithm="RS256", headers={"kid": "t1"}))


def test_plain_inference_open_without_license(keys):
    from digikey.license_edge import evaluate_hosted_license

    _, pub = keys
    assert (
        evaluate_hosted_license(
            {}, needs_corpus=False, needs_web_search=False, public_key_pem=None, issuer=ISSUER
        )
        is None
    )
    # Even a revoked-shaped request (no crypto configured) stays open when plain.
    assert (
        evaluate_hosted_license(
            {"X-Digi-License": "garbage"},
            needs_corpus=False,
            needs_web_search=False,
            public_key_pem=pub,
        )
        is None
    )


def test_corpus_in_scope_allows(keys):
    from digikey.license_edge import evaluate_hosted_license

    priv, pub = keys
    lid = uuid.uuid4().hex
    headers = {
        "X-Digi-Corpus-Index": "customer-docs",
        "X-Digi-License": _mint(priv, lid, services=["digisearch-corpus"]),
    }
    assert (
        evaluate_hosted_license(
            headers, needs_corpus=True, needs_web_search=False, public_key_pem=pub, issuer=ISSUER
        )
        is None
    )


def test_corpus_absent_invalid_out_of_scope_denies(keys):
    from digikey.license_edge import LICENSE_CORPUS_SCOPE, evaluate_hosted_license

    priv, pub = keys
    lid = uuid.uuid4().hex
    base = {"X-Digi-Corpus-Index": "customer-docs"}
    assert (
        evaluate_hosted_license(
            dict(base), needs_corpus=True, needs_web_search=False, public_key_pem=pub, issuer=ISSUER
        )
        == LICENSE_CORPUS_SCOPE
    )
    assert (
        evaluate_hosted_license(
            dict(base, **{"X-Digi-License": "garbage"}),
            needs_corpus=True,
            needs_web_search=False,
            public_key_pem=pub,
        )
        == LICENSE_CORPUS_SCOPE
    )
    out_of_scope = dict(
        base, **{"X-Digi-License": _mint(priv, lid, services=["hosted-web-search"])}
    )
    assert (
        evaluate_hosted_license(
            out_of_scope,
            needs_corpus=True,
            needs_web_search=False,
            public_key_pem=pub,
            issuer=ISSUER,
        )
        == LICENSE_CORPUS_SCOPE
    )


def test_services_absent_means_entitled(keys):
    from digikey.license_edge import evaluate_hosted_license

    priv, pub = keys
    lid = uuid.uuid4().hex
    headers = {
        "X-Digi-Corpus-Index": "customer-docs",
        "X-Digi-Enable-Web-Search": "true",
        "X-Digi-License": _mint(priv, lid, services=None),
    }
    assert (
        evaluate_hosted_license(
            headers, needs_corpus=True, needs_web_search=True, public_key_pem=pub, issuer=ISSUER
        )
        is None
    )


def test_web_search_scope(keys):
    from digikey.license_edge import LICENSE_WEB_SEARCH_SCOPE, evaluate_hosted_license

    priv, pub = keys
    lid = uuid.uuid4().hex
    headers = {
        "X-Digi-Enable-Web-Search": "true",
        "X-Digi-License": _mint(priv, lid, services=["hosted-web-search"]),
    }
    assert (
        evaluate_hosted_license(
            headers, needs_corpus=False, needs_web_search=True, public_key_pem=pub, issuer=ISSUER
        )
        is None
    )
    assert (
        evaluate_hosted_license(
            {"X-Digi-Enable-Web-Search": "true"},
            needs_corpus=False,
            needs_web_search=True,
            public_key_pem=pub,
        )
        == LICENSE_WEB_SEARCH_SCOPE
    )


def test_expired_license_denies_at_edge(keys):
    from digikey.license_edge import LICENSE_CORPUS_SCOPE, evaluate_hosted_license

    priv, pub = keys
    lid = uuid.uuid4().hex
    headers = {
        "X-Digi-Corpus-Index": "customer-docs",
        "X-Digi-License": _mint(priv, lid, exp=int(time.time()) - 3600),
    }
    assert (
        evaluate_hosted_license(
            headers, needs_corpus=True, needs_web_search=False, public_key_pem=pub, issuer=ISSUER
        )
        == LICENSE_CORPUS_SCOPE
    )


def test_identity_free_license_denies(keys):
    from digikey.license_edge import LICENSE_CORPUS_SCOPE, evaluate_hosted_license

    priv, pub = keys
    lid = uuid.uuid4().hex
    headers = {
        "X-Digi-Corpus-Index": "customer-docs",
        "X-Digi-License": _mint(priv, lid, sub=""),
    }
    assert (
        evaluate_hosted_license(
            headers, needs_corpus=True, needs_web_search=False, public_key_pem=pub, issuer=ISSUER
        )
        == LICENSE_CORPUS_SCOPE
    )


def test_denial_body_names_scope():
    from digikey.license_edge import INSUFFICIENT_LICENSE_SCOPE, denial_body

    body = denial_body("digisearch-corpus")
    assert body["error"] == INSUFFICIENT_LICENSE_SCOPE
    assert "digisearch-corpus" in body["message"]


def test_header_case_insensitive(keys):
    from digikey.license_edge import evaluate_hosted_license

    priv, pub = keys
    lid = uuid.uuid4().hex
    headers = {
        "x-digi-corpus-index": "customer-docs",
        "x-digi-license": _mint(priv, lid, services=["digisearch-corpus"]),
    }
    assert (
        evaluate_hosted_license(
            headers, needs_corpus=True, needs_web_search=False, public_key_pem=pub, issuer=ISSUER
        )
        is None
    )
