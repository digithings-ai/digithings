"""The root conftest's paid-LLM guard (2026-10-21): no test may reach a paid API."""

from __future__ import annotations

import os
import socket

import pytest

import conftest as root_conftest

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "host",
    [
        "api.cheaperinference.com",
        "API.CheaperInference.com.",
        b"openrouter.ai",
        "api.openai.com",
        "generativelanguage.googleapis.com",
        "api.deepseek.com",
    ],
)
def test_paid_hosts_are_recognised(host: object) -> None:
    assert root_conftest.is_paid_llm_host(host)


@pytest.mark.parametrize(
    "host", ["127.0.0.1", "localhost", "example.com", "notcheaperinference.com", None, 443]
)
def test_other_hosts_are_not(host: object) -> None:
    assert not root_conftest.is_paid_llm_host(host)


def test_resolving_a_paid_host_is_blocked_this_session() -> None:
    if root_conftest.live_llm_allowed():
        pytest.skip(f"{root_conftest.ALLOW_LIVE_ENV} is set")
    with pytest.raises(OSError, match="live LLM call blocked"):
        socket.getaddrinfo("api.cheaperinference.com", 443)


def test_loopback_still_resolves() -> None:
    assert socket.getaddrinfo("127.0.0.1", 80)


def test_cheaperinference_key_is_absent_this_session() -> None:
    if root_conftest.live_llm_allowed():
        pytest.skip(f"{root_conftest.ALLOW_LIVE_ENV} is set")
    assert not (os.environ.get("CHEAPERINFERENCE_API_KEY") or "").strip()


def test_opt_in_values() -> None:
    allow = root_conftest.ALLOW_LIVE_ENV
    assert root_conftest.live_llm_allowed({allow: "1"})
    assert root_conftest.live_llm_allowed({allow: "true"})
    assert not root_conftest.live_llm_allowed({allow: "0"})
    assert not root_conftest.live_llm_allowed({})
