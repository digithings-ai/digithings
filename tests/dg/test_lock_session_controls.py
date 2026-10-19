"""DIG-1210: a locked tenant never exposes the session control tools."""

from __future__ import annotations

import pytest
from digigraph.graph.research import LOCKED_SESSION_TOOLS, _tool_def_name

pytestmark = pytest.mark.unit


def test_locked_session_tools_cover_model_mcp_and_toggles() -> None:
    assert LOCKED_SESSION_TOOLS == frozenset(
        {"session_set_model", "session_upsert_mcp", "session_remove_mcp", "session_toggle_tool"}
    )


def test_tool_def_name_reads_dict_forms_and_objects() -> None:
    assert _tool_def_name({"type": "function", "function": {"name": "digisearch"}}) == "digisearch"
    assert _tool_def_name({"name": "session_set_model"}) == "session_set_model"

    class Tool:
        name = "vault_search_notes"

    assert _tool_def_name(Tool()) == "vault_search_notes"


def test_filter_removes_only_session_controls() -> None:
    tools = [
        {"type": "function", "function": {"name": "digisearch"}},
        {"type": "function", "function": {"name": "session_set_model"}},
        {"type": "function", "function": {"name": "ticket_search_tickets"}},
        {"type": "function", "function": {"name": "session_toggle_tool"}},
    ]
    kept = [t for t in tools if _tool_def_name(t) not in LOCKED_SESSION_TOOLS]
    assert [_tool_def_name(t) for t in kept] == ["digisearch", "ticket_search_tickets"]
