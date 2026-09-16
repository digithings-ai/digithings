"""Session preference tools (#3736, #4218)."""

from __future__ import annotations

import pytest
from digigraph.orchestration import builtin as _  # noqa: F401
from digigraph.orchestration.registry import ToolContext, execute, get_tools
from digigraph.orchestration.session_prefs_tools import (
    SESSION_SET_THINKING,
    SESSION_SET_THINKING_TOOL,
    SESSION_SET_VIEW,
    SESSION_SET_VIEW_TOOL,
    SESSION_TOOL_NAMES,
)


def _ctx() -> ToolContext:
    return ToolContext(
        session_id="s",
        run_data_dir=None,
        index_name="default",
        index_config={},
        state={},
    )


def _session_tool_names(ctx: ToolContext) -> set[str]:
    names: set[str] = set()
    for t in get_tools(["session"], ctx):
        fn = t.get("function") if isinstance(t, dict) else None
        if isinstance(fn, dict) and fn.get("name"):
            names.add(fn["name"])
    return names


@pytest.mark.unit
def test_session_tools_echo_args() -> None:
    ctx = _ctx()
    out = execute("session_set_language", {"code": "nl"}, ctx)
    assert out == {"ok": True, "session_prefs": {"code": "nl"}}
    assert "session_set_language" in SESSION_TOOL_NAMES
    for name in SESSION_TOOL_NAMES:
        execute(name, {"id": "linear"}, ctx)


@pytest.mark.unit
def test_session_set_view_registered_in_session_skill() -> None:
    """#4218: the merged digichat view feature needs the server tool to exist."""
    assert SESSION_SET_VIEW in SESSION_TOOL_NAMES
    assert SESSION_SET_VIEW in _session_tool_names(_ctx())


@pytest.mark.unit
def test_session_set_view_accepts_every_view_mode() -> None:
    ctx = _ctx()
    for mode in ("hidden", "compact", "balanced", "detailed"):
        out = execute(SESSION_SET_VIEW, {"mode": mode}, ctx)
        assert out == {"ok": True, "session_prefs": {"mode": mode}}


@pytest.mark.unit
def test_session_set_view_rejects_unknown_mode() -> None:
    out = execute(SESSION_SET_VIEW, {"mode": "verbose"}, _ctx())
    assert out.get("ok") is False
    assert "hidden, compact, balanced, or detailed" in str(out.get("error"))


@pytest.mark.unit
def test_session_set_view_schema_requires_mode_enum() -> None:
    params = SESSION_SET_VIEW_TOOL["function"]["parameters"]
    assert params["required"] == ["mode"]
    assert params["properties"]["mode"]["enum"] == [
        "hidden",
        "compact",
        "balanced",
        "detailed",
    ]


@pytest.mark.unit
def test_session_set_thinking_accepts_three_mode_call_shape() -> None:
    ctx = _ctx()
    for mode in ("auto", "collapsed", "open"):
        out = execute(SESSION_SET_THINKING, {"mode": mode}, ctx)
        assert out == {"ok": True, "session_prefs": {"mode": mode}}


@pytest.mark.unit
def test_session_set_thinking_keeps_boolean_back_compat() -> None:
    ctx = _ctx()
    assert execute(SESSION_SET_THINKING, {"enabled": True}, ctx) == {
        "ok": True,
        "session_prefs": {"enabled": True},
    }
    assert execute(SESSION_SET_THINKING, {"enabled": False}, ctx) == {
        "ok": True,
        "session_prefs": {"enabled": False},
    }


@pytest.mark.unit
def test_session_set_thinking_rejects_unknown_mode_and_empty_args() -> None:
    bad_mode = execute(SESSION_SET_THINKING, {"mode": "hidden"}, _ctx())
    assert bad_mode.get("ok") is False
    assert "auto, collapsed, or open" in str(bad_mode.get("error"))

    empty = execute(SESSION_SET_THINKING, {}, _ctx())
    assert empty.get("ok") is False
    assert "mode" in str(empty.get("error"))


@pytest.mark.unit
def test_session_set_thinking_schema_offers_both_call_shapes() -> None:
    params = SESSION_SET_THINKING_TOOL["function"]["parameters"]
    assert params["required"] == []
    assert params["properties"]["mode"]["enum"] == ["auto", "collapsed", "open"]
    assert params["properties"]["enabled"]["type"] == "boolean"
