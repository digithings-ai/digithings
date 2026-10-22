"""The note that tells the model an integration is unreachable (DIG-5187)."""

from __future__ import annotations

import pytest
from digigraph.graph.research import mcp_failure_note


@pytest.mark.unit
def test_mcp_failure_note_names_the_unreachable_server() -> None:
    note = mcp_failure_note({"helpdesk": "RuntimeError: connection refused"})
    assert "helpdesk" in note
    assert "unavailable" in note.lower()


@pytest.mark.unit
def test_mcp_failure_note_keeps_the_reason_out_of_the_prompt() -> None:
    note = mcp_failure_note({"helpdesk": "RuntimeError: https://internal.example/mcp"})
    assert "internal.example" not in note
