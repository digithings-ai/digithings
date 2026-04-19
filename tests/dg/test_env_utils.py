"""Unit tests for digigraph.env_utils.resolve_env_refs."""

from __future__ import annotations

import pytest

from digigraph.env_utils import resolve_env_refs


# ---------------------------------------------------------------------------
# ${VAR} — present in environment
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_var_present_returns_env_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """Given ${MY_VAR} and MY_VAR set, When resolved, Then the value replaces the reference."""
    monkeypatch.setenv("MY_VAR", "hello")
    result = resolve_env_refs("prefix_${MY_VAR}_suffix")
    assert result == "prefix_hello_suffix"


# ---------------------------------------------------------------------------
# ${VAR} — absent, no errors list (silent mode → "")
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_var_absent_silent_returns_empty_string(monkeypatch: pytest.MonkeyPatch) -> None:
    """Given ${UNSET_VAR} with no default and errors=None, When resolved, Then returns empty string silently."""
    monkeypatch.delenv("UNSET_VAR", raising=False)
    result = resolve_env_refs("${UNSET_VAR}")
    assert result == ""


@pytest.mark.unit
def test_var_absent_silent_no_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    """Given errors=None (default), When a var is missing, Then no errors list is mutated."""
    monkeypatch.delenv("UNSET_VAR2", raising=False)
    # Just confirm no exception is raised and result is ""
    result = resolve_env_refs("${UNSET_VAR2}")
    assert result == ""


# ---------------------------------------------------------------------------
# ${VAR} — absent, with errors list (tracked mode → preserve literal + append error)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_var_absent_tracked_preserves_literal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Given ${UNSET_TRACK} absent and errors list provided, When resolved, Then literal ref is preserved."""
    monkeypatch.delenv("UNSET_TRACK", raising=False)
    errors: list[str] = []
    result = resolve_env_refs("${UNSET_TRACK}", errors=errors)
    assert "${UNSET_TRACK}" in result


@pytest.mark.unit
def test_var_absent_tracked_appends_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Given ${UNSET_TRACK} absent and errors list provided, When resolved, Then error referencing the var is appended."""
    monkeypatch.delenv("UNSET_TRACK2", raising=False)
    errors: list[str] = []
    resolve_env_refs("${UNSET_TRACK2}", errors=errors)
    assert len(errors) == 1
    assert "UNSET_TRACK2" in errors[0]
    assert "unresolved" in errors[0]


# ---------------------------------------------------------------------------
# ${VAR:-default} — env set: env wins
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_var_with_default_env_set_returns_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Given ${MY_VAR:-fallback} and MY_VAR set, When resolved, Then env value wins over default."""
    monkeypatch.setenv("MY_VAR2", "from-env")
    result = resolve_env_refs("${MY_VAR2:-fallback}")
    assert result == "from-env"


# ---------------------------------------------------------------------------
# ${VAR:-default} — env absent: default wins
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_var_with_default_env_absent_returns_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Given ${MISSING:-my-default} and MISSING unset, When resolved, Then default value is used."""
    monkeypatch.delenv("MISSING", raising=False)
    result = resolve_env_refs("${MISSING:-my-default}")
    assert result == "my-default"


@pytest.mark.unit
def test_var_with_default_env_absent_no_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Given ${MISSING2:-fallback} with errors list and MISSING2 unset, When resolved, Then no error appended."""
    monkeypatch.delenv("MISSING2", raising=False)
    errors: list[str] = []
    result = resolve_env_refs("${MISSING2:-fallback}", errors=errors)
    assert result == "fallback"
    assert errors == []


# ---------------------------------------------------------------------------
# Nested strings within dict / list
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_nested_dict_resolved(monkeypatch: pytest.MonkeyPatch) -> None:
    """Given a nested dict containing ${VAR} refs, When resolved, Then all refs are substituted."""
    monkeypatch.setenv("SVC_HOST", "myhost")
    value = {"services": {"url": "http://${SVC_HOST}:8000"}, "other": 42}
    result = resolve_env_refs(value)
    assert result == {"services": {"url": "http://myhost:8000"}, "other": 42}


@pytest.mark.unit
def test_nested_list_resolved(monkeypatch: pytest.MonkeyPatch) -> None:
    """Given a list containing ${VAR} refs, When resolved, Then all list elements are substituted."""
    monkeypatch.setenv("TAG", "prod")
    value = ["item_${TAG}", "plain", 99]
    result = resolve_env_refs(value)
    assert result == ["item_prod", "plain", 99]


# ---------------------------------------------------------------------------
# Non-string passthrough (int, None)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_non_string_passthrough_int() -> None:
    """Given an integer value, When resolved, Then it is returned unchanged."""
    assert resolve_env_refs(42) == 42  # type: ignore[arg-type]


@pytest.mark.unit
def test_non_string_passthrough_none() -> None:
    """Given None, When resolved, Then None is returned unchanged."""
    assert resolve_env_refs(None) is None  # type: ignore[arg-type]
