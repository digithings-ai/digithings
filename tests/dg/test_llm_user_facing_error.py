"""User-facing LLM / provider errors (sanitized; no Compose DNS)."""

from __future__ import annotations

import pytest
from digigraph.llm_errors import (
    LLM_ERROR,
    provider_error_text,
    sanitize_user_facing_error,
    user_facing_llm_failure,
)


@pytest.mark.unit
def test_sanitize_strips_compose_dns_and_secrets() -> None:
    raw = "failed http://digisearch:8002 with api_key=sk-abcdefghijklmnop"
    out = sanitize_user_facing_error(raw)
    assert "digisearch" not in out
    assert "sk-" not in out
    assert "[internal host]" in out
    assert "[redacted]" in out


@pytest.mark.unit
def test_provider_error_text_extracts_litellm_dict() -> None:
    exc = RuntimeError(
        "Error code: 404 - {'error': {'message': 'No endpoints found for this model.', 'code': 404}}"
    )
    assert provider_error_text(exc) == "No endpoints found for this model."


@pytest.mark.unit
def test_user_facing_llm_failure_surfaces_api_message() -> None:
    exc = RuntimeError(
        "Error code: 404 - {'error': {'message': 'No endpoints found for openai/gpt-oss-20b:free.'}}"
    )
    message, code, detail = user_facing_llm_failure(exc)
    assert code == LLM_ERROR
    assert "Research failed" not in message
    assert "No endpoints found" in message
    assert "digisearch" not in message
    if detail:
        assert "digisearch" not in detail
