"""Registry: duplicate registration guard and tool manifest."""

from __future__ import annotations

import digigraph.skills  # noqa: F401  # side effect: register built-in orchestrator tools

import pytest

from digigraph.orchestration import list_registered_tools_detailed, list_tool_names
from digigraph.orchestration import registry as reg


@pytest.mark.unit
def test_register_tool_rejects_duplicate() -> None:
    name = "__unit_duplicate_probe__"
    reg._tools.pop(name, None)

    def _handler(args: dict, ctx: object) -> str:
        return "ok"

    schema: dict = {
        "type": "function",
        "function": {"name": name, "description": "probe", "parameters": {"type": "object", "properties": {}}},
    }
    reg.register_tool(name, schema, _handler)
    with pytest.raises(ValueError, match="already registered"):
        reg.register_tool(name, schema, _handler)
    reg._tools.pop(name, None)


@pytest.mark.unit
def test_list_registered_tools_detailed_covers_registered_names() -> None:
    manifest = list_registered_tools_detailed()
    names_m = {e["name"] for e in manifest}
    names_plain = set(list_tool_names())
    assert names_m == names_plain
    for entry in manifest:
        assert "tags" in entry
        assert "dynamic_schema" in entry
        assert isinstance(entry["tags"], list)
