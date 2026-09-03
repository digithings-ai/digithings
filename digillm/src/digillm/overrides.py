"""Per-request credential overrides for the default digillm client path."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from contextvars import ContextVar

_proxy_key_override: ContextVar[str | None] = ContextVar("digillm_proxy_key_override", default=None)
_byok_override: ContextVar[tuple[str, str] | None] = ContextVar(
    "digillm_byok_override", default=None
)


def set_proxy_key(token: str | None) -> object:
    """Set the per-request proxy/bearer key override; return a reset token."""
    val = token.strip() if token else None
    return _proxy_key_override.set(val)


def reset_proxy_key(token: object) -> None:
    """Restore the proxy-key override to the value before :func:`set_proxy_key`."""
    _proxy_key_override.reset(token)  # type: ignore[arg-type]


def get_proxy_key() -> str | None:
    """Return the active per-request proxy-key override, or ``None``."""
    return _proxy_key_override.get()


def set_byok(api_key: str, base_url: str = "https://api.openai.com/v1") -> object:
    """Set a per-request BYOK ``(api_key, base_url)`` override; return a reset token."""
    val: tuple[str, str] | None = (api_key, base_url) if api_key else None
    return _byok_override.set(val)


def reset_byok(token: object) -> None:
    """Restore the BYOK override to the value before :func:`set_byok`."""
    _byok_override.reset(token)  # type: ignore[arg-type]


def get_byok() -> tuple[str, str] | None:
    """Return the active per-request BYOK ``(api_key, base_url)`` override, or ``None``."""
    return _byok_override.get()


def clear_byok() -> None:
    """Drop the inherited BYOK override from a copied worker context."""
    _byok_override.set(None)


@contextlib.contextmanager
def proxy_key(token: str | None) -> Iterator[None]:
    """Set the proxy-key override for the duration of the block."""
    tok = set_proxy_key(token)
    try:
        yield
    finally:
        reset_proxy_key(tok)


@contextlib.contextmanager
def byok(api_key: str, base_url: str = "https://api.openai.com/v1") -> Iterator[None]:
    """Set the BYOK override for the duration of the block."""
    tok = set_byok(api_key, base_url)
    try:
        yield
    finally:
        reset_byok(tok)
