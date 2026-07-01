"""Unit tests for ToolExposureMode: progressive tool discovery (issue #404)."""

from __future__ import annotations

import inspect

import pytest

from digigraph.orchestration.registry import (
    ToolContext,
    ToolExposureMode,
    get_tools,
    register_skill,
    register_tool,
)
from digigraph.orchestration.registry import _skills as _reg_skills
from digigraph.orchestration.registry import _tools as _reg_tools

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TOOL_A = "__unit_exposure_tool_a__"
_TOOL_B = "__unit_exposure_tool_b__"
_SKILL_ID = "__unit_exposure_skill__"


def _make_context() -> ToolContext:
    return ToolContext(
        session_id=None,
        run_data_dir=None,
        index_name="test",
        index_config={},
        state={},
    )


def _make_schema(name: str, description: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"},
                },
                "required": ["query"],
            },
        },
    }


def _handler(args: dict, ctx: object) -> str:
    return "ok"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _cleanup_registry():
    """Remove probe tools/skills before and after each test to avoid leaking global state."""
    for key in (_TOOL_A, _TOOL_B):
        _reg_tools.pop(key, None)
    _reg_skills.pop(_SKILL_ID, None)

    yield

    for key in (_TOOL_A, _TOOL_B):
        _reg_tools.pop(key, None)
    _reg_skills.pop(_SKILL_ID, None)


@pytest.fixture()
def registered_tools():
    """Register two probe tools and a skill bundling them."""
    register_tool(_TOOL_A, _make_schema(_TOOL_A, "Search the knowledge base"), _handler)
    register_tool(_TOOL_B, _make_schema(_TOOL_B, "Fetch a document by URL"), _handler)
    register_skill(_SKILL_ID, [_TOOL_A, _TOOL_B])
    return [_TOOL_A, _TOOL_B]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_default_mode_is_detailed():
    """Default mode must be DETAILED for backwards compatibility."""
    assert ToolExposureMode.DETAILED == ToolExposureMode("detailed")
    sig = inspect.signature(get_tools)
    default = sig.parameters["mode"].default
    assert default is ToolExposureMode.DETAILED


@pytest.mark.unit
def test_detailed_mode_returns_full_schema(registered_tools):
    """DETAILED mode returns OpenAI tool dicts with full JSON schema."""
    ctx = _make_context()
    result = get_tools([_SKILL_ID], ctx, mode=ToolExposureMode.DETAILED)

    assert isinstance(result, list)
    assert len(result) == 2

    for td in result:
        assert isinstance(td, dict)
        assert "type" in td
        assert "function" in td
        fn = td["function"]
        assert "name" in fn
        assert "description" in fn
        assert "parameters" in fn
        # Full schema includes properties
        assert "properties" in fn["parameters"]


@pytest.mark.unit
def test_summary_mode_returns_one_liners(registered_tools):
    """SUMMARY mode returns 'tool_name: description' strings, not dicts."""
    ctx = _make_context()
    result = get_tools([_SKILL_ID], ctx, mode=ToolExposureMode.SUMMARY)

    assert isinstance(result, list)
    assert len(result) == 2

    for item in result:
        assert isinstance(item, str)
        # Must be a single line
        assert "\n" not in item
        # Must follow 'name: description' format
        assert ": " in item

    names = [line.split(": ")[0] for line in result]
    assert _TOOL_A in names
    assert _TOOL_B in names


@pytest.mark.unit
def test_summary_mode_content_matches_description(registered_tools):
    """SUMMARY strings must carry the tool's registered description."""
    ctx = _make_context()
    result = get_tools([_SKILL_ID], ctx, mode=ToolExposureMode.SUMMARY)

    summary_map = {line.split(": ", 1)[0]: line.split(": ", 1)[1] for line in result}
    assert summary_map[_TOOL_A] == "Search the knowledge base"
    assert summary_map[_TOOL_B] == "Fetch a document by URL"


@pytest.mark.unit
def test_detailed_mode_via_enum_string_value():
    """ToolExposureMode can be constructed from string values."""
    assert ToolExposureMode("summary") is ToolExposureMode.SUMMARY
    assert ToolExposureMode("detailed") is ToolExposureMode.DETAILED


@pytest.mark.unit
def test_summary_mode_empty_description():
    """SUMMARY mode handles a tool with no description gracefully (emits just the name)."""
    name = "__unit_exposure_no_desc__"
    _reg_tools.pop(name, None)
    skill_id = "__unit_exposure_no_desc_skill__"
    _reg_skills.pop(skill_id, None)
    try:
        schema = {
            "type": "function",
            "function": {
                "name": name,
                "parameters": {"type": "object", "properties": {}},
            },
        }
        register_tool(name, schema, _handler)
        register_skill(skill_id, [name])

        ctx = _make_context()
        result = get_tools([skill_id], ctx, mode=ToolExposureMode.SUMMARY)

        assert len(result) == 1
        assert isinstance(result[0], str)
        # No colon appended when description is absent
        assert result[0] == name
    finally:
        _reg_tools.pop(name, None)
        _reg_skills.pop(skill_id, None)


@pytest.mark.unit
def test_tool_exposure_mode_exported_from_orchestration_package():
    """ToolExposureMode must be importable from the orchestration package (for issue #401)."""
    from digigraph.orchestration import ToolExposureMode as _imported

    assert _imported is ToolExposureMode


@pytest.mark.unit
def test_detailed_mode_deduplicates_tools():
    """Tools appearing in multiple skills are included only once (existing behaviour, both modes)."""
    name = "__unit_exposure_dedup__"
    _reg_tools.pop(name, None)
    skill_a = "__unit_exposure_dedup_skill_a__"
    skill_b = "__unit_exposure_dedup_skill_b__"
    _reg_skills.pop(skill_a, None)
    _reg_skills.pop(skill_b, None)
    try:
        register_tool(name, _make_schema(name, "Dedup probe"), _handler)
        register_skill(skill_a, [name])
        register_skill(skill_b, [name])

        ctx = _make_context()
        result_detailed = get_tools([skill_a, skill_b], ctx, mode=ToolExposureMode.DETAILED)
        result_summary = get_tools([skill_a, skill_b], ctx, mode=ToolExposureMode.SUMMARY)

        assert len(result_detailed) == 1
        assert len(result_summary) == 1
    finally:
        _reg_tools.pop(name, None)
        _reg_skills.pop(skill_a, None)
        _reg_skills.pop(skill_b, None)
