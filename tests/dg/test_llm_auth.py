"""Unit tests for digigraph.llm_auth (per-request proxy-key + BYOK funnel).

Split from the former tests/dg/test_llm.py (#632 P2). These are the safety net
for the auth/credential funnel: they assert that the header parsers feed digillm's
override contextvars correctly and that DigiGraph's own ``(key, provider)`` BYOK
record is preserved. Client-side key resolution now lives in digillm and is
covered by digillm/tests/test_digillm.py.
"""

from __future__ import annotations

import pytest
from digillm import get_byok as digillm_get_byok
from digillm import get_proxy_key as digillm_get_proxy_key

from digigraph.llm_auth import (
    get_byok_override,
    pop_byok,
    pop_lite_llm_proxy,
    push_byok_header,
    push_lite_llm_proxy_header,
)


class _Headers:
    """Case-insensitive header mapping mirroring Starlette's request.headers."""

    def __init__(self, d: dict[str, str]) -> None:
        self._d = {k.lower(): v for k, v in d.items()}

    def get(self, name: str) -> str | None:
        return self._d.get(name.lower())


class _Req:
    def __init__(self, headers: _Headers) -> None:
        self.headers = headers


def _byok_request(key: str = "", provider: str = "openai") -> _Req:
    h: dict[str, str] = {}
    if key:
        h["x-byok-key"] = key
    if provider:
        h["x-byok-provider"] = provider
    return _Req(_Headers(h))


def _proxy_request(value: str | None) -> _Req:
    h: dict[str, str] = {}
    if value is not None:
        h["x-litellm-proxy-key"] = value
    return _Req(_Headers(h))


@pytest.mark.unit
class TestLiteLlmProxyHeader:
    """X-LiteLLM-Proxy-Key parsing → digillm proxy-key override."""

    def test_header_feeds_digillm_proxy_key(self) -> None:
        tok = push_lite_llm_proxy_header(_proxy_request("sk-header"))
        try:
            assert digillm_get_proxy_key() == "sk-header"
        finally:
            pop_lite_llm_proxy(tok)
        assert digillm_get_proxy_key() is None

    def test_no_header_leaves_override_unset(self) -> None:
        tok = push_lite_llm_proxy_header(_proxy_request(None))
        try:
            assert digillm_get_proxy_key() is None
        finally:
            pop_lite_llm_proxy(tok)

    def test_whitespace_header_ignored(self) -> None:
        tok = push_lite_llm_proxy_header(_proxy_request("   "))
        try:
            assert digillm_get_proxy_key() is None
        finally:
            pop_lite_llm_proxy(tok)


@pytest.mark.unit
class TestByokHeader:
    """X-BYOK-Key / X-BYOK-Provider lifecycle + digillm BYOK funnel."""

    def test_no_header_gives_none(self) -> None:
        tok = push_byok_header(_byok_request())
        try:
            assert get_byok_override() is None
            assert digillm_get_byok() is None
        finally:
            pop_byok(tok)

    def test_openai_key_stored(self) -> None:
        tok = push_byok_header(_byok_request(key="sk-test123", provider="openai"))
        try:
            result = get_byok_override()
            assert result is not None
            key, provider = result
            assert key == "sk-test123"
            assert provider == "openai"
        finally:
            pop_byok(tok)

    def test_anthropic_key_stored(self) -> None:
        tok = push_byok_header(_byok_request(key="sk-ant-testkey", provider="anthropic"))
        try:
            result = get_byok_override()
            assert result is not None
            key, provider = result
            assert key == "sk-ant-testkey"
            assert provider == "anthropic"
        finally:
            pop_byok(tok)

    def test_pop_clears_override(self) -> None:
        tok = push_byok_header(_byok_request(key="sk-abc", provider="openai"))
        pop_byok(tok)
        assert get_byok_override() is None
        assert digillm_get_byok() is None

    def test_openai_byok_feeds_digillm(self) -> None:
        """OpenAI BYOK → digillm BYOK override (direct api.openai.com client)."""
        tok = push_byok_header(_byok_request(key="sk-byok-key", provider="openai"))
        try:
            byok = digillm_get_byok()
            assert byok is not None
            key, base_url = byok
            assert key == "sk-byok-key"
            assert base_url == "https://api.openai.com/v1"
        finally:
            pop_byok(tok)
        assert digillm_get_byok() is None

    def test_anthropic_byok_does_not_feed_digillm(self) -> None:
        """Anthropic BYOK is stored on DigiGraph's contextvar but NOT wired into the OpenAI client.

        It falls through to the env-configured credentials, matching legacy behavior.
        """
        tok = push_byok_header(_byok_request(key="sk-ant-xyz", provider="anthropic"))
        try:
            assert get_byok_override() == ("sk-ant-xyz", "anthropic")
            assert digillm_get_byok() is None
        finally:
            pop_byok(tok)
