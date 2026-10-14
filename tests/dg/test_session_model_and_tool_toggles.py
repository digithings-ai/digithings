"""Session house-model pick and per-tool disables (OCC settings)."""

from __future__ import annotations

from unittest.mock import patch

from digigraph.tool_policy import expand_disabled_tool_tokens

from digigraph import model_config


def test_house_model_only_binds_allowlisted(monkeypatch) -> None:
    monkeypatch.setenv("DIGI_SESSION_MODEL_ALLOWLIST", "a/one, b/two")
    with patch.object(model_config, "operator_default_model", return_value="house/default"):
        tok = model_config.push_house_model("b/two")
        try:
            assert model_config.get_model_for_mode() == "b/two"
        finally:
            model_config.pop_house_model(tok)
        tok = model_config.push_house_model("evil/model")
        try:
            assert model_config.get_house_model_override() is None
            assert model_config.get_model_for_mode() == "house/default"
        finally:
            model_config.pop_house_model(tok)


def test_house_model_ignored_without_allowlist(monkeypatch) -> None:
    monkeypatch.delenv("DIGI_SESSION_MODEL_ALLOWLIST", raising=False)
    tok = model_config.push_house_model("a/one")
    try:
        assert model_config.get_house_model_override() is None
    finally:
        model_config.pop_house_model(tok)


def test_exact_registered_tool_name_disables_only_that_tool() -> None:
    with patch(
        "digigraph.orchestration.registry.list_tool_names",
        return_value=["digivault_search_tag", "digivault_backlinks"],
    ):
        assert expand_disabled_tool_tokens(["digivault_search_tag", "nope"]) == frozenset(
            {"digivault_search_tag"}
        )
