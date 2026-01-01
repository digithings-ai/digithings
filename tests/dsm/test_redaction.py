"""Unit tests for digitrace.redaction."""

from __future__ import annotations

import pytest
from digitrace.redaction import PiiRedactor, default_redactor

pytestmark = pytest.mark.unit


def test_redacts_email() -> None:
    r = PiiRedactor()
    assert r.redact_text("contact user@example.com now") == "contact [REDACTED_EMAIL] now"


def test_redacts_api_key_prefixes() -> None:
    r = PiiRedactor()
    assert r.redact_text("key=sk-abc123def456789") == "key=[REDACTED_KEY]"
    assert r.redact_text("key=sk_abc123def456789") == "key=[REDACTED_KEY]"
    assert r.redact_text("key=dgk_live_deadbeef1234567") == "key=[REDACTED_KEY]"
    assert r.redact_text("key=dgk_test_cafebabe1234567") == "key=[REDACTED_KEY]"
    assert r.redact_text("key=lsv2_test_fake_key_value") == "key=[REDACTED_KEY]"


def test_redacts_phone_numbers() -> None:
    r = PiiRedactor()
    assert r.redact_text("call +1-415-555-0199") == "call [REDACTED_PHONE]"
    assert r.redact_text("tel (415) 555-0199") == "tel [REDACTED_PHONE]"
    assert r.redact_text("tel 415.555.0199") == "tel [REDACTED_PHONE]"
    assert r.redact_text("tel +442071838750") == "tel [REDACTED_PHONE]"


def test_clean_text_unchanged() -> None:
    r = PiiRedactor()
    assert r.redact_text("hello world") == "hello world"
    assert r.redact("hello world") == "hello world"


def test_non_string_values_passthrough() -> None:
    r = PiiRedactor()
    assert r.redact(42) == 42
    assert r.redact(None) is None
    assert r.redact(True) is True
    assert r.redact(3.14) == 3.14


def test_nested_dict_redaction() -> None:
    r = PiiRedactor()
    out = r.redact({"outer": {"email": "u@e.co"}})
    assert out == {"outer": {"email": "[REDACTED_EMAIL]"}}


def test_nested_list_and_tuple_redaction() -> None:
    r = PiiRedactor()
    assert r.redact(["u@e.co", 1, None]) == ["[REDACTED_EMAIL]", 1, None]
    assert r.redact(("sk-abcdefgh12345", "clean")) == ("[REDACTED_KEY]", "clean")


def test_mixed_payload() -> None:
    r = PiiRedactor()
    payload = {
        "messages": [
            {"role": "user", "content": "email me at jane@doe.com"},
            {"role": "assistant", "content": "sure, call +1-415-555-0199"},
        ],
        "meta": {"key": "sk-abcdefghij1234567", "safe": "hello"},
        "count": 3,
    }
    out = r.redact(payload)
    assert out["messages"][0]["content"] == "email me at [REDACTED_EMAIL]"
    assert out["messages"][1]["content"] == "sure, call [REDACTED_PHONE]"
    assert out["meta"]["key"] == "[REDACTED_KEY]"
    assert out["meta"]["safe"] == "hello"
    assert out["count"] == 3


def test_digi_pii_patterns_env_appends(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGI_PII_PATTERNS", r"TOP_SECRET_\w+,BADGE-\d{4}")
    r = PiiRedactor.from_env()
    assert r.redact_text("data TOP_SECRET_alpha tag") == "data [REDACTED] tag"
    assert r.redact_text("BADGE-4242 in lobby") == "[REDACTED] in lobby"
    # defaults still active
    assert r.redact_text("u@e.co") == "[REDACTED_EMAIL]"


def test_digi_pii_patterns_invalid_regex_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGI_PII_PATTERNS", "[unclosed,VALID_\\d+")
    r = PiiRedactor.from_env()
    assert r.redact_text("VALID_123 here") == "[REDACTED] here"


def test_digi_pii_patterns_empty_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGI_PII_PATTERNS", raising=False)
    r = PiiRedactor.from_env()
    assert r.rules == PiiRedactor().rules


def test_process_inputs_returns_dict() -> None:
    r = PiiRedactor()
    out = r.process_inputs({"email": "u@e.co"})
    assert out == {"email": "[REDACTED_EMAIL]"}


def test_process_outputs_handles_any() -> None:
    r = PiiRedactor()
    assert r.process_outputs("sk-abcdefghij12345") == "[REDACTED_KEY]"
    assert r.process_outputs({"x": "u@e.co"}) == {"x": "[REDACTED_EMAIL]"}


def test_default_redactor_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGI_PII_PATTERNS", r"ZZ_\d+")
    r = default_redactor()
    assert r.redact_text("ZZ_9 hidden") == "[REDACTED] hidden"


def test_sensitive_key_names_are_redacted_whole() -> None:
    r = PiiRedactor()
    out = r.redact(
        {
            "api_key": "sk-abcdefghij1234567",
            "openai_api_key": "opaque",
            "openaiApiKey": "camel",
            "authorization": "Bearer abc",
            "password": "hunter2",
            "nested": {"db_password": "swordfish"},
        }
    )
    assert out["api_key"] == "[REDACTED]"
    assert out["openai_api_key"] == "[REDACTED]"
    assert out["openaiApiKey"] == "[REDACTED]"
    assert out["authorization"] == "[REDACTED]"
    assert out["password"] == "[REDACTED]"
    assert out["nested"]["db_password"] == "[REDACTED]"


def test_token_counts_are_not_treated_as_secrets() -> None:
    r = PiiRedactor()
    out = r.redact(
        {
            "total_tokens": 18,
            "max_tokens": 512,
            "prompt_tokens": 11,
            "completion_tokens": 7,
            "token_count": 3,
        }
    )
    assert out == {
        "total_tokens": 18,
        "max_tokens": 512,
        "prompt_tokens": 11,
        "completion_tokens": 7,
        "token_count": 3,
    }


def test_long_document_is_summarised_to_hash_and_length() -> None:
    r = PiiRedactor(max_document_chars=10)
    out = r.redact("x" * 50)
    assert out.startswith("[DOCUMENT sha256:")
    assert out.endswith("chars:50]")
    assert "x" * 11 not in out


def test_document_summarisation_can_be_disabled() -> None:
    r = PiiRedactor(max_document_chars=None)
    assert r.redact("y" * 50) == "y" * 50


def test_document_threshold_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGI_PII_MAX_DOCUMENT_CHARS", "8")
    assert "[DOCUMENT" in default_redactor().redact("z" * 9)
    monkeypatch.setenv("DIGI_PII_MAX_DOCUMENT_CHARS", "0")
    assert default_redactor().max_document_chars is None
