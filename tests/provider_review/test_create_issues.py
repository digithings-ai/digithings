# tests/provider_review/test_create_issues.py
"""Unit tests for scripts/provider_review/create_issues.py."""
from __future__ import annotations

import pytest

from scripts.provider_review.create_issues import DEDUP_KEY_FORMAT, is_duplicate


@pytest.mark.unit
def test_is_duplicate_same_provider_trigger():
    """Returns True when an open issue body contains the same dedup key."""
    finding = {"provider": "gemini", "trigger": "quota_drop"}
    key = DEDUP_KEY_FORMAT.format(**finding)
    open_issues = [{"number": 1, "title": "...", "body": f"<!-- dedup-key: {key} -->"}]
    assert is_duplicate(finding, open_issues) is True


@pytest.mark.unit
def test_is_duplicate_different_trigger():
    """Returns False when same provider has a different trigger in open issues."""
    finding = {"provider": "gemini", "trigger": "better_free"}
    open_issues = [
        {"number": 1, "title": "...", "body": "<!-- dedup-key: gemini:quota_drop -->"}
    ]
    assert is_duplicate(finding, open_issues) is False


@pytest.mark.unit
def test_is_duplicate_no_open_issues():
    """Returns False when there are no open issues at all."""
    finding = {"provider": "groq", "trigger": "model_deprecated"}
    assert is_duplicate(finding, []) is False


@pytest.mark.unit
def test_is_duplicate_none_body():
    """Returns False when an open issue has a None body (edge case)."""
    finding = {"provider": "gemini", "trigger": "quota_drop"}
    open_issues = [{"number": 1, "title": "...", "body": None}]
    assert is_duplicate(finding, open_issues) is False
