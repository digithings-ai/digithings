"""DIG-1210: skill ids called as tools, and answers cut off mid-intent."""

from __future__ import annotations

import pytest
from digigraph.graph.research import answer_looks_unfinished
import digigraph.orchestration.builtin  # noqa: F401  (registers get_skill)
from digigraph.orchestration import registry
from digigraph.orchestration.registry import ToolContext

pytestmark = pytest.mark.unit


def _ctx(**kw: object) -> ToolContext:
    d: dict[str, object] = {
        "session_id": "s",
        "run_data_dir": None,
        "index_name": "occ_help",
        "index_config": {},
        "state": {},
        "request_id": "r",
    }
    d.update(kw)
    return ToolContext(**d)  # type: ignore[arg-type]


def test_skill_id_called_as_tool_returns_the_skill_document() -> None:
    from digigraph.skill_library.loader import list_skill_documents

    name = "summarize-tickets-by-topic"
    assert name in {d.name for d in list_skill_documents()}
    if not registry.has_tool("get_skill"):
        pytest.skip("skill library tools not registered in this process")
    out = registry.execute(name, {}, _ctx())
    assert isinstance(out, dict) and out.get("ok") is True
    assert out["name"] == name and out["content"]
    assert "not a tool" in out["note"]


def test_real_unknown_tool_still_reports_unknown() -> None:
    assert registry.execute("no-such-tool-xyz", {}, _ctx()) == "Unknown tool: no-such-tool-xyz"


def test_skill_route_respects_allowlist_without_get_skill() -> None:
    out = registry.execute("summarize-tickets-by-topic", {}, _ctx(allowed_tool_names={"digisearch"}))
    assert out == "Unknown tool: summarize-tickets-by-topic"


@pytest.mark.parametrize(
    "text",
    ["Here is what I found.\n\nLet me", "I'll now check the tickets", "The steps are:", "", "Lass mich nachsehen"],
)
def test_unfinished_answers_detected(text: str) -> None:
    assert answer_looks_unfinished(text)


@pytest.mark.parametrize(
    "text",
    ["Reset your password via Forgot password.", "Let me know if you need more help.", "Done!"],
)
def test_finished_answers_pass(text: str) -> None:
    assert not answer_looks_unfinished(text)
