"""Unit tests for digisearch.core.filter_validator — OData injection prevention."""

from __future__ import annotations

import pytest

from digisearch.core.filter_validator import validate_odata_filter


# ---------------------------------------------------------------------------
# Valid filters — must pass through unchanged
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestValidFilters:
    @pytest.mark.parametrize("filter_str", [
        "sourceType eq 'EXCHANGE'",
        "score ge 0.5",
        "createdAt le '2024-01-01T00:00:00Z'",
        "status ne 'deleted'",
        "priority gt 3",
        "count lt 100",
        "field eq 'value' and other ne 'x'",
        "a eq 1 or b eq 2",
        "not (status eq 'inactive')",
        "items/any(i: i/type eq 'pdf')",
        "tags/all(t: t/active eq true)",
        "field in ('a', 'b', 'c')",
        "price add 10 ge 100",
        "price sub 5 lt 50",
        "qty mul 2 gt 10",
        "total div 3 le 7",
        "index mod 2 eq 0",
    ])
    def test_valid_filter_passes_through(self, filter_str: str) -> None:
        result = validate_odata_filter(filter_str)
        assert result == filter_str

    def test_empty_string_passes(self) -> None:
        assert validate_odata_filter("") == ""

    def test_whitespace_only_passes(self) -> None:
        result = validate_odata_filter("   ")
        assert result == "   "

    def test_returns_exact_input_unchanged(self) -> None:
        f = "field eq 'hello world'"
        assert validate_odata_filter(f) is f  # same object


# ---------------------------------------------------------------------------
# Blocked patterns — must raise ValueError
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestBlockedPatterns:
    @pytest.mark.parametrize("malicious", [
        "exec(import os)",
        "eval('__import__(\"os\")')",
        "system('rm -rf /')",
        "__class__.__subclasses__()",
        "__import__('os').system('ls')",
        "<script>alert(1)</script>",
        "javascript:alert(1)",
        "data:text/html,<h1>XSS</h1>",
        "EXEC(SELECT 1)",
        "EVAL(something)",
    ])
    def test_blocked_pattern_raises(self, malicious: str) -> None:
        with pytest.raises(ValueError, match="blocked pattern|unsupported"):
            validate_odata_filter(malicious)

    def test_blocked_pattern_error_includes_filter(self) -> None:
        with pytest.raises(ValueError) as exc_info:
            validate_odata_filter("exec(bad)")
        assert "exec" in str(exc_info.value).lower() or "blocked" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Unsupported characters — must raise ValueError
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestUnsupportedCharacters:
    @pytest.mark.parametrize("bad_char_filter", [
        "field eq 'value'; DROP TABLE users",
        "field eq `backtick`",
        "field eq value\x00null",
        "field eq value\ninjected",
        "field eq value\rinjected",
        "field ~ 'pattern'",
        "field ^ 'value'",
        "field | 'value'",
        "field & 'value'",
        "{\"$where\": \"this\"}",
    ])
    def test_unsupported_chars_raises(self, bad_char_filter: str) -> None:
        with pytest.raises(ValueError):
            validate_odata_filter(bad_char_filter)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestEdgeCases:
    def test_very_long_valid_filter(self) -> None:
        # Long but valid OData filter
        parts = [f"field{i} eq 'value{i}'" for i in range(20)]
        long_filter = " or ".join(parts)
        result = validate_odata_filter(long_filter)
        assert result == long_filter

    def test_unicode_letters_in_values(self) -> None:
        # Word chars include unicode in Python re
        result = validate_odata_filter("name eq 'München'")
        assert result == "name eq 'München'"

    def test_numeric_values(self) -> None:
        result = validate_odata_filter("price ge 3.14")
        assert result == "price ge 3.14"

    def test_iso_date_in_filter(self) -> None:
        result = validate_odata_filter("date ge '2024-01-01T00:00:00Z'")
        assert result == "date ge '2024-01-01T00:00:00Z'"

    def test_nested_navigation_property(self) -> None:
        result = validate_odata_filter("address/city eq 'Berlin'")
        assert result == "address/city eq 'Berlin'"
