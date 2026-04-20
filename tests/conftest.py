"""Shared pytest fixtures. E2E fixtures: digigraph_url, digiquant_url, e2e_available."""

from __future__ import annotations

import os

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Fail-closed services need JWT settings; unit tests mint tokens locally (no DigiKey process)."""
    if os.environ.get("DIGI_STRICT_BACKEND_TESTS") == "1":
        os.environ.pop("DIGISEARCH_ALLOW_STUB", None)
    else:
        os.environ["DIGISEARCH_ALLOW_STUB"] = "1"
    if os.environ.get("_PYTEST_DIGIKEY_PRIVATE_PEM"):
        return
    from cryptography.hazmat.primitives.asymmetric import rsa

    from digikey.crypto_keys import private_key_to_pem, public_key_to_pem

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = private_key_to_pem(key)
    pub_pem = public_key_to_pem(key.public_key())
    os.environ["_PYTEST_DIGIKEY_PRIVATE_PEM"] = priv_pem
    os.environ["DIGIKEY_PUBLIC_KEY_PEM"] = pub_pem
    os.environ.setdefault("DIGIKEY_ISSUER", "http://127.0.0.1:8005")
    os.environ.setdefault("DIGIKEY_AUDIENCE", "digi-ecosystem")


def _url(env_var: str, default_port: int) -> str:
    return os.environ.get(env_var, f"http://127.0.0.1:{default_port}")


@pytest.fixture(scope="session")
def digiquant_url() -> str:
    """Base URL for DigiQuant API. Set DIGIQUANT_URL or default 127.0.0.1:8001."""
    return _url("DIGIQUANT_URL", 8001).rstrip("/")


@pytest.fixture(scope="session")
def digigraph_url() -> str:
    """Base URL for DigiGraph API. Set DIGIGRAPH_URL or default 127.0.0.1:8000."""
    return _url("DIGIGRAPH_URL", 8000).rstrip("/")


@pytest.fixture(scope="session")
def digisearch_url() -> str:
    """Base URL for DigiSearch API. Set DIGISEARCH_URL or default 127.0.0.1:8002."""
    return _url("DIGISEARCH_URL", 8002).rstrip("/")


@pytest.fixture(scope="session")
def e2e_available() -> bool:
    """True if e2e tests should run (stack is up). Check health endpoints."""
    import httpx

    try:
        dq = _url("DIGIQUANT_URL", 8001).rstrip("/")
        dg = _url("DIGIGRAPH_URL", 8000).rstrip("/")
        with httpx.Client(timeout=2.0) as client:
            client.get(f"{dq}/health")
            client.get(f"{dg}/health")
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def digisearch_available() -> bool:
    """True if DigiSearch is up (e.g. Docker stack with digisearch)."""
    import httpx

    try:
        ds = _url("DIGISEARCH_URL", 8002).rstrip("/")
        with httpx.Client(timeout=2.0) as client:
            client.get(f"{ds}/health")
        return True
    except Exception:
        return False


def assert_prom_metrics_labels(body: str, *, service: str) -> None:
    """Assert a Prometheus text response carries the unified deploy-identity labels."""
    assert f'service="{service}"' in body, f"missing service label for {service}"
    assert 'version="' in body, "missing version label"
    assert 'environment="' in body, "missing environment label"
