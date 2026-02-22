"""Shared pytest fixtures. E2E fixtures: digigraph_url, digiquant_url, e2e_available."""

from __future__ import annotations

import os

import pytest


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
