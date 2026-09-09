"""Typed LLM / quota errors for digigraph → digichat handoff.

Stable machine codes (never change without a digichat contract bump):

- ``free_quota_exceeded`` — free-tier provider rate limit / RPD; digichat opens BYOK.
- ``rate_limit`` — generic provider rate limit outside free mode.
- ``llm_error`` — classified provider/API failure (sanitized message; optional detail).
"""

from __future__ import annotations

import ast
import json
import re

FREE_QUOTA_EXCEEDED = "free_quota_exceeded"
RATE_LIMIT = "rate_limit"
LLM_ERROR = "llm_error"

_MAX_MESSAGE = 280
_MAX_DETAIL = 2000

# Compose DNS, loopback, and RFC1918 — never stream these to embed clients.
_INTERNAL_HOST_RE = re.compile(
    r"(?i)(?:https?://)?(?:"
    r"host\.docker\.internal|"
    r"(?:digisearch|digiquant|digigraph|digikey|digivault|litellm)(?::\d+)?|"
    r"[a-z0-9._-]+\.(?:internal|local|lan)(?::\d+)?|"
    r"localhost(?::\d+)?|"
    r"127\.\d+\.\d+\.\d+(?::\d+)?|"
    r"10\.\d+\.\d+\.\d+(?::\d+)?|"
    r"192\.168\.\d+\.\d+(?::\d+)?|"
    r"172\.(?:1[6-9]|2\d|3[0-1])\.\d+\.\d+(?::\d+)?"
    r")"
)
_SECRET_RE = re.compile(
    r"(?i)\b(?:sk-[A-Za-z0-9_-]{10,}|dgk_[A-Za-z0-9_]+|Bearer\s+\S+|"
    r"api[_-]?key\s*[:=]\s*\S+)"
)

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


def sanitize_user_facing_error(text: str, *, limit: int = _MAX_DETAIL) -> str:
    """Strip secrets and internal hostnames from provider/exception text."""
    cleaned = _SECRET_RE.sub("[redacted]", text or "")
    cleaned = _INTERNAL_HOST_RE.sub("[internal host]", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) > limit:
        return cleaned[: limit - 1].rstrip() + "…"
    return cleaned


def _message_from_mapping(obj: object) -> str | None:
    if not isinstance(obj, dict):
        return None
    err = obj.get("error")
    if isinstance(err, dict) and isinstance(err.get("message"), str) and err["message"].strip():
        return str(err["message"]).strip()
    if isinstance(err, str) and err.strip():
        return err.strip()
    msg = obj.get("message")
    if isinstance(msg, str) and msg.strip():
        return msg.strip()
    return None


def _mapping_from_exc_text(text: str) -> dict | None:
    start = text.find("{")
    if start < 0:
        return None
    snippet = text[start:]
    try:
        obj = ast.literal_eval(snippet)
    except (ValueError, SyntaxError):
        try:
            obj = json.loads(snippet)
        except (ValueError, TypeError):
            return None
    return obj if isinstance(obj, dict) else None


def provider_error_text(exc: BaseException) -> str:
    """Best-effort provider/API message from an LLM exception (pre-sanitize)."""
    for attr in ("body", "response"):
        raw = getattr(exc, attr, None)
        json_fn = getattr(raw, "json", None)
        if callable(json_fn):
            try:
                raw = json_fn()
            except Exception:
                raw = None
        found = _message_from_mapping(raw)
        if found:
            return found
    msg_attr = getattr(exc, "message", None)
    if isinstance(msg_attr, str) and msg_attr.strip():
        mapped = _mapping_from_exc_text(msg_attr)
        found = _message_from_mapping(mapped) if mapped else None
        if found:
            return found
        if msg_attr.strip() != str(exc).strip():
            return msg_attr.strip()
    text = str(exc)
    mapped = _mapping_from_exc_text(text)
    found = _message_from_mapping(mapped)
    if found:
        return found
    return text


def user_facing_llm_failure(exc: BaseException) -> tuple[str, str, str | None]:
    """Return ``(message, error_code, detail)`` for an LLM / provider failure.

    ``detail`` is a longer sanitized dump for the embed error disclosure; omit
    when it would duplicate ``message``. Internal hostnames and secrets never
    appear in either field.
    """
    code = classify_llm_error(exc)
    if code == FREE_QUOTA_EXCEEDED:
        return free_quota_message(), FREE_QUOTA_EXCEEDED, None
    if code == RATE_LIMIT:
        return rate_limit_message(), RATE_LIMIT, None

    raw = provider_error_text(exc)
    lower = raw.lower()
    if "context window exceeds limit" in lower or "context_length_exceeded" in lower:
        return (
            "The conversation or context is too long for this model. "
            "Try starting a new chat or shortening your question.",
            LLM_ERROR,
            sanitize_user_facing_error(raw) or None,
        )
    if "invalid api key" in lower or "authentication" in lower or "401" in lower:
        return (
            "The model provider rejected this request (authentication failed).",
            LLM_ERROR,
            sanitize_user_facing_error(raw) or None,
        )

    message = sanitize_user_facing_error(raw, limit=_MAX_MESSAGE)
    if not message:
        message = "The model request failed."
    detail_full = sanitize_user_facing_error(raw, limit=_MAX_DETAIL)
    detail = detail_full if detail_full and detail_full != message else None
    return message, LLM_ERROR, detail
