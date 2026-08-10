"""Typed LLM / quota errors for digigraph → digichat handoff.

Stable machine codes (never change without a digichat contract bump):

- ``free_quota_exceeded`` — free-tier provider rate limit / RPD; digichat opens BYOK.
- ``rate_limit`` — generic provider rate limit outside free mode.
"""

from __future__ import annotations

FREE_QUOTA_EXCEEDED = "free_quota_exceeded"
RATE_LIMIT = "rate_limit"

_RATE_LIMIT_MARKERS = (
    "rate limit",
    "rate_limit",
    "ratelimit",
    "too many requests",
    "requests per day",
    "rpd",
    "free-models-per-day",
    "free tier",
    "quota exceeded",
    "quota_exceeded",
    "429",
)


def is_rate_limit_error(exc: BaseException) -> bool:
    """True when *exc* looks like a provider rate-limit / free-quota failure."""
    try:
        from openai import RateLimitError

        if isinstance(exc, RateLimitError):
            return True
    except ImportError:
        pass
    status = getattr(exc, "status_code", None)
    if status == 429:
        return True
    msg = str(exc).lower()
    return any(marker in msg for marker in _RATE_LIMIT_MARKERS)


def classify_llm_error(exc: BaseException, *, llm_mode: str | None = None) -> str | None:
    """Return a stable error code for *exc*, or ``None`` when unclassified.

    When ``llm_mode`` is ``free`` and the provider rate-limited the free path,
    returns :data:`FREE_QUOTA_EXCEEDED` so digichat can open the BYOK wizard.
    """
    if not is_rate_limit_error(exc):
        return None
    mode = (llm_mode or "").strip().lower()
    if not mode:
        # Lazy import avoids cycles with model_config → llm_auth.
        from digigraph.model_config import get_llm_mode

        mode = get_llm_mode()
    if mode == "free":
        return FREE_QUOTA_EXCEEDED
    return RATE_LIMIT


def free_quota_message() -> str:
    """User-facing copy for :data:`FREE_QUOTA_EXCEEDED` (no secrets)."""
    return (
        "Free-tier model quota is exhausted. Add your own API key (BYOK) to continue, "
        "or wait for the free quota to reset."
    )


def rate_limit_message() -> str:
    """User-facing copy for :data:`RATE_LIMIT`."""
    return "Rate limit reached. Please wait a moment and try again."
