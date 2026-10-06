"""Unit tests for the credential rules in digitrace.redaction (DIG-1653).

These exist because DIG-1639 leaked a Cloudflare OAuth ``refresh_token`` into a
Paperclip run transcript: the PII ruleset ran over that output and matched
nothing. An opaque OAuth token has no prefix to anchor on the way ``sk-`` does,
so credential *shapes* are their own ruleset.

Every value here is fake. Nothing in this file is, or ever was, a real
credential.
"""

from __future__ import annotations

import pytest
from digitrace.redaction import detect_credential_value, redact_credentials

pytestmark = pytest.mark.unit

# Fake shapes. The hex string is the canary shape; it is not a key.
FAKE_REFRESH_TOKEN = "6f1d0a4b8c2e97a35b10df74ec81aa20"  # 32 hex chars, generated
FAKE_JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJzdWIiOiJhZ2VudC0xIiwiZXhwIjoxNzAwMDAwMDAwfQ"
    ".kQ8vZ1nB3xW7yJ0mN5pR2tY9uI4oP6aS8dF1gH3jK"
)


def test_detects_refresh_token_assignment() -> None:
    line = f'refresh_token = "{FAKE_REFRESH_TOKEN}"'
    assert detect_credential_value(line) == "secret-assignment"


def test_detects_jwt() -> None:
    assert detect_credential_value(f"token: {FAKE_JWT}") == "jwt"


def test_detects_bearer_token() -> None:
    assert detect_credential_value("Authorization: Bearer abcdefghijklmnopqrstuvwxyz01") == (
        "bearer-token"
    )


def test_detects_pem_private_key_block() -> None:
    pem = "-----BEGIN PRIVATE KEY-----\nMIIBOgIBAAJBAK\n-----END PRIVATE KEY-----"
    assert detect_credential_value(pem) == "private-key-block"


def test_clean_text_is_not_a_detection() -> None:
    assert detect_credential_value("refresh the stack and deploy") is None
    assert detect_credential_value("") is None
    assert detect_credential_value("token rotation is quarterly") is None


@pytest.mark.parametrize(
    "line",
    [
        'token = "***"',
        'token = "xxxxxxxx"',
        "password: changeme",
        "password: ${PASSWORD_VAR}",
        'secret = "${SECRET:-default}"',
        "api_key = <your-api-key-here>",
        'client_secret = "replace-with-real-value"',
        "refresh_token = null",
        "refresh_token = none",
        'auth_token = "aaaaaaaaaaaaaaaaaaaa"',
    ],
)
def test_placeholder_values_are_not_detections(line: str) -> None:
    """A guard fixture, a config template and a runbook example must not trip the guard.

    This is the property that lets the credential guard name these values in a
    deny reason and lets ``redact_credentials`` be safe to run over a whole
    transcript: a masked value is not a secret.
    """
    assert detect_credential_value(line) is None


def test_redact_replaces_the_value_but_keeps_the_key() -> None:
    line = f'refresh_token = "{FAKE_REFRESH_TOKEN}"'
    out = redact_credentials(line)
    assert FAKE_REFRESH_TOKEN not in out
    assert out == 'refresh_token = "[REDACTED_CREDENTIAL]"'


def test_redact_preserves_placeholders() -> None:
    assert redact_credentials('token = "***"') == 'token = "***"'
    assert redact_credentials("password: changeme") == "password: changeme"


def test_redact_leaves_clean_text_untouched() -> None:
    assert redact_credentials("deploy the stack") == "deploy the stack"
    assert redact_credentials("") == ""


def test_default_patterns_are_unchanged_by_the_credential_rules() -> None:
    """The trace ruleset must not have been widened in place.

    Adding credential shapes to ``DEFAULT_PATTERNS`` would silently change every
    existing span payload, which is why they are a separate ruleset.
    """
    from digitrace.redaction import DEFAULT_PATTERNS

    replacements = {rule.replacement for rule in DEFAULT_PATTERNS}
    assert "[REDACTED_CREDENTIAL]" not in replacements
    assert len(DEFAULT_PATTERNS) == 3
