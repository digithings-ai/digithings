"""Session preference tools (#3736)."""

from __future__ import annotations

import pytest
from digigraph.orchestration import builtin as _  # noqa: F401
from digigraph.orchestration.registry import ToolContext, execute
from digigraph.orchestration.session_prefs_tools import SESSION_TOOL_NAMES


@pytest.mark.unit
def test_session_tools_echo_args() -> None:
    ctx = ToolContext(
        session_id="s",
        run_data_dir=None,
        index_name="default",
        index_config={},
        state={},
    )
    out = execute("session_set_language", {"code": "nl"}, ctx)
    assert out == {"ok": True, "session_prefs": {"code": "nl"}}
    assert "session_set_language" in SESSION_TOOL_NAMES
    names = {n for n in SESSION_TOOL_NAMES}
    for name in names:
        execute(name, {"id": "linear"}, ctx)
